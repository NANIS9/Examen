"""
Clasificador por reglas (palabras clave) y extracción de entidades con expresiones regulares.
Funciona sin internet y sirve como plan de respaldo cuando el LLM no responde o devuelve JSON inválido.
"""
import re
from typing import Dict, List, Optional

from .esquema import PRIORIDADES

CATEGORIAS: Dict[str, List[str]] = {
    "materiales_peligrosos": ["peligroso", "derrame", "fuga", "quimico", "inflamable", "toxico", "corrosivo",
                              "gas", "diesel", "fuego", "incendio", "placas de riesgo"],
    "sobrepeso": ["sobrepeso", "excede", "bascula", "exceso de peso", "sobrecarga", "toneladas", "pesado"],
    "acceso_no_autorizado": ["sin autorizacion", "no autorizado", "no autorizada", "acceso denegado", "barrera",
                             "intruso", "gafete", "forzo", "forzada"],
    "falla_hardware": ["camara", "sensor", "lector", "rfid", "no enciende", "apagado", "apagada", "danado",
                       "danada", "falla electrica", "descalibrado", "tarjeta"],
    "falla_software": ["sistema", "error", "pantalla", "caido", "no carga", "lento", "lenta", "software",
                       "aplicacion", "modulo"],
    "somnolencia_conductor": ["somnolencia", "dormido", "cansancio", "fatiga", "sueno", "bosteza",
                              "se le cierran los ojos"],
}

PALABRAS_URGENTES = ["urgente", "emergencia", "accidente", "incendio", "herido", "critico", "inmediato", "evacuando"]

PRIORIDAD_BASE: Dict[str, str] = {
    "materiales_peligrosos": "critica",
    "somnolencia_conductor": "alta",
    "acceso_no_autorizado": "alta",
    "sobrepeso": "media",
    "falla_hardware": "media",
    "falla_software": "baja",
    "otro": "baja",
}


def _normalizar(texto: str) -> str:
    tabla = str.maketrans("áéíóúüñ", "aeiouun")
    return texto.lower().translate(tabla)


def escalar_prioridad(prioridad: str, niveles: int = 1) -> str:
    idx = min(PRIORIDADES.index(prioridad) + niveles, len(PRIORIDADES) - 1)
    return PRIORIDADES[idx]


def clasificar_por_reglas(asunto: str, cuerpo: str) -> Dict[str, object]:
    """Clasificación por conteo de palabras clave. Empate -> primera categoría (seguridad primero)."""
    texto = _normalizar(f"{asunto} {cuerpo}")
    puntajes = {cat: [kw for kw in kws if kw in texto] for cat, kws in CATEGORIAS.items()}
    mejor = max(puntajes, key=lambda c: len(puntajes[c]))
    coincidencias = puntajes[mejor]
    if not coincidencias:
        mejor = "otro"
    prioridad = PRIORIDAD_BASE[mejor]
    urgentes = [p for p in PALABRAS_URGENTES if p in texto]
    if urgentes:
        prioridad = escalar_prioridad(prioridad)
    entidades = extraer_datos(asunto, cuerpo)
    return {
        "categoria": mejor,
        "prioridad": prioridad,
        "entidades": entidades,
        "resumen": f"Clasificado por reglas: {mejor} ({prioridad}). Palabras clave: "
                   f"{', '.join(coincidencias + urgentes) or 'ninguna'}.",
        "palabras_clave": coincidencias + urgentes,
    }


def extraer_datos(asunto: str, cuerpo: str) -> Dict[str, Optional[object]]:
    """Extrae entidades con regex. Lo que no se encuentra queda en None, nunca se inventa."""
    texto = f"{asunto}\n{cuerpo}"
    m_placa = re.search(r"\b[A-Z0-9]{2,3}-\d{2,3}-[A-Z0-9]{1,2}\b", texto.upper())
    m_camion = re.search(r"\bCAM-\d+\b", texto.upper())
    m_peso = re.search(r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(toneladas|tonelada|ton|t|kg)\b",
                       texto.lower())
    peso_kg = None
    if m_peso:
        crudo = m_peso.group(1)
        # "43,200" -> 43200 ; "48.5" -> 48.5 ; "48,5" -> 48.5
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", crudo):
            valor = float(crudo.replace(",", "").replace(".", ""))
        else:
            valor = float(crudo.replace(",", "."))
        peso_kg = valor if m_peso.group(2) == "kg" else valor * 1000
    m_ubic = re.search(r"\b(and[eé]n|puerta|muelle|caseta|dock|barrera|rampa|patio)\s+([A-Za-z0-9]+)", texto,
                       re.IGNORECASE)
    return {
        "placa": m_placa.group(0) if m_placa else None,
        "camion_id": m_camion.group(0) if m_camion else None,
        "peso_reportado_kg": peso_kg,
        "ubicacion": f"{m_ubic.group(1)} {m_ubic.group(2)}".lower() if m_ubic else None,
    }
