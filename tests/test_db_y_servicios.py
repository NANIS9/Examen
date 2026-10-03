import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from logismart.asistente import Asistente
from logismart.clasificador import ClasificadorHibrido, ClienteOllama, ErrorLLM, clasificar_por_reglas, extraer_datos
from logismart.clasificador.esquema import ClasificacionLLM
from logismart.datos import cargar_demo
from logismart.db import BaseDatos, Repositorios
from logismart.reglas import decidir
from logismart.reportes import exportar_csv, exportar_json, exportar_pdf, generar_reporte_completo, reporte_a_lineas
from logismart.riesgos import ServicioRiesgos
from pydantic import ValidationError


def repos_memoria():
    return Repositorios(BaseDatos(forzar_memoria=True))


class TestRepositorios(unittest.TestCase):
    def setUp(self):
        self.repos = repos_memoria()

    def test_crud_camiones(self):
        _id = self.repos.camiones.crear({"placa": "abc-123-d", "camion_id": "cam-1", "empresa": "X", "autorizacion": True})
        self.assertEqual(self.repos.camiones.por_placa("ABC-123-D")["_id"], _id)
        with self.assertRaises(ValueError):
            self.repos.camiones.crear({"placa": "ABC-123-D", "camion_id": "CAM-2", "empresa": "Y"})
        self.repos.camiones.actualizar(_id, {"empresa": "Z"})
        self.assertEqual(self.repos.camiones.obtener(_id)["empresa"], "Z")
        self.assertTrue(self.repos.camiones.eliminar(_id))
        self.assertEqual(self.repos.camiones.contar(), 0)

    def test_accesos_y_filtro_fecha(self):
        d = decidir({"P": True, "Q": False, "R": False, "S": True})
        self.repos.accesos.registrar(d, "op", placa="AAA-111-A", camion_id="CAM-9")
        self.assertEqual(len(self.repos.accesos.por_camion("cam-9")), 1)
        ind = self.repos.indicadores(desde=datetime.now() - timedelta(minutes=1))
        self.assertEqual(ind["camiones_atendidos"], 1)
        self.assertEqual(ind["accesos_permitidos"], 1)
        self.assertEqual(self.repos.indicadores(desde=datetime.now() + timedelta(days=1))["camiones_atendidos"], 0)

    def test_incidentes_estados_y_agregacion(self):
        c = clasificar_por_reglas("derrame", "fuga de químico CAM-5")
        _id = self.repos.incidentes.registrar({"remitente": "a", "asunto": "derrame", "cuerpo": "x"}, c, c["entidades"], "op")
        self.assertEqual(self.repos.incidentes.abiertos(), 1)
        self.repos.incidentes.cambiar_estado(_id, "cerrado", "op")
        self.assertEqual(self.repos.incidentes.abiertos(), 0)
        self.assertEqual(len(self.repos.incidentes.obtener(_id)["historial"]), 2)
        with self.assertRaises(ValueError):
            self.repos.incidentes.cambiar_estado(_id, "inventado", "op")
        agg = self.repos.incidentes.por_categoria_y_semana()
        self.assertEqual(agg[0]["categoria"], "materiales_peligrosos")
        self.assertEqual(agg[0]["total"], 1)
        self.assertEqual(len(self.repos.incidentes.por_camion("CAM-5")), 1)

    def test_filtros_memoria(self):
        col = self.repos.bd.coleccion("camiones")
        col.insert_one({"a": 5, "b": {"c": "Hola"}})
        self.assertEqual(col.count_documents({"a": {"$gte": 5}}), 1)
        self.assertEqual(col.count_documents({"a": {"$gt": 5}}), 0)
        self.assertEqual(col.count_documents({"b.c": {"$regex": "hol"}}), 1)
        self.assertEqual(col.count_documents({"$or": [{"a": 1}, {"a": 5}]}), 1)


class TestClasificador(unittest.TestCase):
    def test_reglas_y_extraccion(self):
        r = clasificar_por_reglas("URGENTE: derrame en andén 3",
                                  "El camión CAM-102 con placas ABC-123-D presenta fuga de químico. La báscula marcó 48.5 toneladas.")
        self.assertEqual(r["categoria"], "materiales_peligrosos")
        self.assertEqual(r["prioridad"], "critica")
        self.assertEqual(r["entidades"]["placa"], "ABC-123-D")
        self.assertEqual(r["entidades"]["camion_id"], "CAM-102")
        self.assertEqual(r["entidades"]["peso_reportado_kg"], 48500.0)
        self.assertEqual(r["entidades"]["ubicacion"], "andén 3")

    def test_peso_con_miles(self):
        self.assertEqual(extraer_datos("", "marcó 43,200 kg")["peso_reportado_kg"], 43200.0)

    def test_escalamiento_urgente(self):
        self.assertEqual(clasificar_por_reglas("Pantalla lenta", "El sistema carga lento")["prioridad"], "baja")
        self.assertEqual(clasificar_por_reglas("Pantalla lenta urgente", "El sistema carga lento")["prioridad"], "media")

    def test_esquema_pydantic(self):
        ok = ClasificacionLLM.model_validate({"categoria": "Sobrepeso", "prioridad": "MEDIA", "resumen": "exceso",
                                              "entidades": {"placa": "abc-123-d", "peso_reportado_kg": "null"}})
        self.assertEqual(ok.categoria, "sobrepeso")
        self.assertEqual(ok.entidades.placa, "ABC-123-D")
        self.assertIsNone(ok.entidades.peso_reportado_kg)
        with self.assertRaises(ValidationError):
            ClasificacionLLM.model_validate({"categoria": "inventada", "prioridad": "alta", "resumen": "x"})

    def test_hibrido_cae_a_reglas_si_llm_falla(self):
        class LLMRoto(ClienteOllama):
            def clasificar(self, *a, **k):
                raise ErrorLLM("sin conexión")
        repos = repos_memoria()
        res = ClasificadorHibrido(llm=LLMRoto(), repos=repos).clasificar("derrame", "fuga de químico")
        self.assertEqual(res["fuente"], "reglas")
        self.assertEqual(res["categoria"], "materiales_peligrosos")
        self.assertIn("sin conexión", res["detalle"]["error_llm"])

    def test_hibrido_fusion_prioridad_mas_alta(self):
        class LLMFalso(ClienteOllama):
            def clasificar(self, asunto, cuerpo, remitente="", reintentos=None):
                c = ClasificacionLLM(categoria="falla_software", prioridad="baja", resumen="resumen llm",
                                     entidades={"ubicacion": "puerta b"})
                return c, {"prompt": "p", "respuesta": "{}", "latencia_ms": 12.0, "intentos": 1, "modelo": "falso"}
        repos = repos_memoria()
        res = ClasificadorHibrido(llm=LLMFalso(), repos=repos).clasificar("Intruso", "Persona sin autorizacion en anden 7")
        self.assertTrue(res["requiere_revision_humana"])
        self.assertEqual(res["prioridad"], "alta")          # reglas (alta) > LLM (baja)
        self.assertEqual(res["entidades"]["ubicacion"], "anden 7")   # regex tiene preferencia
        self.assertEqual(repos.evaluaciones.contar(), 1)
        self.assertFalse(repos.evaluaciones.listar()[0]["coincide_reglas"])


class TestAsistenteRiesgosReportes(unittest.TestCase):
    def setUp(self):
        self.repos = repos_memoria()
        self.sr = ServicioRiesgos(self.repos)
        cargar_demo(self.repos, self.sr)

    def test_demo_carga(self):
        self.assertEqual(self.repos.camiones.contar(), 10)
        self.assertGreaterEqual(self.repos.incidentes.contar(), 30)
        self.assertEqual(self.repos.riesgos.contar(), 8)

    def test_asistente_sin_datos_no_inventa(self):
        class LLMRoto(ClienteOllama):
            def chat(self, *a, **k):
                raise AssertionError("no debe llamarse al LLM sin contexto")
        a = Asistente(self.repos, LLMRoto())
        r = a.responder("¿Qué opinas del clima?")
        self.assertEqual(r["modo"], "sin_datos")
        self.assertIn("No tengo información", r["texto"])

    def test_asistente_recupera_y_cita(self):
        class LLMFalso(ClienteOllama):
            def chat(self, mensajes, formato=None, temperatura=None):
                assert "CONTEXTO" in mensajes[1]["content"]
                return "Respuesta con cita [accesos:x]", 5.0
        a = Asistente(self.repos, LLMFalso())
        r = a.responder("¿Por qué CAM-102 fue enviado a inspección?")
        self.assertEqual(r["modo"], "llm")
        self.assertTrue(any(f.startswith("[camiones:") for f in r["fuentes"]))
        self.assertTrue(any(f.startswith("[accesos:") for f in r["fuentes"]))
        self.assertEqual(self.repos.evaluaciones.listar()[-1]["tipo"], "asistente")

    def test_riesgos_validacion_y_residual(self):
        with self.assertRaises(ValueError):
            self.sr.crear({"modulo": "m", "descripcion": "d", "categoria": "sesgo", "probabilidad": 6, "impacto": 1})
        with self.assertRaises(ValueError):
            self.sr.crear({"modulo": "m", "descripcion": "d", "categoria": "sesgo", "probabilidad": 2, "impacto": 2,
                           "probabilidad_residual": 5, "impacto_residual": 5})
        _id = self.sr.crear({"modulo": "m", "descripcion": "d", "categoria": "sesgo", "probabilidad": 5, "impacto": 4,
                             "probabilidad_residual": 2, "impacto_residual": 2})
        r = self.repos.riesgos.obtener(_id)
        self.assertEqual((r["puntaje"], r["nivel"], r["puntaje_residual"], r["nivel_residual"]), (20, "crítico", 4, "bajo"))
        self.assertEqual(self.repos.riesgos.criticos(), 1)
        self.sr.actualizar(_id, {**r, "probabilidad": 3})
        self.assertEqual(len(self.repos.riesgos.obtener(_id)["historico"]), 2)
        self.assertEqual(sum(sum(f) for f in self.sr.matriz_5x5()), 9)

    def test_exportaciones(self):
        rep = generar_reporte_completo(self.repos, self.sr)
        with tempfile.TemporaryDirectory() as d:
            j = exportar_json(rep, os.path.join(d, "r.json"))
            self.assertEqual(json.load(open(j, encoding="utf-8"))["indicadores"]["camiones_registrados"], 10)
            c = exportar_csv(rep["accesos"], os.path.join(d, "a.csv"))
            with open(c, encoding="utf-8-sig") as f:
                lineas = f.read().splitlines()
            self.assertEqual(len(lineas), len(rep["accesos"]) + 1)
            self.assertIn("premisas.P", lineas[0])
            p = exportar_pdf("T", reporte_a_lineas(rep), os.path.join(d, "r.pdf"))
            datos = open(p, "rb").read()
            self.assertTrue(datos.startswith(b"%PDF-1.4"))
            self.assertTrue(datos.rstrip().endswith(b"%%EOF"))
            self.assertIn(b"/Type /Pages", datos)


if __name__ == "__main__":
    unittest.main()
