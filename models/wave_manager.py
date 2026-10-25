"""
models/wave_manager.py

Arma las waves a partir de los pedidos pendientes y les asigna pickers
(consigna §6 y §7). Trabaja en dos etapas que nunca se deshacen.

Etapa 1: armar waves (generate_waves). Algoritmo greedy y determinista:
    1. Se ordenan los pedidos pendientes: mayor prioridad primero y, si
       empatan, por id.
    2. Se abre una wave con el primero (la "semilla"). Si no entra completo,
       se divide por ítems; es el único caso en que un pedido se divide.
    3. Se calcula, con un BFS que arranca desde todas las celdas de recogida
       de la wave a la vez, la distancia de la wave a cada celda.
    4. Entre los pedidos que entran completos, se agrega el mejor: el de
       mayor prioridad y, si empatan, el más cercano (y si también empatan,
       el de menor id). La prioridad manda; la distancia solo desempata.
    5. Se repiten 3 y 4 hasta que no entre ninguno, y se vuelve a 2.
    El peso máximo de una wave es la capacidad del picker más grande, así
    siempre hay algún picker que puede prepararla.

Etapa 2: asignar pickers (assign_pickers y complete_wave).
    Las waves sin picker esperan en una cola ordenada por prioridad y, si
    empatan, por orden de creación. Cada wave recibe el picker libre de
    MENOR capacidad que la pueda cargar (best fit), así los grandes quedan
    para las waves pesadas. Cuando un picker termina su wave, queda libre
    y toma la siguiente de la cola.

Ordenar con tuplas:
    Las funciones _order_key, _picker_key y _queue_key devuelven tuplas como (-prioridad, order_id).
    Python compara tuplas elemento por elemento: primero el primero, y solo
    si son iguales mira el segundo. Por eso (-5, "P2") < (-3, "P1"): gana
    la prioridad 5. Se usa -prioridad para que la prioridad MAYOR quede primero.
"""

from __future__ import annotations

from models.order import Order, OrderItem
from models.warehouse import Picker, Warehouse
from models.wave import Wave, WaveStatus
from algorithms import Graph, bfs_distances, generate_graph, pickup_cells


INFINITO = float("inf")


def _order_key(order: Order) -> tuple[int, str]:
    """Orden de los pedidos pendientes: mayor prioridad primero, después por id."""
    return (-order.prioridad, order.order_id)


def _picker_key(picker: Picker) -> tuple[float, str]:
    """Orden de los pickers libres: menor capacidad primero, después por id."""
    return (picker.capacidad_carga_kg, picker.picker_id)


class WaveManager:
    """
    Atributos:
        warehouse            (Warehouse o None) : Warehouse asociado.
        graph                (Graph o None)     : Grafo para medir distancias.
        max_pedidos          (int)              : Máximo de pedidos por wave.
        max_productos        (int)              : Máximo de UNIDADES por wave.
        orders               (list[Order])      : Todos los pedidos.
        pickers              (list[Picker])     : Pickers que conoce el manager.
        waves                (list[Wave])       : Todas las waves, en orden de creación.
        queue                (list[Wave])       : Waves esperando picker, en orden de atención.
        unprocessable_orders (list)             : Ítems imposibles de la última generación,
                                                  como pares (pedido, motivo).

    Sin warehouse (o sin grafo), la distancia vale 0 para todos y el armado
    queda guiado solo por prioridad e id.
    """

    def __init__(
        self,
        warehouse: Warehouse | None = None,
        orders: list[Order] | None = None,
        max_pedidos: int | None = None,
        max_productos: int | None = None,
        graph: Graph | None = None,
    ):
        self.warehouse = warehouse

        self.orders = []
        if orders is not None:
            for order in orders:
                self.orders.append(order)

        self.pickers = []
        if warehouse is not None:
            for picker in warehouse.pickers:
                self.pickers.append(picker)

        self.waves = []
        self.queue = []
        self.unprocessable_orders = []

        # Límites: los recibidos, o los del warehouse, o los valores por defecto.
        if max_pedidos is not None:
            self.max_pedidos = max_pedidos
        elif warehouse is not None:
            self.max_pedidos = warehouse.wave_max_pedidos
        else:
            self.max_pedidos = 5

        if max_productos is not None:
            self.max_productos = max_productos
        elif warehouse is not None:
            self.max_productos = warehouse.wave_max_productos
        else:
            self.max_productos = 20

        if self.max_pedidos <= 0:
            raise ValueError("max_pedidos debe ser mayor a 0.")
        if self.max_productos <= 0:
            raise ValueError("max_productos debe ser mayor a 0.")

        self.graph = graph
        if self.graph is None and warehouse is not None:
            self.graph = generate_graph(warehouse)

        # Guardamos las celdas de recogida de cada producto para no
        # recalcularlas en cada wave: {product_id: set de celdas}.
        self._pickup_cache = {}

    # ------------------------------------------------------------------
    # Pedidos y pickers
    # ------------------------------------------------------------------

    def add_order(self, order: Order) -> None:
        self.orders.append(order)

    def add_orders(self, orders: list[Order]) -> None:
        for order in orders:
            self.add_order(order)

    def get_pending_orders(self) -> list[Order]:
        """Pedidos con al menos un ítem sin wave (PENDIENTE o PARCIAL)."""
        pendientes = []
        for order in self.orders:
            if len(order.pending_items) > 0:
                pendientes.append(order)
        return pendientes

    def _register_pickers(self, pickers: list[Picker] | None) -> list[Picker]:
        """Suma los pickers nuevos (los que no conocía) y devuelve todos."""
        if pickers is not None:
            ids_conocidos = set()
            for p in self.pickers:
                ids_conocidos.add(p.picker_id)
            for p in pickers:
                if p.picker_id not in ids_conocidos:
                    self.pickers.append(p)
        return self.pickers

    def _max_capacity(self, pickers: list[Picker]) -> float:
        """Capacidad del picker más grande (0 si no hay pickers)."""
        mayor = 0.0
        for p in pickers:
            if p.capacidad_carga_kg > mayor:
                mayor = p.capacidad_carga_kg
        return mayor

    def _validate_item_feasibility(
        self,
        order: Order,
        item: OrderItem,
        max_picker_cap: float,
    ) -> tuple[bool, str]:
        """
        Revisa si un ítem puede entrar en alguna wave: no tiene más unidades
        que max_productos ni pesa más que el picker más grande.

        Returns:
            (True, "") si puede, o (False, motivo) si no.
        """
        if item.cantidad > self.max_productos:
            motivo = (
                f"El ítem '{item.product.product_id}' del pedido '{order.order_id}' "
                f"tiene {item.cantidad} unidades, que superan el máximo por wave "
                f"({self.max_productos})."
            )
            return False, motivo
        if item.total_weight > max_picker_cap:
            motivo = (
                f"El ítem '{item.product.product_id}' del pedido '{order.order_id}' "
                f"pesa {item.total_weight:.2f} kg, superando la capacidad del picker "
                f"más capaz ({max_picker_cap:.2f} kg)."
            )
            return False, motivo
        return True, ""

    # ------------------------------------------------------------------
    # Distancias (etapa 1)
    # ------------------------------------------------------------------

    def _pickup_cells(self, item: OrderItem) -> set[tuple[int, int]]:
        """Celdas de pasillo desde las que se recoge el producto del ítem."""
        pid = item.product.product_id
        if pid not in self._pickup_cache:
            celdas = pickup_cells(item.product, self.warehouse, self.graph)
            self._pickup_cache[pid] = set(celdas)
        return self._pickup_cache[pid]

    def _distances_from_wave(self, wave: Wave) -> dict[tuple[int, int], int] | None:
        """
        BFS multi-origen desde todas las celdas de recogida de la wave.
        Devuelve {celda: distancia}, o None si no hay grafo.

        Complejidad: O(V + E).
        """
        if self.graph is None or self.warehouse is None:
            return None
        origenes = set()
        for item in wave.get_items():
            for celda in self._pickup_cells(item):
                origenes.add(celda)
        return bfs_distances(self.graph, origenes)

    def _distance(
        self,
        items: list[OrderItem],
        dist: dict[tuple[int, int], int] | None,
    ) -> float:
        """
        Distancia de la wave a un pedido: la menor distancia a alguna celda
        de recogida de sus ítems. 0 si no hay grafo; infinito si no llega.
        """
        if dist is None:
            return 0
        menor = INFINITO
        for item in items:
            for celda in self._pickup_cells(item):
                if celda in dist and dist[celda] < menor:
                    menor = dist[celda]
        return menor

    # ------------------------------------------------------------------
    # Etapa 1: armar waves
    # ------------------------------------------------------------------

    def generate_waves(
        self,
        pickers: list[Picker] | None = None,
        prefix: str = "WAVE_",
    ) -> list[Wave]:
        """
        Arma waves con los ítems pendientes (etapa 1) y después asigna
        pickers libres a la cola (etapa 2).

        Args:
            pickers: Pickers extra a considerar (por defecto, los del warehouse).
            prefix : Prefijo de los ids de las waves ("WAVE_01", "WAVE_02"...).

        Returns:
            Las waves nuevas, en orden de creación. Las que no consiguieron
            picker quedan en la cola (get_queued_waves).

        Complejidad: con P pedidos pendientes, agregar cada pedido cuesta un
        BFS O(V + E) más recorrer los candidatos O(P): en total O(P · (V + E + P)).
        """
        self.unprocessable_orders = []
        todos_los_pickers = self._register_pickers(pickers)
        max_peso = self._max_capacity(todos_los_pickers)
        if max_peso <= 0:
            return []

        # 1. Ítems posibles de cada pedido. Los imposibles se informan y no se usan.
        viable = {}    # {order_id: lista de ítems que sí pueden entrar}
        for order in self.get_pending_orders():
            posibles = []
            for item in order.pending_items:
                ok, motivo = self._validate_item_feasibility(order, item, max_peso)
                if ok:
                    posibles.append(item)
                else:
                    self.unprocessable_orders.append((order, motivo))
            if len(posibles) > 0:
                viable[order.order_id] = posibles

        # 2. Pedidos a repartir, del más prioritario al menos prioritario.
        pending = []
        for order in self.get_pending_orders():
            if order.order_id in viable:
                pending.append(order)
        pending = sorted(pending, key=_order_key)

        new_waves = []
        while len(pending) > 0:
            numero = len(self.waves) + len(new_waves) + 1
            wave = Wave(
                wave_id=prefix + str(numero).zfill(2),   # zfill(2): 1 -> "01"
                max_pedidos=self.max_pedidos,
                max_productos=self.max_productos,
            )

            # 3. La semilla: el pedido más prioritario que queda.
            seed = pending[0]
            self._add_seed(wave, seed, viable, max_peso)

            # 4. Agregar el mejor candidato mientras entre alguno.
            while True:
                dist = self._distances_from_wave(wave)
                best = self._best_candidate(wave, pending, seed, viable, dist, max_peso)
                if best is None:
                    break
                wave.add_items(best, viable[best.order_id], max_peso)
                viable[best.order_id] = []

            # 5. Quedan solo los pedidos con ítems sin wave.
            quedan = []
            for order in pending:
                if len(viable[order.order_id]) > 0:
                    quedan.append(order)
            pending = quedan
            new_waves.append(wave)

        for wave in new_waves:
            self.waves.append(wave)
            self.queue.append(wave)
        self.queue = sorted(self.queue, key=self._queue_key)
        self.assign_pickers()
        return new_waves

    def _best_candidate(
        self,
        wave: Wave,
        pending: list[Order],
        seed: Order,
        viable: dict[str, list[OrderItem]],
        dist: dict[tuple[int, int], int] | None,
        max_peso: float,
    ) -> Order | None:
        """
        Entre los pedidos que entran completos en la wave, devuelve el de
        menor clave (-prioridad, distancia, order_id), o None si no entra ninguno.
        """
        mejor = None
        mejor_clave = None
        for order in pending:
            if order is seed:
                continue
            items = viable[order.order_id]
            if not wave.can_add_items(order, items, max_peso):
                continue
            clave = (-order.prioridad, self._distance(items, dist), order.order_id)
            if mejor is None or clave < mejor_clave:
                mejor = order
                mejor_clave = clave
        return mejor

    def _add_seed(
        self,
        wave: Wave,
        seed: Order,
        viable: dict[str, list[OrderItem]],
        max_peso: float,
    ) -> None:
        """
        Pone el pedido semilla en una wave vacía. Si no entra completo, se
        agregan sus ítems de a uno mientras quepan, y el resto queda en
        viable para la wave siguiente. Como cada ítem posible entra solo en
        una wave vacía, siempre entra al menos uno y el armado avanza.
        """
        items = viable[seed.order_id]
        if wave.can_add_items(seed, items, max_peso):
            wave.add_items(seed, items, max_peso)
            viable[seed.order_id] = []
            return

        for item in items:
            if wave.can_add_items(seed, [item], max_peso):
                wave.add_items(seed, [item], max_peso)

        sin_wave = []
        for item in items:
            if item.wave is None:
                sin_wave.append(item)
        viable[seed.order_id] = sin_wave

    # ------------------------------------------------------------------
    # Etapa 2: asignar pickers
    # ------------------------------------------------------------------

    def _queue_key(self, wave: Wave) -> tuple[int, int]:
        """Orden de la cola: mayor prioridad primero, después la más antigua."""
        return (-wave.priority(), self.waves.index(wave))

    def assign_pickers(self, pickers: list[Picker] | None = None) -> list[Wave]:
        """
        Recorre la cola en orden y le da a cada wave el picker libre más chico
        que la pueda cargar. Una wave que no encuentra picker sigue esperando,
        y las siguientes pueden tomar pickers más chicos mientras tanto.

        Returns:
            Las waves que recibieron picker en esta llamada.
        """
        libres = []
        for p in self._register_pickers(pickers):
            if not p.is_busy:
                libres.append(p)
        libres = sorted(libres, key=_picker_key)

        assigned = []
        for wave in list(self.queue):    # copia: vamos a sacar elementos de self.queue
            elegido = None
            for p in libres:
                if p.capacidad_carga_kg >= wave.total_weight():
                    elegido = p
                    break
            if elegido is None:
                continue
            wave.assign_picker(elegido)
            libres.remove(elegido)
            self.queue.remove(wave)
            assigned.append(wave)
        return assigned

    def complete_wave(self, wave: Wave) -> list[Wave]:
        """
        Termina una wave en proceso, libera su picker y vuelve a repartir
        pickers en la cola.

        Returns:
            Las waves que recibieron picker al liberarse el de esta wave.
        """
        wave.complete()
        return self.assign_pickers()

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_waves(self) -> list[Wave]:
        return list(self.waves)

    def get_queued_waves(self) -> list[Wave]:
        return list(self.queue)

    def get_unprocessable_orders(self) -> list[tuple[Order, str]]:
        return list(self.unprocessable_orders)

    # ------------------------------------------------------------------
    # Guardar y cargar 
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Pedidos y waves, para guardarlos junto al escenario."""
        pedidos = []
        for o in self.orders:
            pedidos.append(o.to_dict())
        waves = []
        for w in self.waves:
            waves.append(w.to_dict())
        return {"pedidos": pedidos, "waves": waves}

    @classmethod
    def from_dict(cls, data: dict, warehouse: Warehouse) -> WaveManager:
        """
        Vuelve a cargar pedidos y waves guardados. Pedidos y pickers quedan
        como estaban al guardar, y las waves sin picker vuelven a la cola.
        """
        orders = []
        for o_data in data.get("pedidos", []):
            orders.append(Order.from_dict(o_data, warehouse.products))
        manager = cls(warehouse=warehouse, orders=orders)

        pedidos_por_id = {}
        for o in orders:
            pedidos_por_id[o.order_id] = o
        pickers_por_id = {}
        for p in manager.pickers:
            pickers_por_id[p.picker_id] = p

        for w_data in data.get("waves", []):
            manager.waves.append(Wave.from_dict(w_data, pedidos_por_id, pickers_por_id))

        for w in manager.waves:
            if w.status == WaveStatus.ABIERTA and w.picker is None:
                manager.queue.append(w)
        manager.queue = sorted(manager.queue, key=manager._queue_key)
        return manager

    def __repr__(self) -> str:
        return (
            f"WaveManager(pedidos_totales={len(self.orders)}, "
            f"con_pendientes={len(self.get_pending_orders())}, "
            f"waves={len(self.waves)}, en_cola={len(self.queue)})"
        )
