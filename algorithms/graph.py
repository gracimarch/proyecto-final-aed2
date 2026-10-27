"""
algorithms/graph.py

Grafo con lista de adyacencia y los algoritmos de búsqueda que usa el
proyecto: BFS (varias variantes) y A*.

Nodos: cualquier valor que pueda ser clave de un diccionario. En el
warehouse son tuplas (x, y), una por celda de pasillo.

Estructuras de Python que se usan:
    deque (de collections): cola doble. popleft() saca el primero en O(1).
        Con una lista común, lista.pop(0) cuesta O(n) porque corre todos
        los elementos, y eso arruinaría el O(V + E) del BFS.
    heapq: funciones para usar una lista como cola de prioridad (min-heap).
        heappush agrega y heappop saca el MENOR, los dos en O(log n). Lo usa A*.
"""

import heapq
from collections import deque
from collections.abc import Callable


INFINITO = float("inf")


class Graph:
    """
    Grafo con pesos implementado con lista de adyacencia.

    _adj es un diccionario de diccionarios:
        _adj[u] = {v1: peso1, v2: peso2, ...}   (los vecinos de u y el peso de cada arista)

    Si el grafo es dirigido, la arista u -> v NO implica v -> u. El warehouse
    usa un grafo dirigido porque los pasillos tienen sentido de circulación.
    """

    def __init__(self, directed: bool = False):
        self._directed = directed
        self._adj = {}
        self._node_count = 0
        self._edge_count = 0

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def add_node(self, node: object) -> None:
        """Agrega un nodo. Si ya existe, no hace nada."""
        if node not in self._adj:
            self._adj[node] = {}
            self._node_count = self._node_count + 1

    def add_edge(self, u: object, v: object, weight: float = 1.0) -> None:
        """
        Agrega la arista u -> v (y v -> u si el grafo no es dirigido).
        Si ya existía, actualiza su peso.

        Raises:
            ValueError: Si el peso es negativo.
        """
        if weight < 0:
            raise ValueError(f"El peso de una arista no puede ser negativo: {weight}")
        self.add_node(u)
        self.add_node(v)
        if v not in self._adj[u]:
            self._edge_count = self._edge_count + 1
        self._adj[u][v] = weight
        if not self._directed:
            self._adj[v][u] = weight

    def remove_edge(self, u: object, v: object) -> None:
        """Borra la arista u -> v (y v -> u si no es dirigido). Si no existe, no hace nada."""
        if self.has_edge(u, v):
            del self._adj[u][v]
            self._edge_count = self._edge_count - 1
            if not self._directed:
                del self._adj[v][u]

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def has_node(self, node: object) -> bool:
        return node in self._adj

    def has_edge(self, u: object, v: object) -> bool:
        return u in self._adj and v in self._adj[u]

    def weight(self, u: object, v: object) -> float:
        """
        Raises:
            KeyError: Si la arista no existe.
        """
        if not self.has_edge(u, v):
            raise KeyError(f"No existe arista entre {u} y {v}.")
        return self._adj[u][v]

    def neighbors(self, node: object) -> dict[object, float]:
        """
        Vecinos del nodo como diccionario {vecino: peso}. Recorrerlo con un
        for da los vecinos.

        Raises:
            KeyError: Si el nodo no existe.
        """
        if node not in self._adj:
            raise KeyError(f"Nodo '{node}' no existe en el grafo.")
        return dict(self._adj[node])

    def nodes(self) -> list[object]:
        return list(self._adj.keys())

    def node_count(self) -> int:
        return self._node_count

    def edge_count(self) -> int:
        return self._edge_count

    # ------------------------------------------------------------------
    # BFS desde un nodo
    # ------------------------------------------------------------------

    def bfs(self, source: object) -> dict[object, int]:
        """
        Recorrido en anchura desde source.

        Returns:
            {nodo: nivel}, donde nivel es la cantidad de aristas desde source.
            Solo aparecen los nodos alcanzables.

        Complejidad: O(V + E) en tiempo, O(V) en espacio.

        Raises:
            KeyError: Si source no existe.
        """
        if not self.has_node(source):
            raise KeyError(f"Nodo fuente '{source}' no existe en el grafo.")

        nivel = {source: 0}       # también sirve como "visitados"
        cola = deque([source])
        while len(cola) > 0:
            u = cola.popleft()
            for v in self._adj[u]:
                if v not in nivel:
                    nivel[v] = nivel[u] + 1
                    cola.append(v)
        return nivel

    def reachable_from(self, source: object) -> set[object]:
        """Conjunto de nodos a los que se puede llegar desde source."""
        alcanzables = set()
        for nodo in self.bfs(source):
            alcanzables.add(nodo)
        return alcanzables

    def __repr__(self) -> str:
        return (
            f"Graph(nodes={self._node_count}, edges={self._edge_count}, "
            f"directed={self._directed})"
        )


# ===========================================================================
# Ayudas
# ===========================================================================

def _reconstruct(prev: dict[object, object], target: object) -> tuple[list[object], int]:
    """
    Arma el camino desde el origen hasta target usando prev.

    prev[v] es el nodo desde el que se llegó a v. El origen se guarda como
    prev[origen] = origen, y así sabemos dónde parar.

    Returns:
        (camino, cantidad de aristas)
    """
    path = []
    node = target
    while True:
        path.append(node)
        if prev[node] == node:
            break
        node = prev[node]
    path.reverse()     # lo armamos de atrás para adelante
    return path, len(path) - 1


def _count_expanded(stats: dict | None, expanded: int) -> None:
    """Suma nodos expandidos en stats["nodos_expandidos"], si se pasó stats."""
    if stats is not None:
        anterior = stats.get("nodos_expandidos", 0)
        stats["nodos_expandidos"] = anterior + expanded


# ===========================================================================
# BFS multi-origen: distancia desde un conjunto de nodos
# ===========================================================================

def bfs_distances(graph: Graph, sources: set[object]) -> dict[object, int]:
    """
    BFS que arranca a la vez desde todos los nodos de sources.

    Devuelve {nodo: distancia}: la menor cantidad de aristas desde
    CUALQUIERA de los orígenes. Es lo mismo que hacer un BFS desde cada
    origen y quedarse con el mínimo, pero en un solo recorrido.

    Lo usa WaveManager para medir qué tan cerca está cada pedido de una wave.
    Los orígenes que no están en el grafo se ignoran.

    Complejidad: O(V + E) en tiempo, O(V) en espacio.
    """
    dist = {}
    cola = deque()
    for s in sources:
        if graph.has_node(s) and s not in dist:
            dist[s] = 0
            cola.append(s)

    while len(cola) > 0:
        u = cola.popleft()
        for v in graph.neighbors(u):
            if v not in dist:
                dist[v] = dist[u] + 1
                cola.append(v)
    return dist


# ===========================================================================
# BFS hacia uno o varios destinos
# ===========================================================================

def bfs_to_any(
    graph: Graph,
    source: object,
    targets: set[object],
    stats: dict | None = None,
) -> tuple[list[object], float, object | None]:
    """
    BFS desde source hasta el destino de targets que esté más cerca.

    Como BFS avanza por niveles, el primer destino que encuentra es el más
    cercano. Cuenta aristas e ignora los pesos (en el warehouse todos valen 1).

    Args:
        targets: Conjunto de nodos destino.
        stats  : Diccionario opcional donde se suma "nodos_expandidos".

    Returns:
        (camino, distancia, destino alcanzado), o ([], infinito, None) si no llega.

    Complejidad: O(V + E) en el peor caso.

    Raises:
        KeyError: Si source no existe.
    """
    if not graph.has_node(source):
        raise KeyError(f"Nodo origen {source} no existe en el grafo.")

    if source in targets:
        _count_expanded(stats, 1)
        return [source], 0, source

    prev = {source: source}    # también sirve como "visitados"
    cola = deque([source])
    expanded = 0

    while len(cola) > 0:
        u = cola.popleft()
        expanded = expanded + 1
        for v in graph.neighbors(u):
            if v not in prev:
                prev[v] = u
                if v in targets:
                    path, distance = _reconstruct(prev, v)
                    _count_expanded(stats, expanded)
                    return path, distance, v
                cola.append(v)

    _count_expanded(stats, expanded)
    return [], INFINITO, None


def bfs_shortest_path(
    graph: Graph,
    source: object,
    target: object,
) -> tuple[list[object], float]:
    """Camino mínimo de source a target con BFS. Devuelve (camino, distancia)."""
    if not graph.has_node(target):
        raise KeyError(f"Nodo destino {target} no existe en el grafo.")
    path, distance, alcanzado = bfs_to_any(graph, source, {target})
    return path, distance


# ===========================================================================
# A* hacia uno o varios destinos
# ===========================================================================

def _estimate(
    node: object,
    targets: set[object],
    heuristic: Callable[[object, object], float],
) -> float:
    """Estimación de A* para varios destinos: la menor heurística hacia alguno."""
    menor = INFINITO
    for target in targets:
        valor = heuristic(node, target)
        if valor < menor:
            menor = valor
    return menor


def astar_to_any(
    graph: Graph,
    source: object,
    targets: set[object],
    heuristic: Callable[[object, object], float],
    stats: dict | None = None,
) -> tuple[list[object], float, object | None]:
    """
    A*: busca el camino de menor costo hacia alguno de los destinos.

    Siempre expande primero el nodo con menor f = g + h, donde
        g = costo real desde source hasta el nodo,
        h = heuristic(nodo, destino), una estimación de lo que falta.
    Si h nunca sobreestima (por ejemplo Manhattan en una grilla con
    movimientos de costo 1), el camino encontrado es mínimo, igual que BFS,
    pero suele expandir menos nodos porque se orienta hacia el destino.

    Cada elemento del heap es la tupla (f, orden, g, nodo). heapq saca la
    tupla menor comparando primero f; "orden" es un contador que desempata
    para que nunca tenga que comparar dos nodos.

    Args:
        heuristic: Función heuristic(nodo, destino) que devuelve un número.
        stats    : Diccionario opcional donde se suma "nodos_expandidos".

    Returns:
        (camino, costo, destino alcanzado), o ([], infinito, None) si no llega.

    Raises:
        KeyError: Si source no existe.
    """
    if not graph.has_node(source):
        raise KeyError(f"Nodo origen {source} no existe en el grafo.")

    destinos = set()
    for target in targets:
        if graph.has_node(target):
            destinos.add(target)
    if len(destinos) == 0:
        return [], INFINITO, None

    if source in destinos:
        _count_expanded(stats, 1)
        return [source], 0, source

    orden = 0
    heap = [(_estimate(source, destinos, heuristic), orden, 0.0, source)]
    dist = {source: 0.0}       # mejor costo conocido hasta cada nodo (g)
    prev = {source: source}
    expanded = 0

    while len(heap) > 0:
        f, orden_sacado, cost, u = heapq.heappop(heap)

        # Si ya encontramos un camino mejor a u, esta entrada quedó vieja.
        if cost > dist[u]:
            continue

        expanded = expanded + 1
        if u in destinos:
            path, aristas = _reconstruct(prev, u)
            _count_expanded(stats, expanded)
            return path, cost, u

        vecinos = graph.neighbors(u)
        for v in vecinos:
            alternativa = cost + vecinos[v]
            costo_conocido = dist.get(v, INFINITO)
            if alternativa < costo_conocido:
                dist[v] = alternativa
                prev[v] = u
                orden = orden + 1
                f_nuevo = alternativa + _estimate(v, destinos, heuristic)
                heapq.heappush(heap, (f_nuevo, orden, alternativa, v))

    _count_expanded(stats, expanded)
    return [], INFINITO, None


def astar_shortest_path(
    graph: Graph,
    source: object,
    target: object,
    heuristic: Callable[[object, object], float],
) -> tuple[list[object], float]:
    """Camino mínimo de source a target con A*. Devuelve (camino, costo)."""
    if not graph.has_node(target):
        raise KeyError(f"Nodo destino {target} no existe en el grafo.")
    path, distance, alcanzado = astar_to_any(graph, source, {target}, heuristic)
    return path, distance
