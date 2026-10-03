from enum import Enum
from models.product import Product


class OrderStatus(Enum):
    """Estados posibles de un pedido, según las consignas."""
    PENDIENTE      = "PENDIENTE"
    EN_WAVE        = "EN_WAVE"
    EN_PREPARACION = "EN_PREPARACION"
    PREPARADO      = "PREPARADO"


class OrderItem:
    """
    Representa una línea dentro de un pedido:
    un producto específico y la cantidad solicitada.
    """

    def __init__(self, product: Product, quantity: int):
        if quantity <= 0:
            raise ValueError("La cantidad solicitada debe ser mayor a 0.")
        self.product = product
        self.quantity = quantity

    def to_dict(self) -> dict:
        return {
            "product_id": self.product.product_id,
            "quantity": self.quantity,
        }

    def __repr__(self) -> str:
        return f"OrderItem(product={self.product.product_id!r}, qty={self.quantity})"


class Order:
    """
    Representa un pedido realizado por un cliente.

    Atributos:
        order_id  (str)         : Identificador único del pedido.
        items     (list[OrderItem]): Productos solicitados con sus cantidades.
        priority  (int)         : Prioridad entre 1 (mínima) y 5 (máxima).
        status    (OrderStatus) : Estado actual del pedido.
    """

    MIN_PRIORITY = 1
    MAX_PRIORITY = 5

    def __init__(self, order_id: str, items: list, priority: int):
        if not (self.MIN_PRIORITY <= priority <= self.MAX_PRIORITY):
            raise ValueError(
                f"La prioridad debe estar entre {self.MIN_PRIORITY} y "
                f"{self.MAX_PRIORITY}: recibido={priority}"
            )
        if not items:
            raise ValueError("Un pedido debe contener al menos un producto.")

        self.order_id = order_id
        self.items: list[OrderItem] = items
        self.priority = priority
        self.status = OrderStatus.PENDIENTE

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_locations(self) -> list[tuple]:
        """Retorna la lista de ubicaciones (x, y, z) de todos los productos del pedido."""
        return [item.product.location for item in self.items]

    def total_units(self) -> int:
        """Cantidad total de unidades solicitadas en el pedido."""
        return sum(item.quantity for item in self.items)

    def total_products(self) -> int:
        """Cantidad de líneas de producto distintas en el pedido."""
        return len(self.items)

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def mark_in_wave(self) -> None:
        if self.status != OrderStatus.PENDIENTE:
            raise ValueError(
                f"Solo pedidos PENDIENTE pueden entrar a una wave. "
                f"Estado actual: {self.status.value}"
            )
        self.status = OrderStatus.EN_WAVE

    def mark_in_preparation(self) -> None:
        if self.status != OrderStatus.EN_WAVE:
            raise ValueError(
                f"El pedido debe estar EN_WAVE para pasar a EN_PREPARACION. "
                f"Estado actual: {self.status.value}"
            )
        self.status = OrderStatus.EN_PREPARACION

    def mark_prepared(self) -> None:
        if self.status != OrderStatus.EN_PREPARACION:
            raise ValueError(
                f"El pedido debe estar EN_PREPARACION para marcarse como PREPARADO. "
                f"Estado actual: {self.status.value}"
            )
        self.status = OrderStatus.PREPARADO

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa el pedido a diccionario (para persistencia JSON)."""
        return {
            "order_id": self.order_id,
            "items": [item.to_dict() for item in self.items],
            "priority": self.priority,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict, product_registry: dict) -> "Order":
        """
        Reconstruye un Order desde un diccionario.

        Args:
            data             : Diccionario con los datos del pedido.
            product_registry : Diccionario {product_id: Product} del warehouse.
        """
        items = []
        for item_data in data["items"]:
            pid = item_data["product_id"]
            if pid not in product_registry:
                raise KeyError(f"Producto '{pid}' no encontrado en el registro.")
            items.append(OrderItem(product_registry[pid], item_data["quantity"]))

        order = cls(
            order_id=data["order_id"],
            items=items,
            priority=data["priority"],
        )
        order.status = OrderStatus(data["status"])
        return order

    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id!r}, priority={self.priority}, "
            f"status={self.status.value}, items={len(self.items)})"
        )
