import unittest

from algorithms.graph_builder import generate_graph
from algorithms.routing import validate_reachability
from models.generator import generate_scenario
from models.warehouse import Warehouse


class TestScenarioGenerator(unittest.TestCase):
    """Pruebas del generador procedural de escenarios (consigna §16)."""

    def _validar(self, resultado, **esperado):
        scenario = resultado["scenario"]
        wh = Warehouse.from_dict(scenario)

        self.assertEqual(len(wh.racks), esperado["cantidad_racks"])
        self.assertEqual(len(wh.products), esperado["cantidad_productos"])
        self.assertEqual(len(scenario["pedidos"]), esperado["cantidad_pedidos"])

        # El generador NO declara pasillos: todos los pasillos quedan AMBOS
        # hasta que el usuario los defina manualmente.
        self.assertEqual(len(wh.aisles), 0)
        self.assertEqual(scenario["warehouse"]["pasillos"], [])

        # Todos los racks tienen un lado = 2 (Warehouse.add_rack ya lo exige).
        for rack in wh.racks.values():
            self.assertTrue(rack.ancho == 2 or rack.alto == 2)

        # Puertas en el borde y con zona de despacho asociada.
        for door in wh.doors:
            x, y = door.position
            self.assertTrue(
                x == 0 or x == wh.ancho_x - 1 or y == 0 or y == wh.largo_y - 1
            )
            self.assertTrue(
                any(z.puerta_id == door.door_id for z in wh.dispatch_zones)
            )

        # Todos los productos están dentro de su rack.
        for product in wh.products.values():
            rack = wh.get_rack(product.rack_id)
            self.assertTrue(rack.contains_cell(product.x, product.y))

        # Todos los productos son alcanzables ida y vuelta desde la zona.
        graph = generate_graph(wh)
        validate_reachability(wh, graph)

        self.assertTrue(resultado["meta"]["validacion"]["ok"])

    def test_generacion_basica(self):
        resultado = generate_scenario(
            cantidad_racks=12,
            cantidad_pasillos=5,
            cantidad_productos=40,
            cantidad_pedidos=15,
            max_productos_por_pedido=3,
            wave_max_pedidos=4,
            semilla=42,
        )
        self._validar(
            resultado,
            cantidad_racks=12,
            cantidad_productos=40,
            cantidad_pedidos=15,
        )
        # La orientación por defecto es vertical.
        self.assertEqual(resultado["meta"]["orientacion_racks"], "vertical")
        self.assertEqual(resultado["meta"]["racks_horizontales"], 0)
        self.assertEqual(resultado["meta"]["racks_verticales"], 12)
        self.assertFalse(resultado["meta"]["dimensiones_fijas"])

    def test_generacion_minima(self):
        resultado = generate_scenario(
            cantidad_racks=1,
            cantidad_pasillos=1,
            cantidad_productos=1,
            cantidad_pedidos=1,
            max_productos_por_pedido=1,
            wave_max_pedidos=1,
            cantidad_puertas=1,
            cantidad_pickers=1,
            semilla=1,
        )
        self._validar(
            resultado,
            cantidad_racks=1,
            cantidad_productos=1,
            cantidad_pedidos=1,
        )

    def test_distribuciones_y_muchos_pasillos(self):
        for distribucion in ("uniforme", "aleatoria", "concentrada"):
            with self.subTest(distribucion=distribucion):
                resultado = generate_scenario(
                    cantidad_racks=8,
                    cantidad_pasillos=5,
                    cantidad_productos=100,
                    cantidad_pedidos=30,
                    max_productos_por_pedido=5,
                    wave_max_pedidos=4,
                    distribucion_productos=distribucion,
                    cantidad_puertas=3,
                    cantidad_pickers=4,
                    semilla=7,
                )
                self._validar(
                    resultado,
                    cantidad_racks=8,
                    cantidad_productos=100,
                    cantidad_pedidos=30,
                )

    def test_orientacion_vertical_explicita(self):
        resultado = generate_scenario(
            cantidad_racks=10,
            cantidad_pasillos=4,
            cantidad_productos=30,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="vertical",
            semilla=21,
        )
        self._validar(
            resultado,
            cantidad_racks=10,
            cantidad_productos=30,
            cantidad_pedidos=10,
        )
        self.assertEqual(resultado["meta"]["orientacion_racks"], "vertical")
        for rack in resultado["scenario"]["warehouse"]["racks"]:
            self.assertEqual(rack["ancho"], 2)
            self.assertGreater(rack["alto"], 2)

    def test_orientacion_horizontal_explicita(self):
        resultado = generate_scenario(
            cantidad_racks=10,
            cantidad_pasillos=4,
            cantidad_productos=30,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="horizontal",
            semilla=22,
        )
        self._validar(
            resultado,
            cantidad_racks=10,
            cantidad_productos=30,
            cantidad_pedidos=10,
        )
        self.assertEqual(resultado["meta"]["orientacion_racks"], "horizontal")
        for rack in resultado["scenario"]["warehouse"]["racks"]:
            self.assertEqual(rack["alto"], 2)
            self.assertGreater(rack["ancho"], 2)

    def test_orientacion_aleatoria_mezcla_ambas(self):
        resultado = generate_scenario(
            cantidad_racks=20,
            cantidad_pasillos=4,
            cantidad_productos=60,
            cantidad_pedidos=15,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="aleatorio",
            semilla=5,
        )
        self._validar(
            resultado,
            cantidad_racks=20,
            cantidad_productos=60,
            cantidad_pedidos=15,
        )
        meta = resultado["meta"]
        self.assertEqual(meta["orientacion_racks"], "aleatorio")
        self.assertGreater(meta["racks_verticales"], 0)
        self.assertGreater(meta["racks_horizontales"], 0)
        self.assertEqual(
            meta["racks_verticales"] + meta["racks_horizontales"], 20
        )

        # Cada rack respeta una de las dos formas permitidas.
        for rack in resultado["scenario"]["warehouse"]["racks"]:
            self.assertTrue(
                (rack["ancho"] == 2 and rack["alto"] > 2)
                or (rack["alto"] == 2 and rack["ancho"] > 2)
            )

    def test_dimensiones_fijas_se_respetan(self):
        resultado = generate_scenario(
            cantidad_racks=12,
            cantidad_pasillos=5,
            cantidad_productos=40,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="vertical",
            ancho_x=30,
            largo_y=22,
            semilla=31,
        )
        self._validar(
            resultado,
            cantidad_racks=12,
            cantidad_productos=40,
            cantidad_pedidos=10,
        )
        dims = resultado["scenario"]["warehouse"]["dimensiones"]
        self.assertEqual(dims["ancho_x"], 30)
        self.assertEqual(dims["largo_y"], 22)
        self.assertTrue(resultado["meta"]["dimensiones_fijas"])

    def test_dimensiones_ajustadas_reducen_el_largo_del_rack(self):
        resultado = generate_scenario(
            cantidad_racks=6,
            cantidad_pasillos=1,
            cantidad_productos=40,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="vertical",
            ancho_x=20,
            largo_y=19,
            semilla=42,
        )
        self._validar(
            resultado,
            cantidad_racks=6,
            cantidad_productos=40,
            cantidad_pedidos=10,
        )
        meta = resultado["meta"]
        self.assertEqual(
            (meta["dimensiones"]["ancho_x"], meta["dimensiones"]["largo_y"]),
            (20, 19),
        )
        # No entraba con el largo preferido (4): se reduce automáticamente.
        self.assertLess(meta["largo_rack"], meta["largo_rack_preferido"])
        self.assertGreaterEqual(meta["largo_rack"], 2)
        # Con dimensiones fijas cada rack vertical tiene alto <= largo_rack.
        for rack in resultado["scenario"]["warehouse"]["racks"]:
            if rack["ancho"] == 2:  # rack vertical
                self.assertLessEqual(rack["alto"], meta["largo_rack_preferido"])
                self.assertGreaterEqual(rack["alto"], 2)

    def test_metadata_de_layout(self):
        resultado = generate_scenario(
            cantidad_racks=12,
            cantidad_pasillos=2,
            cantidad_productos=40,
            cantidad_pedidos=15,
            max_productos_por_pedido=3,
            wave_max_pedidos=4,
            semilla=42,
        )
        meta = resultado["meta"]
        self.assertIn("largo_rack", meta)
        self.assertIn("largo_rack_preferido", meta)
        self.assertEqual(meta["largo_rack"], meta["largo_rack_preferido"])
        self.assertGreaterEqual(meta["ancho_pasillo"], 1)
        self.assertLessEqual(meta["ancho_pasillo"], 5)
        self.assertGreater(meta["grilla"]["columnas"], 0)
        self.assertGreater(meta["grilla"]["filas"], 0)
        self.assertGreater(meta["pasillos_totales"], 0)

    def test_dimensiones_fijas_con_orientacion_aleatoria(self):
        resultado = generate_scenario(
            cantidad_racks=16,
            cantidad_pasillos=4,
            cantidad_productos=50,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="aleatorio",
            ancho_x=40,
            largo_y=35,
            semilla=32,
        )
        self._validar(
            resultado,
            cantidad_racks=16,
            cantidad_productos=50,
            cantidad_pedidos=10,
        )
        dims = resultado["scenario"]["warehouse"]["dimensiones"]
        self.assertEqual((dims["ancho_x"], dims["largo_y"]), (40, 35))

    def test_dimensiones_demasiado_chicas(self):
        with self.assertRaises(ValueError):
            generate_scenario(
                cantidad_racks=20,
                cantidad_pasillos=4,
                cantidad_productos=40,
                cantidad_pedidos=5,
                max_productos_por_pedido=3,
                wave_max_pedidos=3,
                orientacion_racks="vertical",
                ancho_x=8,
                largo_y=8,
                semilla=33,
            )

    def test_semilla_reproducible(self):
        params = dict(
            cantidad_racks=6,
            cantidad_pasillos=4,
            cantidad_productos=25,
            cantidad_pedidos=10,
            max_productos_por_pedido=3,
            wave_max_pedidos=3,
            orientacion_racks="aleatorio",
            semilla=1234,
        )
        a = generate_scenario(**params)
        b = generate_scenario(**params)
        self.assertEqual(a["scenario"], b["scenario"])

    def test_parametros_invalidos(self):
        with self.assertRaises(ValueError):
            generate_scenario(cantidad_racks=0)
        with self.assertRaises(ValueError):
            generate_scenario(cantidad_pasillos=0)
        with self.assertRaises(ValueError):
            generate_scenario(cantidad_productos=0)
        with self.assertRaises(ValueError):
            generate_scenario(cantidad_pedidos=0)
        with self.assertRaises(ValueError):
            generate_scenario(max_productos_por_pedido=0)
        with self.assertRaises(ValueError):
            generate_scenario(wave_max_pedidos=0)
        with self.assertRaises(ValueError):
            generate_scenario(distribucion_productos="inexistente")
        with self.assertRaises(ValueError):
            generate_scenario(orientacion_racks="inexistente")
        with self.assertRaises(ValueError):
            generate_scenario(ancho_x=0)
        with self.assertRaises(ValueError):
            generate_scenario(largo_y=-3)


if __name__ == "__main__":
    unittest.main()
