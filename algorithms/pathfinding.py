"""
algorithms/pathfinding.py

Cómo llega un picker hasta un producto.

Un producto está dentro de un rack, y los racks no son transitables. El
picker lo recoge parado en una celda de pasillo ortogonalmente adyacente a
la celda del rack donde está el producto. Esa celda se llama "celda de
recogida".

Funciones:
    adjacent_aisle_cells  : celdas de pasillo ortogonalmente adyacentes.
    pickup_cells          : celdas de recogida de un producto.
    manhattan             : heurística que usa A*.
"""

from algorithms.graph import Graph

from models.product import Product
from models.warehouse import Warehouse


# ===========================================================================
# 1. Celdas de recogida de un producto
# ===========================================================================

# Las cuatro vecinas ortogonales de una celda.
DIRECCIONES_ORT = ((1, 0), (-1, 0), (0, 1), (0, -1))


def adjacent_aisle_cells(
    cells: list[tuple[int, int]],
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Celdas de pasillo que están ortogonalmente pegadas a `cells`.

    Se usa tanto para las celdas de un rack (celdas de recogida de un
    producto) como para las de una zona de despacho (celdas de acceso).
    Devuelve solo nodos del grafo, sin repetir y en orden determinista.

    Complejidad: O(4 × cantidad de celdas de entrada).
    """
    celdas = []
    vistas = set()
    for cx, cy in cells:
        for dx, dy in DIRECCIONES_ORT:
            vecina = (cx + dx, cy + dy)
            if vecina in vistas:
                continue
            vistas.add(vecina)
            if graph.has_node(vecina):
                celdas.append(vecina)
    return celdas


def pickup_cells(
    product: Product,
    warehouse: Warehouse,
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Lista de celdas de pasillo desde las que se puede recoger el producto.

    Un producto se recoge desde cualquier celda de pasillo ortogonalmente
    adyacente a la celda del rack donde está (§3.6 y §8). La regla de que un
    lado del rack valga 2 garantiza que cada celda tenga al menos una cara
    expuesta, pero no limita la recogida a esa cara: los extremos del rack
    también sirven si dan a un pasillo.

    Por eso no se calcula una única cara según la columna/fila del producto:
    se miran las cuatro vecinas, igual que para las zonas de despacho.

    La altura z no cambia la celda.

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

    return adjacent_aisle_cells([(px, py)], graph)


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
