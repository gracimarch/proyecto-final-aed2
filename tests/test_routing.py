import copy
import json
import unittest

from algorithms.graph_builder import generate_graph
from algorithms.pathfinding import pickup_cells
from algorithms.routing import (
    compare_all_combinations,
    plan_route,
    validate_reachability,
)
from models.warehouse import Warehouse
from models.wave_manager import WaveManager


class TestRouting(unittest.TestCase):
    """Pruebas unitarias para el cálculo de rutas (BFS / A*), heurística y validación de alcanzabilidad."""

    def setUp(self):
        with open("scenarios/escenario_basico.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.wh = Warehouse.from_dict(self.data)
        self.graph = generate_graph(self.wh)
        self.wm = WaveManager.from_dict(self.data, self.wh)
        self.waves = self.wm.generate_waves()
        self.wave = self.waves[0]

    def test_pickup_cells_vertical_and_horizontal(self):
        # En escenario_basico.json, R1 es vertical (x=3..4, y=5..10, ancho=2, alto=6)
        # P001 está en (3, 5) -> cara izquierda -> se recoge desde (2, 5)
        p1 = self.wh.products["P001"]
        celdas1 = pickup_cells(p1, self.wh, self.graph)
        self.assertIn((2, 5), celdas1)

        # P003 está en (4, 7) -> cara derecha -> se recoge desde (5, 7)
        p3 = self.wh.products["P003"]
        celdas3 = pickup_cells(p3, self.wh, self.graph)
        self.assertIn((5, 7), celdas3)

    def test_pickup_cells_en_esquina_usa_vecina_perpendicular(self):
        # RACK01 es 2x1 y está pegado a la pared derecha. Sus productos en la
        # columna derecha (11,5) no pueden recogerse desde (12,5) porque está
        # fuera del warehouse, pero sí desde el pasillo (11,4) de abajo.
        with open("scenarios/escenario_racks_esquinas.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        wh = Warehouse.from_dict(data)
        graph = generate_graph(wh)

        for product_id in ("PRD002", "PRD004"):
            product = wh.products[product_id]
            self.assertEqual(set(pickup_cells(product, wh, graph)), {(11, 4)})

        # El escenario completo debe poder validarse y generar waves.
        validate_reachability(wh, graph)
        wm = WaveManager.from_dict(data, wh)
        self.assertGreater(len(wm.generate_waves()), 0)

    def test_pickup_cells_rack_horizontal_en_borde_superior(self):
        # Rack 1x2 apoyado en el borde superior. El producto de la fila de
        # arriba (3,5) solo tiene vecinas laterales: (2,5) y (4,5).
        data = {
            "warehouse": {
                "dimensiones": {"ancho_x": 6, "largo_y": 6},
                "puertas": [
                    {"id": "D1", "tipo": "AMBOS", "ubicacion": {"x": 0, "y": 0}}
                ],
                "zonas_despacho": [
                    {
                        "id": "Z1",
                        "puerta_id": "D1",
                        "ubicacion": {"x": 1, "y": 0},
                        "ancho": 2,
                        "alto": 2,
                        "peso_max_kg": 100,
                    }
                ],
                "racks": [
                    {"id": "R1", "ubicacion": {"x": 3, "y": 4}, "ancho": 1, "alto": 2}
                ],
                "pasillos": [],
            },
            "pickers": [
                {
                    "id": "P1",
                    "posicion_inicial": {"x": 0, "y": 2},
                    "capacidad_carga_kg": 100,
                }
            ],
            "productos": [
                {
                    "id": "X1",
                    "nombre": "Producto X",
                    "rack_id": "R1",
                    "ubicacion": {"x": 3, "y": 5, "z": 1},
                    "cantidad_disponible": 5,
                    "peso_kg": 1,
                }
            ],
            "pedidos": [
                {
                    "id": "O1",
                    "prioridad": 1,
                    "estado": "PENDIENTE",
                    "items": [{"producto_id": "X1", "cantidad": 1}],
                }
            ],
        }

        wh = Warehouse.from_dict(data)
        graph = generate_graph(wh)

        self.assertEqual(
            set(pickup_cells(wh.products["X1"], wh, graph)), {(2, 5), (4, 5)}
        )

        validate_reachability(wh, graph)
        wm = WaveManager.from_dict(data, wh)
        self.assertGreater(len(wm.generate_waves()), 0)

    def test_plan_route_valid_path_continuity(self):
        combos = [
            ("cercania", "bfs"),
            ("cercania", "astar"),
            ("orden", "bfs"),
            ("orden", "astar"),
        ]

        for est, bus in combos:
            with self.subTest(estrategia=est, buscador=bus):
                res = plan_route(self.wave, self.wh, self.graph, estrategia=est, buscador=bus)

                # El camino debe tener al menos 2 celdas
                self.assertGreater(len(res.path), 1)

                # Continuidad: cada paso adyacente debe ser una arista válida del grafo
                for i in range(len(res.path) - 1):
                    u = tuple(res.path[i])
                    v = tuple(res.path[i + 1])
                    self.assertTrue(
                        self.graph.has_edge(u, v),
                        f"Paso inválido {u} -> {v} para {est}/{bus}",
                    )

                # Métricas deben estar presentes y ser consistentes
                m = res.metrics()
                self.assertEqual(m["distancia_total"], len(res.path) - 1)
                self.assertEqual(m["distancia_total"], m["aristas_recorridas"])
                self.assertGreater(m["nodos_visitados"], 0)
                self.assertGreater(m["nodos_expandidos"], 0)
                self.assertGreaterEqual(m["tiempo_ms"], 0.0)

                # La ruta debe recoger todos los productos pedidos en la wave
                recogidos = set()
                for _, prods in res.paradas:
                    for p_id in prods:
                        recogidos.add(p_id)

                for item in self.wave.get_items():
                    self.assertIn(item.product.product_id, recogidos)

    def test_compare_all_combinations(self):
        resultados = compare_all_combinations(self.wave, self.wh, self.graph)
        self.assertEqual(len(resultados), 4)

        estrategias = {r.estrategia for r in resultados}
        buscadores = {r.buscador for r in resultados}
        self.assertEqual(estrategias, {"cercania", "orden"})
        self.assertEqual(buscadores, {"bfs", "astar"})

    def test_validate_reachability_basic_scenario(self):
        # En escenario_basico.json todos los productos deben ser alcanzables
        try:
            validate_reachability(self.wh, self.graph)
        except ValueError as e:
            self.fail(f"validate_reachability falló inesperadamente: {e}")

    def test_tiempo_estimado_suma_la_altura(self):
        res = plan_route(self.wave, self.wh, self.graph, "cercania", "bfs")
        # En cada parada: 1 tick base + costo_altura del producto más alto.
        esperado = 0
        for _, product_ids in res.paradas:
            mayor = 0
            for p_id in product_ids:
                altura = self.wh.products[p_id].costo_altura()
                if altura > mayor:
                    mayor = altura
            esperado = esperado + 1 + mayor
        m = res.metrics()
        self.assertEqual(m["tiempo_recogida"], esperado)
        self.assertEqual(m["tiempo_estimado"], m["distancia_total"] + esperado)

    def test_cercania_no_deja_atras_una_parada_en_pasillo_de_un_sentido(self):
        """
        Con un solo picker, P005 (10,9) y P006 (12,8) quedan en el mismo
        pasillo de sentido N. El vecino más cercano elegía P005 por 1 paso
        (10 contra 11) y después no podía volver a P006 sin dar la vuelta
        completa (21 pasos). La regla de no dejar paradas atrás debe visitar
        P006 primero y bajar el recorrido de 64 a 48 pasos.
        """
        data = copy.deepcopy(self.data)
        data["pickers"] = [p for p in data["pickers"] if p["id"] == "PK_01"]

        wh = Warehouse.from_dict(data)
        wm = WaveManager.from_dict(data, wh)
        wm.generate_waves(estrategia_wave="por_cercania")
        wm.assign_pickers()
        wave = wm.get_waves()[0]

        res = plan_route(wave, wh, wm.graph, "cercania", "bfs", inicio=(1, 3))
        productos = [p_id for _, p_ids in res.paradas for p_id in p_ids]

        self.assertLess(productos.index("P006"), productos.index("P005"))
        self.assertEqual(res.distancia_total, 48)

    def test_orden_no_aplica_la_regla_de_pasillo(self):
        # La estrategia "orden" mantiene el orden de los pedidos: no se toca.
        res = plan_route(self.wave, self.wh, self.graph, "orden", "bfs", inicio=(1, 3))
        self.assertEqual(res.estrategia, "orden")
        self.assertGreater(res.distancia_total, 0)


if __name__ == "__main__":
    unittest.main()

