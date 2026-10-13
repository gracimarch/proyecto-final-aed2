"""
algorithms/graph.py

Implementación propia de un grafo no dirigido con pesos
usando lista de adyacencia.

Nodos: cualquier tipo hashable (se usan tuplas (x, y) para
       representar posiciones en el warehouse).
Aristas: pares de nodos con un peso numérico (distancia del pasillo).

Algoritmos incluidos:
    - Dijkstra  → camino mínimo entre dos nodos   O((V+E) log V)
    - BFS       → recorrido en anchura             O(V+E)
"""

import heapq
from typing import Any


class Graph:
    """
    Grafo no dirigido ponderado implementado con lista de adyacencia.

    Atributos internos:
        _adj  (dict[Any, dict[Any, float]]): {nodo: {vecino: peso}}
        _directed (bool): Si es True, las aristas son dirigidas.
    """

    def __init__(self, directed: bool = False):
        self._directed = directed
        self._adj: dict[Any, dict[Any, float]] = {}
        self._node_count: int = 0
        self._edge_count: int = 0

    # ------------------------------------------------------------------
    # Construcción del grafo
    # ------------------------------------------------------------------

    def add_node(self, node: Any) -> None:
        """Agrega un nodo. No hace nada si ya existe."""
        if node not in self._adj:
            self._adj[node] = {}
            self._node_count += 1

    def add_edge(self, u: Any, v: Any, weight: float = 1.0) -> None:
        """
        Agrega una arista entre u y v con el peso dado.
        Si el grafo es no dirigido, agrega en ambas direcciones.
        Si la arista ya existe, actualiza su peso.
        """
        if weight < 0:
            raise ValueError(f"El peso de una arista no puede ser negativo: {weight}")
        self.add_node(u)
        self.add_node(v)

        if v not in self._adj[u]:
            self._edge_count += 1

        self._adj[u][v] = weight
        if not self._directed:
            self._adj[v][u] = weight

    def remove_edge(self, u: Any, v: Any) -> None:
        """Elimina la arista entre u y v."""
        if self.has_edge(u, v):
            del self._adj[u][v]
            self._edge_count -= 1
            if not self._directed:
                del self._adj[v][u]

    # ------------------------------------------------------------------
    # Consultas básicas
    # ------------------------------------------------------------------

    def has_node(self, node: Any) -> bool:
        return node in self._adj

    def has_edge(self, u: Any, v: Any) -> bool:
        return u in self._adj and v in self._adj[u]

    def weight(self, u: Any, v: Any) -> float:
        """Retorna el peso de la arista (u, v). Lanza KeyError si no existe."""
        if not self.has_edge(u, v):
            raise KeyError(f"No existe arista entre {u} y {v}.")
        return self._adj[u][v]

    def neighbors(self, node: Any) -> dict:
        """Retorna {vecino: peso} del nodo. Lanza KeyError si no existe."""
        if node not in self._adj:
            raise KeyError(f"Nodo '{node}' no existe en el grafo.")
        return dict(self._adj[node])

    def nodes(self) -> list:
        """Lista de todos los nodos."""
        return list(self._adj.keys())

    def node_count(self) -> int:
        return self._node_count

    def edge_count(self) -> int:
        return self._edge_count

    # ------------------------------------------------------------------
    # Dijkstra
    # ------------------------------------------------------------------

    def dijkstra(self, source: Any) -> tuple:
        """
        Algoritmo de Dijkstra desde un nodo fuente.

        Utiliza un min-heap (heapq de la stdlib de Python) para
        extraer eficientemente el nodo con menor distancia acumulada.

        Complejidad temporal : O((V + E) log V)
        Complejidad espacial : O(V)

        Mejor caso  : O(V log V) — grafo disperso, source conectado a pocos nodos.
        Peor caso   : O((V + E) log V) — grafo denso.

        Args:
            source: Nodo de partida.

        Returns:
            (dist, prev)
            dist : dict {nodo: distancia mínima desde source}
            prev : dict {nodo: nodo anterior en el camino óptimo}
                   (None si el nodo no es alcanzable o es el source)
        """
        if not self.has_node(source):
            raise KeyError(f"Nodo fuente '{source}' no existe en el grafo.")

        INF = float("inf")
        dist = {node: INF for node in self._adj}
        prev = {node: None for node in self._adj}
        dist[source] = 0.0

        # heap de (distancia_acumulada, nodo)
        heap = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)

            # Entrada obsoleta (ya encontramos un camino mejor antes)
            if d > dist[u]:
                continue

            for v, weight in self._adj[u].items():
                alt = dist[u] + weight
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u
                    heapq.heappush(heap, (alt, v))

        return dist, prev

    def shortest_path(self, source: Any, target: Any) -> tuple:
        """
        Camino más corto entre source y target usando Dijkstra.

        Returns:
            (path, distance)
            path     : lista de nodos del recorrido (incluye source y target).
            distance : costo total del camino.
            Si no hay camino: ([], inf).
        """
        dist, prev = self.dijkstra(source)

        if dist[target] == float("inf"):
            return [], float("inf")

        # Reconstruir el camino recorriendo los predecesores
        path = []
        current = target
        while current is not None:
            path.append(current)
            current = prev[current]
        path.reverse()

        return path, dist[target]

    # ------------------------------------------------------------------
    # BFS
    # ------------------------------------------------------------------

    def bfs(self, source: Any) -> dict:
        """
        Recorrido BFS desde source.

        Implementado con lista + puntero de cabeza para simular
        una cola en O(1) por operación, sin imports adicionales.

        Complejidad temporal : O(V + E)
        Complejidad espacial : O(V)

        Returns:
            {nodo: nivel} — nivel = distancia en cantidad de saltos desde source.
        """
        if not self.has_node(source):
            raise KeyError(f"Nodo fuente '{source}' no existe en el grafo.")

        visited = {source: 0}
        queue = [source]
        head = 0

        while head < len(queue):
            u = queue[head]
            head += 1

            for v in self._adj[u]:
                if v not in visited:
                    visited[v] = visited[u] + 1
                    queue.append(v)

        return visited

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    def is_connected(self) -> bool:
        """
        Verifica si el grafo es conexo (todos los nodos son alcanzables
        desde cualquier nodo). Complejidad: O(V + E).
        """
        if self._node_count == 0:
            return True
        source = next(iter(self._adj))
        return len(self.bfs(source)) == self._node_count

    def reachable_from(self, source: Any) -> set:
        """Retorna el conjunto de nodos alcanzables desde source."""
        return set(self.bfs(source).keys())

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa el grafo a diccionario para persistencia JSON."""
        edges = []
        seen = set()
        for u, neighbors in self._adj.items():
            for v, w in neighbors.items():
                key = (min(str(u), str(v)), max(str(u), str(v)))
                if self._directed or key not in seen:
                    edges.append({"u": list(u) if isinstance(u, tuple) else u,
                                  "v": list(v) if isinstance(v, tuple) else v,
                                  "weight": w})
                    seen.add(key)
        return {
            "directed": self._directed,
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        """Reconstruye un grafo desde un diccionario serializado."""
        g = cls(directed=data.get("directed", False))
        for edge in data.get("edges", []):
            u = tuple(edge["u"]) if isinstance(edge["u"], list) else edge["u"]
            v = tuple(edge["v"]) if isinstance(edge["v"], list) else edge["v"]
            g.add_edge(u, v, edge.get("weight", 1.0))
        return g

    def __repr__(self) -> str:
        return (
            f"Graph(nodes={self._node_count}, edges={self._edge_count}, "
            f"directed={self._directed})"
        )
