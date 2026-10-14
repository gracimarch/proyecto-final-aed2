from enum import Enum
from models.order import Order, OrderStatus


class WaveStatus(Enum):
    """Estados posibles de una wave."""
    ABIERTA    = "ABIERTA"      # recibiendo pedidos
    EN_PROCESO = "EN_PROCESO"   # picker recorriendo el warehouse
    COMPLETADA = "COMPLETADA"   # todos los pedidos preparados


class Wave:
    """
    Conjunto de pedidos que se preparan conjuntamente en una misma pasada
    del picker por el warehouse.

    Atributos:
        wave_id          (str)         : Identificador de la wave.
        max_pedidos      (int)         : Cantidad máxima de pedidos que puede contener.
        max_productos    (int)         : Cantidad máxima de unidades totales de producto.
        orders           (list[Order]) : Pedidos asignados a esta wave.
        status           (WaveStatus)  : Estado actual de la wave.
        route            (list)        : Secuencia de nodos del recorrido calculado
                                         por el algoritmo de pathfinding.
    """

    def __init__(self, wave_id: str, max_pedidos: int, max_productos: int):
        if max_pedidos <= 0:
            raise ValueError("max_pedidos debe ser mayor a 0.")
        if max_productos <= 0:
            raise ValueError("max_productos debe ser mayor a 0.")

        self.wave_id = wave_id
        self.max_pedidos = max_pedidos
        self.max_productos = max_productos
        self.orders: list[Order] = []
        self.status = WaveStatus.ABIERTA
        self.route: list = []

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def current_pedidos(self) -> int:
        """Cantidad de pedidos asignados actualmente."""
        return len(self.orders)

    def current_unidades(self) -> int:
        """Total de unidades de producto asignadas actualmente."""
        return sum(order.total_unidades() for order in self.orders)

    def has_capacity_for(self, order: Order) -> bool:
        """
        Devuelve True si la wave puede aceptar el pedido sin superar
        los límites de pedidos y unidades, y está en estado ABIERTA.
        """
        if self.status != WaveStatus.ABIERTA:
            return False
        if self.current_pedidos() >= self.max_pedidos:
            return False
        if self.current_unidades() + order.total_unidades() > self.max_productos:
            return False
        return True

    def get_all_locations(self) -> list[tuple]:
        """
        Retorna las ubicaciones (x, y, z) únicas requeridas por todos los
        pedidos de la wave, en el orden en que aparecen.
        """
        seen = set()
        locations = []
        for order in self.orders:
            for loc in order.get_locations():
                loc_t = tuple(loc)
                if loc_t not in seen:
                    seen.add(loc_t)
                    locations.append(loc_t)
        return locations

    # ------------------------------------------------------------------
    # Modificación
    # ------------------------------------------------------------------

    def add_order(self, order: Order) -> None:
        """
        Agrega un pedido a la wave.

        Raises:
            ValueError: Si no hay capacidad o el pedido no está en estado PENDIENTE.
        """
        if not self.has_capacity_for(order):
            raise ValueError(
                f"No hay capacidad para agregar el pedido '{order.order_id}' "
                f"a la wave '{self.wave_id}'."
            )
        if order.status != OrderStatus.PENDIENTE:
            raise ValueError(
                f"Solo pedidos PENDIENTE pueden agregarse a una wave. "
                f"Estado actual de '{order.order_id}': {order.status.value}"
            )
        order.mark_in_wave()
        self.orders.append(order)

    def set_route(self, route: list) -> None:
        """Asigna el recorrido calculado a la wave."""
        self.route = route

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Inicia la preparación de la wave, transicionando todos sus pedidos
        a EN_PREPARACION.

        Raises:
            ValueError: Si la wave no está ABIERTA o no tiene pedidos.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        if not self.orders:
            raise ValueError("La wave no tiene pedidos.")
        self.status = WaveStatus.EN_PROCESO
        for order in self.orders:
            order.mark_in_preparation()

    def complete(self) -> None:
        """
        Marca la wave como completada y todos sus pedidos como PREPARADO.

        Raises:
            ValueError: Si la wave no está EN_PROCESO.
        """
        if self.status != WaveStatus.EN_PROCESO:
            raise ValueError(
                f"La wave '{self.wave_id}' debe estar EN_PROCESO para completarse."
            )
        self.status = WaveStatus.COMPLETADA
        for order in self.orders:
            order.mark_prepared()

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serializa la wave a un diccionario para persistencia.

        Los pedidos se referencian por su id; para reconstruir la wave
        se necesita un registro de pedidos externo.
        """
        return {
            "wave_id": self.wave_id,
            "max_pedidos": self.max_pedidos,
            "max_productos": self.max_productos,
            "status": self.status.value,
            "order_ids": [o.order_id for o in self.orders],
            "route": self.route,
        }

    @classmethod
    def from_dict(cls, data: dict, order_registry: dict) -> "Wave":
        """
        Reconstruye una Wave desde un diccionario serializado.

        Args:
            data           : Diccionario con los campos de la wave.
            order_registry : Diccionario {order_id: Order} con los pedidos del sistema.

        Raises:
            KeyError: Si algún pedido referenciado no existe en el registro.
        """
        wave = cls(
            wave_id=data["wave_id"],
            max_pedidos=data["max_pedidos"],
            max_productos=data["max_productos"],
        )
        wave.status = WaveStatus(data["status"])
        wave.route = data.get("route", [])
        for oid in data.get("order_ids", []):
            if oid not in order_registry:
                raise KeyError(f"Pedido '{oid}' no encontrado en el registro.")
            wave.orders.append(order_registry[oid])
        return wave

    def __repr__(self) -> str:
        return (
            f"Wave(id={self.wave_id!r}, pedidos={self.current_pedidos()}/"
            f"{self.max_pedidos}, unidades={self.current_unidades()}/"
            f"{self.max_productos}, status={self.status.value})"
        )
