"""
models/wave.py

Una wave es un grupo de ítems de pedidos que prepara un solo picker en
una misma pasada por el warehouse (consigna §6).
"""

from enum import Enum

from models.order import Order, OrderItem
from models.picker import Picker


class WaveStatus(Enum):
    """Estados posibles de una wave."""
    ABIERTA    = "ABIERTA"      # armada, esperando picker o esperando arrancar
    EN_PROCESO = "EN_PROCESO"   # el picker está recorriendo el warehouse
    COMPLETADA = "COMPLETADA"   # todos sus ítems fueron recogidos


class WaveOrderEntry:
    """
    Une un pedido con los ítems de ese pedido que entraron en esta wave.

    Un pedido grande puede quedar repartido en varias waves; cada wave
    guarda solo los ítems que le tocaron. Los ítems no se copian: son los
    mismos objetos que están en order.items.

    Atributos:
        order (Order)           : Pedido al que pertenecen los ítems.
        items (list[OrderItem]) : Ítems de ese pedido que están en esta wave.
    """

    def __init__(self, order: Order, items: list[OrderItem]):
        self.order = order
        self.items = list(items)

    @property
    def units(self) -> int:
        total = 0
        for item in self.items:
            total = total + item.cantidad
        return total

    @property
    def weight(self) -> float:
        total = 0
        for item in self.items:
            total = total + item.total_weight
        return total

    def get_locations(self) -> list[tuple]:
        ubicaciones = []
        for item in self.items:
            ubicaciones.append(tuple(item.product.location))
        return ubicaciones

    def __repr__(self) -> str:
        return (
            f"WaveOrderEntry(order='{self.order.order_id}', "
            f"items={len(self.items)}, peso={self.weight:.2f}kg)"
        )


class Wave:
    """
    Grupo de ítems de pedidos que uno o más pickers preparan juntos.

    Un picker siempre trabaja en una sola wave a la vez, pero una wave
    puede tener varios pickers cuando el volumen de trabajo lo justifica:
    cada picker recibe un subconjunto disjunto de paradas.

    Atributos:
        wave_id       (str)                  : Identificador de la wave.
        max_pedidos   (int)                  : Máximo de pedidos distintos en la wave.
        max_productos (int)                  : Máximo de UNIDADES en la wave.
        entries       (list[WaveOrderEntry]) : Pedidos de la wave con sus ítems.
        status        (WaveStatus)           : Estado de la wave.
        route         (list)                 : Recorrido del primer picker, lista de celdas (x, y).
        pickers       (list[Picker])         : Pickers asignados a la wave (uno o más).
    """

    def __init__(self, wave_id: str, max_pedidos: int, max_productos: int):
        if max_pedidos <= 0:
            raise ValueError("max_pedidos debe ser mayor a 0.")
        if max_productos <= 0:
            raise ValueError("max_productos debe ser mayor a 0.")

        self.wave_id = wave_id
        self.max_pedidos = max_pedidos
        self.max_productos = max_productos
        self.entries = []
        self.status = WaveStatus.ABIERTA
        self.route = []
        self.pickers = []        # lista de pickers asignados (uno o más)

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    @property
    def orders(self) -> list[Order]:
        """Pedidos que tienen ítems en esta wave."""
        pedidos = []
        for entry in self.entries:
            pedidos.append(entry.order)
        return pedidos

    @property
    def is_started(self) -> bool:
        """True si la wave ya empezó (en proceso o completada)."""
        return self.status != WaveStatus.ABIERTA

    @property
    def picker(self) -> "Picker | None":
        """
        Propiedad de compatibilidad: el primer picker de la wave, o None.

        Para waves con varios pickers, usar self.pickers directamente.
        """
        return self.pickers[0] if self.pickers else None

    @property
    def is_completed(self) -> bool:
        return self.status == WaveStatus.COMPLETADA

    def priority(self) -> int:
        """Prioridad de la wave: la mayor de sus pedidos (0 si está vacía)."""
        mayor = 0
        for entry in self.entries:
            if entry.order.prioridad > mayor:
                mayor = entry.order.prioridad
        return mayor

    def current_orders(self) -> int:
        """Cantidad de pedidos distintos en la wave."""
        return len(self.entries)

    def current_units(self) -> int:
        """Total de unidades en la wave."""
        total = 0
        for entry in self.entries:
            total = total + entry.units
        return total

    def total_weight(self) -> float:
        """Peso total de la wave (kg)."""
        total = 0
        for entry in self.entries:
            total = total + entry.weight
        return total

    def get_items(self) -> list[OrderItem]:
        """Todos los ítems de la wave, en el orden en que entraron sus pedidos."""
        todos = []
        for entry in self.entries:
            for item in entry.items:
                todos.append(item)
        return todos

    def can_add_items(
        self,
        order: Order,
        items: list[OrderItem],
        max_peso: float | None = None,
    ) -> bool:
        """
        True si los ítems entran en la wave sin pasar sus límites.

        Se controla, en este orden:
            1. que la wave siga abierta y haya algo para agregar;
            2. la cantidad de pedidos (un pedido que ya está en la wave no
               cuenta como pedido nuevo);
            3. la cantidad de unidades (max_productos);
            4. el peso, si se pasa max_peso.
        """
        if self.status != WaveStatus.ABIERTA or len(items) == 0:
            return False

        pedido_ya_esta = self._entry_for(order) is not None
        if not pedido_ya_esta and self.current_orders() >= self.max_pedidos:
            return False

        unidades_nuevas = 0
        peso_nuevo = 0
        for item in items:
            unidades_nuevas = unidades_nuevas + item.cantidad
            peso_nuevo = peso_nuevo + item.total_weight

        if self.current_units() + unidades_nuevas > self.max_productos:
            return False
        if max_peso is not None and self.total_weight() + peso_nuevo > max_peso:
            return False
        return True

    def get_all_locations(self) -> list[tuple]:
        """Ubicaciones (x, y, z) distintas de todos los ítems, en orden de aparición."""
        vistas = set()
        ubicaciones = []
        for entry in self.entries:
            for ubicacion in entry.get_locations():
                if ubicacion not in vistas:
                    vistas.add(ubicacion)
                    ubicaciones.append(ubicacion)
        return ubicaciones

    # ------------------------------------------------------------------
    # Agregar ítems
    # ------------------------------------------------------------------

    def add_items(
        self,
        order: Order,
        items: list[OrderItem],
        max_peso: float | None = None,
    ) -> None:
        """
        Agrega ítems de un pedido a la wave y los marca como asignados.

        Raises:
            ValueError: Si no entran o alguno ya está en otra wave.
        """
        if not self.can_add_items(order, items, max_peso):
            raise ValueError(
                f"No hay capacidad para agregar los ítems del pedido '{order.order_id}' "
                f"a la wave '{self.wave_id}'."
            )
        order.assign_items(items, self)
        self._register(order, items)

    def add_order(self, order: Order, max_peso: float | None = None) -> None:
        """
        Agrega todos los ítems pendientes de un pedido.

        Raises:
            ValueError: Si el pedido no tiene ítems pendientes o no entran.
        """
        items = order.pending_items
        if len(items) == 0:
            raise ValueError(f"El pedido '{order.order_id}' no tiene ítems pendientes.")
        self.add_items(order, items, max_peso)

    def _entry_for(self, order: Order) -> WaveOrderEntry | None:
        """Devuelve la entrada de este pedido en la wave, o None si no está."""
        for entry in self.entries:
            if entry.order.order_id == order.order_id:
                return entry
        return None

    def _register(self, order: Order, items: list[OrderItem]) -> None:
        """Anota los ítems en la entrada del pedido (la crea si no existe)."""
        entry = self._entry_for(order)
        if entry is None:
            self.entries.append(WaveOrderEntry(order, items))
        else:
            for item in items:
                entry.items.append(item)

    # ------------------------------------------------------------------
    # Picker y recorrido
    # ------------------------------------------------------------------

    def assign_picker(self, picker: Picker) -> None:
        """
        Agrega un picker a la wave.

        Permite asignar varios pickers a la misma wave para distribuir la
        carga entre operarios. Cada picker recibe un subconjunto disjunto
        de paradas durante la planificación de rutas, por lo que no se
        controla el peso total de la wave aquí (cada picker carga solo su
        fracción).

        La validación de peso del primer picker (que sí debe poder cargar
        el total si opera solo) la hace WaveManager.assign_pickers antes
        de llamar a este método.

        Raises:
            ValueError: Si la wave ya no está ABIERTA, el picker ya está
                        en esta wave, o ya está ocupado en otra.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        for p in self.pickers:
            if p.picker_id == picker.picker_id:
                raise ValueError(
                    f"El picker '{picker.picker_id}' ya está asignado a la "
                    f"wave '{self.wave_id}'."
                )
        if picker.is_busy:
            raise ValueError(
                f"El picker '{picker.picker_id}' ya está ocupado en la wave "
                f"'{picker.assigned_wave_id}'."
            )
        self.pickers.append(picker)
        picker.assign_wave(self.wave_id)

    def set_route(self, route: list[tuple[int, int]]) -> None:
        """Guarda el recorrido calculado para la wave."""
        self.route = route

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Empieza la preparación. Necesita al menos un picker asignado.

        Raises:
            ValueError: Si la wave no está ABIERTA, está vacía o no
                        tiene ningún picker asignado.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        if len(self.entries) == 0:
            raise ValueError("La wave no tiene ítems asignados.")
        if len(self.pickers) == 0:
            raise ValueError(
                f"La wave '{self.wave_id}' debe tener al menos un picker "
                f"asignado para iniciar la preparación."
            )
        self.status = WaveStatus.EN_PROCESO

    def complete(self) -> None:
        """
        Termina la wave y libera a todos sus pickers. El estado de los
        pedidos se actualiza solo (ver Order.status).

        Raises:
            ValueError: Si la wave no está EN_PROCESO.
        """
        if self.status != WaveStatus.EN_PROCESO:
            raise ValueError(
                f"La wave '{self.wave_id}' debe estar EN_PROCESO para completarse."
            )
        self.status = WaveStatus.COMPLETADA
        for p in self.pickers:
            if p.is_busy:
                p.release()

    # ------------------------------------------------------------------
    # Guardar y cargar
    # ------------------------------------------------------------------

    def _index_in_order(self, order: Order, item: OrderItem) -> int:
        """Posición (0, 1, 2...) del ítem dentro de order.items."""
        for i in range(len(order.items)):
            if order.items[i] is item:
                return i
        raise ValueError("El ítem no pertenece al pedido.")

    def to_dict(self) -> dict:
        """
        Devuelve la wave como diccionario para guardarla.

        Cada ítem se guarda como su posición dentro de su pedido, porque
        al cargar hay que volver a apuntar a ese mismo ítem.
        """
        entries_dict = []
        for entry in self.entries:
            posiciones = []
            for item in entry.items:
                posiciones.append(self._index_in_order(entry.order, item))
            entries_dict.append({"order_id": entry.order.order_id, "item_indices": posiciones})

        route_dict = []
        for cell in self.route:
            route_dict.append(list(cell))

        picker_ids = []
        for p in self.pickers:
            picker_ids.append(p.picker_id)

        return {
            "wave_id": self.wave_id,
            "max_pedidos": self.max_pedidos,
            "max_productos": self.max_productos,
            "status": self.status.value,
            "picker_ids": picker_ids,
            "entries": entries_dict,
            "route": route_dict,
        }

    # El tipo de retorno va entre comillas porque la clase todavía se está
    # definiendo en este punto (Python no la conoce hasta terminar la clase).
    @classmethod
    def from_dict(
        cls,
        data: dict,
        order_registry: dict[str, Order],
        picker_registry: dict[str, Picker] | None = None,
    ) -> "Wave":
        """
        Reconstruye una wave guardada.

        Soporta el formato nuevo (picker_ids: lista) y el formato legacy
        (picker_id: string). Los ítems vuelven a quedar asignados a esta
        wave. Si la wave no está completada, sus pickers vuelven a quedar
        ocupados; si está completada, se recuerda quiénes la hicieron,
        pero quedan libres.

        Args:
            data            : Diccionario guardado con to_dict.
            order_registry  : {order_id: Order}
            picker_registry : {picker_id: Picker} (opcional).

        Raises:
            KeyError:   Si un pedido o un picker no existen.
            ValueError: Si algún ítem ya estaba en otra wave.
        """
        wave = cls(
            wave_id=data["wave_id"],
            max_pedidos=data["max_pedidos"],
            max_productos=data["max_productos"],
        )
        for cell in data.get("route", []):
            wave.route.append(tuple(cell))

        for entry_data in data.get("entries", []):
            oid = entry_data["order_id"]
            if oid not in order_registry:
                raise KeyError(f"Pedido '{oid}' no encontrado en el registro.")
            order = order_registry[oid]
            items = []
            for posicion in entry_data.get("item_indices", []):
                items.append(order.items[posicion])
            order.assign_items(items, wave)
            wave._register(order, items)

        # Soportar formato nuevo (picker_ids: lista) y formato legacy (picker_id: str)
        picker_ids_data = data.get("picker_ids")
        if picker_ids_data is None:
            pid_legacy = data.get("picker_id")
            picker_ids_data = [pid_legacy] if pid_legacy is not None else []

        if picker_registry is not None:
            for pid in picker_ids_data:
                if pid not in picker_registry:
                    raise KeyError(f"Picker '{pid}' no encontrado en el registro.")
                picker = picker_registry[pid]
                if data["status"] == WaveStatus.COMPLETADA.value:
                    wave.pickers.append(picker)    # la hizo, pero ya está libre
                else:
                    wave.assign_picker(picker)     # vuelve a quedar ocupado

        # El estado se pone al final: assign_picker necesita la wave sin empezar.
        wave.status = WaveStatus(data["status"])
        return wave

    def __repr__(self) -> str:
        if self.pickers:
            ids_pickers = [p.picker_id for p in self.pickers]
            texto_pickers = f", pickers={ids_pickers}"
        else:
            texto_pickers = ""
        return (
            f"Wave(id='{self.wave_id}', pedidos={self.current_orders()}/"
            f"{self.max_pedidos}, unidades={self.current_units()}/"
            f"{self.max_productos}, peso={self.total_weight():.2f}kg{texto_pickers}, "
            f"status={self.status.value})"
        )
