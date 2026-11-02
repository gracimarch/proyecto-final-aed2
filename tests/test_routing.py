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


if __name__ == "__main__":
    unittest.main()

