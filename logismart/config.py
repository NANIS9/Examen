"""
Configuración de la aplicación.

Los valores se leen en este orden de prioridad:
  1. Variables de entorno (LOGISMART_MONGO_URI, LOGISMART_MODELO, ...)
  2. Archivo config.json junto al proyecto (editable desde la GUI)
  3. Valores por defecto
"""
import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict

RUTA_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_CONFIG = RUTA_PROYECTO / "config.json"


@dataclass
class Config:
    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "logismart"
    mongo_timeout_ms: int = 3000

    # --- Ollama ---
    modelo_llm: str = "llama3.2"
    ollama_host: str = "http://localhost:11434"
    llm_reintentos: int = 2
    llm_timeout_s: int = 60
    llm_temperatura: float = 0.0

    # --- Umbrales del motor de reglas ---
    peso_maximo_kg: float = 40000.0           # Límite legal de peso bruto
    hora_inicio_peligrosos: int = 6           # Materiales peligrosos sólo de 06:00 ...
    hora_fin_peligrosos: int = 20             # ... a 20:00

    # --- Correo ---
    modo_simulacion_correo: bool = True
    correo_soporte: str = "soporte@logismart.example"

    # --- Operación ---
    operador: str = "operador1"

    def guardar(self, ruta: Path = RUTA_CONFIG) -> None:
        ruta.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def como_dict(self) -> Dict:
        return asdict(self)


def cargar_config(ruta: Path = RUTA_CONFIG) -> Config:
    datos: Dict = {}
    if ruta.exists():
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            datos = {}
    cfg = Config(**{k: v for k, v in datos.items() if k in Config.__dataclass_fields__})
    # Las variables de entorno tienen prioridad (útil para no escribir credenciales en archivos)
    cfg.mongo_uri = os.environ.get("LOGISMART_MONGO_URI", cfg.mongo_uri)
    cfg.mongo_db = os.environ.get("LOGISMART_MONGO_DB", cfg.mongo_db)
    cfg.modelo_llm = os.environ.get("LOGISMART_MODELO", cfg.modelo_llm)
    cfg.ollama_host = os.environ.get("OLLAMA_HOST", cfg.ollama_host)
    return cfg


# Instancia global compartida por toda la aplicación
config: Config = cargar_config()
