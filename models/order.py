"""
models/order.py

Pedidos de los clientes (consigna §5).

Un pedido tiene varias líneas (OrderItem). Cada línea recuerda en qué wave
quedó, y con eso se calcula el estado del pedido.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from models.product import Product

if TYPE_CHECKING:
    # Solo para las anotaciones de tipo. Python no ejecuta este bloque, así que
    # estos imports no pueden armar un import circular (ver GUIA.md).
    from models.wave import Wave


class OrderStatus(Enum):
    """
    Estados posibles de un pedido.

    Un Enum es una lista cerrada de valores con nombre. Se usa así:
    OrderStatus.PENDIENTE, y OrderStatus.PENDIENTE.value es el texto "PENDIENTE".
    """
    PENDIENTE      = "PENDIENTE"       # ningún ítem está en una wave
    PARCIAL        = "PARCIAL"         # algunos ítems están en waves y otros no
    EN_WAVE        = "EN_WAVE"         # todos en waves que todavía no empezaron
    EN_PREPARACION = "EN_PREPARACION"  # alguna de sus waves ya empezó
    PREPARADO      = "PREPARADO"       # todas sus waves están completadas


class OrderItem:
    """
    Línea de un pedido: un producto y la cantidad pedida.

    Atributos:
        product  (Product)     : Producto solicitado.
        cantidad (int)         : Cantidad de unidades pedidas.
        wave     (Wave o None) : Wave a la que se asignó la línea.
                                 None mientras está pendiente.
    """

    def __init__(self, product: Product, cantidad: int):
        if cantidad <= 0:
            raise ValueError("La cantidad solicitada debe ser mayor a 0.")
        self.product = product
        self.cantidad = cantidad
        self.wave = None

    @property
    def total_weight(self) -> float:
        """Peso de la línea: peso por unidad × cantidad."""
        return self.product.peso_kg * self.cantidad

    def to_dict(self) -> dict:
        return {
            "producto_id": self.product.product_id,
            "cantidad": self.cantidad,
        }

    def __repr__(self) -> str:
        return f"OrderItem(product='{self.product.product_id}', cantidad={self.cantidad})"


class Order:
    """
    Pedido realizado por un cliente.

    El estado NO se guarda en un atributo: se calcula cada vez que se pide
    (propiedad status), mirando las waves de sus ítems. Así un pedido
    repartido en dos waves recién queda PREPARADO cuando terminan las dos.

    Atributos:
        order_id  (str)             : Identificador único del pedido.
        items     (list[OrderItem]) : Líneas del pedido.
        prioridad (int)             : De 1 (mínima) a 5 (máxima).
    """

    MIN_PRIORIDAD = 1
    MAX_PRIORIDAD = 5

    def __init__(self, order_id: str, items: list[OrderItem], prioridad: int):
        if prioridad < self.MIN_PRIORIDAD or prioridad > self.MAX_PRIORIDAD:
            raise ValueError(
                f"La prioridad debe estar entre {self.MIN_PRIORIDAD} y "
                f"{self.MAX_PRIORIDAD}: recibido={prioridad}"
            )
        if len(items) == 0:
            raise ValueError("Un pedido debe contener al menos un producto.")

        self.order_id = order_id
        self.items = items
        self.prioridad = prioridad

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    @property
    def status(self) -> OrderStatus:
        """
        Estado del pedido según dónde están sus ítems.

        Se cuentan los ítems sin wave, en waves completadas y en waves que
        ya empezaron, y con esos tres números se decide el estado.

        Complejidad: O(cantidad de ítems).
        """
        sin_wave = 0
        completados = 0
        empezados = 0
        for item in self.items:
            if item.wave is None:
                sin_wave = sin_wave + 1
            else:
                if item.wave.is_completed:
                    completados = completados + 1
                if item.wave.is_started:
                    empezados = empezados + 1

        total = len(self.items)
        if sin_wave == total:
            return OrderStatus.PENDIENTE
        if sin_wave > 0:
            return OrderStatus.PARCIAL
        if completados == total:
            return OrderStatus.PREPARADO
        if empezados > 0:
            return OrderStatus.EN_PREPARACION
        return OrderStatus.EN_WAVE

    @property
    def pending_items(self) -> list[OrderItem]:
        """Ítems que todavía no tienen wave."""
        pendientes = []
        for item in self.items:
            if item.wave is None:
                pendientes.append(item)
        return pendientes

    # ------------------------------------------------------------------
    # Totales del pedido
    # ------------------------------------------------------------------

    def get_locations(self) -> list[tuple]:
        """Ubicaciones (x, y, z) de los productos del pedido."""
        ubicaciones = []
        for item in self.items:
            ubicaciones.append(tuple(item.product.location))
        return ubicaciones

    def total_units(self) -> int:
        """Cantidad total de unidades pedidas."""
        total = 0
        for item in self.items:
            total = total + item.cantidad
        return total

    def total_lines(self) -> int:
        """Cantidad de líneas (productos distintos) del pedido."""
        return len(self.items)

    def total_weight(self) -> float:
        """Peso total del pedido (kg)."""
        total = 0
        for item in self.items:
            total = total + item.total_weight
        return total

    # ------------------------------------------------------------------
    # Totales de lo que falta asignar
    # ------------------------------------------------------------------

    def pending_units(self) -> int:
        total = 0
        for item in self.pending_items:
            total = total + item.cantidad
        return total

    def pending_lines(self) -> int:
        return len(self.pending_items)

    def pending_weight(self) -> float:
        total = 0
        for item in self.pending_items:
            total = total + item.total_weight
        return total

    def is_fully_assigned(self) -> bool:
        """True si todos los ítems ya tienen wave."""
        return len(self.pending_items) == 0

    # ------------------------------------------------------------------
    # Asignación de ítems a una wave
    # ------------------------------------------------------------------

    def _owns_item(self, item: OrderItem) -> bool:
        """
        True si item es uno de los ítems de este pedido.

        Se compara con "is" (el mismo objeto) y no con "==": dos pedidos
        pueden tener ítems iguales (mismo producto y cantidad) que son
        objetos distintos.
        """
        for propio in self.items:
            if propio is item:
                return True
        return False

    def assign_items(self, items: list[OrderItem], wave: Wave) -> None:
        """
        Marca los ítems como asignados a la wave.

        Primero se validan todos y recién después se asignan, para no dejar
        el pedido a medio asignar si alguno falla.

        Raises:
            ValueError: Si algún ítem no es del pedido o ya tiene wave.
        """
        for item in items:
            if not self._owns_item(item):
                raise ValueError(
                    f"El ítem '{item.product.product_id}' no pertenece al "
                    f"pedido '{self.order_id}'."
                )
            if item.wave is not None:
                raise ValueError(
                    f"El ítem '{item.product.product_id}' del pedido '{self.order_id}' "
                    f"ya está asignado a la wave '{item.wave.wave_id}'."
                )
        for item in items:
            item.wave = wave

    # ------------------------------------------------------------------
    # Serealización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        items_dict = []
        for item in self.items:
            items_dict.append(item.to_dict())
        return {
            "id": self.order_id,
            "prioridad": self.prioridad,
            "estado": self.status.value,
            "items": items_dict,
        }

    @classmethod
    def from_dict(cls, data: dict, product_registry: dict[str, Product]) -> Order:
        """
        Crea un Order a partir del JSON del escenario.

        El campo "estado" solo se valida (que sea un estado conocido). El
        estado real se recalcula solo cuando se cargan las waves.

        Args:
            data             : Diccionario con id, prioridad, estado e items.
            product_registry : Diccionario {product_id: Product} del warehouse.

        Raises:
            KeyError:   Si un producto no existe en el warehouse.
            ValueError: Si el estado no es uno de OrderStatus.
        """
        items = []
        for item_data in data["items"]:
            pid = item_data["producto_id"]
            if pid not in product_registry:
                raise KeyError(f"Producto '{pid}' no encontrado en el registro.")
            items.append(OrderItem(product_registry[pid], item_data["cantidad"]))

        # OrderStatus("XYZ") lanza ValueError si "XYZ" no es un estado válido.
        OrderStatus(data.get("estado", "PENDIENTE"))

        return cls(order_id=data["id"], items=items, prioridad=data["prioridad"])

    def __repr__(self) -> str:
        return (
            f"Order(id='{self.order_id}', prioridad={self.prioridad}, "
            f"status={self.status.value}, items={len(self.items)}, "
            f"pendientes={self.pending_lines()})"
        )
