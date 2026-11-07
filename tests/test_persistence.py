import copy
import glob
import json
import unittest

from app import app
from models.persistence import validate_saved_state, validate_scenario


def _cargar(ruta: str) -> dict:
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _sin_tiempos(dato):
    """Copia del resultado sin los tiempos medidos (cambian en cada corrida)."""
    if isinstance(dato, dict):
        return {k: _sin_tiempos(v) for k, v in dato.items() if k != "tiempo_ms"}
    if isinstance(dato, list):
        return [_sin_tiempos(v) for v in dato]
    return dato


ESTADO_OK = {
    "estrategia_wave": "por_pedido",
    "estrategia": "cercania",
    "buscador": "bfs",
    "velocidad": 1,
    "frame": 10,
    "tick": 10,
}


class TestValidarEscenario(unittest.TestCase):
    """validate_scenario: el back decide si un archivo guardado se puede cargar."""

    def setUp(self):
        self.data = _cargar("scenarios/escenario_basico.json")

    def test_todos_los_escenarios_de_ejemplo_son_validos(self):
        for ruta in sorted(glob.glob("scenarios/*.json")):
            with self.subTest(escenario=ruta):
                resultado = validate_scenario(_cargar(ruta))
                self.assertTrue(resultado["valido"], resultado["errores"])

    def test_acepta_la_seccion_estado(self):
        self.data["estado"] = dict(ESTADO_OK)
        resultado = validate_scenario(self.data)
        self.assertTrue(resultado["valido"], resultado["errores"])

    def test_no_es_un_objeto(self):
        resultado = validate_scenario([1, 2, 3])
        self.assertFalse(resultado["valido"])

    def test_falta_el_warehouse(self):
        del self.data["warehouse"]
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])
        self.assertIn("warehouse", resultado["errores"][0])

    def test_racks_solapados(self):
        racks = self.data["warehouse"]["racks"]
        copia = copy.deepcopy(racks[0])
        copia["id"] = "RACK_COPIA"
        racks.append(copia)
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])

    def test_puerta_fuera_del_borde(self):
        self.data["warehouse"]["puertas"][0]["ubicacion"] = {"x": 5, "y": 5}
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])

    def test_pedido_con_producto_inexistente(self):
        self.data["pedidos"][0]["items"][0]["producto_id"] = "NO_EXISTE"
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])
        self.assertIn("NO_EXISTE", resultado["errores"][0])

    def test_dimension_con_tipo_incorrecto(self):
        self.data["warehouse"]["dimensiones"]["ancho_x"] = "veinte"
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])

    def test_stock_insuficiente_es_un_aviso(self):
        self.data["pedidos"][0]["items"][0]["cantidad"] = 10_000
        resultado = validate_scenario(self.data)
        self.assertTrue(resultado["valido"], resultado["errores"])
        self.assertGreater(len(resultado["avisos"]), 0)
        self.assertIn(self.data["pedidos"][0]["id"], resultado["avisos"][0])

    def test_estado_invalido_hace_invalido_el_escenario(self):
        self.data["estado"] = {"estrategia": "zigzag"}
        resultado = validate_scenario(self.data)
        self.assertFalse(resultado["valido"])


class TestValidarEstado(unittest.TestCase):
    """validate_saved_state: la sección 'estado' de la simulación guardada."""

    def test_estado_completo(self):
        self.assertEqual(validate_saved_state(dict(ESTADO_OK)), [])

    def test_estado_solo_con_waves(self):
        estado = dict(ESTADO_OK, frame=None, tick=None)
        self.assertEqual(validate_saved_state(estado), [])

    def test_no_es_un_objeto(self):
        self.assertEqual(len(validate_saved_state("hola")), 1)

    def test_opciones_desconocidas(self):
        for clave in ("estrategia_wave", "estrategia", "buscador"):
            with self.subTest(clave=clave):
                errores = validate_saved_state(dict(ESTADO_OK, **{clave: "otra"}))
                self.assertEqual(len(errores), 1)
                self.assertIn(clave, errores[0])

    def test_frame_negativo_o_no_entero(self):
        for valor in (-1, 2.5, "3", True):
            with self.subTest(frame=valor):
                self.assertEqual(len(validate_saved_state(dict(ESTADO_OK, frame=valor))), 1)

    def test_velocidad_fuera_de_rango(self):
        for valor in (0, 11, "1"):
            with self.subTest(velocidad=valor):
                self.assertEqual(len(validate_saved_state(dict(ESTADO_OK, velocidad=valor))), 1)

    def test_frame_sin_estrategia_de_waves(self):
        estado = dict(ESTADO_OK)
        del estado["estrategia_wave"]
        self.assertEqual(len(validate_saved_state(estado)), 1)


class TestRutaValidar(unittest.TestCase):
    """POST /api/escenario/validar"""

    def setUp(self):
        self.client = app.test_client()
        self.data = _cargar("scenarios/escenario_basico.json")

    def test_escenario_valido(self):
        r = self.client.post("/api/escenario/validar", json=self.data)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["valido"])

    def test_escenario_invalido_responde_200_con_errores(self):
        del self.data["warehouse"]
        r = self.client.post("/api/escenario/validar", json=self.data)
        self.assertEqual(r.status_code, 200)
        cuerpo = r.get_json()
        self.assertFalse(cuerpo["valido"])
        self.assertGreater(len(cuerpo["errores"]), 0)

    def test_cuerpo_que_no_es_json(self):
        r = self.client.post("/api/escenario/validar", data="esto no es json",
                             content_type="text/plain")
        self.assertEqual(r.status_code, 400)


class TestContinuarSimulacion(unittest.TestCase):
    """
    La simulación guardada se retoma volviendo a simular: tiene que dar
    exactamente los mismos frames que la primera vez.
    """

    def setUp(self):
        self.client = app.test_client()

    def _simular(self, escenario, estado):
        cuerpo = {
            "escenario": escenario,
            "estrategia": estado["estrategia"],
            "buscador": estado["buscador"],
            "estrategia_wave": estado["estrategia_wave"],
            "velocidad": estado["velocidad"],
        }
        r = self.client.post("/api/simulacion", json=cuerpo)
        self.assertEqual(r.status_code, 200)
        return r.get_json()

    def test_volver_a_simular_da_los_mismos_frames(self):
        for ruta in ("scenarios/escenario_basico.json",
                     "scenarios/escenario_despacho_multiple.json"):
            for estrategia in ("orden", "cercania"):
                with self.subTest(escenario=ruta, estrategia=estrategia):
                    data = _cargar(ruta)
                    estado = dict(ESTADO_OK, estrategia=estrategia)
                    primera = self._simular(data, estado)

                    # Lo que haría el front al guardar y volver a cargar.
                    estado["frame"] = len(primera["frames"]) // 2
                    estado["tick"] = primera["frames"][estado["frame"]]["tick"]
                    guardado = json.loads(json.dumps(dict(data, estado=estado)))
                    self.assertTrue(validate_scenario(guardado)["valido"])

                    segunda = self._simular(guardado, estado)
                    self.assertEqual(_sin_tiempos(primera), _sin_tiempos(segunda))
                    self.assertEqual(segunda["frames"][estado["frame"]]["tick"], estado["tick"])

    def test_las_demas_rutas_ignoran_estado_y_editor(self):
        data = _cargar("scenarios/escenario_basico.json")
        data["estado"] = dict(ESTADO_OK)
        data["_editor"] = {"name": "Prueba"}
        r = self.client.post("/api/waves/generate", json=data)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.get_json()["waves"]), 0)


if __name__ == "__main__":
    unittest.main()
