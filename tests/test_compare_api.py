import json
import unittest

from app import app


class TestComparacionesConTicks(unittest.TestCase):
    """Las tablas de comparación deben informar los ticks totales."""

    def setUp(self):
        with open("scenarios/escenario_basico.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.client = app.test_client()

    def test_comparar_armado_de_waves_incluye_total_ticks(self):
        respuesta = self.client.post(
            "/api/waves/compare",
            json={"escenario": self.data},
        )

        self.assertEqual(respuesta.status_code, 200)
        comparacion = respuesta.get_json()["comparacion"]
        self.assertGreater(len(comparacion), 0)
        for estrategia in comparacion:
            self.assertIn("total_ticks", estrategia)
            self.assertIsInstance(estrategia["total_ticks"], int)
            self.assertGreater(estrategia["total_ticks"], 0)

    def test_todas_las_combinaciones_incluye_ticks(self):
        respuesta = self.client.post(
            "/api/routes/compare",
            json={"escenario": self.data, "todas_combinaciones": True},
        )

        self.assertEqual(respuesta.status_code, 200)
        combinaciones = respuesta.get_json()["combinaciones"]
        self.assertGreater(len(combinaciones), 0)
        for combinacion in combinaciones:
            self.assertIn("ticks", combinacion)
            self.assertIsInstance(combinacion["ticks"], int)
            self.assertGreater(combinacion["ticks"], 0)


if __name__ == "__main__":
    unittest.main()
