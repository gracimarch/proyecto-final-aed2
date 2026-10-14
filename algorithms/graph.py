"""
algorithms/graph.py

Grafo dirigido o no dirigido con pesos, implementado con lista de adyacencia.

Nodos: cualquier tipo hashable (se usan tuplas (x, y) para representar
       celdas del warehouse).
Aristas: pares de nodos con un peso numérico no negativo.
"""

import heapq
from typing import Any


class Graph:
    """
    Grafo ponderado implementado con lista de adyacencia.

    Puede ser dirigido o no dirigido, según el parámetro ``directed``.
    En el grafo no dirigido, cada arista se almacena en ambas direcciones.

    Atributos internos:
        _adj      (dict[Any, dict[Any, float]]): {nodo: {vecino: peso}}
        _directed (bool): Si True, las aristas son dirigidas.
    """

    def __init__(self, directed: bool = False):
        self._directed = directed
        self._adj: dict[Any, dict[Any, float]] = {}
        self._node_count: int = 0
        self._edge_count: int = 0

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def add_node(self, node: Any) -> None:
        """Agrega un nodo al grafo. No hace nada si ya existe."""
        if node not in self._adj:
            self._adj[node] = {}
            self._node_count += 1

    def add_edge(self, u: Any, v: Any, weight: float = 1.0) -> None:
        """
        Agrega una arista entre u y v con el peso indicado.
        Si la arista ya existe, actualiza su peso.
        En un grafo no dirigido, agrega la arista en ambas direcciones.

        Args:
            u, v   : Nodos extremos de la arista.
            weight : Peso de la arista. Debe ser no negativo.

        Raises:
            ValueError: Si el peso es negativo.
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
        """
        Elimina la arista (u, v) del grafo.
        En un grafo no dirigido, elimina también (v, u).
        No hace nada si la arista no existe.
        """
        if self.has_edge(u, v):
            del self._adj[u][v]
            self._edge_count -= 1
            if not self._directed:
                del self._adj[v][u]

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def has_node(self, node: Any) -> bool:
        """Devuelve True si el nodo existe en el grafo."""
        return node in self._adj

    def has_edge(self, u: Any, v: Any) -> bool:
        """Devuelve True si existe la arista (u, v)."""
        return u in self._adj and v in self._adj[u]

    def weight(self, u: Any, v: Any) -> float:
        """
        Retorna el peso de la arista (u, v).

        Raises:
            KeyError: Si la arista no existe.
        """
        if not self.has_edge(u, v):
            raise KeyError(f"No existe arista entre {u} y {v}.")
        return self._adj[u][v]

    def neighbors(self, node: Any) -> dict:
        """
        Retorna un diccionario {vecino: peso} con los vecinos del nodo.

        Raises:
            KeyError: Si el nodo no existe.
        """
        if node not in self._adj:
            raise KeyError(f"Nodo '{node}' no existe en el grafo.")
        return dict(self._adj[node])

    def nodes(self) -> list:
        """Retorna la lista de todos los nodos del grafo."""
        return list(self._adj.keys())

    def node_count(self) -> int:
        """Retorna la cantidad de nodos."""
        return self._node_count

    def edge_count(self) -> int:
        """Retorna la cantidad de aristas."""
        return self._edge_count

    # ------------------------------------------------------------------
    # Dijkstra
    # ------------------------------------------------------------------

    def dijkstra(self, source: Any) -> tuple:
        """
        Calcula las distancias mínimas desde ``source`` a todos los nodos
        alcanzables, usando el algoritmo de Dijkstra con min-heap.

        Complejidad temporal : O((V + E) log V)
        Complejidad espacial : O(V)

        Args:
            source: Nodo de partida. Debe existir en el grafo.

        Returns:
            (dist, prev) donde:
              dist : dict {nodo: distancia mínima desde source}
              prev : dict {nodo: predecesor en el camino óptimo}
                     (None para source y para nodos no alcanzables)

        Raises:
            KeyError: Si ``source`` no existe en el grafo.
        """
        if not self.has_node(source):
            raise KeyError(f"Nodo fuente '{source}' no existe en el grafo.")

        INF = float("inf")
        dist = {node: INF for node in self._adj}
        prev = {node: None for node in self._adj}
        dist[source] = 0.0

        heap = [(0.0, source)]

        while heap:
            d, u = heapq.heappop(heap)

            if d > dist[u]:
                # Entrada obsoleta: ya existe un camino más corto conocido
                continue

            for v, w in self._adj[u].items():
                alt = dist[u] + w
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u
                    heapq.heappush(heap, (alt, v))

        return dist, prev

    def shortest_path(self, source: Any, target: Any) -> tuple:
        """
        Retorna el camino más corto entre ``source`` y ``target``.

        Args:
            source : Nodo de partida.
            target : Nodo de destino.

        Returns:
            (path, distance) donde:
              path     : lista de nodos del recorrido, incluyendo source y target.
              distance : costo total del camino.
            Si no existe camino, retorna ([], inf).

        Raises:
            KeyError: Si ``source`` o ``target`` no existen en el grafo.
        """
        if not self.has_node(target):
            raise KeyError(f"Nodo destino '{target}' no existe en el grafo.")

        dist, prev = self.dijkstra(source)

        if dist[target] == float("inf"):
            return [], float("inf")

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
        Recorrido en anchura (BFS) desde ``source``.

        Utiliza una lista con puntero de cabeza como cola para evitar
        el costo lineal de ``list.pop(0)``.

        Complejidad temporal : O(V + E)
        Complejidad espacial : O(V)

        Args:
            source: Nodo de partida. Debe existir en el grafo.

        Returns:
            Diccionario {nodo: nivel}, donde nivel es la cantidad de saltos
            desde ``source`` hasta ese nodo.

        Raises:
            KeyError: Si ``source`` no existe en el grafo.
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
        desde cualquier nodo). Para grafos dirigidos, verifica conectividad débil.

        Complejidad: O(V + E).
        """
        if self._node_count == 0:
            return True
        source = next(iter(self._adj))
        return len(self.bfs(source)) == self._node_count

    def reachable_from(self, source: Any) -> set:
        """
        Retorna el conjunto de nodos alcanzables desde ``source``.

        Args:
            source: Nodo de partida. Debe existir en el grafo.
        """
        return set(self.bfs(source).keys())

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serializa el grafo a un diccionario para persistencia.

        Las tuplas de nodo se convierten a listas para compatibilidad JSON.

        Returns:
            Diccionario con las claves 'directed' y 'edges'.
        """
        edges = []
        seen = set()
        for u, neighbors in self._adj.items():
            for v, w in neighbors.items():
                key = (min(str(u), str(v)), max(str(u), str(v)))
                if self._directed or key not in seen:
                    edges.append({
                        "u": list(u) if isinstance(u, tuple) else u,
                        "v": list(v) if isinstance(v, tuple) else v,
                        "weight": w,
                    })
                    seen.add(key)
        return {
            "directed": self._directed,
            "edges": edges,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        """
        Reconstruye un grafo desde un diccionario serializado por ``to_dict``.

        Args:
            data: Diccionario con las claves 'directed' y 'edges'.
        """
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
