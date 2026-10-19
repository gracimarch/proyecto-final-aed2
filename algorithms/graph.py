"""
algorithms/graph.py

Grafo dirigido o no dirigido con pesos, implementado con lista de adyacencia.

Nodos: cualquier tipo hashable (se usan tuplas (x, y) para representar
       celdas del warehouse).
Aristas: pares de nodos con un peso numérico no negativo.
"""

import heapq
from collections import deque


class Graph:
    """
    Grafo ponderado implementado con lista de adyacencia.

    Puede ser dirigido o no dirigido, según el parámetro ``directed``.
    En el grafo no dirigido, cada arista se almacena en ambas direcciones.

    Atributos internos:
        _adj      (dict[object, dict[object, float]]): {nodo: {vecino: peso}}
        _directed (bool): Si True, las aristas son dirigidas.
    """

    def __init__(self, directed: bool = False):
        self._directed = directed
        self._adj: dict[object, dict[object, float]] = {}
        self._node_count: int = 0
        self._edge_count: int = 0

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def add_node(self, node: object) -> None:
        """Agrega un nodo al grafo. No hace nada si ya existe."""
        if node not in self._adj:
            self._adj[node] = {}
            self._node_count += 1

    def add_edge(self, u: object, v: object, weight: float = 1.0) -> None:
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

    def remove_edge(self, u: object, v: object) -> None:
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

    def has_node(self, node: object) -> bool:
        """Devuelve True si el nodo existe en el grafo."""
        return node in self._adj

    def has_edge(self, u: object, v: object) -> bool:
        """Devuelve True si existe la arista (u, v)."""
        return u in self._adj and v in self._adj[u]

    def weight(self, u: object, v: object) -> float:
        """
        Retorna el peso de la arista (u, v).

        Raises:
            KeyError: Si la arista no existe.
        """
        if not self.has_edge(u, v):
            raise KeyError(f"No existe arista entre {u} y {v}.")
        return self._adj[u][v]

    def neighbors(self, node: object) -> dict:
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
    # BFS
    # ------------------------------------------------------------------

    def bfs(self, source: object) -> dict:
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
        Verifica si el grafo es conexo. Para grafos dirigidos, verifica
        conectividad débil: ignora el sentido de las aristas para comprobar
        que todos los nodos pertenecen a una misma componente.

        Complejidad: O(V + E).
        """
        if self._node_count == 0:
            return True
        source = next(iter(self._adj))
        if not self._directed:
            return len(self.bfs(source)) == self._node_count

        # Construir vecinos en ambos sentidos sin modificar el grafo original.
        neighbors = {node: set() for node in self._adj}
        for u in self._adj:
            for v in self._adj[u]:
                neighbors[u].add(v)
                neighbors[v].add(u)

        visited = {source}
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v in neighbors[u]:
                if v not in visited:
                    visited.add(v)
                    queue.append(v)

        return len(visited) == self._node_count

    def reachable_from(self, source: object) -> set:
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


# ===========================================================================
# 1. Reconstrucción de camino
# ===========================================================================

def _reconstruct(
    prev: dict[object, object | None],
    target: object,
) -> tuple[list[object], int]:

    path: list[object] = []

    node: object = target

    while True:
        path.append(node)
        if prev[node] == node:
            break
        node = prev[node]

    path.reverse()

    return path, len(path) - 1


# ===========================================================================
# 2. BFS hacia uno o varios destinos
# ===========================================================================

def bfs_to_any(
    graph: Graph,
    source: object,
    targets: set[object],
) -> tuple[
    list[object],
    float,
    object | None,
]:
    """
    Ejecuta BFS desde source hasta cualquiera de los nodos de targets.

    Minimiza la cantidad de aristas; ignora sus pesos.
    Retorna (camino, saltos, destino), o ([], inf, None) si no llega.
    Los destinos ausentes del grafo se consideran inalcanzables.
    """

    if not graph.has_node(source):
        raise KeyError(
            f"Nodo origen {source} no existe en el grafo."
        )

    # Caso trivial:
    # el origen ya es uno de los destinos.
    if source in targets:
        return [source], 0, source

    # prev también funciona como conjunto de visitados.
    prev: dict[
        object,
        object | None
    ] = {
        source: source
    }

    queue: deque[object] = deque([source])

    while queue:

        u = queue.popleft()

        # Usamos la interfaz pública de Graph.
        # neighbors(u) devuelve {vecino: peso}.
        # Al iterar el dict obtenemos los vecinos.
        for v in graph.neighbors(u):

            # Si todavía no fue descubierto
            if v not in prev:

                prev[v] = u

                # BFS explora por niveles.
                # La primera vez que llegamos a un target,
                # su distancia es mínima.
                if v in targets:

                    path, distance = _reconstruct(
                        prev,
                        v,
                    )

                    return path, distance, v

                queue.append(v)

    # Ninguno de los destinos es alcanzable.
    return [], float("inf"), None


# ===========================================================================
# 3. BFS entre dos nodos
# ===========================================================================

def bfs_shortest_path(
    graph: Graph,
    source: object,
    target: object,
) -> tuple[list[object], float]:
    """
    Encuentra mediante BFS el camino mínimo entre source y target.

    """

    if not graph.has_node(target):
        raise KeyError(
            f"Nodo destino {target} no existe en el grafo."
        )

    path, distance, _ = bfs_to_any(
        graph,
        source,
        {target},
    )

    return path, distance


# ===========================================================================
# 4. A* hacia uno o varios destinos
# ===========================================================================


def astar_to_any(
    graph: Graph,
    source: object,
    targets: set[object],
    heuristic,
) -> tuple[list[object], float, object | None]:
    """
    Busca un camino de costo mínimo hacia cualquiera de los destinos.

    heuristic(nodo, destino) estima el costo restante. Para garantizar
    optimalidad debe ser admisible, no negativa y valer 0 en el destino.
    Para varios destinos se utiliza la menor de esas estimaciones.

    Retorna (camino, costo, destino), o ([], inf, None) si no llega.
    Los destinos ausentes del grafo se consideran inalcanzables.
    Lanza KeyError si el origen no existe.
    """
    if not graph.has_node(source):
        raise KeyError(f"Nodo origen {source} no existe en el grafo.")

    targets = {target for target in targets if graph.has_node(target)}
    if not targets:
        return [], float("inf"), None

    if source in targets:
        return [source], 0, source

    def estimate(node: object) -> float:
        return min(heuristic(node, target) for target in targets)

    # El contador desempata sin comparar nodos, que pueden ser de
    # cualquier tipo hashable y no necesariamente ordenables.
    order = 0
    heap = [(estimate(source), order, 0.0, source)]
    dist = {source: 0.0}
    prev = {source: source}

    while heap:
        _, _, cost, u = heapq.heappop(heap)

        # Entrada obsoleta: ya existe un camino más corto conocido.
        if cost > dist[u]:
            continue

        if u in targets:
            path, _ = _reconstruct(prev, u)
            return path, cost, u

        for v, weight in graph.neighbors(u).items():
            alternative = cost + weight
            if alternative < dist.get(v, float("inf")):
                dist[v] = alternative
                prev[v] = u
                # Un nodo puede reabrirse si se encuentra un camino mejor.
                order += 1
                heapq.heappush(
                    heap,
                    (alternative + estimate(v), order, alternative, v),
                )

    return [], float("inf"), None


# ===========================================================================
# 5. A* entre dos nodos
# ===========================================================================


def astar_shortest_path(
    graph: Graph,
    source: object,
    target: object,
    heuristic,
) -> tuple[list[object], float]:
    """Retorna (camino, costo) usando A* con la heurística recibida."""
    if not graph.has_node(target):
        raise KeyError(f"Nodo destino {target} no existe en el grafo.")

    path, distance, _ = astar_to_any(graph, source, {target}, heuristic)
    return path, distance
