from algorithms.graph import Graph, bfs_to_any, astar_to_any

from models.warehouse import Warehouse
from models.product import Product


# ===========================================================================
# 1. Celdas de recogida de un producto
# ===========================================================================

def pickup_cells(
    product: "Product",
    warehouse: "Warehouse",
    graph: Graph,
) -> list[tuple[int, int]]:
    """
    Retorna las celdas de pasillo desde las cuales puede recogerse product.

    El acceso se determina según la cara del rack en la que se encuentra
    el producto.

    Un rack tiene ancho == 2 o alto == 2.

    Rack vertical
    -------------
    ancho == 2

        cara izquierda:
            producto en x == rack.x
            acceso = (product.x - 1, product.y)

        cara derecha:
            producto en x == rack.x + ancho - 1
            acceso = (product.x + 1, product.y)

    Rack horizontal
    ---------------
    alto == 2

        cara inferior:
            producto en y == rack.y
            acceso = (product.x, product.y - 1)

        cara superior:
            producto en y == rack.y + alto - 1
            acceso = (product.x, product.y + 1)

    Si el rack es 2x2, un producto puede estar expuesto por dos caras,
    por lo que pueden existir dos celdas de recogida válidas.

    z no interviene en el cálculo del acceso.

    Una celda candidata solamente se devuelve si:
      1. está dentro del Warehouse;
      2. existe como nodo del grafo, por lo tanto es transitable.


    """

    # ---------------------------------------------------------------
    # 1. Obtener el rack real del producto
    # ---------------------------------------------------------------

    rack = warehouse.get_rack(product.rack_id)

    px = product.x
    py = product.y

    # ---------------------------------------------------------------
    # 2. Validar que el producto realmente pertenece a ese rack
    # ---------------------------------------------------------------

    if not rack.contains_cell(px, py):
        raise ValueError(
            f"El producto '{product.product_id}' está ubicado en "
            f"({px},{py}), pero esa celda no pertenece al rack "
            f"'{rack.rack_id}'."
        )

    # Según la consigna, una de las dimensiones del rack debe ser 2.
    if rack.ancho != 2 and rack.alto != 2:
        raise ValueError(
            f"El rack '{rack.rack_id}' no tiene una dimensión igual a 2 "
            f"(ancho={rack.ancho}, alto={rack.alto})."
        )

    candidates: list[tuple[int, int]] = []

    # ---------------------------------------------------------------
    # 3. Rack vertical: ancho == 2
    # ---------------------------------------------------------------

    if rack.ancho == 2:

        # Producto en la cara izquierda
        if px == rack.x:
            candidates.append(
                (px - 1, py)
            )

        # Producto en la cara derecha
        if px == rack.x + rack.ancho - 1:
            candidates.append(
                (px + 1, py)
            )

    # ---------------------------------------------------------------
    # 4. Rack horizontal: alto == 2
    # ---------------------------------------------------------------

    if rack.alto == 2:

        # Producto en la cara inferior
        if py == rack.y:
            candidates.append(
                (px, py - 1)
            )

        # Producto en la cara superior
        if py == rack.y + rack.alto - 1:
            candidates.append(
                (px, py + 1)
            )

    # ---------------------------------------------------------------
    # 5. Filtrar candidatos
    # ---------------------------------------------------------------

    W = warehouse.ancho_x
    H = warehouse.largo_y

    cells: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for cell in candidates:

        cx, cy = cell

        # Fuera del Warehouse
        if not (0 <= cx < W and 0 <= cy < H):
            continue

        # Debe ser realmente una celda transitable del Graph
        if not graph.has_node(cell):
            continue

        # Evitar duplicados
        if cell not in seen:
            cells.append(cell)
            seen.add(cell)

    return cells


# ===========================================================================
# 2. Camino mediante BFS desde una posición hasta un producto
# ===========================================================================

def path_to_product_bfs(
    graph: Graph,
    source: tuple[int, int],
    product: "Product",
    warehouse: "Warehouse",
) -> tuple[
    list[tuple[int, int]],
    float,
    tuple[int, int] | None,
]:
    if not graph.has_node(source):
        raise KeyError(
            f"La posición del picker {source} "
            f"no es un nodo del grafo."
        )

    # ---------------------------------------------------------------
    # Obtener las celdas desde las cuales se puede recoger
    # físicamente el producto
    # ---------------------------------------------------------------

    targets = pickup_cells(
        product,
        warehouse,
        graph,
    )

    if not targets:
        raise ValueError(
            f"El producto '{product.product_id}' ubicado en "
            f"({product.x},{product.y},{product.z}) no tiene "
            f"ninguna celda válida de recogida."
        )


    path, distance, reached_target = bfs_to_any(
        graph,
        source,
        set(targets),
    )

    return path, distance, reached_target

# ===========================================================================
# 3. Heurística espacial del Warehouse
# ===========================================================================


def manhattan(source: tuple[int, int], target: tuple[int, int]) -> int:
    """Distancia mínima sin obstáculos para movimientos ortogonales de costo 1."""
    return abs(source[0] - target[0]) + abs(source[1] - target[1])


# ===========================================================================
# 4. Camino mediante A* desde una posición hasta un producto
# ===========================================================================


def path_to_product_astar(
    graph: Graph,
    source: tuple[int, int],
    product: "Product",
    warehouse: "Warehouse",
) -> tuple[
    list[tuple[int, int]],
    float,
    tuple[int, int] | None,
]:
    if not graph.has_node(source):
        raise KeyError(
            f"La posición del picker {source} "
            f"no es un nodo del grafo."
        )

    # ---------------------------------------------------------------
    # Obtener las celdas desde las cuales se puede recoger
    # físicamente el producto
    # ---------------------------------------------------------------

    targets = pickup_cells(
        product,
        warehouse,
        graph,
    )

    if not targets:
        raise ValueError(
            f"El producto '{product.product_id}' ubicado en "
            f"({product.x},{product.y},{product.z}) no tiene "
            f"ninguna celda válida de recogida."
        )


    path, distance, reached_target = astar_to_any(
        graph,
        source,
        set(targets),
        manhattan,
    )

    return path, distance, reached_target
