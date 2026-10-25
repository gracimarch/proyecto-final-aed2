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

from __future__ import annotations

from typing import TYPE_CHECKING

from algorithms.graph import Graph

if TYPE_CHECKING:
    # Solo para las anotaciones de tipo. Python no ejecuta este bloque, así que
    # estos imports no pueden armar un import circular (ver GUIA.md).
    from models import Warehouse


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
