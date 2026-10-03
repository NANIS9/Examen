"""
Capa de conexión a MongoDB.

- Intenta conectarse a MongoDB (local Compass o Atlas) con un tiempo de espera corto.
- Si la conexión falla, la aplicación NO se cae: usa un respaldo en memoria
  (ColeccionMemoria) con la misma interfaz, y la GUI avisa del modo sin conexión.
- Todos los documentos usan un `_id` de texto (uuid) para que ambos modos se comporten igual.
"""
import logging
import operator
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from ..config import config

log = logging.getLogger("logismart.db")


class ErrorConexion(Exception):
    """Error de conexión con MongoDB (se muestra al usuario de forma amigable)."""


def nuevo_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Respaldo en memoria: implementa el subconjunto de operaciones que usamos
# ---------------------------------------------------------------------------
_OPS = {"$gte": operator.ge, "$lte": operator.le, "$gt": operator.gt, "$lt": operator.lt, "$ne": operator.ne}


def _valor(doc: Dict, ruta: str):
    """Obtiene un campo anidado con notación de punto ('clasificacion.categoria')."""
    for parte in ruta.split("."):
        if not isinstance(doc, dict):
            return None
        doc = doc.get(parte)
    return doc


def _coincide(doc: Dict, filtro: Dict) -> bool:
    for campo, cond in filtro.items():
        if campo == "$or":
            if not any(_coincide(doc, sub) for sub in cond):
                return False
            continue
        valor = _valor(doc, campo)
        if isinstance(cond, dict):
            for op, esperado in cond.items():
                if op == "$in":
                    if valor not in esperado:
                        return False
                elif op == "$regex":
                    if valor is None or not re.search(esperado, str(valor), re.IGNORECASE):
                        return False
                elif op in _OPS:
                    if valor is None or not _OPS[op](valor, esperado):
                        return False
                else:
                    raise ValueError(f"Operador no soportado en memoria: {op}")
        elif valor != cond:
            return False
    return True


class ColeccionMemoria:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self._docs: Dict[str, Dict] = {}

    def insert_one(self, doc: Dict):
        doc.setdefault("_id", nuevo_id())
        self._docs[doc["_id"]] = dict(doc)
        return doc["_id"]

    def insert_many(self, docs: Iterable[Dict]):
        return [self.insert_one(d) for d in docs]

    def find(self, filtro: Optional[Dict] = None, orden: Optional[List] = None, limite: int = 0) -> List[Dict]:
        res = [dict(d) for d in self._docs.values() if _coincide(d, filtro or {})]
        for campo, direccion in reversed(orden or []):
            res.sort(key=lambda d: (d.get(campo) is None, d.get(campo)), reverse=direccion < 0)
        return res[:limite] if limite else res

    def find_one(self, filtro: Dict) -> Optional[Dict]:
        res = self.find(filtro, limite=1)
        return res[0] if res else None

    def update_one(self, filtro: Dict, cambios: Dict) -> int:
        doc = next((d for d in self._docs.values() if _coincide(d, filtro)), None)
        if doc is None:
            return 0
        doc.update(cambios.get("$set", {}))
        for campo, valor in cambios.get("$push", {}).items():
            doc.setdefault(campo, []).append(valor)
        return 1

    def delete_one(self, filtro: Dict) -> int:
        doc = next((d for d in self._docs.values() if _coincide(d, filtro)), None)
        if doc is None:
            return 0
        del self._docs[doc["_id"]]
        return 1

    def delete_many(self, filtro: Dict) -> int:
        ids = [d["_id"] for d in self._docs.values() if _coincide(d, filtro)]
        for i in ids:
            del self._docs[i]
        return len(ids)

    def count_documents(self, filtro: Optional[Dict] = None) -> int:
        return len(self.find(filtro))


# ---------------------------------------------------------------------------
# Adaptador sobre pymongo con la misma interfaz que ColeccionMemoria
# ---------------------------------------------------------------------------
class ColeccionMongo:
    def __init__(self, coleccion):
        self._c = coleccion
        self.nombre = coleccion.name

    def insert_one(self, doc: Dict):
        doc.setdefault("_id", nuevo_id())
        self._c.insert_one(doc)
        return doc["_id"]

    def insert_many(self, docs: Iterable[Dict]):
        docs = list(docs)
        for d in docs:
            d.setdefault("_id", nuevo_id())
        if docs:
            self._c.insert_many(docs)
        return [d["_id"] for d in docs]

    def find(self, filtro: Optional[Dict] = None, orden: Optional[List] = None, limite: int = 0) -> List[Dict]:
        cursor = self._c.find(filtro or {})
        if orden:
            cursor = cursor.sort(orden)
        if limite:
            cursor = cursor.limit(limite)
        return list(cursor)

    def find_one(self, filtro: Dict) -> Optional[Dict]:
        return self._c.find_one(filtro)

    def update_one(self, filtro: Dict, cambios: Dict) -> int:
        return self._c.update_one(filtro, cambios).matched_count

    def delete_one(self, filtro: Dict) -> int:
        return self._c.delete_one(filtro).deleted_count

    def delete_many(self, filtro: Dict) -> int:
        return self._c.delete_many(filtro).deleted_count

    def count_documents(self, filtro: Optional[Dict] = None) -> int:
        return self._c.count_documents(filtro or {})

    def aggregate(self, pipeline: List[Dict]) -> List[Dict]:
        return list(self._c.aggregate(pipeline))


# ---------------------------------------------------------------------------
# Base de datos: decide el modo (mongo / memoria) y entrega colecciones
# ---------------------------------------------------------------------------
COLECCIONES = ("camiones", "accesos", "incidentes", "riesgos_eticos", "evaluaciones_llm")


class BaseDatos:
    def __init__(self, uri: Optional[str] = None, nombre: Optional[str] = None,
                 forzar_memoria: bool = False):
        self.uri = uri or config.mongo_uri
        self.nombre = nombre or config.mongo_db
        self.modo = "memoria"
        self.error: Optional[str] = None
        self._cliente = None
        self._memoria: Dict[str, ColeccionMemoria] = {n: ColeccionMemoria(n) for n in COLECCIONES}
        if not forzar_memoria:
            self.conectar()

    # ----------------------------------------------------------------------
    def conectar(self) -> bool:
        """Intenta conectarse a MongoDB. Devuelve True si lo logra; si no, deja el modo memoria."""
        try:
            from pymongo import MongoClient
            from pymongo.errors import PyMongoError
        except ImportError:
            self.error = "pymongo no está instalado (pip install pymongo)"
            log.warning(self.error)
            return False
        try:
            cliente = MongoClient(self.uri, serverSelectionTimeoutMS=config.mongo_timeout_ms)
            cliente.admin.command("ping")            # Fuerza la conexión real
            self._cliente = cliente
            self.modo = "mongo"
            self.error = None
            self._crear_indices()
            log.info("Conectado a MongoDB (%s / %s)", self._uri_segura(), self.nombre)
            return True
        except PyMongoError as exc:
            self.error = f"No se pudo conectar a MongoDB ({self._uri_segura()}): {type(exc).__name__}"
            log.warning("%s -> usando respaldo en memoria", self.error)
            self.modo = "memoria"
            return False

    def _uri_segura(self) -> str:
        """Oculta usuario/contraseña de la URI para mostrarla en pantalla o logs."""
        return re.sub(r"//[^@]+@", "//***:***@", self.uri)

    def _crear_indices(self) -> None:
        db = self._cliente[self.nombre]
        db.camiones.create_index("placa", unique=True)
        db.camiones.create_index("camion_id")
        db.accesos.create_index([("marca_tiempo", -1)])
        db.incidentes.create_index([("fecha", -1)])
        db.incidentes.create_index("estado")

    # ----------------------------------------------------------------------
    def coleccion(self, nombre: str):
        if nombre not in COLECCIONES:
            raise KeyError(f"Colección desconocida: {nombre}")
        if self.modo == "mongo":
            return ColeccionMongo(self._cliente[self.nombre][nombre])
        return self._memoria[nombre]

    def estado(self) -> Dict[str, Any]:
        return {
            "modo": self.modo,
            "uri": self._uri_segura(),
            "base": self.nombre,
            "error": self.error,
            "hora": datetime.now().isoformat(timespec="seconds"),
        }

    def limpiar_todo(self) -> None:
        """Borra todas las colecciones (sólo para datos de demostración / pruebas)."""
        for n in COLECCIONES:
            self.coleccion(n).delete_many({})
