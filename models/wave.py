"""
models/wave.py

Una wave es un grupo de ítems de pedidos que prepara un solo picker en
una misma pasada por el warehouse (consigna §6).
"""

from enum import Enum


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

    def __init__(self, order, items):
        self.order = order
        self.items = list(items)

    @property
    def units(self):
        total = 0
        for item in self.items:
            total = total + item.cantidad
        return total

    @property
    def weight(self):
        total = 0
        for item in self.items:
            total = total + item.total_weight
        return total

    def get_locations(self):
        ubicaciones = []
        for item in self.items:
            ubicaciones.append(tuple(item.product.location))
        return ubicaciones

    def __repr__(self):
        return (
            f"WaveOrderEntry(order='{self.order.order_id}', "
            f"items={len(self.items)}, peso={self.weight:.2f}kg)"
        )


class Wave:
    """
    Grupo de ítems de pedidos que un único picker prepara junto.

    Atributos:
        wave_id       (str)                  : Identificador de la wave.
        max_pedidos   (int)                  : Máximo de pedidos distintos en la wave.
        max_productos (int)                  : Máximo de UNIDADES en la wave.
        entries       (list[WaveOrderEntry]) : Pedidos de la wave con sus ítems.
        status        (WaveStatus)           : Estado de la wave.
        route         (list)                 : Recorrido guardado, lista de celdas (x, y).
        picker        (Picker o None)        : Picker que prepara la wave.
    """

    def __init__(self, wave_id, max_pedidos, max_productos):
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
        self.picker = None

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    @property
    def orders(self):
        """Pedidos que tienen ítems en esta wave."""
        pedidos = []
        for entry in self.entries:
            pedidos.append(entry.order)
        return pedidos

    @property
    def is_started(self):
        """True si la wave ya empezó (en proceso o completada)."""
        return self.status != WaveStatus.ABIERTA

    @property
    def is_completed(self):
        return self.status == WaveStatus.COMPLETADA

    def priority(self):
        """Prioridad de la wave: la mayor de sus pedidos (0 si está vacía)."""
        mayor = 0
        for entry in self.entries:
            if entry.order.prioridad > mayor:
                mayor = entry.order.prioridad
        return mayor

    def current_orders(self):
        """Cantidad de pedidos distintos en la wave."""
        return len(self.entries)

    def current_units(self):
        """Total de unidades en la wave."""
        total = 0
        for entry in self.entries:
            total = total + entry.units
        return total

    def total_weight(self):
        """Peso total de la wave (kg)."""
        total = 0
        for entry in self.entries:
            total = total + entry.weight
        return total

    def get_items(self):
        """Todos los ítems de la wave, en el orden en que entraron sus pedidos."""
        todos = []
        for entry in self.entries:
            for item in entry.items:
                todos.append(item)
        return todos

    def can_add_items(self, order, items, max_peso=None):
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

    def get_all_locations(self):
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

    def add_items(self, order, items, max_peso=None):
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

    def add_order(self, order, max_peso=None):
        """
        Agrega todos los ítems pendientes de un pedido.

        Raises:
            ValueError: Si el pedido no tiene ítems pendientes o no entran.
        """
        items = order.pending_items
        if len(items) == 0:
            raise ValueError(f"El pedido '{order.order_id}' no tiene ítems pendientes.")
        self.add_items(order, items, max_peso)

    def _entry_for(self, order):
        """Devuelve la entrada de este pedido en la wave, o None si no está."""
        for entry in self.entries:
            if entry.order.order_id == order.order_id:
                return entry
        return None

    def _register(self, order, items):
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

    def assign_picker(self, picker):
        """
        Asigna el picker que va a preparar la wave.

        Raises:
            ValueError: Si la wave ya tiene picker, si el picker está ocupado
                        o si la wave pesa más de lo que el picker puede cargar
                        (consigna §6).
        """
        if self.picker is not None:
            raise ValueError(
                f"La wave '{self.wave_id}' ya tiene asignado al picker "
                f"'{self.picker.picker_id}'."
            )
        if picker.is_busy:
            raise ValueError(
                f"El picker '{picker.picker_id}' ya está ocupado en la wave "
                f"'{picker.assigned_wave_id}'."
            )
        if self.total_weight() > picker.capacidad_carga_kg:
            raise ValueError(
                f"La wave '{self.wave_id}' pesa {self.total_weight():.2f} kg y supera "
                f"la capacidad del picker '{picker.picker_id}' "
                f"({picker.capacidad_carga_kg:.2f} kg)."
            )
        self.picker = picker
        picker.assign_wave(self.wave_id)

    def set_route(self, route):
        """Guarda el recorrido calculado para la wave."""
        self.route = route

    # ------------------------------------------------------------------
    # Cambios de estado
    # ------------------------------------------------------------------

    def start(self):
        """
        Empieza la preparación. Necesita un picker asignado.

        Raises:
            ValueError: Si la wave no está ABIERTA, está vacía o no tiene picker.
        """
        if self.status != WaveStatus.ABIERTA:
            raise ValueError(
                f"La wave '{self.wave_id}' ya no está abierta: {self.status.value}"
            )
        if len(self.entries) == 0:
            raise ValueError("La wave no tiene ítems asignados.")
        if self.picker is None:
            raise ValueError(
                f"La wave '{self.wave_id}' debe tener un picker asignado "
                f"para iniciar la preparación."
            )
        self.status = WaveStatus.EN_PROCESO

    def complete(self):
        """
        Termina la wave y libera a su picker. El estado de los pedidos se
        actualiza solo (ver Order.status).

        Raises:
            ValueError: Si la wave no está EN_PROCESO.
        """
        if self.status != WaveStatus.EN_PROCESO:
            raise ValueError(
                f"La wave '{self.wave_id}' debe estar EN_PROCESO para completarse."
            )
        self.status = WaveStatus.COMPLETADA
        self.picker.release()

    # ------------------------------------------------------------------
    # Guardar y cargar
    # ------------------------------------------------------------------

    def _index_in_order(self, order, item):
        """Posición (0, 1, 2...) del ítem dentro de order.items."""
        for i in range(len(order.items)):
            if order.items[i] is item:
                return i
        raise ValueError("El ítem no pertenece al pedido.")

    def to_dict(self):
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

        if self.picker is None:
            picker_id = None
        else:
            picker_id = self.picker.picker_id

        return {
            "wave_id": self.wave_id,
            "max_pedidos": self.max_pedidos,
            "max_productos": self.max_productos,
            "status": self.status.value,
            "picker_id": picker_id,
            "entries": entries_dict,
            "route": route_dict,
        }

    @classmethod
    def from_dict(cls, data, order_registry, picker_registry=None):
        """
        Reconstruye una wave guardada.

        Los ítems vuelven a quedar asignados a esta wave. Si la wave no está
        completada, su picker vuelve a quedar ocupado; si está completada,
        se recuerda qué picker la hizo, pero el picker queda libre.

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

        pid = data.get("picker_id")
        if pid is not None and picker_registry is not None:
            if pid not in picker_registry:
                raise KeyError(f"Picker '{pid}' no encontrado en el registro.")
            picker = picker_registry[pid]
            if data["status"] == WaveStatus.COMPLETADA.value:
                wave.picker = picker          # la hizo, pero ya está libre
            else:
                wave.assign_picker(picker)    # vuelve a quedar ocupado

        # El estado se pone al final: assign_picker necesita la wave sin empezar.
        wave.status = WaveStatus(data["status"])
        return wave

    def __repr__(self):
        texto_picker = ""
        if self.picker is not None:
            texto_picker = f", picker={self.picker.picker_id}"
        return (
            f"Wave(id='{self.wave_id}', pedidos={self.current_orders()}/"
            f"{self.max_pedidos}, unidades={self.current_units()}/"
            f"{self.max_productos}, peso={self.total_weight():.2f}kg{texto_picker}, "
            f"status={self.status.value})"
        )
