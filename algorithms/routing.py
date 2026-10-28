"""
algorithms/routing.py

Recorrido completo de una wave.

El recorrido sale de una celda de pasillo adyacente a la zona de despacho,
pasa por una celda de recogida de cada producto de la wave y vuelve a una
celda adyacente a la zona. Cada tramo entre dos paradas es un camino mínimo
en el grafo dirigido del warehouse, calculado con BFS o con A*.

Estrategias implementadas (qué parada se visita después):
    "orden"    (A) : las paradas en el orden en que aparecen los pedidos.
    "cercania" (B) : siempre la parada pendiente más cercana (greedy de
                     vecino más cercano). Un BFS hacia TODAS las paradas
                     pendientes a la vez la encuentra en una sola búsqueda,
                     porque el primer destino que toca BFS es el más cercano.

Métricas de cada recorrido:
    distancia_total    : movimientos del picker. Como cada arista cuesta 1,
                         coincide con aristas_recorridas.
    aristas_recorridas : aristas del camino completo (con repeticiones).
    nodos_visitados    : celdas distintas por las que pasa el picker.
    nodos_expandidos   : nodos que sacó de la cola el algoritmo de búsqueda
                         sumando todos los tramos (costo del algoritmo).
    tiempo_ms          : tiempo de cálculo del recorrido.
"""

import time

from algorithms.graph import Graph, bfs_to_any, astar_to_any, bfs_distances
from algorithms.pathfinding import pickup_cells, manhattan

from models.warehouse import DispatchZone, Warehouse
from models.wave import Wave


ESTRATEGIAS = ("orden", "cercania")
BUSCADORES = ("bfs", "astar")


# ===========================================================================
# 1. Resultado de un recorrido
# ===========================================================================

class RouteResult:
    """
    Recorrido calculado para una wave y sus métricas.

    Atributos:
        estrategia         (str)   : "orden" o "cercania".
        buscador           (str)   : "bfs" o "astar".
        path               (list)  : Celdas (x, y) del recorrido completo, en orden.
        paradas            (list)  : [(celda_de_recogida, [product_id, ...]), ...]
                                     en el orden en que se recogen.
        distancia_total    (int)
        aristas_recorridas (int)
        nodos_visitados    (int)
        nodos_expandidos   (int)
        tiempo_ms          (float)
    """

    def __init__(
        self,
        estrategia: str,
        buscador: str,
        path: list[tuple[int, int]],
        paradas: list[tuple[tuple[int, int], list[str]]],
        nodos_expandidos: int,
        tiempo_ms: float,
    ):
        self.estrategia = estrategia
        self.buscador = buscador
        self.path = path
        self.paradas = paradas
        self.aristas_recorridas = len(path) - 1
        self.distancia_total = self.aristas_recorridas
        self.nodos_visitados = len(set(path))   # set() elimina las celdas repetidas
        self.nodos_expandidos = nodos_expandidos
        self.tiempo_ms = tiempo_ms

    def metrics(self) -> dict:
        """Métricas del recorrido, listas para mostrar o comparar (§10)."""
        return {
            "estrategia": self.estrategia,
            "buscador": self.buscador,
            "distancia_total": self.distancia_total,
            "aristas_recorridas": self.aristas_recorridas,
            "nodos_visitados": self.nodos_visitados,
            "nodos_expandidos": self.nodos_expandidos,
            "tiempo_ms": round(self.tiempo_ms, 3),
        }

    def to_dict(self) -> dict:
        """Serializa el recorrido completo (métricas, camino y paradas)."""
        datos = self.metrics()

        camino = []
        for celda in self.path:
            camino.append([celda[0], celda[1]])
        datos["path"] = camino

        paradas = []
        for celda, product_ids in self.paradas:
            paradas.append({
                "celda": [celda[0], celda[1]],
                "productos": list(product_ids),
            })
        datos["paradas"] = paradas

        return datos

    def __repr__(self) -> str:
        return (
            f"RouteResult({self.estrategia}/{self.buscador}, "
            f"distancia={self.distancia_total}, nodos_visitados={self.nodos_visitados}, "
            f"nodos_expandidos={self.nodos_expandidos}, tiempo={self.tiempo_ms:.2f}ms)"
        )


# ===========================================================================
# 2. Zona de despacho
# ===========================================================================

def default_dispatch_zone(warehouse: Warehouse) -> DispatchZone:
    """
    Zona de despacho por defecto: la primera cuya puerta sea OUTBOUND o AMBOS
    (expedición); si no hay ninguna, la primera zona.

    Raises:
        ValueError: Si el warehouse no tiene zonas de despacho.
    """
    zones = warehouse.dispatch_zones
    if len(zones) == 0:
        raise ValueError("El warehouse no tiene zonas de despacho.")

    for zone in zones:
        for door in warehouse.doors:
            if door.door_id == zone.puerta_id and door.tipo in ("OUTBOUND", "AMBOS"):
                return zone
    return zones[0]


def _row_column_key(celda: tuple[int, int]) -> tuple[int, int]:
    """Clave para ordenar celdas por fila (y) y, dentro de la fila, por columna (x)."""
    x, y = celda
    return (y, x)


def dispatch_access_cells(
    zone: DispatchZone,
    warehouse: Warehouse,
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Celdas de pasillo pegadas (arriba, abajo, izquierda o derecha) a la zona
    de despacho, ordenadas por (y, x) para que siempre se elija la misma.
    """
    celdas = []
    for dx in range(zone.ancho):
        for dy in range(zone.alto):
            cx = zone.x + dx
            cy = zone.y + dy
            vecinas = [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
            for vecina in vecinas:
                if graph.has_node(vecina) and vecina not in celdas:
                    celdas.append(vecina)

    celdas.sort(key=_row_column_key)
    return celdas


# ===========================================================================
# 3. Paradas de una wave
# ===========================================================================

class _Stop:
    """
    Parada del recorrido: una celda de rack con uno o más productos de la
    wave (productos apilados en distintas alturas z se recogen juntos).

    Atributos:
        rack_cell   : celda (x, y) del rack.
        product_ids : productos que se recogen en esta parada.
        pickup      : conjunto de celdas de pasillo desde donde se recogen.
    """

    def __init__(self, rack_cell: tuple[int, int], pickup: set[tuple[int, int]]):
        self.rack_cell = rack_cell
        self.product_ids = []
        self.pickup = pickup


def _wave_stops(wave: Wave, warehouse: Warehouse, graph: Graph) -> list[_Stop]:
    """
    Agrupa los productos de la wave por celda de rack, en el orden en que
    aparecen sus pedidos.

    Raises:
        ValueError: Si algún producto no tiene celda de recogida transitable.
    """
    paradas = {}    # celda del rack -> _Stop (los dict recuerdan el orden de inserción)
    for item in wave.get_items():
        product = item.product
        celda = (product.x, product.y)

        if celda not in paradas:
            pickup = set(pickup_cells(product, warehouse, graph))
            if len(pickup) == 0:
                raise ValueError(
                    f"El producto '{product.product_id}' no tiene ninguna celda "
                    f"de recogida transitable."
                )
            paradas[celda] = _Stop(celda, pickup)

        parada = paradas[celda]
        if product.product_id not in parada.product_ids:
            parada.product_ids.append(product.product_id)

    return list(paradas.values())


# ===========================================================================
# 4. Recorrido
# ===========================================================================

def _search(
    graph: Graph,
    source: tuple[int, int],
    targets: set[tuple[int, int]],
    buscador: str,
    stats: dict,
) -> tuple[list[tuple[int, int]], float, tuple[int, int] | None]:
    """Camino mínimo de source a cualquiera de targets con el buscador elegido."""
    if buscador == "bfs":
        return bfs_to_any(graph, source, targets, stats)
    return astar_to_any(graph, source, targets, manhattan, stats)


def _next_targets(pendientes: list[_Stop], estrategia: str) -> set[tuple[int, int]]:
    """
    Celdas a las que puede ir el picker en el próximo tramo.
        "orden"    : solo las de la primera parada pendiente.
        "cercania" : las de todas las paradas pendientes.
    """
    if estrategia == "orden":
        return pendientes[0].pickup

    destinos = set()
    for parada in pendientes:
        for celda in parada.pickup:
            destinos.add(celda)
    return destinos


def _served_stops(
    pendientes: list[_Stop],
    estrategia: str,
    celda: tuple[int, int],
) -> list[_Stop]:
    """
    Paradas que se completan al llegar a celda.
        "orden"    : la primera pendiente.
        "cercania" : todas las que se recogen desde esa celda (puede haber
                     más de una, por ejemplo dos racks enfrentados).
    """
    if estrategia == "orden":
        return [pendientes[0]]

    atendidas = []
    for parada in pendientes:
        if celda in parada.pickup:
            atendidas.append(parada)
    return atendidas


def plan_route(
    wave: Wave,
    warehouse: Warehouse,
    graph: Graph,
    estrategia: str = "cercania",
    buscador: str = "bfs",
    zone: DispatchZone | None = None,
) -> RouteResult:
    """
    Calcula el recorrido de una wave: zona -> productos -> zona.

    No modifica la wave; para guardarlo usar wave.set_route(resultado.path).

    Args:
        wave       : Wave con al menos un ítem.
        warehouse  : Warehouse de la wave.
        graph      : Grafo dirigido construido con graph_builder.generate_graph.
        estrategia : "orden" (A) o "cercania" (B).
        buscador   : "bfs" o "astar".
        zone       : Zona de despacho de salida y llegada. Por defecto,
                     default_dispatch_zone(warehouse).

    Complejidad: con k paradas, cada tramo es una búsqueda O(V + E), así que
    el total es O(k * (V + E)) para las dos estrategias. La B hace una sola
    búsqueda por paso porque busca hacia todas las paradas pendientes a la vez.

    Raises:
        ValueError: Si la estrategia o el buscador no existen, la wave está
                    vacía, la zona no tiene celdas de acceso o alguna parada
                    es inalcanzable respetando los sentidos de circulación.
    """
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estrategia desconocida '{estrategia}'. Opciones: {ESTRATEGIAS}")
    if buscador not in BUSCADORES:
        raise ValueError(f"Buscador desconocido '{buscador}'. Opciones: {BUSCADORES}")
    if len(wave.entries) == 0:
        raise ValueError(f"La wave '{wave.wave_id}' no tiene ítems.")

    inicio = time.perf_counter()
    stats = {"nodos_expandidos": 0}

    if zone is None:
        zone = default_dispatch_zone(warehouse)
    acceso = dispatch_access_cells(zone, warehouse, graph)
    if len(acceso) == 0:
        raise ValueError(f"La zona '{zone.zone_id}' no tiene celdas de pasillo adyacentes.")

    actual = acceso[0]
    path = [actual]
    paradas = []
    pendientes = _wave_stops(wave, warehouse, graph)

    # Ida: un tramo por parada hasta que no quede ninguna pendiente.
    while len(pendientes) > 0:
        destinos = _next_targets(pendientes, estrategia)
        tramo, distancia, llegada = _search(graph, actual, destinos, buscador, stats)

        if llegada is None:
            faltan = []
            for parada in pendientes:
                for product_id in parada.product_ids:
                    faltan.append(product_id)
            raise ValueError(
                f"Desde {actual} no se puede llegar a los productos {faltan} "
                f"respetando los sentidos de circulación."
            )

        # tramo[0] es la celda donde ya estamos; no la repetimos.
        for celda in tramo[1:]:
            path.append(celda)
        actual = llegada

        atendidas = _served_stops(pendientes, estrategia, llegada)
        recogidos = []
        for parada in atendidas:
            for product_id in parada.product_ids:
                recogidos.append(product_id)
        paradas.append((llegada, recogidos))

        quedan = []
        for parada in pendientes:
            if parada not in atendidas:
                quedan.append(parada)
        pendientes = quedan

    # Vuelta: a cualquier celda de acceso a la zona.
    tramo, distancia, llegada = _search(graph, actual, set(acceso), buscador, stats)
    if llegada is None:
        raise ValueError(
            f"Desde {actual} no se puede volver a la zona '{zone.zone_id}' "
            f"respetando los sentidos de circulación."
        )
    for celda in tramo[1:]:
        path.append(celda)

    tiempo_ms = (time.perf_counter() - inicio) * 1000
    return RouteResult(estrategia, buscador, path, paradas, stats["nodos_expandidos"], tiempo_ms)


def compare_strategies(
    wave: Wave,
    warehouse: Warehouse,
    graph: Graph,
    buscador: str = "bfs",
    zone: DispatchZone | None = None,
) -> dict[str, RouteResult]:
    """
    Ejecuta todas las estrategias sobre la misma wave (§10).

    Returns:
        {estrategia: RouteResult}
    """
    resultados = {}
    for estrategia in ESTRATEGIAS:
        resultados[estrategia] = plan_route(wave, warehouse, graph, estrategia, buscador, zone)
    return resultados


# ===========================================================================
# 5. Validación: todo producto se puede alcanzar
# ===========================================================================

def reverse_graph(graph: Graph) -> Graph:
    """
    Grafo con todas las aristas dadas vuelta: si en graph hay u -> v, en el
    nuevo hay v -> u.

    Sirve para saber desde qué celdas se puede LLEGAR a un lugar: un BFS en
    el grafo invertido que arranca en ese lugar encuentra justamente esas
    celdas.

    Complejidad: O(V + E).
    """
    invertido = Graph(directed=True)
    for u in graph.nodes():
        invertido.add_node(u)
    for u in graph.nodes():
        for v in graph.neighbors(u):
            invertido.add_edge(v, u, graph.weight(u, v))
    return invertido


def validate_reachability(
    warehouse: Warehouse,
    graph: Graph,
    zone: DispatchZone | None = None,
) -> None:
    """
    Controla que cada producto se pueda ir a buscar y traer: tiene que
    haber al menos una celda de recogida a la que se llegue desde la zona de
    despacho y desde la que se pueda volver a la zona, respetando los
    sentidos de los pasillos.

    Cómo lo hace (dos BFS que arrancan desde todas las celdas de acceso de
    la zona a la vez):
        ida    : BFS en el grafo normal   -> celdas a las que se LLEGA desde la zona.
        vuelta : BFS en el grafo invertido -> celdas desde las que se VUELVE a la zona.
    Una celda de recogida sirve si aparece en los dos resultados.

    Complejidad: O(V + E) por los dos BFS, más O(1) por cada celda de
    recogida de cada producto.

    Raises:
        ValueError: Si no hay zona de despacho, la zona no tiene celdas de
                    acceso o hay productos que no se pueden alcanzar.
    """
    if zone is None:
        zone = default_dispatch_zone(warehouse)

    acceso = dispatch_access_cells(zone, warehouse, graph)
    if len(acceso) == 0:
        raise ValueError(
            f"La zona de despacho '{zone.zone_id}' no tiene ninguna celda de pasillo al lado."
        )

    ida = bfs_distances(graph, set(acceso))
    vuelta = bfs_distances(reverse_graph(graph), set(acceso))

    inalcanzables = []
    for product_id in sorted(warehouse.products):
        product = warehouse.products[product_id]
        alcanzable = False
        for celda in pickup_cells(product, warehouse, graph):
            if celda in ida and celda in vuelta:
                alcanzable = True
                break    # con una celda que sirva alcanza
        if not alcanzable:
            inalcanzables.append(product_id)

    if len(inalcanzables) > 0:
        raise ValueError(
            f"Desde la zona de despacho '{zone.zone_id}' no se puede ir a buscar "
            f"y volver con estos productos: {', '.join(inalcanzables)}."
        )
