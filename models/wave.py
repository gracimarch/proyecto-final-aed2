from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
from models.order import Order, OrderStatus

if TYPE_CHECKING:
    from models.warehouse import Picker


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
        wave_id          (str)           : Identificador de la wave.
        max_pedidos      (int)           : Cantidad máxima de pedidos que puede contener.
        max_productos    (int)           : Cantidad máxima de unidades totales de producto.
        orders           (list[Order])   : Pedidos asignados a esta wave.
        status           (WaveStatus)    : Estado actual de la wave.
        route            (list)          : Secuencia de nodos del recorrido calculado
                                           por el algoritmo de pathfinding.
        picker           (Picker | None) : Picker asignado a la wave para prepararla.
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
        self.picker: Picker | None = None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def current_pedidos(self) -> int:
        """Cantidad de pedidos asignados actualmente."""
        return len(self.orders)

    def current_unidades(self) -> int:
        """Total de unidades de producto asignadas actualmente."""
        return sum(order.total_unidades() for order in self.orders)

    def peso_total(self) -> float:
        """Peso total acumulado de todos los pedidos en la wave (kg)."""
        return sum(order.peso_total() for order in self.orders)

    def has_capacity_for(self, order: Order, max_peso: float | None = None) -> bool:
        """
        Devuelve True si la wave puede aceptar el pedido sin superar
        los límites de pedidos, unidades y peso, y está en estado ABIERTA.

        Args:
            order: Pedido a evaluar.
            max_peso: Límite de peso máximo permitido (kg). Si es None, utiliza
                      la capacidad del picker asignado (si existe).
        """
        if self.status != WaveStatus.ABIERTA:
            return False
        if self.current_pedidos() >= self.max_pedidos:
            return False
        if self.current_unidades() + order.total_unidades() > self.max_productos:
            return False

        limite_peso = max_peso if max_peso is not None else (
            self.picker.capacidad_carga_kg if self.picker else None
        )
        if limite_peso is not None and (self.peso_total() + order.peso_total() > limite_peso):
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

    def add_order(self, order: Order, max_peso: float | None = None) -> None:
        """
        Agrega un pedido a la wave.

        Args:
            order: Pedido en estado PENDIENTE.
            max_peso: Límite opcional de peso máximo (kg).

        Raises:
            ValueError: Si no hay capacidad o el pedido no está en estado PENDIENTE.
        """
        if not self.has_capacity_for(order, max_peso=max_peso):
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

    def assign_picker(self, picker: "Picker") -> None:
        """
        Asigna un picker a la wave si soporta el peso total acumulado.

        Raises:
            ValueError: Si la wave ya tiene picker asignado o el peso total
                        supera la capacidad del picker.
        """
        if self.picker is not None:
            raise ValueError(
                f"La wave '{self.wave_id}' ya tiene asignado al picker '{self.picker.picker_id}'."
            )
        if self.peso_total() > picker.capacidad_carga_kg:
            raise ValueError(
                f"El peso total de la wave ({self.peso_total()} kg) supera la capacidad "
                f"del picker '{picker.picker_id}' ({picker.capacidad_carga_kg} kg)."
            )
        self.picker = picker
        picker.assign_wave(self.wave_id)

    def set_route(self, route: list) -> None:
        """Asigna el recorrido calculado a la wave."""
        self.route = route

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Inicia la preparación de la wave, transicionando todos sus pedidos
        a EN_PREPARACION. Requiere que la wave tenga un picker asignado.

        Raises:
            ValueError: Si la wave no está ABIERTA, no tiene pedidos o no tiene picker asignado.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        if not self.orders:
            raise ValueError("La wave no tiene pedidos.")
        if self.picker is None:
            raise ValueError(
                f"La wave '{self.wave_id}' debe tener un picker asignado para iniciar la preparación."
            )
        self.status = WaveStatus.EN_PROCESO
        for order in self.orders:
            order.mark_in_preparation()

    def complete(self) -> None:
        """
        Marca la wave como completada, todos sus pedidos como PREPARADO
        y libera al picker asignado.

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
        if self.picker is not None:
            self.picker.release()

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        Serializa la wave a un diccionario para persistencia.
        """
        return {
            "wave_id": self.wave_id,
            "max_pedidos": self.max_pedidos,
            "max_productos": self.max_productos,
            "status": self.status.value,
            "picker_id": self.picker.picker_id if self.picker else None,
            "order_ids": [o.order_id for o in self.orders],
            "route": self.route,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        order_registry: dict,
        picker_registry: dict | None = None,
    ) -> "Wave":
        """
        Reconstruye una Wave desde un diccionario serializado.

        Args:
            data           : Diccionario con los campos de la wave.
            order_registry : Diccionario {order_id: Order} con los pedidos del sistema.
            picker_registry: Diccionario opcional {picker_id: Picker}.

        Raises:
            KeyError: Si algún pedido o picker referenciado no existe en el registro.
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

        picker_id = data.get("picker_id")
        if picker_id and picker_registry:
            if picker_id not in picker_registry:
                raise KeyError(f"Picker '{picker_id}' no encontrado en el registro.")
            wave.assign_picker(picker_registry[picker_id])

        return wave

    def __repr__(self) -> str:
        pk_info = f", picker={self.picker.picker_id}" if self.picker else ""
        return (
            f"Wave(id={self.wave_id!r}, pedidos={self.current_pedidos()}/"
            f"{self.max_pedidos}, unidades={self.current_unidades()}/"
            f"{self.max_productos}, peso={self.peso_total():.2f}kg{pk_info}, "
            f"status={self.status.value})"
        )
