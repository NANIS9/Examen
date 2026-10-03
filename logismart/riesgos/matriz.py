"""
Matriz de riesgos éticos con riesgo residual.

  puntaje          = probabilidad x impacto                  (1..25, antes de mitigar)
  puntaje_residual = probabilidad_residual x impacto_residual (después de aplicar la mitigación)
  nivel: 1-4 bajo | 5-9 medio | 10-16 alto | 17-25 crítico

Cada cambio se guarda en `historico` para poder ver la evolución del riesgo.
"""
from datetime import datetime
from typing import Dict, List, Optional

CATEGORIAS_RIESGO = ("sesgo", "privacidad", "transparencia", "seguridad", "responsabilidad", "otro")
NIVELES = ("bajo", "medio", "alto", "crítico")


def calcular_nivel(puntaje: int) -> str:
    if puntaje >= 17:
        return "crítico"
    if puntaje >= 10:
        return "alto"
    if puntaje >= 5:
        return "medio"
    return "bajo"


def _validar_escala(nombre: str, valor) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 5:
        raise ValueError(f"{nombre} debe ser un entero entre 1 y 5")
    return valor


class ServicioRiesgos:
    """Lógica de negocio sobre la colección riesgos_eticos."""

    def __init__(self, repos):
        self.repos = repos

    def _completar(self, datos: Dict) -> Dict:
        if not datos.get("modulo", "").strip():
            raise ValueError("El módulo no puede estar vacío")
        if not datos.get("descripcion", "").strip():
            raise ValueError("La descripción no puede estar vacía")
        if datos.get("categoria") not in CATEGORIAS_RIESGO:
            raise ValueError(f"Categoría inválida. Usa una de {CATEGORIAS_RIESGO}")
        p = _validar_escala("probabilidad", datos["probabilidad"])
        i = _validar_escala("impacto", datos["impacto"])
        pr = _validar_escala("probabilidad_residual", datos.get("probabilidad_residual", p))
        ir = _validar_escala("impacto_residual", datos.get("impacto_residual", i))
        if pr * ir > p * i:
            raise ValueError("El riesgo residual no puede ser mayor que el riesgo inicial")
        return {
            "modulo": datos["modulo"].strip(), "descripcion": datos["descripcion"].strip(),
            "categoria": datos["categoria"], "probabilidad": p, "impacto": i,
            "mitigacion": datos.get("mitigacion", "").strip(),
            "probabilidad_residual": pr, "impacto_residual": ir,
            "puntaje": p * i, "nivel": calcular_nivel(p * i),
            "puntaje_residual": pr * ir, "nivel_residual": calcular_nivel(pr * ir),
        }

    # CRUD ------------------------------------------------------------------
    def crear(self, datos: Dict, operador: str = "sistema") -> str:
        doc = self._completar(datos)
        doc["historico"] = [{"fecha": datetime.now(), "operador": operador, "accion": "alta",
                             "puntaje": doc["puntaje"], "puntaje_residual": doc["puntaje_residual"]}]
        return self.repos.riesgos.crear(doc)

    def actualizar(self, _id: str, datos: Dict, operador: str = "sistema") -> bool:
        doc = self._completar(datos)
        return self.repos.riesgos.col.update_one({"_id": _id}, {
            "$set": doc,
            "$push": {"historico": {"fecha": datetime.now(), "operador": operador, "accion": "edición",
                                    "puntaje": doc["puntaje"], "puntaje_residual": doc["puntaje_residual"]}},
        }) > 0

    def eliminar(self, _id: str) -> bool:
        return self.repos.riesgos.eliminar(_id)

    def listar(self) -> List[Dict]:
        return self.repos.riesgos.ordenados()

    # Consultas para gráficas ---------------------------------------------------
    def matriz_5x5(self, residual: bool = False) -> List[List[int]]:
        """Celda [impacto-1][probabilidad-1] = número de riesgos en esa combinación."""
        m = [[0] * 5 for _ in range(5)]
        kp, ki = ("probabilidad_residual", "impacto_residual") if residual else ("probabilidad", "impacto")
        for r in self.listar():
            m[r[ki] - 1][r[kp] - 1] += 1
        return m

    def resumen(self) -> Dict:
        riesgos = self.listar()
        por_nivel = {n: 0 for n in NIVELES}
        por_nivel_res = {n: 0 for n in NIVELES}
        por_cat: Dict[str, int] = {}
        for r in riesgos:
            por_nivel[r["nivel"]] += 1
            por_nivel_res[r["nivel_residual"]] += 1
            por_cat[r["categoria"]] = por_cat.get(r["categoria"], 0) + 1
        return {
            "total": len(riesgos), "por_nivel": por_nivel, "por_nivel_residual": por_nivel_res,
            "por_categoria": por_cat,
            "puntaje_promedio": round(sum(r["puntaje"] for r in riesgos) / len(riesgos), 2) if riesgos else 0,
            "puntaje_residual_promedio": round(sum(r["puntaje_residual"] for r in riesgos) / len(riesgos), 2) if riesgos else 0,
            "reduccion_pct": round(100 * (1 - sum(r["puntaje_residual"] for r in riesgos) / sum(r["puntaje"] for r in riesgos)), 1)
            if riesgos else 0,
        }


# Riesgos de demostración: incluyen los de ESTA implementación (LLM, MongoDB, automatización)
RIESGOS_PREDETERMINADOS: List[Dict] = [
    {"modulo": "Asistente LLM (RAG)", "categoria": "transparencia",
     "descripcion": "Alucinaciones del LLM: inventar motivos de una decisión que no están en los registros",
     "probabilidad": 4, "impacto": 4, "probabilidad_residual": 2, "impacto_residual": 3,
     "mitigacion": "Patrón RAG estricto: sólo responde con contexto de MongoDB, cita [coleccion:_id] y responde 'no tengo información' si no hay datos; temperatura 0"},
    {"modulo": "Clasificador híbrido", "categoria": "sesgo",
     "descripcion": "Sesgo contra correos con ortografía informal o sin acentos (operadores de caseta) -> peor clasificación",
     "probabilidad": 4, "impacto": 3, "probabilidad_residual": 2, "impacto_residual": 3,
     "mitigacion": "Normalizar texto (acentos/minúsculas), incluir correos informales en el conjunto de evaluación, fusión con prioridad más alta y revisión humana al discrepar"},
    {"modulo": "Base de datos (camiones)", "categoria": "privacidad",
     "descripcion": "Privacidad de datos del conductor (nombre, certificación, vigencia) almacenados y enviados al LLM",
     "probabilidad": 3, "impacto": 5, "probabilidad_residual": 2, "impacto_residual": 4,
     "mitigacion": "LLM local (Ollama, nada sale de la red), credenciales de Mongo en variables de entorno, minimizar campos personales y política de retención"},
    {"modulo": "Motor de reglas + GUI", "categoria": "responsabilidad",
     "descripcion": "Dependencia excesiva de la automatización: el operador acepta el semáforo sin revisar la explicación",
     "probabilidad": 4, "impacto": 4, "probabilidad_residual": 2, "impacto_residual": 4,
     "mitigacion": "Explicación paso a paso obligatoria en pantalla, marca requiere_revision_humana, registro del operador en cada acceso y canal de apelación"},
    {"modulo": "Clasificador híbrido", "categoria": "seguridad",
     "descripcion": "Falso negativo: un incidente crítico (derrame) clasificado como 'otro' o baja prioridad",
     "probabilidad": 2, "impacto": 5, "probabilidad_residual": 1, "impacto_residual": 5,
     "mitigacion": "Las reglas de materiales peligrosos prevalecen sobre el LLM; palabras urgentes siempre escalan"},
    {"modulo": "Cámara de somnolencia", "categoria": "sesgo",
     "descripcion": "Sesgo en visión nocturna (falsos positivos por tono de piel / poca luz)",
     "probabilidad": 4, "impacto": 4, "probabilidad_residual": 2, "impacto_residual": 3,
     "mitigacion": "Entrenar y auditar con datos nocturnos y diversos; umbral ajustable"},
    {"modulo": "Lector de placas (LPR)", "categoria": "responsabilidad",
     "descripcion": "Lectura errónea que niega el acceso injustificadamente",
     "probabilidad": 3, "impacto": 3, "probabilidad_residual": 2, "impacto_residual": 2,
     "mitigacion": "Búsqueda manual por placa en la GUI y canal de apelación"},
    {"modulo": "Asistente LLM (RAG)", "categoria": "seguridad",
     "descripcion": "Inyección de instrucciones dentro de un correo que altere la clasificación del LLM",
     "probabilidad": 2, "impacto": 3, "probabilidad_residual": 1, "impacto_residual": 3,
     "mitigacion": "Salida JSON con esquema validado por pydantic; el correo va como dato, nunca como instrucción del sistema"},
]
