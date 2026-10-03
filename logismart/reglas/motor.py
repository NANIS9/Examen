"""
Motor de reglas (lógica proposicional).

Premisas (variables booleanas)
    P : Vehículo con autorización previa
    Q : El peso excede el límite
    R : Carga con materiales peligrosos
    S : El conductor presenta certificación
    V : La certificación está VIGENTE (no vencida)          <- nueva
    H : La hora actual está dentro del horario permitido
        para materiales peligrosos (06:00 - 20:00)          <- nueva

Reglas originales (se conservan tal cual)
    A (Acceso estándar)      = P ∧ S ∧ ¬Q
    E (Inspección especial)  = P ∧ (R ∨ Q)

Reglas nuevas (justificación)
    B (Bloqueo documental)   = P ∧ S ∧ ¬V
        Un conductor cuya certificación venció no debe operar aunque el camión esté
        autorizado; a diferencia de "sin certificación" (¬S), el trato operativo es
        distinto: se le envía a ventanilla a renovar, no se le niega de forma permanente.
    X (Retención por horario) = P ∧ R ∧ ¬H
        La normativa de transporte de materiales peligrosos restringe su circulación
        nocturna dentro de instalaciones; si llega fuera de horario se retiene en patio
        de espera hasta la ventana permitida.

Prioridad de la decisión final (ante la duda, seguridad):
    ¬P -> DENEGADO  >  X -> RETENIDO  >  B -> DENEGADO (documentos)  >  E -> INSPECCIÓN  >  A -> ACCESO
"""
import itertools
from datetime import datetime, date
from typing import Callable, Dict, List, Optional

PREMISAS: Dict[str, str] = {
    "P": "Autorización previa",
    "Q": "Peso excede el límite",
    "R": "Materiales peligrosos",
    "S": "Conductor presenta certificación",
    "V": "Certificación vigente",
    "H": "Dentro del horario permitido para peligrosos",
}

Premisas = Dict[str, bool]

# Cada regla: (fórmula legible, variables de las que depende, función de evaluación)
REGLAS: Dict[str, Dict] = {
    "A": {"nombre": "Acceso estándar", "formula": "P ∧ S ∧ ¬Q", "vars": ("P", "Q", "S"),
          "fn": lambda p: p["P"] and p["S"] and not p["Q"]},
    "E": {"nombre": "Inspección especial", "formula": "P ∧ (R ∨ Q)", "vars": ("P", "Q", "R"),
          "fn": lambda p: p["P"] and (p["R"] or p["Q"])},
    "B": {"nombre": "Bloqueo documental", "formula": "P ∧ S ∧ ¬V", "vars": ("P", "S", "V"),
          "fn": lambda p: p["P"] and p["S"] and not p["V"]},
    "X": {"nombre": "Retención por horario", "formula": "P ∧ R ∧ ¬H", "vars": ("P", "R", "H"),
          "fn": lambda p: p["P"] and p["R"] and not p["H"]},
}


def _validar(premisas: Premisas) -> Premisas:
    completas = {"P": False, "Q": False, "R": False, "S": False, "V": True, "H": True}
    for k, v in premisas.items():
        if k not in PREMISAS:
            raise KeyError(f"Premisa desconocida: {k}")
        if not isinstance(v, bool):
            raise TypeError(f"La premisa {k} debe ser bool, se recibió {type(v).__name__}")
        completas[k] = v
    return completas


def evaluar(premisas: Premisas) -> Dict[str, bool]:
    """Evalúa todas las reglas. Las premisas V y H son opcionales (por defecto V=True, H=True)."""
    p = _validar(premisas)
    return {letra: bool(r["fn"](p)) for letra, r in REGLAS.items()}


def _v(b: bool) -> str:
    return "V" if b else "F"


def decidir(premisas: Premisas) -> Dict:
    """
    Decisión final + explicación paso a paso (qué premisas la causaron).
    Devuelve un dict listo para guardarse en la colección `accesos`.
    """
    p = _validar(premisas)
    r = evaluar(p)
    pasos: List[str] = [f"{k} = {_v(v)}  ({PREMISAS[k]})" for k, v in p.items()]
    pasos += [
        f"¬Q = {_v(not p['Q'])}",
        f"P ∧ S = {_v(p['P'] and p['S'])}",
        f"R ∨ Q = {_v(p['R'] or p['Q'])}",
        f"A = P ∧ S ∧ ¬Q = {_v(r['A'])}",
        f"E = P ∧ (R ∨ Q) = {_v(r['E'])}",
        f"B = P ∧ S ∧ ¬V = {_v(r['B'])}",
        f"X = P ∧ R ∧ ¬H = {_v(r['X'])}",
    ]

    if not p["P"]:
        decision, semaforo, causa = "DENEGADO", "rojo", "No tiene autorización previa (¬P): ninguna regla de ingreso aplica."
    elif r["X"]:
        decision, semaforo, causa = "RETENIDO", "rojo", "Materiales peligrosos fuera del horario permitido (P ∧ R ∧ ¬H)."
    elif r["B"]:
        decision, semaforo, causa = "DENEGADO", "rojo", "Certificación del conductor vencida (P ∧ S ∧ ¬V): enviar a ventanilla."
    elif r["E"]:
        causa = "Autorizado con " + (" y ".join(filter(None, ["exceso de peso (Q)" if p["Q"] else "",
                                                               "materiales peligrosos (R)" if p["R"] else ""])))
        decision, semaforo = "INSPECCION_ESPECIAL", "amarillo"
        causa += " -> E = P ∧ (R ∨ Q)." + (" Además cumple A: tras la inspección puede usar acceso estándar." if r["A"] else "")
    elif r["A"]:
        decision, semaforo, causa = "ACCESO_ESTANDAR", "verde", "Autorizado, conductor certificado y sin exceso de peso (P ∧ S ∧ ¬Q)."
    else:
        decision, semaforo, causa = "DENEGADO", "rojo", "Autorizado pero sin certificación del conductor (¬S) y sin motivo de inspección."
    pasos.append(f"DECISIÓN: {decision} -> {causa}")
    return {"premisas": p, "resultado": r, "decision": decision, "semaforo": semaforo,
            "causa": causa, "explicacion": pasos}


# ---------------------------------------------------------------------------
# Tablas de verdad
# ---------------------------------------------------------------------------
def generar_tabla_verdad(variables: tuple = ("P", "Q", "R", "S", "V", "H")) -> List[Dict]:
    """Tabla completa sobre las variables dadas (2^n filas), con columnas intermedias y todas las reglas."""
    filas = []
    for valores in itertools.product([True, False], repeat=len(variables)):
        p = dict(zip(variables, valores))
        r = evaluar(p)
        pc = _validar(p)
        filas.append({**pc, "no_Q": not pc["Q"], "P_y_S": pc["P"] and pc["S"], "R_o_Q": pc["R"] or pc["Q"],
                      "no_V": not pc["V"], "no_H": not pc["H"], **r})
    return filas


def tabla_regla(letra: str) -> List[Dict]:
    """Tabla de verdad reducida a las variables de las que depende la regla (8 filas)."""
    regla = REGLAS[letra]
    return [{**{v: f[v] for v in regla["vars"]}, letra: f[letra]} for f in generar_tabla_verdad(regla["vars"])]


def tabla_texto(letra: str) -> str:
    regla = REGLAS[letra]
    enc = "".join(f"{v:^4}" for v in regla["vars"]) + f" | {letra:^4}"
    lineas = [f"{letra} = {regla['formula']}   ({regla['nombre']})", enc, "-" * len(enc)]
    for f in tabla_regla(letra):
        lineas.append("".join(f"{_v(f[v]):^4}" for v in regla["vars"]) + f" | {_v(f[letra]):^4}")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Reto: detección de redundancias y contradicciones entre reglas
# ---------------------------------------------------------------------------
def analizar_reglas(reglas: Optional[Dict[str, Callable]] = None) -> List[Dict]:
    """
    Compara las reglas por pares sobre la tabla de verdad completa (64 combinaciones):
      - equivalente : misma salida siempre            -> regla redundante
      - implica     : si X es V entonces Y es V        -> X está contenida en Y (redundancia parcial)
      - excluyente  : nunca son V a la vez             -> no pueden chocar
      - solapamiento: pueden ser V a la vez            -> posible contradicción de acción; se resuelve por prioridad
      - insatisfacible / tautología : regla siempre F o siempre V -> regla inútil
    """
    fns = reglas or {k: r["fn"] for k, r in REGLAS.items()}
    tabla = [_validar(dict(zip(PREMISAS, vals))) for vals in itertools.product([True, False], repeat=len(PREMISAS))]
    salidas = {k: [bool(fn(p)) for p in tabla] for k, fn in fns.items()}
    hallazgos = []
    for k, s in salidas.items():
        if not any(s):
            hallazgos.append({"tipo": "insatisfacible", "reglas": [k], "detalle": f"{k} nunca es verdadera"})
        if all(s):
            hallazgos.append({"tipo": "tautologia", "reglas": [k], "detalle": f"{k} siempre es verdadera"})
    for a, b in itertools.combinations(salidas, 2):
        sa, sb = salidas[a], salidas[b]
        ambas = sum(1 for x, y in zip(sa, sb) if x and y)
        if sa == sb:
            hallazgos.append({"tipo": "equivalente", "reglas": [a, b], "detalle": f"{a} ≡ {b}: una es redundante"})
        elif all((not x) or y for x, y in zip(sa, sb)):
            hallazgos.append({"tipo": "implica", "reglas": [a, b], "detalle": f"{a} → {b}: {a} está contenida en {b}"})
        elif all((not y) or x for x, y in zip(sa, sb)):
            hallazgos.append({"tipo": "implica", "reglas": [b, a], "detalle": f"{b} → {a}: {b} está contenida en {a}"})
        elif ambas == 0:
            hallazgos.append({"tipo": "excluyente", "reglas": [a, b], "detalle": f"{a} y {b} nunca coinciden"})
        else:
            hallazgos.append({"tipo": "solapamiento", "reglas": [a, b],
                              "detalle": f"{a} y {b} son verdaderas a la vez en {ambas}/{len(tabla)} casos; "
                                         "la acción se resuelve por prioridad"})
    return hallazgos


# ---------------------------------------------------------------------------
# Derivar premisas desde un documento de la colección `camiones`
# ---------------------------------------------------------------------------
def premisas_desde_camion(camion: Dict, peso_kg: Optional[float], peso_maximo_kg: float,
                          ahora: Optional[datetime] = None, hora_inicio: int = 6, hora_fin: int = 20) -> Premisas:
    ahora = ahora or datetime.now()
    conductor = camion.get("conductor", {}) or {}
    vigente_hasta = conductor.get("vigente_hasta")
    if isinstance(vigente_hasta, str):
        vigente_hasta = date.fromisoformat(vigente_hasta)
    elif isinstance(vigente_hasta, datetime):
        vigente_hasta = vigente_hasta.date()
    peso = peso_kg if peso_kg is not None else camion.get("peso_bruto_kg", 0) or 0
    return {
        "P": bool(camion.get("autorizacion", False)),
        "Q": float(peso) > float(peso_maximo_kg),
        "R": bool(camion.get("materiales_peligrosos", False)),
        "S": bool(conductor.get("certificacion")),
        "V": bool(vigente_hasta and vigente_hasta >= ahora.date()),
        "H": hora_inicio <= ahora.hour < hora_fin,
    }
