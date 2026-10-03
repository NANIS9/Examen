"""
Asistente explicativo con patrón RAG sencillo:

   pregunta -> (1) recuperar registros de MongoDB relacionados
            -> (2) construir contexto con cita [coleccion:_id]
            -> (3) el LLM responde SÓLO con ese contexto
            -> si no hay registros: "No tengo información..." (sin llamar al LLM, sin inventar)
"""
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ..clasificador.llm import ClienteOllama, ErrorLLM
from ..config import config

PROMPT_SISTEMA = """Eres el asistente del centro de control LogiSmart. Respondes preguntas del operador
EXCLUSIVAMENTE con la información del CONTEXTO que se te entrega (registros de la base de datos MongoDB).

Reglas estrictas:
1. No inventes datos. Si el contexto no contiene la respuesta, di exactamente: "No tengo información
   suficiente en los registros para responder eso."
2. Cita siempre el registro de origen entre corchetes tal como aparece en el contexto, por ejemplo [accesos:3f2a9c].
3. Cuando expliques una decisión de acceso, menciona las premisas (P, Q, R, S, V, H) y la regla que la causó.
4. Responde en español, breve y claro (máximo 8 líneas)."""


def _fmt_fecha(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M") if isinstance(v, datetime) else str(v)


class Asistente:
    def __init__(self, repos, llm: Optional[ClienteOllama] = None):
        self.repos = repos
        self.llm = llm or ClienteOllama()
        self.historial: List[Dict] = []       # [{"rol", "texto", "fuentes", "hora"}]

    # ------------------------------------------------------------------
    # 1) Recuperación
    # ------------------------------------------------------------------
    def recuperar(self, pregunta: str) -> Tuple[List[str], List[str]]:
        """Devuelve (fragmentos_de_contexto, fuentes) a partir de la pregunta."""
        q = pregunta.upper()
        fragmentos, fuentes = [], []
        ids = set(re.findall(r"\bCAM-\d+\b", q)) | set(re.findall(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", q))

        def agregar(coleccion: str, doc: Dict, texto: str):
            ref = f"[{coleccion}:{doc['_id']}]"
            fragmentos.append(f"{ref} {texto}")
            fuentes.append(ref)

        for ident in ids:
            cam = self.repos.camiones.por_camion_id(ident) or self.repos.camiones.por_placa(ident)
            if cam:
                cond = cam.get("conductor", {})
                agregar("camiones", cam, f"Camión {cam['camion_id']} placa {cam['placa']} empresa {cam.get('empresa')}; "
                        f"autorización={cam.get('autorizacion')}; materiales peligrosos={cam.get('materiales_peligrosos')}; "
                        f"peso bruto {cam.get('peso_bruto_kg')} kg; conductor {cond.get('nombre')} certificación "
                        f"{cond.get('certificacion')} vigente hasta {cond.get('vigente_hasta')}.")
            for a in self.repos.accesos.por_camion(ident)[:3]:
                agregar("accesos", a, f"Acceso {_fmt_fecha(a['marca_tiempo'])} camión {a.get('camion_id')} placa {a.get('placa')}: "
                        f"premisas {a['premisas']} -> resultado {a['resultado']} -> decisión {a['decision']}. "
                        f"Causa: {a['causa']} Operador: {a.get('operador')}.")
            for inc in self.repos.incidentes.por_camion(ident)[:3]:
                c = inc["clasificacion"]
                agregar("incidentes", inc, f"Incidente {_fmt_fecha(inc['fecha'])} '{inc['correo']['asunto']}': categoría "
                        f"{c['categoria']}, prioridad {c['prioridad']}, estado {inc['estado']}, fuente {c.get('fuente')}. "
                        f"Resumen: {c.get('resumen')}")

        ql = pregunta.lower()
        if any(p in ql for p in ("riesgo", "ético", "etico", "mitigaci")):
            for r in self.repos.riesgos.ordenados()[:6]:
                agregar("riesgos_eticos", r, f"Riesgo '{r['descripcion']}' módulo {r['modulo']} categoría {r['categoria']}: "
                        f"P={r['probabilidad']} I={r['impacto']} puntaje {r['puntaje']} ({r['nivel']}); residual "
                        f"{r.get('puntaje_residual')}. Mitigación: {r.get('mitigacion')}")
        if any(p in ql for p in ("incidente", "correo", "abierto", "pendiente", "cerrado")) and not ids:
            for inc in self.repos.incidentes.recientes(limite=6):
                c = inc["clasificacion"]
                agregar("incidentes", inc, f"Incidente {_fmt_fecha(inc['fecha'])} '{inc['correo']['asunto']}': "
                        f"{c['categoria']} / {c['prioridad']} / estado {inc['estado']}. {c.get('resumen')}")
        if any(p in ql for p in ("último", "ultimo", "recientes", "hoy", "acceso")) and not ids:
            for a in self.repos.accesos.recientes(limite=6):
                agregar("accesos", a, f"Acceso {_fmt_fecha(a['marca_tiempo'])} {a.get('camion_id')} -> {a['decision']}. {a['causa']}")
        if any(p in ql for p in ("cuántos", "cuantos", "total", "indicador", "resumen", "estadística", "estadistica")):
            ind = self.repos.indicadores()
            fragmentos.append(f"[indicadores:hoy] camiones atendidos={ind['camiones_atendidos']}, accesos permitidos="
                              f"{ind['accesos_permitidos']}, inspecciones={ind['inspecciones']}, denegados={ind['accesos_denegados']}, "
                              f"incidentes abiertos={ind['incidentes_abiertos']}, riesgos críticos={ind['riesgos_criticos']}, "
                              f"camiones registrados={ind['camiones_registrados']}.")
            fuentes.append("[indicadores:hoy]")
        if any(p in ql for p in ("regla", "fórmula", "formula", "lógica", "logica")):
            fragmentos.append("[reglas:motor] A = P ∧ S ∧ ¬Q (acceso estándar); E = P ∧ (R ∨ Q) (inspección especial); "
                              "B = P ∧ S ∧ ¬V (bloqueo por certificación vencida); X = P ∧ R ∧ ¬H (retención de materiales "
                              "peligrosos fuera de horario). Prioridad: ¬P > X > B > E > A.")
            fuentes.append("[reglas:motor]")
        return fragmentos, list(dict.fromkeys(fuentes))

    # ------------------------------------------------------------------
    # 2) + 3) Generación
    # ------------------------------------------------------------------
    def responder(self, pregunta: str) -> Dict:
        hora = datetime.now()
        self.historial.append({"rol": "user", "texto": pregunta, "fuentes": [], "hora": hora})
        fragmentos, fuentes = self.recuperar(pregunta)

        if not fragmentos:
            texto = ("No tengo información en los registros sobre eso. Prueba indicando un camión (CAM-102) o una "
                     "placa, o pregunta por incidentes, accesos recientes, riesgos éticos o indicadores.")
            return self._registrar(texto, [], 0.0, "sin_datos")

        contexto = "\n".join(fragmentos)
        mensajes = [{"role": "system", "content": PROMPT_SISTEMA},
                    {"role": "user", "content": f"CONTEXTO:\n{contexto}\n\nPREGUNTA DEL OPERADOR: {pregunta}"}]
        try:
            texto, latencia = self.llm.chat(mensajes)
            modo = "llm"
            if self.repos is not None:
                self.repos.evaluaciones.registrar(tipo="asistente", prompt=mensajes[1]["content"], respuesta=texto,
                                                  modelo=self.llm.modelo, latencia_ms=latencia,
                                                  extra={"fuentes": fuentes})
        except ErrorLLM as exc:
            # Plan de respaldo: se muestran los registros recuperados tal cual (sin generación)
            texto = ("(LLM no disponible: se muestran los registros encontrados sin redactar)\n" +
                     "\n".join(f"- {f}" for f in fragmentos[:8]) + f"\n\nDetalle: {exc}")
            latencia, modo = 0.0, "respaldo"
        return self._registrar(texto, fuentes, latencia, modo)

    def _registrar(self, texto: str, fuentes: List[str], latencia: float, modo: str) -> Dict:
        entrada = {"rol": "assistant", "texto": texto, "fuentes": fuentes, "hora": datetime.now(),
                   "latencia_ms": round(latencia, 1), "modo": modo}
        self.historial.append(entrada)
        return entrada
