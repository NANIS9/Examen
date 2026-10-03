"""
Cliente del LLM local (Ollama).

- clasificar(): pide al modelo un JSON con el esquema exacto (salida estructurada de Ollama),
  lo valida con pydantic y reintenta si es inválido. Si agota reintentos lanza ErrorLLM
  (el clasificador híbrido cae entonces al clasificador por reglas).
- chat(): conversación libre (usada por el asistente RAG).
- Cada llamada mide la latencia en milisegundos.
"""
import json
import logging
import time
from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError

from ..config import config
from .esquema import ClasificacionLLM, CATEGORIAS_VALIDAS, PRIORIDADES

log = logging.getLogger("logismart.llm")


class ErrorLLM(Exception):
    """El LLM no está disponible o no devolvió una respuesta válida."""


PROMPT_SISTEMA_CLASIFICADOR = f"""Eres el clasificador de incidentes de un centro logístico (LogiSmart).
Recibirás un correo de soporte y debes devolver ÚNICAMENTE un objeto JSON con este esquema exacto:

{{
  "categoria": una de {list(CATEGORIAS_VALIDAS)},
  "prioridad": una de {list(PRIORIDADES)},
  "entidades": {{
      "placa": "texto o null (formato ABC-123-D)",
      "camion_id": "texto o null (formato CAM-102)",
      "peso_reportado_kg": número en kilogramos o null,
      "ubicacion": "texto o null (andén 3, puerta B, caseta norte...)"
  }},
  "resumen": "una oración en español que resuma el incidente"
}}

Criterios de categoría:
- materiales_peligrosos: derrames, fugas, químicos, inflamables, gas, diésel, fuego, tóxicos, corrosivos.
- sobrepeso: exceso de peso, báscula, toneladas por encima del límite.
- acceso_no_autorizado: vehículos o personas sin autorización, barreras forzadas, gafetes ajenos.
- falla_hardware: cámaras, sensores, lectores RFID, pantallas físicas, tarjetas o básculas descompuestas.
- falla_software: errores del sistema, aplicaciones lentas o caídas, módulos que no cargan.
- somnolencia_conductor: fatiga, sueño, conductor dormido, cansancio.
- otro: consultas, facturas, citas o cualquier cosa que no sea un incidente de seguridad.

Criterios de prioridad: critica = riesgo inmediato para personas o instalaciones; alta = riesgo de seguridad
sin daño inmediato; media = afecta la operación; baja = informativo o menor. Palabras como URGENTE,
EMERGENCIA, accidente, incendio o heridos elevan la prioridad.
Si un dato no aparece en el correo usa null. No inventes información. Responde solo con el JSON."""


class ClienteOllama:
    def __init__(self, modelo: Optional[str] = None, host: Optional[str] = None):
        self.modelo = modelo or config.modelo_llm
        self.host = host or config.ollama_host
        self._cliente = None

    # ------------------------------------------------------------------
    def _conectar(self):
        if self._cliente is None:
            try:
                import ollama
            except ImportError as exc:
                raise ErrorLLM("La biblioteca 'ollama' no está instalada (pip install ollama)") from exc
            self._cliente = ollama.Client(host=self.host, timeout=config.llm_timeout_s)
        return self._cliente

    def disponible(self) -> Tuple[bool, str]:
        """Comprueba que Ollama responde y que el modelo está descargado."""
        try:
            modelos = self.modelos()
        except ErrorLLM as exc:
            return False, str(exc)
        if not any(m == self.modelo or m.startswith(self.modelo + ":") for m in modelos):
            return False, f"Ollama responde pero el modelo '{self.modelo}' no está descargado. Ejecuta: ollama pull {self.modelo}"
        return True, f"Ollama OK ({self.host}), modelo {self.modelo}"

    def modelos(self) -> List[str]:
        try:
            respuesta = self._conectar().list()
        except Exception as exc:
            raise ErrorLLM(f"No se pudo conectar con Ollama en {self.host}: {type(exc).__name__}. "
                           "Verifica que esté en ejecución (ollama serve).") from exc
        return [m.get("model") or m.get("name") for m in respuesta.get("models", [])]

    # ------------------------------------------------------------------
    def chat(self, mensajes: List[Dict], formato: Optional[Dict] = None,
             temperatura: Optional[float] = None) -> Tuple[str, float]:
        """Envía mensajes y devuelve (texto, latencia_ms)."""
        cliente = self._conectar()
        inicio = time.perf_counter()
        try:
            respuesta = cliente.chat(
                model=self.modelo, messages=mensajes, format=formato,
                options={"temperature": config.llm_temperatura if temperatura is None else temperatura},
            )
        except Exception as exc:
            raise ErrorLLM(f"Fallo al consultar el modelo '{self.modelo}': {type(exc).__name__}: {exc}") from exc
        latencia = (time.perf_counter() - inicio) * 1000
        return respuesta["message"]["content"], latencia

    def clasificar(self, asunto: str, cuerpo: str, remitente: str = "",
                   reintentos: Optional[int] = None) -> Tuple[ClasificacionLLM, Dict]:
        """
        Devuelve (clasificacion_validada, metadatos) donde metadatos incluye prompt, respuesta cruda,
        latencia total e intentos. Lanza ErrorLLM si tras los reintentos no hay JSON válido.
        """
        reintentos = config.llm_reintentos if reintentos is None else reintentos
        prompt_usuario = f"Remitente: {remitente}\nAsunto: {asunto}\nCuerpo:\n{cuerpo}"
        mensajes = [{"role": "system", "content": PROMPT_SISTEMA_CLASIFICADOR},
                    {"role": "user", "content": prompt_usuario}]
        esquema = ClasificacionLLM.model_json_schema()
        latencia_total, ultimo_error, cruda = 0.0, "", ""
        for intento in range(1, reintentos + 2):
            cruda, lat = self.chat(mensajes, formato=esquema)
            latencia_total += lat
            try:
                datos = json.loads(cruda)
                clasif = ClasificacionLLM.model_validate(datos)
                return clasif, {"prompt": prompt_usuario, "respuesta": cruda, "latencia_ms": latencia_total,
                                "intentos": intento, "modelo": self.modelo}
            except (json.JSONDecodeError, ValidationError) as exc:
                ultimo_error = f"{type(exc).__name__}: {str(exc)[:300]}"
                log.warning("Intento %d: JSON inválido del LLM (%s)", intento, ultimo_error)
                # Se le indica el error al modelo para que corrija en el siguiente intento
                mensajes.append({"role": "assistant", "content": cruda})
                mensajes.append({"role": "user", "content": f"Tu respuesta no cumple el esquema ({ultimo_error}). "
                                                            "Devuelve únicamente el JSON corregido."})
        raise ErrorLLM(f"El modelo no devolvió JSON válido tras {reintentos + 1} intentos. Último error: {ultimo_error}")
