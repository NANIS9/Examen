"""Prueba de humo de la GUI: construye todas las pestañas en modo memoria y ejercita acciones básicas."""
import time
import tkinter as tk
import unittest

from logismart.datos import cargar_demo


def _esperar(app, condicion, seg=10):
    t = time.time()
    while not condicion() and time.time() - t < seg:
        app.update()


class TestGUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from logismart.gui.app import AplicacionLogiSmart
            cls.app = AplicacionLogiSmart(forzar_memoria=True)
        except tk.TclError as exc:          # sin pantalla (CI sin display)
            raise unittest.SkipTest(f"Sin entorno gráfico: {exc}")
        cls.app.withdraw()
        cargar_demo(cls.app.ctx.repos, cls.app.ctx.riesgos)
        cls.app.ctx.notificar()
        cls.app.update()
        cls.tabs = cls.app.winfo_children()[0].winfo_children()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def test_pestanas(self):
        self.assertEqual([type(t).__name__ for t in self.tabs],
                         ["PanelControl", "ControlAcceso", "Simulador", "BandejaIncidentes", "AsistenteGUI",
                          "RiesgosGUI", "CamionesGUI", "ReportesGUI", "ConfiguracionGUI"])

    def test_panel_indicadores(self):
        panel = self.tabs[0]
        _esperar(self.app, lambda: panel._vars["camiones_atendidos"].get() not in ("-", "0"))
        self.assertEqual(panel._vars["camiones_registrados"].get(), "10")

    def test_control_acceso_semaforo(self):
        ca = self.tabs[1]
        ca.e_busqueda.delete(0, "end"); ca.e_busqueda.insert(0, "CAM-077"); ca.buscar()
        self.assertEqual(ca.lbl_decision.cget("text"), "ACCESO DENEGADO")      # certificación vencida
        ca.e_busqueda.delete(0, "end"); ca.e_busqueda.insert(0, "CAM-512"); ca.buscar()
        self.assertEqual(ca.lbl_decision.cget("text"), "ACCESO ESTÁNDAR")
        ca.e_peso.insert(0, "abc")
        ca.buscar()      # muestra error amigable, no excepción
        ca.e_peso.delete(0, "end")

    def test_simulador_en_vivo(self):
        sim = self.tabs[2]
        sim.vars["P"].set(True); sim.vars["S"].set(True); sim.vars["Q"].set(False)
        self.assertEqual(sim.labels["A"].cget("text"), "V")
        sim.vars["Q"].set(True)
        self.assertEqual(sim.labels["A"].cget("text"), "F")
        self.assertEqual(sim.labels["E"].cget("text"), "V")

    def test_bandeja_clasifica_por_reglas(self):
        b = self.tabs[3]
        b._ejemplo(); b.usar_llm.set(False); b.clasificar()
        _esperar(self.app, lambda: b.resultado is not None)
        self.assertEqual(b.resultado["categoria"], "materiales_peligrosos")
        self.assertEqual(b.cb_pri.get(), "critica")

    def test_asistente_responde(self):
        a = self.tabs[4]
        a.entrada.insert(0, "¿Por qué CAM-077 fue denegado?"); a.preguntar()
        _esperar(self.app, lambda: str(a.btn.cget("state")) == "normal", seg=90)
        self.assertGreater(a.lst_fuentes.size(), 0)

    def test_riesgos_y_camiones_listados(self):
        self.assertEqual(len(self.tabs[5].tabla.tree.get_children()), 8)
        self.assertEqual(len(self.tabs[6].tabla.tree.get_children()), 10)


if __name__ == "__main__":
    unittest.main()
