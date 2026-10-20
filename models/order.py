from enum import Enum
from models.product import Product


class OrderStatus(Enum):
    """Estados posibles de un pedido."""
    PENDIENTE      = "PENDIENTE"
    PARCIAL        = "PARCIAL"       # algunos ítems asignados a waves, otros pendientes
    EN_WAVE        = "EN_WAVE"       # todos los ítems asignados a una o más waves
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
        order_id         (str)             : Identificador único del pedido.
        items            (list[OrderItem]) : Líneas de producto con sus cantidades (total del pedido).
        prioridad        (int)             : Prioridad de 1 (mínima) a 5 (máxima).
        status           (OrderStatus)     : Estado actual del pedido.
        items_pendientes (list[OrderItem]) : Ítems que todavía no han sido asignados a ninguna wave.
                                             Inicialmente es una copia de items. Se vacía conforme
                                             los ítems se asignan parcialmente a waves.
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
        # items_pendientes rastrea qué ítems todavía no fueron asignados a ninguna wave.
        # Es una lista de referencias a los mismos OrderItem que componen el pedido.
        self.items_pendientes: list[OrderItem] = list(items)

    # ------------------------------------------------------------------
    # Consultas totales (sobre el pedido completo)
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
    # Consultas sobre ítems pendientes
    # ------------------------------------------------------------------

    def unidades_pendientes(self) -> int:
        """Cantidad de unidades aún no asignadas a ninguna wave."""
        return sum(item.cantidad for item in self.items_pendientes)

    def lineas_pendientes(self) -> int:
        """Número de líneas de producto aún no asignadas."""
        return len(self.items_pendientes)

    def peso_pendiente(self) -> float:
        """Peso de los ítems aún no asignados a ninguna wave (kg)."""
        return sum(item.peso_total for item in self.items_pendientes)

    def esta_completamente_asignado(self) -> bool:
        """True si todos los ítems del pedido han sido asignados a alguna wave."""
        return len(self.items_pendientes) == 0

    # ------------------------------------------------------------------
    # Asignación parcial de ítems
    # ------------------------------------------------------------------

    def assign_items(self, items: list) -> None:
        """
        Marca una lista de OrderItem como asignados a una wave, retirándolos
        de items_pendientes y actualizando el estado del pedido.

        Args:
            items: Subconjunto de items_pendientes a asignar. Deben ser
                   referencias exactas a objetos presentes en items_pendientes.

        Raises:
            ValueError: Si algún ítem no está en items_pendientes o el pedido
                        no está en estado PENDIENTE o PARCIAL.
        """
        if self.status not in (OrderStatus.PENDIENTE, OrderStatus.PARCIAL):
            raise ValueError(
                f"Solo pedidos PENDIENTE o PARCIAL pueden tener ítems asignados. "
                f"Estado actual de '{self.order_id}': {self.status.value}"
            )
        for item in items:
            if item not in self.items_pendientes:
                raise ValueError(
                    f"El ítem '{item.product.product_id}' no está en los ítems "
                    f"pendientes del pedido '{self.order_id}'."
                )
        for item in items:
            self.items_pendientes.remove(item)

        # Actualizar estado según cobertura
        if self.esta_completamente_asignado():
            self.status = OrderStatus.EN_WAVE
        else:
            self.status = OrderStatus.PARCIAL

    def reset_assignment(self) -> None:
        """
        Revierte la asignación parcial o total, devolviendo todos los ítems
        a items_pendientes y el estado a PENDIENTE.

        Solo válido si el pedido no ha iniciado preparación.

        Raises:
            ValueError: Si el pedido ya está EN_PREPARACION o PREPARADO.
        """
        if self.status in (OrderStatus.EN_PREPARACION, OrderStatus.PREPARADO):
            raise ValueError(
                f"No se puede revertir un pedido que ya inició preparación. "
                f"Estado actual de '{self.order_id}': {self.status.value}"
            )
        self.items_pendientes = list(self.items)
        self.status = OrderStatus.PENDIENTE

    # ------------------------------------------------------------------
    # Cambios de estado completo (sin división)
    # ------------------------------------------------------------------

    def mark_in_wave(self) -> None:
        """
        Transiciona el pedido a EN_WAVE (todos sus ítems asignados a una wave).

        Raises:
            ValueError: Si el pedido no está en estado PENDIENTE.
        """
        if self.status != OrderStatus.PENDIENTE:
            raise ValueError(
                f"Solo pedidos PENDIENTE pueden entrar a una wave de forma completa. "
                f"Estado actual: {self.status.value}"
            )
        self.items_pendientes = []
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
            f"status={self.status.value}, items={len(self.items)}, "
            f"pendientes={self.lineas_pendientes()})"
        )
