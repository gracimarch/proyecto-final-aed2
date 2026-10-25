"""
algorithms/pathfinding.py

Cómo llega un picker hasta un producto.

Un producto está dentro de un rack, y los racks no son transitables. El
picker lo recoge parado en la celda de pasillo que está pegada a la cara del
rack donde está el producto. Esa celda se llama "celda de recogida".

Funciones:
    pickup_cells          : celdas de recogida de un producto.
    path_to_product_bfs   : camino mínimo hasta un producto con BFS.
    path_to_product_astar : camino mínimo hasta un producto con A*.
    manhattan             : heurística que usa A*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from algorithms.graph import Graph, bfs_to_any, astar_to_any

if TYPE_CHECKING:
    # Solo para las anotaciones de tipo. Python no ejecuta este bloque, así que
    # estos imports no pueden armar un import circular (ver GUIA.md).
    from models import Product, Warehouse


# ===========================================================================
# 1. Celdas de recogida de un producto
# ===========================================================================

def pickup_cells(
    product: Product,
    warehouse: Warehouse,
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Lista de celdas de pasillo desde las que se puede recoger el producto.

    Todo rack tiene ancho 2 o alto 2, así que cada celda del rack da a una cara:

        Rack vertical (ancho == 2):
            producto en la columna izquierda (x == rack.x)  -> recoge desde (x - 1, y)
            producto en la columna derecha   (x == rack.x + 1) -> recoge desde (x + 1, y)

        Rack horizontal (alto == 2):
            producto en la fila de abajo  (y == rack.y)     -> recoge desde (x, y - 1)
            producto en la fila de arriba (y == rack.y + 1) -> recoge desde (x, y + 1)

    Un rack 2x2 cumple las dos cosas, así que cada producto puede tener dos
    celdas de recogida. La altura z no cambia la celda.

    Solo se devuelven las celdas que son nodos del grafo (transitables y
    dentro del warehouse).

    Raises:
        ValueError: Si el producto no está dentro de su rack o el rack no
                    tiene ninguna dimensión igual a 2.
    """
    rack = warehouse.get_rack(product.rack_id)
    px = product.x
    py = product.y

    if not rack.contains_cell(px, py):
        raise ValueError(
            f"El producto '{product.product_id}' está ubicado en "
            f"({px},{py}), pero esa celda no pertenece al rack "
            f"'{rack.rack_id}'."
        )
    if rack.ancho != 2 and rack.alto != 2:
        raise ValueError(
            f"El rack '{rack.rack_id}' no tiene una dimensión igual a 2 "
            f"(ancho={rack.ancho}, alto={rack.alto})."
        )

    candidatas = []

    if rack.ancho == 2:
        if px == rack.x:                     # cara izquierda
            candidatas.append((px - 1, py))
        if px == rack.x + 1:                 # cara derecha
            candidatas.append((px + 1, py))

    if rack.alto == 2:
        if py == rack.y:                     # cara de abajo
            candidatas.append((px, py - 1))
        if py == rack.y + 1:                 # cara de arriba
            candidatas.append((px, py + 1))

    celdas = []
    for celda in candidatas:
        # graph.has_node ya descarta lo que está fuera del warehouse o bloqueado
        if graph.has_node(celda) and celda not in celdas:
            celdas.append(celda)
    return celdas


def _pickup_targets(
    graph: Graph,
    source: tuple[int, int],
    product: Product,
    warehouse: Warehouse,
) -> set[tuple[int, int]]:
    """
    Controles comunes de BFS y A*: que source sea un nodo y que el producto
    tenga al menos una celda de recogida. Devuelve esas celdas como conjunto.
    """
    if not graph.has_node(source):
        raise KeyError(f"La posición del picker {source} no es un nodo del grafo.")

    celdas = pickup_cells(product, warehouse, graph)
    if len(celdas) == 0:
        raise ValueError(
            f"El producto '{product.product_id}' ubicado en "
            f"({product.x},{product.y},{product.z}) no tiene "
            f"ninguna celda válida de recogida."
        )
    return set(celdas)


# ===========================================================================
# 2. Camino con BFS
# ===========================================================================

def path_to_product_bfs(
    graph: Graph,
    source: tuple[int, int],
    product: Product,
    warehouse: Warehouse,
    stats: dict | None = None,
) -> tuple[list[tuple[int, int]], float, tuple[int, int] | None]:
    """
    Camino mínimo desde source hasta alguna celda de recogida del producto.

    Returns:
        (camino, distancia, celda de recogida a la que llegó)
    """
    destinos = _pickup_targets(graph, source, product, warehouse)
    return bfs_to_any(graph, source, destinos, stats)


# ===========================================================================
# 3. Heurística y camino con A*
# ===========================================================================

def manhattan(source: tuple[int, int], target: tuple[int, int]) -> int:
    """
    Distancia Manhattan: |x1 - x2| + |y1 - y2|.

    Es lo que caminaría el picker si no hubiera racks ni sentidos. Como el
    camino real nunca puede ser más corto, A* con esta heurística sigue
    encontrando el camino mínimo.
    """
    return abs(source[0] - target[0]) + abs(source[1] - target[1])


def path_to_product_astar(
    graph: Graph,
    source: tuple[int, int],
    product: Product,
    warehouse: Warehouse,
    stats: dict | None = None,
) -> tuple[list[tuple[int, int]], float, tuple[int, int] | None]:
    """
    Igual que path_to_product_bfs, pero con A* y la heurística Manhattan.

    Returns:
        (camino, costo, celda de recogida a la que llegó)
    """
    destinos = _pickup_targets(graph, source, product, warehouse)
    return astar_to_any(graph, source, destinos, manhattan, stats)
