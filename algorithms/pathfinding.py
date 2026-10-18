from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from algorithms.graph import Graph

if TYPE_CHECKING:
    from models.warehouse import Warehouse
    from models.product import Product


# ===========================================================================
# 1. Reconstrucción de camino
# ===========================================================================

def _reconstruct(
    prev: dict[tuple[int, int], tuple[int, int] | None],
    target: tuple[int, int],
) -> tuple[list[tuple[int, int]], int]:
 
    path: list[tuple[int, int]] = []

    node: tuple[int, int] | None = target

    while node is not None:
        path.append(node)
        node = prev[node]

    path.reverse()

    return path, len(path) - 1


# ===========================================================================
# 2. BFS interno hacia uno o varios destinos
# ===========================================================================

def _bfs_to_any(
    graph: Graph,
    source: tuple[int, int],
    targets: set[tuple[int, int]],
) -> tuple[
    list[tuple[int, int]],
    float,
    tuple[int, int] | None,
]:
    """
    Ejecuta BFS desde source hasta cualquiera de los nodos de targets.
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
        tuple[int, int],
        tuple[int, int] | None
    ] = {
        source: None
    }

    queue: deque[tuple[int, int]] = deque([source])

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
    source: tuple[int, int],
    target: tuple[int, int],
) -> tuple[list[tuple[int, int]], float]:
    """
    Encuentra mediante BFS el camino mínimo entre source y target.
    
    """

    if not graph.has_node(target):
        raise KeyError(
            f"Nodo destino {target} no existe en el grafo."
        )

    path, distance, _ = _bfs_to_any(
        graph,
        source,
        {target},
    )

    return path, distance


# ===========================================================================
# 4. Celdas de recogida de un producto
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
# 5. Camino desde una posición hasta un producto
# ===========================================================================

def path_to_product(
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


    path, distance, reached_target = _bfs_to_any(
        graph,
        source,
        set(targets),
    )

    return path, distance, reached_target