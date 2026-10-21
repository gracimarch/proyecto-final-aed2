from __future__ import annotations
from enum import Enum
from typing import TYPE_CHECKING
from models.order import Order, OrderItem, OrderStatus

if TYPE_CHECKING:
    from models.warehouse import Picker


class WaveStatus(Enum):
    """Estados posibles de una wave."""
    ABIERTA    = "ABIERTA"      # recibiendo pedidos/ítems
    EN_PROCESO = "EN_PROCESO"   # pickers recorriendo el warehouse
    COMPLETADA = "COMPLETADA"   # todos los pedidos preparados


class WaveOrderEntry:
    """
    Entrada interna que relaciona un pedido con el subconjunto de sus ítems
    que fueron asignados a esta wave en particular.

    Esto permite dividir un pedido entre varias waves sin duplicar datos:
    el OrderItem original permanece en Order.items; aquí solo guardamos
    referencias al subconjunto asignado a esta wave.

    Atributos:
        order  (Order)           : Pedido al que pertenecen los ítems.
        items  (list[OrderItem]) : Ítems de ese pedido incluidos en esta wave.
    """

    def __init__(self, order: Order, items: list[OrderItem]):
        self.order = order
        self.items = list(items)

    @property
    def unidades(self) -> int:
        """Total de unidades de los ítems asignados en esta wave."""
        return sum(it.cantidad for it in self.items)

    @property
    def peso(self) -> float:
        """Peso total de los ítems asignados en esta wave (kg)."""
        return sum(it.peso_total for it in self.items)

    def get_locations(self) -> list[tuple]:
        """Ubicaciones (x, y, z) de los productos de estos ítems."""
        return [tuple(it.product.location) for it in self.items]

    def __repr__(self) -> str:
        return (
            f"WaveOrderEntry(order={self.order.order_id!r}, "
            f"items={len(self.items)}, peso={self.peso:.2f}kg)"
        )


class Wave:
    """
    Conjunto de ítems de pedidos que se preparan conjuntamente en una misma
    pasada de los pickers por el warehouse.

    Un pedido puede estar dividido entre varias waves: cada wave contiene
    una parte (uno o más ítems) de ese pedido. Cada wave puede tener
    varios pickers asignados.

    Atributos:
        wave_id          (str)                  : Identificador de la wave.
        max_pedidos      (int)                  : Cantidad máxima de pedidos distintos
                                                  que pueden contribuir ítems a esta wave.
        max_productos    (int)                  : Máximo de unidades totales en la wave.
        entries          (list[WaveOrderEntry]) : Ítems de pedidos incluidos en esta wave.
        status           (WaveStatus)           : Estado actual de la wave.
        route            (list)                 : Recorrido calculado (pathfinding).
        pickers          (list[Picker])         : Pickers asignados a esta wave.
    """

    def __init__(self, wave_id: str, max_pedidos: int, max_productos: int):
        if max_pedidos <= 0:
            raise ValueError("max_pedidos debe ser mayor a 0.")
        if max_productos <= 0:
            raise ValueError("max_productos debe ser mayor a 0.")

        self.wave_id = wave_id
        self.max_pedidos = max_pedidos
        self.max_productos = max_productos
        self.entries: list[WaveOrderEntry] = []
        self.status = WaveStatus.ABIERTA
        self.route: list = []
        self.pickers: list[Picker] = []

    # ------------------------------------------------------------------
    # Retrocompatibilidad: propiedad `orders`
    # Devuelve los Order distintos que tienen al menos un ítem en la wave.
    # Facilita la integración con pathfinding sin cambiar su interfaz.
    # ------------------------------------------------------------------

    @property
    def orders(self) -> list[Order]:
        """Lista de pedidos distintos que tienen ítems asignados en esta wave."""
        seen: set[str] = set()
        result: list[Order] = []
        for entry in self.entries:
            if entry.order.order_id not in seen:
                seen.add(entry.order.order_id)
                result.append(entry.order)
        return result

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def current_pedidos(self) -> int:
        """Cantidad de pedidos distintos con ítems en la wave."""
        return len(self.orders)

    def current_unidades(self) -> int:
        """Total de unidades de producto asignadas a esta wave."""
        return sum(e.unidades for e in self.entries)

    def peso_total(self) -> float:
        """Peso total de todos los ítems en la wave (kg)."""
        return sum(e.peso for e in self.entries)

    def capacidad_pickers(self) -> float:
        """
        Suma de las capacidades de carga de todos los pickers asignados (kg).

        NOTA: Esta suma se usa como estimación de la capacidad total disponible.
        No garantiza que cualquier distribución de productos sea transportable,
        dado que cada picker solo puede cargar su propio límite individualmente.
        La distribución real de la carga entre pickers queda a cargo del módulo
        de pathfinding.
        """
        return sum(p.capacidad_carga_kg for p in self.pickers)

    def can_add_items(
        self,
        order: Order,
        items: list[OrderItem],
        max_peso: float | None = None,
    ) -> bool:
        """
        Devuelve True si la wave puede aceptar los ítems dados sin superar
        sus límites de pedidos, unidades y peso.

        Args:
            order: Pedido al que pertenecen los ítems.
            items: Subconjunto de ítems del pedido a evaluar.
            max_peso: Límite provisional de peso (kg). Si es None se ignora la restricción
                      de peso provisional (solo aplica la capacidad real de pickers ya asignados).
        """
        if self.status != WaveStatus.ABIERTA:
            return False
        if not items:
            return False

        # Si el pedido ya tiene ítems en esta wave, no cuenta como pedido nuevo
        order_already_in_wave = any(e.order.order_id == order.order_id for e in self.entries)
        if not order_already_in_wave and self.current_pedidos() >= self.max_pedidos:
            return False

        new_unidades = sum(it.cantidad for it in items)
        if self.current_unidades() + new_unidades > self.max_productos:
            return False

        nuevo_peso = sum(it.peso_total for it in items)
        if max_peso is not None and (self.peso_total() + nuevo_peso > max_peso):
            return False

        return True

    def get_all_locations(self) -> list[tuple]:
        """
        Retorna las ubicaciones (x, y, z) únicas requeridas por todos los
        ítems de la wave, en el orden en que aparecen.
        """
        seen: set[tuple] = set()
        locations: list[tuple] = []
        for entry in self.entries:
            for loc in entry.get_locations():
                if loc not in seen:
                    seen.add(loc)
                    locations.append(loc)
        return locations

    # ------------------------------------------------------------------
    # Modificación
    # ------------------------------------------------------------------

    def add_items(
        self,
        order: Order,
        items: list[OrderItem],
        max_peso: float | None = None,
    ) -> None:
        """
        Agrega un subconjunto de ítems de un pedido a la wave.

        Llama a order.assign_items(items) para actualizar el estado del pedido
        y registra la entrada en esta wave.

        Args:
            order: Pedido al que pertenecen los ítems.
            items: Ítems a asignar (deben estar en order.items_pendientes).
            max_peso: Límite provisional de peso para la validación.

        Raises:
            ValueError: Si los ítems no caben o el pedido no tiene ítems pendientes.
        """
        if not self.can_add_items(order, items, max_peso=max_peso):
            raise ValueError(
                f"No hay capacidad para agregar los ítems del pedido '{order.order_id}' "
                f"a la wave '{self.wave_id}'."
            )
        # Registrar en el pedido que estos ítems fueron asignados
        order.assign_items(items)

        # Registrar en la wave
        existing = next((e for e in self.entries if e.order.order_id == order.order_id), None)
        if existing:
            existing.items.extend(items)
        else:
            self.entries.append(WaveOrderEntry(order, items))

    def add_order(self, order: Order, max_peso: float | None = None) -> None:
        """
        Agrega todos los ítems pendientes de un pedido a la wave de una vez.
        Método de conveniencia equivalente a add_items(order, order.items_pendientes).

        Raises:
            ValueError: Si el pedido no tiene ítems pendientes o no caben.
        """
        if order.status not in (OrderStatus.PENDIENTE, OrderStatus.PARCIAL):
            raise ValueError(
                f"Solo pedidos PENDIENTE o PARCIAL pueden agregarse a una wave. "
                f"Estado actual de '{order.order_id}': {order.status.value}"
            )
        items = list(order.items_pendientes)
        if not items:
            raise ValueError(f"El pedido '{order.order_id}' no tiene ítems pendientes.")
        self.add_items(order, items, max_peso=max_peso)

    def has_capacity_for(self, order: Order, max_peso: float | None = None) -> bool:
        """
        Retrocompatibilidad: devuelve True si todos los ítems pendientes del pedido
        caben en la wave. Equivalente a can_add_items(order, order.items_pendientes).
        """
        return self.can_add_items(order, order.items_pendientes, max_peso=max_peso)

    def add_picker(self, picker: "Picker") -> None:
        """
        Agrega un picker a la lista de pickers asignados a la wave.

        Raises:
            ValueError: Si el picker ya está asignado a esta wave o está ocupado en otra.
        """
        if any(p.picker_id == picker.picker_id for p in self.pickers):
            raise ValueError(
                f"El picker '{picker.picker_id}' ya está asignado a la wave '{self.wave_id}'."
            )
        if picker.is_busy:
            raise ValueError(
                f"El picker '{picker.picker_id}' ya está ocupado en la wave '{picker.assigned_wave_id}'."
            )
        self.pickers.append(picker)
        picker.assign_wave(self.wave_id)

    def assign_picker(self, picker: "Picker") -> None:
        """
        Retrocompatibilidad: alias de add_picker para código existente.
        """
        self.add_picker(picker)

    @property
    def picker(self) -> "Picker | None":
        """
        Retrocompatibilidad: retorna el primer picker asignado, o None si no hay ninguno.
        Permite que código que esperaba un único picker siga funcionando.
        """
        return self.pickers[0] if self.pickers else None

    def set_route(self, route: list) -> None:
        """Asigna el recorrido calculado a la wave."""
        self.route = route

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Inicia la preparación de la wave. Requiere al menos un picker asignado.
        Transiciona los pedidos con todos sus ítems completos a EN_PREPARACION.

        Raises:
            ValueError: Si la wave no está ABIERTA, sin ítems o sin picker.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        if not self.entries:
            raise ValueError("La wave no tiene ítems asignados.")
        if not self.pickers:
            raise ValueError(
                f"La wave '{self.wave_id}' debe tener al menos un picker asignado "
                f"para iniciar la preparación."
            )
        self.status = WaveStatus.EN_PROCESO
        # Transicionar pedidos cuya asignación está completa
        for order in self.orders:
            if order.status == OrderStatus.EN_WAVE:
                order.mark_in_preparation()

    def complete(self) -> None:
        """
        Marca la wave como completada, transiciona los pedidos que estaban
        EN_PREPARACION a PREPARADO y libera todos los pickers.

        Raises:
            ValueError: Si la wave no está EN_PROCESO.
        """
        if self.status != WaveStatus.EN_PROCESO:
            raise ValueError(
                f"La wave '{self.wave_id}' debe estar EN_PROCESO para completarse."
            )
        self.status = WaveStatus.COMPLETADA
        for order in self.orders:
            if order.status == OrderStatus.EN_PREPARACION:
                order.mark_prepared()
        for picker in self.pickers:
            picker.release()

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serializa la wave a un diccionario para persistencia."""
        return {
            "wave_id": self.wave_id,
            "max_pedidos": self.max_pedidos,
            "max_productos": self.max_productos,
            "status": self.status.value,
            "picker_ids": [p.picker_id for p in self.pickers],
            # Retrocompatibilidad: incluye también picker_id (primer picker o None)
            "picker_id": self.pickers[0].picker_id if self.pickers else None,
            "entries": [
                {
                    "order_id": e.order.order_id,
                    "item_indices": [
                        e.order.items.index(it) for it in e.items
                    ],
                }
                for e in self.entries
            ],
            # Retrocompatibilidad: lista de order_ids con ítems en la wave
            "order_ids": [e.order.order_id for e in self.entries],
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
            order_registry : {order_id: Order}
            picker_registry: {picker_id: Picker} (opcional).
        """
        wave = cls(
            wave_id=data["wave_id"],
            max_pedidos=data["max_pedidos"],
            max_productos=data["max_productos"],
        )
        wave.status = WaveStatus(data["status"])
        wave.route = data.get("route", [])

        # Reconstruir entries
        for entry_data in data.get("entries", []):
            oid = entry_data["order_id"]
            if oid not in order_registry:
                raise KeyError(f"Pedido '{oid}' no encontrado en el registro.")
            order = order_registry[oid]
            indices = entry_data.get("item_indices", [])
            items = [order.items[i] for i in indices]
            wave.entries.append(WaveOrderEntry(order, items))

        # Soporte legado: si no hay entries pero sí order_ids (formato antiguo)
        if not wave.entries and data.get("order_ids"):
            for oid in data["order_ids"]:
                if oid not in order_registry:
                    raise KeyError(f"Pedido '{oid}' no encontrado en el registro.")
                order = order_registry[oid]
                wave.entries.append(WaveOrderEntry(order, list(order.items)))

        # Asignar pickers
        if picker_registry:
            for pid in data.get("picker_ids", []):
                if pid not in picker_registry:
                    raise KeyError(f"Picker '{pid}' no encontrado en el registro.")
                wave.add_picker(picker_registry[pid])
            # Retrocompatibilidad con campo picker_id (único)
            if not wave.pickers:
                single_pid = data.get("picker_id")
                if single_pid and single_pid in picker_registry:
                    wave.add_picker(picker_registry[single_pid])

        return wave

    def __repr__(self) -> str:
        pk_info = f", pickers={[p.picker_id for p in self.pickers]}" if self.pickers else ""
        return (
            f"Wave(id={self.wave_id!r}, pedidos={self.current_pedidos()}/"
            f"{self.max_pedidos}, unidades={self.current_unidades()}/"
            f"{self.max_productos}, peso={self.peso_total():.2f}kg{pk_info}, "
            f"status={self.status.value})"
        )
