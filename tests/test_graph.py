import unittest

from algorithms.graph import (
    Graph,
    bfs_distances,
    bfs_to_any,
    astar_to_any,
)
from algorithms.pathfinding import manhattan
from algorithms.routing import reverse_graph, graph_without


class TestGraph(unittest.TestCase):
    """Pruebas unitarias para la estructura de datos Graph y sus algoritmos de búsqueda."""

    def test_add_node_and_counts(self):
        g = Graph(directed=True)
        g.add_node((0, 0))
        g.add_node((0, 1))
        # Nodo duplicado no incrementa el contador
        g.add_node((0, 0))

        self.assertEqual(g.node_count(), 2)
        self.assertTrue(g.has_node((0, 0)))
        self.assertTrue(g.has_node((0, 1)))
        self.assertFalse(g.has_node((1, 1)))

    def test_directed_vs_undirected_edges(self):
        # Grafo dirigido
        gd = Graph(directed=True)
        gd.add_edge("A", "B", 2.5)
        self.assertTrue(gd.has_edge("A", "B"))
        self.assertFalse(gd.has_edge("B", "A"))
        self.assertEqual(gd.weight("A", "B"), 2.5)
        self.assertEqual(gd.edge_count(), 1)

        # Grafo no dirigido
        gu = Graph(directed=False)
        gu.add_edge("A", "B", 3.0)
        self.assertTrue(gu.has_edge("A", "B"))
        self.assertTrue(gu.has_edge("B", "A"))
        self.assertEqual(gu.weight("B", "A"), 3.0)

    def test_negative_weight_raises(self):
        g = Graph(directed=True)
        with self.assertRaises(ValueError):
            g.add_edge("A", "B", -1.0)

    def test_remove_edge(self):
        g = Graph(directed=True)
        g.add_edge("A", "B", 1.0)
        self.assertTrue(g.has_edge("A", "B"))
        g.remove_edge("A", "B")
        self.assertFalse(g.has_edge("A", "B"))
        self.assertEqual(g.edge_count(), 0)

    def test_neighbors(self):
        g = Graph(directed=True)
        g.add_edge("A", "B", 1.0)
        g.add_edge("A", "C", 2.0)
        vecinos = g.neighbors("A")
        self.assertEqual(vecinos, {"B": 1.0, "C": 2.0})

    def test_bfs_to_any_simple_path(self):
        # A -> B -> C -> D
        g = Graph(directed=True)
        g.add_edge("A", "B", 1.0)
        g.add_edge("B", "C", 1.0)
        g.add_edge("C", "D", 1.0)

        stats = {"nodos_expandidos": 0}
        path, dist, reached = bfs_to_any(g, "A", {"D"}, stats)
        self.assertEqual(path, ["A", "B", "C", "D"])
        self.assertEqual(dist, 3)
        self.assertEqual(reached, "D")
        self.assertGreater(stats["nodos_expandidos"], 0)

    def test_bfs_to_any_multiple_targets_finds_closest(self):
        # A -> B (dist 1)
        # A -> C -> D (dist 2)
        g = Graph(directed=True)
        g.add_edge("A", "B", 1.0)
        g.add_edge("A", "C", 1.0)
        g.add_edge("C", "D", 1.0)

        path, dist, reached = bfs_to_any(g, "A", {"B", "D"})
        self.assertEqual(reached, "B")
        self.assertEqual(path, ["A", "B"])
        self.assertEqual(dist, 1)

    def test_bfs_to_unreachable_target(self):
        g = Graph(directed=True)
        g.add_node("A")
        g.add_node("B")
        path, dist, reached = bfs_to_any(g, "A", {"B"})
        self.assertEqual(path, [])
        self.assertEqual(dist, float("inf"))
        self.assertIsNone(reached)

    def test_bfs_distances(self):
        # Grafo lineal: 0 -> 1 -> 2 -> 3
        g = Graph(directed=True)
        for i in range(3):
            g.add_edge(i, i + 1, 1.0)

        distancias = bfs_distances(g, {0})
        self.assertEqual(distancias[0], 0)
        self.assertEqual(distancias[1], 1)
        self.assertEqual(distancias[2], 2)
        self.assertEqual(distancias[3], 3)

    def test_astar_to_any_matches_bfs_shortest_path(self):
        # Grilla 4x4
        g = Graph(directed=True)
        for x in range(4):
            for y in range(4):
                if x + 1 < 4:
                    g.add_edge((x, y), (x + 1, y), 1.0)
                    g.add_edge((x + 1, y), (x, y), 1.0)
                if y + 1 < 4:
                    g.add_edge((x, y), (x, y + 1), 1.0)
                    g.add_edge((x, y + 1), (x, y), 1.0)

        start = (0, 0)
        target = (3, 3)

        path_bfs, dist_bfs, reached_bfs = bfs_to_any(g, start, {target})
        path_astar, dist_astar, reached_astar = astar_to_any(g, start, {target}, manhattan)

        self.assertEqual(dist_bfs, dist_astar)
        self.assertEqual(reached_bfs, target)
        self.assertEqual(reached_astar, target)
        self.assertEqual(len(path_bfs), len(path_astar))

    def test_reverse_graph(self):
        g = Graph(directed=True)
        g.add_edge((1, 1), (1, 2), 1.0)
        g.add_edge((1, 2), (2, 2), 2.0)

        rev = reverse_graph(g)
        self.assertTrue(rev.has_edge((1, 2), (1, 1)))
        self.assertTrue(rev.has_edge((2, 2), (1, 2)))
        self.assertFalse(rev.has_edge((1, 1), (1, 2)))
        self.assertEqual(rev.weight((1, 2), (1, 1)), 1.0)

    def test_graph_without_obstacles(self):
        # Grafo 1 -> 2 -> 3
        g = Graph(directed=True)
        g.add_edge(1, 2, 1.0)
        g.add_edge(2, 3, 1.0)
        g.add_edge(1, 4, 1.0)
        g.add_edge(4, 3, 1.0)

        # Quitar nodo 2 (obstáculo)
        gw = graph_without(g, {2})
        self.assertFalse(gw.has_node(2))
        self.assertFalse(gw.has_edge(1, 2))
        self.assertFalse(gw.has_edge(2, 3))

        path, dist, reached = bfs_to_any(gw, 1, {3})
        self.assertEqual(path, [1, 4, 3])
        self.assertEqual(dist, 2)


if __name__ == "__main__":
    unittest.main()

