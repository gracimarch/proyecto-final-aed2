from enum import Enum
from models.order import Order, OrderStatus


class WaveStatus(Enum):
    ABIERTA      = "ABIERTA"       # recibiendo pedidos
    EN_PROCESO   = "EN_PROCESO"    # el picker está recorriendo
    COMPLETADA   = "COMPLETADA"    # todos los pedidos preparados


class Wave:
    def __init__(self, wave_id: str, max_orders: int, max_units: int):
        if max_orders <= 0:
            raise ValueError("max_orders debe ser mayor a 0.")
        if max_units <= 0:
            raise ValueError("max_units debe ser mayor a 0.")

        self.wave_id = wave_id
        self.max_orders = max_orders
        self.max_units = max_units
        self.orders: list[Order] = []
        self.status = WaveStatus.ABIERTA
        self.route: list = []          # se asigna al ejecutar el pathfinding

    def current_orders(self) -> int:
        return len(self.orders)

    def current_units(self) -> int:
        return sum(order.total_units() for order in self.orders)

    def has_capacity_for(self, order: Order) -> bool:
        if self.status != WaveStatus.ABIERTA:
            return False
        if self.current_orders() >= self.max_orders:
            return False
        if self.current_units() + order.total_units() > self.max_units:
            return False
        return True

    # devolver todas las ubicaciones (x, y, z) requeridas por los pedidos de la wave
    def get_all_locations(self) -> list[tuple]:
        seen = set()
        locations = []
        for order in self.orders:
            for loc in order.get_locations():
                if loc not in seen:
                    seen.add(loc)
                    locations.append(loc)
        return locations

    def add_order(self, order: Order) -> None:
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
        self.route = route


    # cambios de estado
    def start(self) -> None:
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
        if self.status != WaveStatus.EN_PROCESO:
            raise ValueError(
                f"La wave '{self.wave_id}' debe estar EN_PROCESO para completarse."
            )
        self.status = WaveStatus.COMPLETADA
        for order in self.orders:
            order.mark_prepared()


    # serialización
    def to_dict(self) -> dict:
        return {
            "wave_id": self.wave_id,
            "max_orders": self.max_orders,
            "max_units": self.max_units,
            "status": self.status.value,
            "order_ids": [o.order_id for o in self.orders],
            "route": self.route,
        }

    @classmethod
    def from_dict(cls, data: dict, order_registry: dict) -> "Wave":
        wave = cls(
            wave_id=data["wave_id"],
            max_orders=data["max_orders"],
            max_units=data["max_units"],
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
            f"Wave(id={self.wave_id!r}, orders={self.current_orders()}/"
            f"{self.max_orders}, units={self.current_units()}/{self.max_units}, "
            f"status={self.status.value})"
        )
