"""
Repositorios: una clase por colección con operaciones CRUD y consultas específicas.

Esquema de colecciones (resumen; detalle en docs/INFORME_TECNICO.md):

  camiones         : placa, camion_id, empresa, autorizacion, conductor{nombre, certificacion, vigente_hasta},
                     materiales_peligrosos, peso_bruto_kg
  accesos          : placa, camion_id, premisas{P,Q,R,S,V,H}, resultado{A,E,D,X}, decision, explicacion[],
                     marca_tiempo, operador
  incidentes       : correo{remitente, asunto, cuerpo}, clasificacion{categoria, prioridad, entidades, resumen,
                     fuente, requiere_revision_humana}, estado, fecha, historial[]
  riesgos_eticos   : modulo, descripcion, categoria, probabilidad, impacto, mitigacion,
                     probabilidad_residual, impacto_residual, puntaje, puntaje_residual, historico[]
  evaluaciones_llm : tipo, prompt, respuesta, modelo, latencia_ms, coincide_reglas, fecha
"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from .conexion import BaseDatos

ESTADOS_INCIDENTE = ("nuevo", "en_atencion", "cerrado")


class _RepoBase:
    nombre = ""

    def __init__(self, bd: BaseDatos):
        self.bd = bd

    @property
    def col(self):
        return self.bd.coleccion(self.nombre)

    # CRUD genérico --------------------------------------------------------
    def crear(self, doc: Dict) -> str:
        return self.col.insert_one(doc)

    def obtener(self, _id: str) -> Optional[Dict]:
        return self.col.find_one({"_id": _id})

    def listar(self, filtro: Optional[Dict] = None, orden: Optional[List] = None, limite: int = 0) -> List[Dict]:
        return self.col.find(filtro, orden, limite)

    def actualizar(self, _id: str, cambios: Dict) -> bool:
        return self.col.update_one({"_id": _id}, {"$set": cambios}) > 0

    def eliminar(self, _id: str) -> bool:
        return self.col.delete_one({"_id": _id}) > 0

    def contar(self, filtro: Optional[Dict] = None) -> int:
        return self.col.count_documents(filtro)


# ---------------------------------------------------------------------------
class RepoCamiones(_RepoBase):
    nombre = "camiones"

    def por_placa(self, placa: str) -> Optional[Dict]:
        return self.col.find_one({"placa": placa.strip().upper()})

    def por_camion_id(self, camion_id: str) -> Optional[Dict]:
        return self.col.find_one({"camion_id": camion_id.strip().upper()})

    def buscar(self, texto: str) -> List[Dict]:
        t = texto.strip()
        if not t:
            return self.listar(orden=[("camion_id", 1)])
        return self.listar({"$or": [{"placa": {"$regex": t}}, {"camion_id": {"$regex": t}},
                                    {"empresa": {"$regex": t}}]}, orden=[("camion_id", 1)])

    def crear(self, doc: Dict) -> str:
        doc["placa"] = doc["placa"].strip().upper()
        doc["camion_id"] = doc["camion_id"].strip().upper()
        if self.por_placa(doc["placa"]):
            raise ValueError(f"Ya existe un camión con la placa {doc['placa']}")
        return super().crear(doc)


# ---------------------------------------------------------------------------
class RepoAccesos(_RepoBase):
    nombre = "accesos"

    def registrar(self, decision: Dict, operador: str, placa: Optional[str] = None,
                  camion_id: Optional[str] = None) -> str:
        doc = {**decision, "placa": placa, "camion_id": camion_id,
               "marca_tiempo": datetime.now(), "operador": operador}
        return self.crear(doc)

    def recientes(self, limite: int = 50, desde: Optional[datetime] = None,
                  hasta: Optional[datetime] = None) -> List[Dict]:
        return self.listar(_filtro_fecha("marca_tiempo", desde, hasta), orden=[("marca_tiempo", -1)], limite=limite)

    def por_camion(self, identificador: str) -> List[Dict]:
        ident = identificador.strip().upper()
        return self.listar({"$or": [{"placa": ident}, {"camion_id": ident}]}, orden=[("marca_tiempo", -1)])


# ---------------------------------------------------------------------------
class RepoIncidentes(_RepoBase):
    nombre = "incidentes"

    def registrar(self, correo: Dict, clasificacion: Dict, datos_extraidos: Dict, operador: str) -> str:
        ahora = datetime.now()
        return self.crear({
            "correo": correo, "clasificacion": clasificacion, "datos_extraidos": datos_extraidos,
            "estado": "nuevo", "fecha": ahora,
            "historial": [{"fecha": ahora, "accion": "creado", "operador": operador}],
        })

    def cambiar_estado(self, _id: str, estado: str, operador: str) -> bool:
        if estado not in ESTADOS_INCIDENTE:
            raise ValueError(f"Estado inválido: {estado}. Usa {ESTADOS_INCIDENTE}")
        return self.col.update_one({"_id": _id}, {
            "$set": {"estado": estado},
            "$push": {"historial": {"fecha": datetime.now(), "accion": f"estado -> {estado}", "operador": operador}},
        }) > 0

    def editar_clasificacion(self, _id: str, clasificacion: Dict, operador: str) -> bool:
        return self.col.update_one({"_id": _id}, {
            "$set": {"clasificacion": clasificacion},
            "$push": {"historial": {"fecha": datetime.now(), "accion": "clasificación editada manualmente",
                                    "operador": operador}},
        }) > 0

    def abiertos(self) -> int:
        return self.contar({"estado": {"$ne": "cerrado"}})

    def recientes(self, limite: int = 100, desde: Optional[datetime] = None,
                  hasta: Optional[datetime] = None, estado: Optional[str] = None) -> List[Dict]:
        filtro = _filtro_fecha("fecha", desde, hasta)
        if estado:
            filtro["estado"] = estado
        return self.listar(filtro, orden=[("fecha", -1)], limite=limite)

    def por_camion(self, identificador: str) -> List[Dict]:
        ident = identificador.strip().upper()
        return self.listar({"$or": [{"datos_extraidos.placa": ident}, {"datos_extraidos.camion_id": ident}]},
                           orden=[("fecha", -1)])

    def por_categoria_y_semana(self) -> List[Dict]:
        """AGREGACIÓN: número de incidentes por categoría y semana ISO."""
        if self.bd.modo == "mongo":
            pipeline = [
                {"$group": {
                    "_id": {"categoria": "$clasificacion.categoria",
                            "anio": {"$isoWeekYear": "$fecha"}, "semana": {"$isoWeek": "$fecha"}},
                    "total": {"$sum": 1},
                }},
                {"$project": {"_id": 0, "categoria": "$_id.categoria", "anio": "$_id.anio",
                              "semana": "$_id.semana", "total": 1}},
                {"$sort": {"anio": 1, "semana": 1, "categoria": 1}},
            ]
            return self.col.aggregate(pipeline)
        # Equivalente en memoria
        conteo: Dict = defaultdict(int)
        for d in self.listar():
            iso = d["fecha"].isocalendar()
            conteo[(d["clasificacion"]["categoria"], iso[0], iso[1])] += 1
        return [{"categoria": c, "anio": a, "semana": s, "total": t}
                for (c, a, s), t in sorted(conteo.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0]))]


# ---------------------------------------------------------------------------
class RepoRiesgos(_RepoBase):
    nombre = "riesgos_eticos"

    def criticos(self) -> int:
        return self.contar({"puntaje": {"$gte": 17}})

    def por_modulo(self, modulo: str) -> List[Dict]:
        return self.listar({"modulo": modulo}, orden=[("puntaje", -1)])

    def ordenados(self) -> List[Dict]:
        return self.listar(orden=[("puntaje", -1)])


# ---------------------------------------------------------------------------
class RepoEvaluacionesLLM(_RepoBase):
    nombre = "evaluaciones_llm"

    def registrar(self, tipo: str, prompt: str, respuesta: str, modelo: str, latencia_ms: float,
                  coincide_reglas: Optional[bool] = None, extra: Optional[Dict] = None) -> str:
        return self.crear({"tipo": tipo, "prompt": prompt, "respuesta": respuesta, "modelo": modelo,
                           "latencia_ms": round(latencia_ms, 1), "coincide_reglas": coincide_reglas,
                           "fecha": datetime.now(), **(extra or {})})

    def resumen(self) -> Dict:
        docs = self.listar()
        clasif = [d for d in docs if d.get("tipo") == "clasificacion"]
        con_dato = [d for d in clasif if d.get("coincide_reglas") is not None]
        return {
            "total": len(docs),
            "clasificaciones": len(clasif),
            "latencia_promedio_ms": round(sum(d["latencia_ms"] for d in docs) / len(docs), 1) if docs else 0,
            "coincidencia_con_reglas": round(sum(d["coincide_reglas"] for d in con_dato) / len(con_dato), 3)
            if con_dato else None,
        }


# ---------------------------------------------------------------------------
def _filtro_fecha(campo: str, desde: Optional[datetime], hasta: Optional[datetime]) -> Dict:
    rango = {}
    if desde:
        rango["$gte"] = desde
    if hasta:
        rango["$lte"] = hasta
    return {campo: rango} if rango else {}


class Repositorios:
    """Agrupa todos los repositorios sobre una misma conexión."""

    def __init__(self, bd: Optional[BaseDatos] = None):
        self.bd = bd or BaseDatos()
        self.camiones = RepoCamiones(self.bd)
        self.accesos = RepoAccesos(self.bd)
        self.incidentes = RepoIncidentes(self.bd)
        self.riesgos = RepoRiesgos(self.bd)
        self.evaluaciones = RepoEvaluacionesLLM(self.bd)

    def indicadores(self, desde: Optional[datetime] = None, hasta: Optional[datetime] = None) -> Dict:
        """Indicadores del panel de control, con filtro por fecha."""
        accesos = self.accesos.listar(_filtro_fecha("marca_tiempo", desde, hasta))
        incidentes = self.incidentes.listar(_filtro_fecha("fecha", desde, hasta))
        return {
            "camiones_atendidos": len(accesos),
            "accesos_permitidos": sum(1 for a in accesos if a["resultado"].get("A")),
            "inspecciones": sum(1 for a in accesos if a["resultado"].get("E")),
            "accesos_denegados": sum(1 for a in accesos if not a["resultado"].get("A") and not a["resultado"].get("E")),
            "incidentes_total": len(incidentes),
            "incidentes_abiertos": sum(1 for i in incidentes if i["estado"] != "cerrado"),
            "incidentes_criticos": sum(1 for i in incidentes if i["clasificacion"]["prioridad"] == "critica"),
            "riesgos_total": self.riesgos.contar(),
            "riesgos_criticos": self.riesgos.criticos(),
            "camiones_registrados": self.camiones.contar(),
            "llm": self.evaluaciones.resumen(),
        }
