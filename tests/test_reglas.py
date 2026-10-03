import itertools
import unittest
from datetime import datetime

from logismart.reglas import evaluar, decidir, generar_tabla_verdad, tabla_regla, analizar_reglas, premisas_desde_camion


class TestReglasOriginales(unittest.TestCase):
    """A = P ∧ S ∧ ¬Q y E = P ∧ (R ∨ Q) deben conservarse exactamente (tabla escrita a mano)."""
    ESPERADO = {
        (1, 1, 1, 1): (0, 1), (1, 1, 1, 0): (0, 1), (1, 1, 0, 1): (0, 1), (1, 1, 0, 0): (0, 1),
        (1, 0, 1, 1): (1, 1), (1, 0, 1, 0): (0, 1), (1, 0, 0, 1): (1, 0), (1, 0, 0, 0): (0, 0),
        (0, 1, 1, 1): (0, 0), (0, 1, 1, 0): (0, 0), (0, 1, 0, 1): (0, 0), (0, 1, 0, 0): (0, 0),
        (0, 0, 1, 1): (0, 0), (0, 0, 1, 0): (0, 0), (0, 0, 0, 1): (0, 0), (0, 0, 0, 0): (0, 0),
    }

    def test_tabla_A_E(self):
        for (p, q, r, s), (a, e) in self.ESPERADO.items():
            res = evaluar({"P": bool(p), "Q": bool(q), "R": bool(r), "S": bool(s)})
            self.assertEqual(res["A"], bool(a), (p, q, r, s))
            self.assertEqual(res["E"], bool(e), (p, q, r, s))

    def test_tipo_invalido(self):
        with self.assertRaises(TypeError):
            evaluar({"P": 1, "Q": False, "R": False, "S": True})


class TestReglasNuevas(unittest.TestCase):
    def test_B_tabla(self):
        # B = P ∧ S ∧ ¬V : sólo verdadera en (V,V,F)
        for f in tabla_regla("B"):
            self.assertEqual(f["B"], f["P"] and f["S"] and not f["V"])
        self.assertEqual(sum(f["B"] for f in tabla_regla("B")), 1)

    def test_X_tabla(self):
        for f in tabla_regla("X"):
            self.assertEqual(f["X"], f["P"] and f["R"] and not f["H"])

    def test_tabla_completa_64(self):
        self.assertEqual(len(generar_tabla_verdad()), 64)

    def test_X_implica_E(self):
        tipos = {(tuple(h["reglas"]), h["tipo"]) for h in analizar_reglas()}
        self.assertIn((("X", "E"), "implica"), tipos)


class TestDecision(unittest.TestCase):
    def test_prioridades(self):
        self.assertEqual(decidir({"P": False, "Q": False, "R": False, "S": True})["decision"], "DENEGADO")
        self.assertEqual(decidir({"P": True, "Q": False, "R": True, "S": True, "V": True, "H": False})["decision"], "RETENIDO")
        self.assertEqual(decidir({"P": True, "Q": False, "R": False, "S": True, "V": False})["decision"], "DENEGADO")
        self.assertEqual(decidir({"P": True, "Q": True, "R": False, "S": True})["decision"], "INSPECCION_ESPECIAL")
        self.assertEqual(decidir({"P": True, "Q": False, "R": False, "S": True})["decision"], "ACCESO_ESTANDAR")
        self.assertEqual(decidir({"P": True, "Q": False, "R": False, "S": False})["decision"], "DENEGADO")

    def test_explicacion_incluye_premisas_y_decision(self):
        d = decidir({"P": True, "Q": False, "R": False, "S": True})
        self.assertTrue(any(l.startswith("P = V") for l in d["explicacion"]))
        self.assertTrue(d["explicacion"][-1].startswith("DECISIÓN"))
        self.assertEqual(d["semaforo"], "verde")

    def test_premisas_desde_camion(self):
        cam = {"autorizacion": True, "materiales_peligrosos": True, "peso_bruto_kg": 30000,
               "conductor": {"certificacion": "C-1", "vigente_hasta": "2000-01-01"}}
        p = premisas_desde_camion(cam, 45000, 40000, ahora=datetime(2026, 1, 1, 23, 0))
        self.assertEqual(p, {"P": True, "Q": True, "R": True, "S": True, "V": False, "H": False})


if __name__ == "__main__":
    unittest.main()
