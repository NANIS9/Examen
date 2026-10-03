"""
Clasificador híbrido = reglas + LLM.

Fusión:
  - Si el LLM falla (sin conexión / JSON inválido tras reintentos) -> se usa sólo reglas (fuente="reglas").
  - Si LLM y reglas coinciden -> fuente="hibrido", sin revisión humana.
  - Si discrepan -> prevalece la PRIORIDAD más alta (ante la duda, seguridad); la categoría se toma del
    LLM salvo que las reglas hayan detectado materiales peligrosos; y se marca requiere_revision_humana.
  - Las entidades se combinan: lo que extrajo el regex tiene preferencia (es determinista), el LLM rellena huecos.
Cada consulta al LLM queda registrada en `evaluaciones_llm` con su latencia y si coincidió con las reglas.
"""
import logging
from typing import Dict, Optional

from .esquema import PRIORIDADES
from .llm import ClienteOllama, ErrorLLM
from .reglas import clasificar_por_reglas

log = logging.getLogger("logismart.hibrido")


def _mas_alta(p1: str, p2: str) -> str:
    return p1 if PRIORIDADES.index(p1) >= PRIORIDADES.index(p2) else p2


class ClasificadorHibrido:
    def __init__(self, llm: Optional[ClienteOllama] = None, repos=None, usar_llm: bool = True):
        self.llm = llm or ClienteOllama()
        self.repos = repos
        self.usar_llm = usar_llm

    def clasificar(self, asunto: str, cuerpo: str, remitente: str = "") -> Dict:
        reglas = clasificar_por_reglas(asunto, cuerpo)
        resultado = {
            "categoria": reglas["categoria"], "prioridad": reglas["prioridad"],
            "entidades": reglas["entidades"], "resumen": reglas["resumen"],
            "fuente": "reglas", "requiere_revision_humana": False,
            "detalle": {"reglas": {k: reglas[k] for k in ("categoria", "prioridad", "palabras_clave")},
                        "llm": None, "error_llm": None},
        }
        if not self.usar_llm:
            return resultado

        try:
            clasif_llm, meta = self.llm.clasificar(asunto, cuerpo, remitente)
        except ErrorLLM as exc:
            log.warning("LLM no disponible, se usa el clasificador por reglas: %s", exc)
            resultado["detalle"]["error_llm"] = str(exc)
            resultado["resumen"] += " (LLM no disponible)"
            return resultado

        llm = clasif_llm.model_dump()
        coincide = llm["categoria"] == reglas["categoria"] and llm["prioridad"] == reglas["prioridad"]
        if self.repos is not None:
            self.repos.evaluaciones.registrar(
                tipo="clasificacion", prompt=meta["prompt"], respuesta=meta["respuesta"], modelo=meta["modelo"],
                latencia_ms=meta["latencia_ms"], coincide_reglas=coincide,
                extra={"intentos": meta["intentos"], "categoria_llm": llm["categoria"],
                       "categoria_reglas": reglas["categoria"]})

        # --- Fusión -------------------------------------------------------
        entidades = {k: (reglas["entidades"].get(k) if reglas["entidades"].get(k) is not None else llm["entidades"].get(k))
                     for k in reglas["entidades"]}
        if coincide:
            categoria, prioridad, revision = llm["categoria"], llm["prioridad"], False
        else:
            prioridad = _mas_alta(llm["prioridad"], reglas["prioridad"])
            categoria = "materiales_peligrosos" if reglas["categoria"] == "materiales_peligrosos" else llm["categoria"]
            revision = True
        resultado.update({
            "categoria": categoria, "prioridad": prioridad, "entidades": entidades,
            "resumen": llm["resumen"], "fuente": "hibrido", "requiere_revision_humana": revision,
        })
        resultado["detalle"]["llm"] = {**llm, "latencia_ms": round(meta["latencia_ms"], 1), "intentos": meta["intentos"]}
        return resultado
