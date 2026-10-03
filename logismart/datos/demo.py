"""
Datos de demostración: camiones, bitácora de accesos (3 semanas), incidentes clasificados por reglas
y la matriz de riesgos éticos. Se cargan desde la GUI (Configuración -> Cargar datos demo) o con:

    python logiuncodigo.py --demo
"""
import random
from datetime import datetime, timedelta, date

from ..clasificador.evaluacion import cargar_dataset
from ..clasificador.reglas import clasificar_por_reglas
from ..config import config
from ..reglas import decidir, premisas_desde_camion
from ..riesgos import RIESGOS_PREDETERMINADOS

HOY = date.today()


def _c(camion_id, placa, empresa, autorizacion, peligrosos, peso, conductor, cert, dias_vigencia):
    return {"camion_id": camion_id, "placa": placa, "empresa": empresa, "autorizacion": autorizacion,
            "materiales_peligrosos": peligrosos, "peso_bruto_kg": peso,
            "conductor": {"nombre": conductor, "certificacion": cert,
                          "vigente_hasta": (HOY + timedelta(days=dias_vigencia)).isoformat() if cert else None}}


CAMIONES_DEMO = [
    _c("CAM-102", "ABC-123-D", "Químicos del Bajío", True, True, 48500, "Luis Ortega", "CERT-7781", 200),
    _c("CAM-210", "XYZ-456-A", "Transportes del Norte", True, True, 36000, "María Pineda", "CERT-1024", 90),
    _c("CAM-315", "DEF-315-B", "Logística Azteca", True, False, 43200, "Jorge Salas", "CERT-3310", 400),
    _c("CAM-118", "PQR-654-D", "Fletes Rápidos MX", True, False, 30000, "Ana Beltrán", "CERT-5520", 15),
    _c("CAM-077", "GHI-077-C", "Transportes del Norte", True, False, 28000, "Pedro Juárez", "CERT-0912", -30),
    _c("CAM-150", "MNO-321-C", "Carga Express", False, False, 25000, "Rosa Medina", "CERT-6611", 120),
    _c("CAM-388", "STU-388-E", "Químicos del Bajío", True, True, 39000, "Hugo Castro", "CERT-8890", 60),
    _c("CAM-444", "VWX-111-F", "Logística Azteca", True, True, 45000, "Elena Ruiz", "CERT-2201", 300),
    _c("CAM-260", "JKL-789-B", "Fletes Rápidos MX", True, False, 41000, "Carlos Vega", None, 0),
    _c("CAM-512", "YZA-512-G", "Carga Express", True, False, 22000, "Sofía Lara", "CERT-4477", 180),
]


def cargar_demo(repos, servicio_riesgos, limpiar: bool = True, semilla: int = 7) -> dict:
    rnd = random.Random(semilla)
    if limpiar:
        repos.bd.limpiar_todo()

    # --- Camiones ------------------------------------------------------
    for c in CAMIONES_DEMO:
        repos.camiones.crear(dict(c, conductor=dict(c["conductor"])))

    # --- Accesos: ~45 registros repartidos en las últimas 3 semanas ----------
    operadores = ["operador1", "operador2", "supervisor"]
    n_accesos = 0
    for i in range(45):
        cam = rnd.choice(CAMIONES_DEMO)
        momento = datetime.now() - timedelta(days=rnd.randint(0, 20), hours=rnd.randint(0, 23), minutes=rnd.randint(0, 59))
        peso = cam["peso_bruto_kg"] * rnd.uniform(0.85, 1.05)
        premisas = premisas_desde_camion(cam, peso, config.peso_maximo_kg, ahora=momento,
                                         hora_inicio=config.hora_inicio_peligrosos, hora_fin=config.hora_fin_peligrosos)
        decision = decidir(premisas)
        decision["peso_kg"] = round(peso)
        doc = {**decision, "placa": cam["placa"], "camion_id": cam["camion_id"], "marca_tiempo": momento,
               "operador": rnd.choice(operadores)}
        repos.accesos.crear(doc)
        n_accesos += 1

    # --- Incidentes: a partir del conjunto etiquetado, clasificados por reglas -------
    estados = ["nuevo", "nuevo", "en_atencion", "cerrado", "cerrado"]
    for correo in cargar_dataset():
        clasif = clasificar_por_reglas(correo["asunto"], correo["cuerpo"])
        clasificacion = {"categoria": clasif["categoria"], "prioridad": clasif["prioridad"],
                         "entidades": clasif["entidades"], "resumen": clasif["resumen"],
                         "fuente": "reglas", "requiere_revision_humana": False, "etiqueta_manual": correo["categoria"]}
        fecha = datetime.now() - timedelta(days=rnd.randint(0, 20), hours=rnd.randint(0, 23))
        estado = rnd.choice(estados)
        historial = [{"fecha": fecha, "accion": "creado", "operador": "demo"}]
        if estado != "nuevo":
            historial.append({"fecha": fecha + timedelta(hours=2), "accion": f"estado -> {estado}", "operador": "operador1"})
        repos.incidentes.crear({
            "correo": {"remitente": correo["remitente"], "asunto": correo["asunto"], "cuerpo": correo["cuerpo"]},
            "clasificacion": clasificacion, "datos_extraidos": clasif["entidades"],
            "estado": estado, "fecha": fecha, "historial": historial,
        })

    # --- Riesgos éticos ----------------------------------------------------
    for r in RIESGOS_PREDETERMINADOS:
        servicio_riesgos.crear(dict(r), operador="demo")

    return {"camiones": len(CAMIONES_DEMO), "accesos": n_accesos, "incidentes": repos.incidentes.contar(),
            "riesgos": repos.riesgos.contar(), "modo_bd": repos.bd.modo}
