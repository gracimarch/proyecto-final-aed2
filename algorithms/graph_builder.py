from __future__ import annotations

from models.warehouse import Warehouse
from algorithms.graph import Graph


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Las cuatro direcciones ortogonales: (dx, dy, nombre)
_DIRECTIONS = ((0, 1), (0, -1), (1, 0), (-1, 0))

# Dirección longitudinal positiva de cada sentido
_LONGITUDINAL = {
    "N": (0, 1),
    "S": (0, -1),
    "E": (1, 0),
    "O": (-1, 0),
}

# Ejes: para N/S el eje longitudinal es Y; para E/O es X
_LONGITUDINAL_AXIS = {
    "N": "y",
    "S": "y",
    "E": "x",
    "O": "x",
    "AMBOS": None,
}


# ---------------------------------------------------------------------------
# Estructuras auxiliares internas
# ---------------------------------------------------------------------------

class _CellInfo:
    """
    Información precalculada de una celda (x, y) del warehouse.

    Atributos
    ---------
    transitable : bool
        True si la celda puede ser pisada por un picker.
    sentido : str
        'N', 'S', 'E', 'O' o 'AMBOS'.
    aisle_index : int | None
        Índice del pasillo declarado al que pertenece la celda,
        o None si es un pasillo implícito (sentido AMBOS).
    """

    __slots__ = ("transitable", "sentido", "aisle_index")

    def __init__(self, transitable: bool, sentido: str, aisle_index):
        self.transitable: bool = transitable
        self.sentido: str = sentido
        self.aisle_index = aisle_index  # int | None


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def generate_graph(warehouse: Warehouse) -> Graph:

    W = warehouse.ancho_x
    H = warehouse.largo_y

    # ------------------------------------------------------------------
    # Paso 1 – Expandir geometría: celdas bloqueadas
    # ------------------------------------------------------------------
    # Una celda está bloqueada si contiene un rack, una puerta o una zona
    # de despacho.  Usamos un set para O(1) de consulta.

    blocked: set[tuple[int, int]] = set()

    for rack in warehouse.racks.values():
        for dx in range(rack.ancho):
            for dy in range(rack.alto):
                blocked.add((rack.x + dx, rack.y + dy))

    for door in warehouse.doors:
        blocked.add((door.position[0], door.position[1]))

    for zone in warehouse.dispatch_zones:
        for dx in range(zone.ancho):
            for dy in range(zone.alto):
                blocked.add((zone.x + dx, zone.y + dy))

    # ------------------------------------------------------------------
    # Paso 2 – Precalcular _CellInfo para cada celda
    # ------------------------------------------------------------------
    # Construimos un dict plano (x, y) → _CellInfo.
    # Para cada pasillo declarado expandimos su rectángulo de celdas
    # y marcamos sentido + aisle_index.
    # El orden importa: si hay solapamiento (inválido según consigna pero
    # nos protegemos) prevalece el último pasillo en la lista.

    # Primero inicializamos todas las celdas como "AMBOS" y no bloqueadas
    cell_info: dict[tuple[int, int], _CellInfo] = {}

    # Expandimos los pasillos declarados primero
    aisles = warehouse.aisles  # tuple de Aisle
    for idx, aisle in enumerate(aisles):
        sentido = aisle.sentido
        for dx in range(aisle.ancho):
            for dy in range(aisle.alto):
                cx, cy = aisle.x + dx, aisle.y + dy
                if 0 <= cx < W and 0 <= cy < H:
                    transitable = (cx, cy) not in blocked
                    cell_info[(cx, cy)] = _CellInfo(transitable, sentido, idx)

    # Las celdas no cubiertas por ningún pasillo declarado son AMBOS implícito
    # Se crean bajo demanda en el paso 3 para evitar iterar W×H dos veces.

    # ------------------------------------------------------------------
    # Paso 3 – Crear nodos (celdas transitables)
    # ------------------------------------------------------------------

    graph = Graph(directed=True)

    for y in range(H):
        for x in range(W):
            cell = (x, y)
            if cell in cell_info:
                info = cell_info[cell]
            else:
                # Celda fuera de todo pasillo declarado
                transitable = cell not in blocked
                info = _CellInfo(transitable, "AMBOS", None)
                cell_info[cell] = info

            if info.transitable:
                graph.add_node(cell)

    # ------------------------------------------------------------------
    # Paso 4 – Crear aristas entre vecinos válidos
    # ------------------------------------------------------------------

    for node in graph.nodes():
        x, y = node
        origin_info = cell_info[(x, y)]

        for dx, dy in _DIRECTIONS:
            nx, ny = x + dx, y + dy

            # Condición 1: dentro de las dimensiones
            if not (0 <= nx < W and 0 <= ny < H):
                continue

            dest = (nx, ny)

            # Condición 2: destino transitable
            dest_info = cell_info[dest]
            if not dest_info.transitable:
                continue

            # Condición 3 + 4: validar con las reglas de circulación
            if _movement_allowed(origin_info, dest_info, dx, dy):
                graph.add_edge(node, dest, 1.0)

    return graph


# ---------------------------------------------------------------------------
# Lógica de validación de movimiento
# ---------------------------------------------------------------------------

def _movement_allowed(
    origin: _CellInfo,
    dest: _CellInfo,
    dx: int,
    dy: int,
) -> bool:
    """
    Determina si el movimiento (dx, dy) desde `origin` hacia `dest` es válido.

    Reglas aplicadas en orden:
    1. Regla del origen: el sentido del origen permite esta dirección.
    2. Regla de entrada al destino: si el destino tiene sentido unidireccional,
       no se puede entrar en su dirección contraria.

    Parámetros
    ----------
    origin : _CellInfo  – info de la celda de origen.
    dest   : _CellInfo  – info de la celda de destino.
    dx, dy : int        – desplazamiento (uno de ellos es 0).
    """
    # ---- Regla del origen -----------------------------------------------
    if not _origin_allows(origin, dest, dx, dy):
        return False

    # ---- Regla de entrada al destino ------------------------------------
    if dest.sentido != "AMBOS":
        if not _can_enter(dest, dx, dy):
            return False

    return True


def _origin_allows(
    origin: _CellInfo,
    dest: _CellInfo,
    dx: int,
    dy: int,
) -> bool:
    """
    ¿El sentido del pasillo de origen permite el movimiento (dx, dy)?

    AMBOS → siempre sí.
    N/S   → longitudinal (dy≠0) debe coincidir; lateral (dx≠0) sólo si
             el destino está en el mismo pasillo declarado o es AMBOS.
    E/O   → longitudinal (dx≠0) debe coincidir; lateral (dy≠0) sólo si
             el destino está en el mismo pasillo declarado o es AMBOS.
    """
    sentido = origin.sentido

    if sentido == "AMBOS":
        return True

    long_dir = _LONGITUDINAL[sentido]

    if (dx, dy) == long_dir:
        # Movimiento en la dirección longitudinal correcta → siempre OK
        return True

    if (dx, dy) == (-long_dir[0], -long_dir[1]):
        # Movimiento longitudinal contrario → prohibido
        return False

    # Movimiento lateral (perpendicular al sentido)
    # Permitido si el destino pertenece al mismo pasillo declarado
    # o al AMBOS (implícito o declarado).
    if dest.sentido == "AMBOS":
        return True
    if dest.aisle_index == origin.aisle_index:
        return True
    # El destino es un pasillo distinto y tiene sentido; el movimiento
    # lateral desde aquí estaría "saliendo" de este pasillo hacia otro.
    # Se permite si ese pasillo destino también lo permite (evaluado en
    # _can_enter).  Aquí sólo restringimos la salida lateral hacia un
    # pasillo diferente si el sentido destino es perpendicular al nuestro
    # y va en dirección contraria (eso lo maneja _can_enter).
    return True


def _can_enter(dest: _CellInfo, dx: int, dy: int) -> bool:
    """
    ¿Se puede entrar en la celda `dest` llegando desde la dirección (dx, dy)?

    Para un pasillo unidireccional no se puede entrar en sentido contrario
    al longitudinal, y tampoco "entrar lateralmente" a un pasillo con
    sentido diferente al movimiento si eso viola la circulación.

    Un pasillo N prohíbe entrar por (0,-1) (venimos de y+1 hacia y, es decir
    moviéndonos en -y, contrario a N).
    """
    sentido = dest.sentido
    if sentido == "AMBOS":
        return True

    long_dir = _LONGITUDINAL[sentido]
    axis = _LONGITUDINAL_AXIS[sentido]

    if axis == "y":
        # Pasillo N o S: el eje longitudinal es Y
        if dy != 0:
            # Movimiento longitudinal: debe coincidir con el sentido
            return (dx, dy) == long_dir
        # Movimiento lateral (dx≠0): siempre permitido entrar lateralmente
        return True
    else:
        # Pasillo E u O: el eje longitudinal es X
        if dx != 0:
            # Movimiento longitudinal: debe coincidir con el sentido
            return (dx, dy) == long_dir
        # Movimiento lateral (dy≠0): siempre permitido entrar lateralmente
        return True