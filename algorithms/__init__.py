"""
algorithms/__init__.py

Junta en un solo lugar las funciones y clases de la carpeta algorithms/,
para poder importarlas sin nombrar el archivo de cada una:

    from algorithms import generate_graph, bfs_to_any

Funciona igual que models/__init__.py (ver la explicación ahí): los
archivos de DENTRO de algorithms/ importan directo del archivo.
"""

from algorithms.graph import (
    Graph,
    bfs_distances,
    bfs_to_any,
    bfs_shortest_path,
    astar_to_any,
    astar_shortest_path,
)
from algorithms.graph_builder import generate_graph
from algorithms.pathfinding import (
    pickup_cells,
    path_to_product_bfs,
    path_to_product_astar,
    manhattan,
)
# (Cuando subamos algorithms/routing.py, sus funciones se agregan acá.)

__all__ = [
    "Graph",
    "bfs_distances",
    "bfs_to_any",
    "bfs_shortest_path",
    "astar_to_any",
    "astar_shortest_path",
    "generate_graph",
    "pickup_cells",
    "path_to_product_bfs",
    "path_to_product_astar",
    "manhattan",
]
