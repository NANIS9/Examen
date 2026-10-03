"""
Esquema EXACTO que debe devolver el LLM (validado con pydantic).

{
  "categoria": "materiales_peligrosos | sobrepeso | acceso_no_autorizado | falla_hardware |
                falla_software | somnolencia_conductor | otro",
  "prioridad": "baja | media | alta | critica",
  "entidades": {"placa": str|null, "camion_id": str|null, "peso_reportado_kg": float|null, "ubicacion": str|null},
  "resumen": "una oración"
}
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CATEGORIAS_VALIDAS = ("materiales_peligrosos", "sobrepeso", "acceso_no_autorizado", "falla_hardware",
                      "falla_software", "somnolencia_conductor", "otro")
PRIORIDADES = ("baja", "media", "alta", "critica")

Categoria = Literal["materiales_peligrosos", "sobrepeso", "acceso_no_autorizado", "falla_hardware",
                    "falla_software", "somnolencia_conductor", "otro"]
Prioridad = Literal["baja", "media", "alta", "critica"]


class Entidades(BaseModel):
    placa: Optional[str] = None
    camion_id: Optional[str] = None
    peso_reportado_kg: Optional[float] = None
    ubicacion: Optional[str] = None

    @field_validator("placa", "camion_id", mode="before")
    @classmethod
    def _mayusculas(cls, v):
        if v in ("", "null", "None"):
            return None
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("peso_reportado_kg", mode="before")
    @classmethod
    def _peso(cls, v):
        if v in ("", "null", "None"):
            return None
        return v


class ClasificacionLLM(BaseModel):
    categoria: Categoria
    prioridad: Prioridad
    entidades: Entidades = Field(default_factory=Entidades)
    resumen: str = Field(min_length=3, max_length=400)

    @field_validator("categoria", "prioridad", mode="before")
    @classmethod
    def _normaliza(cls, v):
        if isinstance(v, str):
            tabla = str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU")
            return v.strip().lower().translate(tabla).replace(" ", "_").replace("-", "_")
        return v
