"""
algorithms/graph_builder.py

Convierte el Warehouse en un grafo dirigido de celdas transitables.

    Nodo   : cada celda (x, y) por la que puede caminar un picker.
    Arista : un paso de una celda a una vecina (arriba, abajo, izquierda,
             derecha), con peso 1.

Una celda NO es transitable si tiene un rack, una puerta o una zona de
despacho. Todas las demás son pasillo: las que están dentro de un pasillo
declarado tienen su sentido (N, S, E, O o AMBOS) y las que no, son AMBOS.

Regla de circulación (una sola):
    El paso de A a B está permitido si B es transitable, está dentro del
    warehouse, y el paso NO va en contra del sentido de A ni del sentido de B.

    "Ir en contra" quiere decir moverse en la dirección opuesta. En un
    pasillo N (se circula hacia y creciente) está prohibido bajar (dy = -1).
    Moverse de costado (dx = ±1 en un pasillo N) siempre está permitido, y
    un pasillo AMBOS no prohíbe nada.
"""

from collections import deque

from algorithms.graph import Graph

from models.warehouse import Warehouse


# Los cuatro pasos posibles (dx, dy). El orden define el orden de los vecinos
# en el grafo, y con eso qué camino elige BFS cuando hay empates.
DIRECCIONES = [(0, 1), (0, -1), (1, 0), (-1, 0)]

# Hacia dónde avanza cada sentido.
AVANCE = {
    "N": (0, 1),
    "S": (0, -1),
    "E": (1, 0),
    "O": (-1, 0),
}


def _goes_against(sentido: str, dx: int, dy: int) -> bool:
    """True si el paso (dx, dy) es justo el opuesto al sentido del pasillo."""
    if sentido == "AMBOS":
        return False
    avance_x, avance_y = AVANCE[sentido]
    return dx == -avance_x and dy == -avance_y


def _blocked_cells(warehouse: Warehouse) -> set[tuple[int, int]]:
    """Conjunto de celdas ocupadas por racks, puertas y zonas de despacho."""
    bloqueadas = set()

    for rack in warehouse.racks.values():
        for dx in range(rack.ancho):
            for dy in range(rack.alto):
                bloqueadas.add((rack.x + dx, rack.y + dy))

    for door in warehouse.doors:
        bloqueadas.add((door.position[0], door.position[1]))

    for zone in warehouse.dispatch_zones:
        for dx in range(zone.ancho):
            for dy in range(zone.alto):
                bloqueadas.add((zone.x + dx, zone.y + dy))

    return bloqueadas


def _cell_directions(warehouse: Warehouse) -> dict[tuple[int, int], str]:
    """
    Diccionario {(x, y): sentido} con las celdas de los pasillos declarados.
    Las celdas que no aparecen son AMBOS. Si dos pasillos se pisaran (el
    warehouse lo rechaza al validar), quedaría el último.
    """
    sentidos = {}
    for aisle in warehouse.aisles:
        for dx in range(aisle.ancho):
            for dy in range(aisle.alto):
                sentidos[(aisle.x + dx, aisle.y + dy)] = aisle.sentido
    return sentidos


def _direction_of(sentidos: dict[tuple[int, int], str], celda: tuple[int, int]) -> str:
    """Sentido de una celda: el de su pasillo declarado, o AMBOS si no tiene."""
    if celda in sentidos:
        return sentidos[celda]
    return "AMBOS"


def generate_graph(warehouse: Warehouse) -> Graph:
    """
    Construye el grafo de circulación del warehouse.

    Complejidad: O(ancho_x * largo_y), porque cada celda se mira una vez y
    tiene a lo sumo 4 vecinas.
    """
    ancho = warehouse.ancho_x
    largo = warehouse.largo_y
    bloqueadas = _blocked_cells(warehouse)
    sentidos = _cell_directions(warehouse)

    graph = Graph(directed=True)

    # Paso 1: un nodo por cada celda transitable (recorriendo fila por fila).
    for y in range(largo):
        for x in range(ancho):
            if (x, y) not in bloqueadas:
                graph.add_node((x, y))

    # Paso 2: una arista por cada paso permitido.
    for origen in graph.nodes():
        x, y = origen
        for dx, dy in DIRECCIONES:
            destino = (x + dx, y + dy)

            if not graph.has_node(destino):
                continue    # fuera del warehouse o bloqueada
            if _goes_against(_direction_of(sentidos, origen), dx, dy):
                continue    # contra el sentido del pasillo de salida
            if _goes_against(_direction_of(sentidos, destino), dx, dy):
                continue    # contra el sentido del pasillo de llegada

            graph.add_edge(origen, destino, 1.0)

    return graph


# ---------------------------------------------------------------------------
# Grafo de navegación: solo la circulación de la que se puede volver
# ---------------------------------------------------------------------------

def _reverse_adjacency(
    graph: Graph,
) -> dict[tuple[int, int], list[tuple[int, int]]]:
    """
    Predecesores de cada nodo: rev[v] contiene los u tales que existe u -> v.

    Sirve para recorrer el grafo al revés y saber desde qué celdas se puede
    LLEGAR a una celda dada.

    Complejidad: O(V + E).
    """
    rev = {u: [] for u in graph.nodes()}
    for u in graph.nodes():
        for v in graph.neighbors(u):
            rev[v].append(u)
    return rev


def _reachable(graph: Graph, sources: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Celdas alcanzables desde `sources` siguiendo las aristas del grafo."""
    vistos = set()
    cola = deque()

    for source in sources:
        if graph.has_node(source) and source not in vistos:
            vistos.add(source)
            cola.append(source)

    while len(cola) > 0:
        u = cola.popleft()
        for v in graph.neighbors(u):
            if v not in vistos:
                vistos.add(v)
                cola.append(v)

    return vistos


def _reachable_reverse(
    rev: dict[tuple[int, int], list[tuple[int, int]]],
    sources: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """
    Celdas desde las que se puede LLEGAR a alguna de `sources`.

    Es un BFS sobre el grafo invertido. Si se arranca en el núcleo, devuelve
    todas las celdas que tienen un camino de vuelta al núcleo.
    """
    vistos = set()
    cola = deque()

    for source in sources:
        if source in rev and source not in vistos:
            vistos.add(source)
            cola.append(source)

    while len(cola) > 0:
        v = cola.popleft()
        for u in rev.get(v, ()):
            if u not in vistos:
                vistos.add(u)
                cola.append(u)

    return vistos


def _strongly_connected_component(
    graph: Graph,
    rev: dict[tuple[int, int], list[tuple[int, int]]],
    source: tuple[int, int],
) -> set[tuple[int, int]]:
    """
    Componente fuertemente conexa (SCC) que contiene a `source`.

    Es la intersección entre lo que se alcanza desde source y lo que puede
    volver a source: dentro de una SCC todos los nodos se alcanzan entre sí.
    """
    ida = _reachable(graph, {source})
    vuelta = _reachable_reverse(rev, {source})
    return ida & vuelta


def _picker_starts(
    warehouse: Warehouse,
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Celdas iniciales de los pickers que existen en el grafo, sin repetir.

    Se usa la posición inicial porque es la que fija la generación de waves.
    """
    starts = []
    vistas = set()
    for picker in warehouse.pickers:
        celda = tuple(picker.posicion_inicial)
        if celda in vistas or not graph.has_node(celda):
            continue
        vistas.add(celda)
        starts.append(celda)
    return starts


def _main_core(
    graph: Graph,
    rev: dict[tuple[int, int], list[tuple[int, int]]],
    starts: list[tuple[int, int]],
) -> set[tuple[int, int]]:
    """
    SCC principal de circulación: la que contiene más pickers.

    Si hay empate se elige la SCC más grande. Es el "núcleo" al que tienen
    que poder volver los pickers; las celdas que no pueden volver a él son
    callejones sin salida y no se usan para navegar.
    """
    sccs = []
    for start in starts:
        comp = _strongly_connected_component(graph, rev, start)
        if not any(comp == otra for otra in sccs):
            sccs.append(comp)

    if len(sccs) == 0:
        return set()

    return max(
        sccs,
        key=lambda comp: (
            sum(1 for start in starts if start in comp),
            len(comp),
        ),
    )


def live_circulation_cells(
    warehouse: Warehouse,
    graph: Graph,
) -> set[tuple[int, int]]:
    """
    Celdas desde las que se puede volver al núcleo de circulación de los
    pickers.

    Un pasillo de sentido único que termina en un callejón sin salida queda
    afuera: se puede entrar, pero no volver. Si no hay pickers, todas las
    celdas del grafo son navegables.

    Complejidad: O(P * (V + E)) por las SCC de los pickers, donde P es la
    cantidad de pickers; después un BFS O(V + E) sobre el grafo invertido.
    """
    starts = _picker_starts(warehouse, graph)
    if len(starts) == 0:
        return set(graph.nodes())

    rev = _reverse_adjacency(graph)
    core = _main_core(graph, rev, starts)
    return _reachable_reverse(rev, core)


def restrict_to_live_circulation(
    graph: Graph,
    warehouse: Warehouse,
) -> Graph:
    """
    Devuelve el subgrafo de navegación: la circulación viva más las islas
    donde arranquen pickers que no pueden volver al núcleo.

    Las aristas que salen de la circulación viva hacia un callejón sin salida
    se eliminan. Así ningún picker puede entrar en una región de la que no
    podría salir. Las islas se conservan desconectadas para que un picker que
    ya arrancó en una de ellas siga teniendo un nodo válido en el grafo.

    Si no hay pickers, devuelve el grafo original.
    """
    starts = _picker_starts(warehouse, graph)
    if len(starts) == 0:
        return graph

    rev = _reverse_adjacency(graph)
    core = _main_core(graph, rev, starts)
    vivo = _reachable_reverse(rev, core)

    grupos = [vivo]
    for start in starts:
        if start in vivo:
            continue
        isla = _strongly_connected_component(graph, rev, start)
        if not any(isla == grupo for grupo in grupos[1:]):
            grupos.append(isla)

    if len(grupos) == 1 and len(vivo) == graph.node_count():
        return graph

    grupo_de = {}
    for indice, grupo in enumerate(grupos):
        for celda in grupo:
            grupo_de[celda] = indice

    navegable = Graph(directed=True)
    for celda in grupo_de:
        navegable.add_node(celda)

    for u in grupo_de:
        for v in graph.neighbors(u):
            # Solo se conservan aristas dentro del mismo grupo. En particular
            # se cortan las entradas desde la circulación viva hacia una isla.
            if grupo_de.get(v) == grupo_de[u]:
                navegable.add_edge(u, v, graph.weight(u, v))

    return navegable


def generate_navigation_graph(warehouse: Warehouse) -> Graph:
    """
    Grafo que usan la generación de waves, el ruteo y la simulación.

    Parte del grafo completo y le quita las regiones de las que no se puede
    volver al núcleo de los pickers. El grafo completo sigue disponible con
    generate_graph() para dibujar o analizar el layout.
    """
    return restrict_to_live_circulation(generate_graph(warehouse), warehouse)
