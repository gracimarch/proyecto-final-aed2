from enum import Enum
from models.product import Product


class OrderStatus(Enum):
    """Estados posibles de un pedido."""
    PENDIENTE      = "PENDIENTE"
    EN_WAVE        = "EN_WAVE"
    EN_PREPARACION = "EN_PREPARACION"
    PREPARADO      = "PREPARADO"


class OrderItem:
    """
    Línea de un pedido: un producto específico y la cantidad solicitada.

    Atributos:
        product  (Product) : Producto solicitado.
        cantidad (int)     : Cantidad de unidades requeridas.
    """

    def __init__(self, product: Product, cantidad: int):
        if cantidad <= 0:
            raise ValueError("La cantidad solicitada debe ser mayor a 0.")
        self.product = product
        self.cantidad = cantidad

    @property
    def peso_total(self) -> float:
        """Peso total de esta línea (peso unitario × cantidad)."""
        return self.product.peso_kg * self.cantidad

    def to_dict(self) -> dict:
        """
        Serializa la línea al formato del escenario JSON.
        """
        return {
            "producto_id": self.product.product_id,
            "cantidad": self.cantidad,
        }

    def __repr__(self) -> str:
        return f"OrderItem(product={self.product.product_id!r}, cantidad={self.cantidad})"


class Order:
    """
    Pedido realizado por un cliente.

    Atributos:
        order_id (str)             : Identificador único del pedido.
        items    (list[OrderItem]) : Líneas de producto con sus cantidades.
        prioridad (int)            : Prioridad de 1 (mínima) a 5 (máxima).
        status   (OrderStatus)     : Estado actual del pedido.
    """

    MIN_PRIORIDAD = 1
    MAX_PRIORIDAD = 5

    def __init__(self, order_id: str, items: list, prioridad: int):
        if not (self.MIN_PRIORIDAD <= prioridad <= self.MAX_PRIORIDAD):
            raise ValueError(
                f"La prioridad debe estar entre {self.MIN_PRIORIDAD} y "
                f"{self.MAX_PRIORIDAD}: recibido={prioridad}"
            )
        if not items:
            raise ValueError("Un pedido debe contener al menos un producto.")

        self.order_id = order_id
        self.items: list[OrderItem] = items
        self.prioridad = prioridad
        self.status = OrderStatus.PENDIENTE

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_locations(self) -> list[tuple]:
        """Retorna la lista de ubicaciones (x, y, z) de todos los productos del pedido."""
        return [tuple(item.product.location) for item in self.items]

    def total_unidades(self) -> int:
        """Cantidad total de unidades solicitadas en el pedido."""
        return sum(item.cantidad for item in self.items)

    def total_lineas(self) -> int:
        """Cantidad de líneas de producto distintas en el pedido."""
        return len(self.items)

    def peso_total(self) -> float:
        """Peso total de todos los items del pedido (kg)."""
        return sum(item.peso_total for item in self.items)

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def mark_in_wave(self) -> None:
        """
        Transiciona el pedido a EN_WAVE.

        Raises:
            ValueError: Si el pedido no está en estado PENDIENTE.
        """
        if self.status != OrderStatus.PENDIENTE:
            raise ValueError(
                f"Solo pedidos PENDIENTE pueden entrar a una wave. "
                f"Estado actual: {self.status.value}"
            )
        self.status = OrderStatus.EN_WAVE

    def mark_in_preparation(self) -> None:
        """
        Transiciona el pedido a EN_PREPARACION.

        Raises:
            ValueError: Si el pedido no está en estado EN_WAVE.
        """
        if self.status != OrderStatus.EN_WAVE:
            raise ValueError(
                f"El pedido debe estar EN_WAVE para pasar a EN_PREPARACION. "
                f"Estado actual: {self.status.value}"
            )
        self.status = OrderStatus.EN_PREPARACION

    def mark_prepared(self) -> None:
        """
        Transiciona el pedido a PREPARADO.

        Raises:
            ValueError: Si el pedido no está en estado EN_PREPARACION.
        """
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
        """
        Serializa el pedido al formato del escenario JSON.
        """
        return {
            "id": self.order_id,
            "prioridad": self.prioridad,
            "estado": self.status.value,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict, product_registry: dict) -> "Order":
        """
        Reconstruye un Order desde un diccionario en formato de escenario JSON.

        Args:
            data             : Diccionario con los campos id, prioridad, estado e items.
            product_registry : Diccionario {product_id: Product} del warehouse.

        Raises:
            KeyError: Si algún producto referenciado en los items no existe en el registro.
        """
        items = []
        for item_data in data["items"]:
            pid = item_data["producto_id"]
            if pid not in product_registry:
                raise KeyError(f"Producto '{pid}' no encontrado en el registro.")
            items.append(OrderItem(product_registry[pid], item_data["cantidad"]))

        order = cls(
            order_id=data["id"],
            items=items,
            prioridad=data["prioridad"],
        )
        order.status = OrderStatus(data["estado"])
        return order

    def __repr__(self) -> str:
        return (
            f"Order(id={self.order_id!r}, prioridad={self.prioridad}, "
            f"status={self.status.value}, items={len(self.items)})"
        )
