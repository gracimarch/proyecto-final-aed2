"""
models/wave_manager.py

Arma las waves a partir de los pedidos pendientes y les asigna pickers
(consigna §6 y §7). Trabaja en dos etapas que nunca se deshacen.

Etapa 1: armar waves (generate_waves). Algoritmo greedy y determinista:
    1. Se ordenan los pedidos pendientes: mayor prioridad primero y, si
       empatan, por id.
    2. Se abre una wave con el primero (la "semilla"). Si no entra completo,
       se divide por ítems; es el único caso en que un pedido se divide.
    3. Se calcula la distancia de la wave a cada celda, usando la tabla de
       distancias (ver más abajo).
    4. Entre los pedidos que entran completos, se agrega el mejor: el de
       mayor prioridad y, si empatan, el más cercano (y si también empatan,
       el de menor id). La prioridad manda; la distancia solo desempata.
    5. Se repiten 3 y 4 hasta que no entre ninguno, y se vuelve a 2.
    El peso máximo de una wave es la capacidad del picker más grande, así
    siempre hay algún picker que puede prepararla.

    Lo de arriba es la estrategia "por_pedido". Hay tres (estrategia_wave):
        "por_pedido"    : pedidos enteros; la prioridad manda y la distancia
                          desempata.
        "por_cercania"  : ítem por ítem; la semilla es el ítem más prioritario
                          y se suma el ítem más cercano entre los de mayor
                          prioridad.
        "solo_cercania" : ítem por ítem SIN mirar la prioridad; la semilla es
                          el ítem más cercano a las zonas de despacho y se suma
                          siempre el ítem más cercano a la wave.

Etapa 2: asignar pickers (assign_pickers y complete_wave).
    Las waves sin picker esperan en una cola ordenada por prioridad y, si
    empatan, por orden de creación (la prioridad sigue mandando). Cada wave
    recibe, entre los pickers libres que la pueden cargar, el MÁS CERCANO:
    el que tiene menos pasos desde su posición actual hasta la parada más
    cercana de la wave. Si empatan en distancia, gana el de menor capacidad
    (best fit, así los grandes quedan para las waves pesadas) y después el
    de menor id. Un picker que no puede llegar a la wave no se elige.
    Cuando un picker termina su wave, queda libre en la celda donde
    descargó y, desde ahí, compite por la siguiente de la cola.

    Si tras la asignación 1:1 sobran pickers libres, se asignan como
    refuerzo a las waves con más paradas distintas: a cada wave se le manda
    el picker sobrante más cercano. Solo se agrega un picker extra si la
    wave tiene al menos un rack por picker (así cada operario tiene al
    menos una parada propia). El máximo de pickers por wave está limitado
    por WaveManager.MAX_PICKERS_POR_WAVE.

    Distancia picker -> wave: con sentidos de circulación el grafo es
    dirigido e ir del rack al picker no cuesta lo mismo que ir del picker
    al rack, así que no se usa la tabla de los racks. Se corre un BFS desde
    la celda del picker y se guarda en self._tabla_desde_pickers (misma
    memoización: los pickers arrancan casi siempre en las mismas celdas,
    la inicial o la de descarga, así que se repiten).

Tabla de distancias (self._tabla_distancias):
    El grafo nunca cambia, así que la distancia de un rack a cualquier celda
    es siempre la misma. La primera vez que se necesita, se corre un BFS
    desde las celdas de recogida de ese rack y se guarda la "fila"
    {celda: distancia}; las siguientes veces solo se lee. Es memoización:
    cada rack se calcula UNA vez por WaveManager, en vez de un BFS nuevo
    cada vez que se agrega algo a una wave.

    La distancia de la wave a una celda es la menor distancia desde alguno
    de sus racks (es lo mismo que daba el BFS multi-origen de antes). Por
    eso, al agregar un ítem, alcanza con quedarse, celda por celda, con el
    mínimo entre lo que ya había y la fila del rack nuevo. Las waves que se
    arman son exactamente las mismas que con el BFS en cada paso.

    La altura z NO va en la tabla: es un costo de la parada, no del camino,
    y se suma aparte con Product.costo_altura().

Ordenar con tuplas:
    Las funciones _order_key, _picker_key y _queue_key devuelven tuplas como (-prioridad, order_id).
    Python compara tuplas elemento por elemento: primero el primero, y solo
    si son iguales mira el segundo. Por eso (-5, "P2") < (-3, "P1"): gana
    la prioridad 5. Se usa -prioridad para que la prioridad MAYOR quede primero.
"""

from models.order import Order, OrderItem
from models.picker import Picker
from models.warehouse import Warehouse
from models.wave import Wave, WaveStatus
from algorithms.graph import Graph, bfs_distances
from algorithms.graph_builder import (
    generate_navigation_graph,
    live_circulation_cells,
    restrict_to_live_circulation,
)
from algorithms.pathfinding import pickup_cells
from algorithms.routing import validate_reachability, dispatch_access_cells


INFINITO = float("inf")


def _order_key(order: Order) -> tuple[int, str]:
    """Orden de los pedidos pendientes: mayor prioridad primero, después por id."""
    return (-order.prioridad, order.order_id)


def _picker_key(picker: Picker) -> tuple[float, str]:
    """Orden de los pickers libres: menor capacidad primero, después por id."""
    return (picker.capacidad_carga_kg, picker.picker_id)


def _closer_picker_key(distancia: float, picker: Picker) -> tuple[float, float, str]:
    """Para elegir picker: el más cercano; si empatan, el más chico; después por id."""
    return (distancia, picker.capacidad_carga_kg, picker.picker_id)


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
        if warehouse is not None:
            # La navegación se limita a la circulación desde la que se puede
            # volver al núcleo de los pickers. Los pasillos de sentido único
            # que terminan en un callejón sin salida quedan afuera antes de
            # generar waves y de simular.
            if self.graph is None:
                self.graph = generate_navigation_graph(warehouse)
            else:
                self.graph = restrict_to_live_circulation(self.graph, warehouse)

        # Antes de armar waves, cada producto tiene que poder buscarse
        # y traerse a la zona de despacho respetando los sentidos.
        if warehouse is not None:
            validate_reachability(warehouse, self.graph)

        # Guardamos las celdas de recogida de cada producto para no
        # recalcularlas en cada wave: {product_id: set de celdas}.
        self._pickup_cache = {}

        # Celdas de la circulación viva. Se calculan la primera vez que hacen
        # falta y no cambian mientras no cambie el grafo.
        self._live_cells_cache = None

        # Tabla de distancias: {celda del rack (x, y): {celda: distancia}}.
        # Se llena de a una fila, la primera vez que se pide cada rack.
        self._tabla_distancias = {}
        # Distancia desde las zonas de despacho a cada celda (para la semilla
        # de "solo_cercania"). Se calcula la primera vez que se pide.
        self._dist_zonas = None
        # Distancia desde la celda de un picker a cada celda: {celda: {celda: dist}}.
        # Para elegir el picker más cercano a cada wave (etapa 2).
        self._tabla_desde_pickers = {}
        # BFS corridos para esa tabla (se cuentan aparte de los de armar waves).
        self.bfs_pickers = 0
        # Cuántos BFS se corrieron para llenar la tabla (para los experimentos).
        self.bfs_corridos = 0

        # Validar consistencia de stock: la suma de unidades pedidas por
        # producto no puede superar el stock disponible en los racks.
        # Defensa en profundidad para escenarios importados por JSON.
        if warehouse is not None and self.orders:
            self._validate_stock_consistency()

    # ------------------------------------------------------------------
    # Validacion de stock (defensa en profundidad)
    # ------------------------------------------------------------------

    def _validate_stock_consistency(self) -> None:
        """
        Verifica que la suma de unidades requeridas por cada producto a lo
        largo de TODOS los pedidos pendientes no supere el stock disponible
        (cantidad_disponible) en los racks del almacén.

        Los pedidos inviables se registran en self.unprocessable_orders con
        el motivo 'Stock insuficiente en almacén'.
        """
        if self.warehouse is None:
            return

        # Indice de stock disponible por product_id
        stock_disponible: dict[str, int] = {}
        products = (
            self.warehouse.products.values()
            if isinstance(self.warehouse.products, dict)
            else self.warehouse.products
        )
        for product in products:
            pid = product.product_id
            stock_disponible[pid] = stock_disponible.get(pid, 0) + product.cantidad_disponible

        # Acumular demanda total por producto en pedidos pendientes
        demanda: dict[str, int] = {}
        for order in self.get_pending_orders():
            for item in order.pending_items:
                pid = item.product.product_id
                demanda[pid] = demanda.get(pid, 0) + item.cantidad

        # Detectar sobredemanda
        sobredemandados: set[str] = set()
        for pid, total in demanda.items():
            disponible = stock_disponible.get(pid, 0)
            if total > disponible:
                sobredemandados.add(pid)

        if not sobredemandados:
            return

        # Registrar cada pedido que referencia un producto sobredemandado
        pedidos_reportados = {o.order_id for o, _ in self.unprocessable_orders}
        for order in self.get_pending_orders():
            for item in order.pending_items:
                pid = item.product.product_id
                if pid in sobredemandados and order.order_id not in pedidos_reportados:
                    motivo = "Stock insuficiente en almacén"
                    self.unprocessable_orders.append((order, motivo))
                    pedidos_reportados.add(order.order_id)
                    break

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

    def _live_cells(self) -> set[tuple[int, int]]:
        """
        Celdas de la circulación viva, calculadas una sola vez.

        Son las celdas desde las que un picker puede volver al núcleo. Si no
        hay warehouse o grafo no se puede decidir y se devuelve un conjunto
        vacío.
        """
        if self._live_cells_cache is None:
            if self.warehouse is None or self.graph is None:
                self._live_cells_cache = set()
            else:
                self._live_cells_cache = live_circulation_cells(
                    self.warehouse, self.graph
                )
        return self._live_cells_cache

    def _operational_pickers(self, pickers: list[Picker]) -> list[Picker]:
        """
        Pickers que pueden participar de la circulación viva.

        Un picker en un callejón sin retorno o en una isla desconectada no es
        operativo: no puede ir a buscar pedidos ni volver al núcleo, así que
        no debe contar ni para dimensionar waves ni para asignarlas.
        """
        if self.warehouse is None or self.graph is None:
            return list(pickers)

        vivo = self._live_cells()
        operativos = []
        for p in pickers:
            if tuple(p.posicion_actual) in vivo:
                operativos.append(p)
        return operativos

    def _max_capacity(self, pickers: list[Picker]) -> float:
        """
        Capacidad del picker operativo más grande (0 si no hay ninguno).

        Solo cuentan los pickers operativos: usar la capacidad de uno aislado
        haría que se armen waves que después nadie puede cargar.
        """
        mayor = 0.0
        for p in self._operational_pickers(pickers):
            if p.capacidad_carga_kg > mayor:
                mayor = p.capacidad_carga_kg
        return mayor

    def isolated_pickers(self) -> list[Picker]:
        """Pickers que están fuera de la circulación viva (no operativos)."""
        if self.warehouse is None or self.graph is None:
            return []

        vivo = self._live_cells()
        aislados = []
        for p in self.pickers:
            if tuple(p.posicion_actual) not in vivo:
                aislados.append(p)
        return aislados

    def infeasible_waves(self) -> list[Wave]:
        """
        Waves en cola que ningún picker operativo puede cargar por peso.

        No mira si los pickers están ocupados: la capacidad no cambia, así
        que si nadie puede cargarla ahora tampoco podrá al liberarse.
        """
        tope = self._max_capacity(self.pickers)
        pesadas = []
        for wave in self.queue:
            if wave.total_weight() > tope:
                pesadas.append(wave)
        return pesadas

    def infeasibility_message(self) -> str | None:
        """
        Motivo por el que la cola no se va a poder vaciar, o None si todavía
        es asignable.

        Permite cortar la simulación con un error concreto en vez de esperar
        a max_ticks y reportar un falso bloqueo entre pickers.
        """
        if self.warehouse is None or self.graph is None:
            return None
        if len(self.queue) == 0:
            return None

        operativos = self._operational_pickers(self.pickers)
        if len(self.pickers) > 0 and len(operativos) == 0:
            detalle = ", ".join(
                f"{p.picker_id} en {tuple(p.posicion_actual)}"
                for p in self.pickers
            )
            return (
                "No hay pickers operativos: todos están en regiones sin "
                f"retorno a la circulación principal ({detalle})."
            )

        pesadas = self.infeasible_waves()
        if len(pesadas) == 0:
            return None

        tope = self._max_capacity(self.pickers)
        wave = pesadas[0]
        mensaje = (
            f"La wave {wave.wave_id} pesa {wave.total_weight():.2f} kg y el "
            f"picker operativo más capaz puede cargar {tope:.2f} kg."
        )
        if len(pesadas) > 1:
            otros = ", ".join(w.wave_id for w in pesadas[1:])
            mensaje = mensaje + f" También quedan sin picker: {otros}."

        aislados = self.isolated_pickers()
        if len(aislados) > 0:
            detalle = ", ".join(
                f"{p.picker_id} ({p.capacidad_carga_kg:.2f} kg) en "
                f"{tuple(p.posicion_actual)}"
                for p in aislados
            )
            mensaje = mensaje + f" Pickers fuera de la circulación: {detalle}."
        return mensaje

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

    def _fila(self, item: OrderItem) -> dict[tuple[int, int], int]:
        """
        Fila de la tabla de distancias para el rack del ítem: la distancia
        desde sus celdas de recogida hasta cada celda de pasillo.

        La primera vez se calcula con un BFS y se guarda; después solo se lee.
        Dos productos en la misma celda del rack comparten la fila.

        Complejidad: O(V + E) la primera vez por rack, O(1) las siguientes.
        """
        rack = (item.product.x, item.product.y)
        if rack not in self._tabla_distancias:
            self._tabla_distancias[rack] = bfs_distances(self.graph, self._pickup_cells(item))
            self.bfs_corridos = self.bfs_corridos + 1
        return self._tabla_distancias[rack]

    def _acercar(
        self,
        dist: dict[tuple[int, int], int],
        nuevos: list[OrderItem],
        racks_sumados: set[tuple[int, int]],
    ) -> None:
        """
        Actualiza dist (distancia de la wave a cada celda) después de agregar
        los ítems nuevos: en cada celda queda el mínimo entre lo que ya había
        y la fila del rack de cada ítem nuevo. Un rack que ya estaba en la
        wave no cambia nada, así que se saltea (racks_sumados).

        Complejidad: O(V) por rack nuevo, sin correr BFS si la fila ya estaba.
        """
        for item in nuevos:
            rack = (item.product.x, item.product.y)
            if rack in racks_sumados:
                continue
            racks_sumados.add(rack)
            fila = self._fila(item)
            for celda in fila:
                if celda not in dist or fila[celda] < dist[celda]:
                    dist[celda] = fila[celda]

    def _distances_from_wave(self, wave: Wave) -> dict[tuple[int, int], int] | None:
        """
        Distancia de la wave a cada celda: la menor distancia desde alguno de
        sus racks, armada con las filas de la tabla. Devuelve {celda: distancia},
        o None si no hay grafo.

        Da lo mismo que un BFS multi-origen desde todas las celdas de recogida
        de la wave, pero sin volver a calcular los racks que ya están en la tabla.
        """
        if self.graph is None or self.warehouse is None:
            return None
        dist = {}
        self._acercar(dist, wave.get_items(), set())
        return dist

    def _distances_from_zones(self) -> dict[tuple[int, int], int] | None:
        """
        Distancia desde las zonas de despacho (la más cercana) hasta cada
        celda: un BFS multi-origen desde las celdas de acceso de todas las
        zonas. Se calcula una sola vez y se guarda. None si no hay grafo.

        Complejidad: O(V + E) la primera vez, O(1) las siguientes.
        """
        if self.graph is None or self.warehouse is None:
            return None
        if self._dist_zonas is None:
            origenes = set()
            for zona in self.warehouse.dispatch_zones:
                for celda in dispatch_access_cells(zona, self.warehouse, self.graph):
                    origenes.add(celda)
            self._dist_zonas = bfs_distances(self.graph, origenes)
            self.bfs_corridos = self.bfs_corridos + 1
        return self._dist_zonas

    def _distance(
        self,
        items: list[OrderItem],
        dist: dict[tuple[int, int], int] | None,
        incluir_z: bool = True,
    ) -> float:
        """
        Distancia de la wave a un pedido: la menor distancia a alguna celda
        de recogida de sus ítems. 0 si no hay grafo; infinito si no llega.

        Si incluir_z es True, se suma Product.costo_altura() (z - 1: solo
        subida, no se cuenta la bajada) a la distancia de pasillo, así un
        producto en un nivel más alto se considera más "lejos" que uno en el
        piso aunque la celda de pasillo sea la misma.
        """
        if dist is None:
            return 0
        menor = INFINITO
        for item in items:
            for celda in self._pickup_cells(item):
                if celda in dist:
                    d = dist[celda]
                    if incluir_z:
                        d = d + item.product.costo_altura()
                    if d < menor:
                        menor = d
        return menor

    # ------------------------------------------------------------------
    # Etapa 1: armar waves
    # ------------------------------------------------------------------

    def generate_waves(
        self,
        pickers: list[Picker] | None = None,
        prefix: str = "WAVE",
        estrategia_wave: str = "por_pedido",
    ) -> list[Wave]:
        """
        Arma waves con los ítems pendientes (etapa 1) y después asigna
        pickers libres a la cola (etapa 2).

        Args:
            pickers: Pickers extra a considerar (por defecto, los del warehouse).
            prefix : Prefijo de los ids de las waves ("WAVE01", "WAVE02"...).
            estrategia_wave: "por_pedido" (el algoritmo original, agrupa
                pedidos enteros y divide solo como último recurso),
                "por_cercania" (agrupa ítems de distintos pedidos si están
                cerca, respetando prioridad y permitiendo dividir pedidos) o
                "solo_cercania" (igual que "por_cercania" pero sin mirar la
                prioridad: solo cuenta la distancia).

        Returns:
            Las waves nuevas, en orden de creación. Las que no consiguieron
            picker quedan en la cola (get_queued_waves).

        Complejidad: con L racks distintos en los pedidos y N candidatos
        (pedidos en "por_pedido", ítems en "por_cercania"):
            - llenar la tabla: como mucho L BFS en toda la vida del manager,
              O(L · (V + E));
            - cada agregado: actualizar la distancia de la wave, O(V) si el
              rack es nuevo en la wave, y recorrer los candidatos, O(N).
        En total O(L · (V + E) + N · (V + N)). Antes era un BFS por cada
        agregado: O(N · (V + E + N)).
        """
        self.unprocessable_orders = []
        # La lista se vacía en cada armado, así que hay que volver a validar
        # el stock: si no, se pierde lo que marcó el constructor.
        if self.warehouse is not None and self.orders:
            self._validate_stock_consistency()

        if estrategia_wave not in ("por_pedido", "por_cercania", "solo_cercania"):
            raise ValueError(
                f"Estrategia de wave desconocida '{estrategia_wave}'. "
                "Opciones: 'por_pedido', 'por_cercania', 'solo_cercania'."
            )

        todos_los_pickers = self._register_pickers(pickers)
        max_peso = self._max_capacity(todos_los_pickers)
        if max_peso <= 0:
            # Distinguir "no hay pickers" de "hay pickers pero ninguno puede
            # operar": en el segundo caso el escenario es inviable y conviene
            # avisar en vez de devolver una lista vacía en silencio.
            if len(todos_los_pickers) > 0 and len(self.get_pending_orders()) > 0:
                raise ValueError(
                    "Hay pickers configurados, pero ninguno puede operar: "
                    "todos están en regiones sin retorno a la circulación "
                    "principal."
                )
            return []

        # 1. Ítems posibles de cada pedido. Los imposibles se informan y no se usan.
        orders_imposibles = {o.order_id for o, _ in self.unprocessable_orders}
        viable = {}    # {order_id: lista de ítems que sí pueden entrar}
        for order in self.get_pending_orders():
            if order.order_id in orders_imposibles:
                continue
            posibles = []
            for item in order.pending_items:
                ok, motivo = self._validate_item_feasibility(order, item, max_peso)
                if ok:
                    posibles.append(item)
                else:
                    self.unprocessable_orders.append((order, motivo))
            if len(posibles) > 0:
                viable[order.order_id] = posibles

        # 2. Pedidos con ítems viables, del más prioritario al menos prioritario.
        pending = []
        for order in self.get_pending_orders():
            if order.order_id in viable:
                pending.append(order)
        pending = sorted(pending, key=_order_key)

        if estrategia_wave == "por_cercania":
            new_waves = self._generate_waves_por_cercania(viable, pending, max_peso, prefix)
        elif estrategia_wave == "solo_cercania":
            new_waves = self._generate_waves_por_cercania(
                viable, pending, max_peso, prefix, usar_prioridad=False
            )
        else:
            new_waves = self._generate_waves_por_pedido(viable, pending, max_peso, prefix)

        for wave in new_waves:
            self.waves.append(wave)
            self.queue.append(wave)
        self.queue = sorted(self.queue, key=self._queue_key)
        self.assign_pickers()
        return new_waves

    def _generate_waves_por_pedido(
        self,
        viable: dict[str, list[OrderItem]],
        pending: list[Order],
        max_peso: float,
        prefix: str,
    ) -> list[Wave]:
        """
        Algoritmo original: arma la wave con un pedido semilla y agrega pedidos
        completos mientras entren; divide un pedido solo si ni siquiera vacío
        entra en una wave nueva.
        """
        new_waves = []
        while len(pending) > 0:
            numero = len(self.waves) + len(new_waves) + 1
            wave = Wave(
                wave_id=prefix + str(numero).zfill(2),
                max_pedidos=self.max_pedidos,
                max_productos=self.max_productos,
            )

            # 3. La semilla: el pedido más prioritario que queda.
            seed = pending[0]
            self._add_seed(wave, seed, viable, max_peso)

            # 4. Agregar el mejor candidato mientras entre alguno. La distancia
            #    de la wave se arma una vez y se actualiza con cada pedido nuevo.
            dist = self._distances_from_wave(wave)
            racks_sumados = set()
            if dist is not None:
                for item in wave.get_items():
                    racks_sumados.add((item.product.x, item.product.y))
            while True:
                best = self._best_candidate(wave, pending, seed, viable, dist, max_peso)
                if best is None:
                    break
                agregados = viable[best.order_id]
                wave.add_items(best, agregados, max_peso)
                viable[best.order_id] = []
                if dist is not None:
                    self._acercar(dist, agregados, racks_sumados)

            # 5. Quedan solo los pedidos con ítems sin wave.
            quedan = []
            for order in pending:
                if len(viable[order.order_id]) > 0:
                    quedan.append(order)
            pending = quedan
            new_waves.append(wave)

        return new_waves

    def _generate_waves_por_cercania(
        self,
        viable: dict[str, list[OrderItem]],
        pending: list[Order],
        max_peso: float,
        prefix: str,
        usar_prioridad: bool = True,
    ) -> list[Wave]:
        """
        Nuevo algoritmo: arma la wave ítem por ítem, eligiendo siempre el
        ítem más cercano a la wave (distancia de pasillo + subida z) entre los
        de mayor prioridad disponible. Esto agrupa naturalmente ítems de
        distintos pedidos que estén cerca, sin esperar a que un pedido entre
        completo. Los pedidos pueden dividirse entre varias waves.

        Si usar_prioridad es False ("solo_cercania"), la prioridad no se mira:
        la semilla es el ítem más cercano a las zonas de despacho y después
        se suma siempre el ítem más cercano a la wave.

        Cada wave respeta max_pedidos (cantidad de pedidos distintos),
        max_productos (unidades) y max_peso.
        """
        # Lista plana de ítems pendientes: (pedido, ítem)
        pending_items: list[tuple[Order, OrderItem]] = []
        for order in pending:
            for item in viable[order.order_id]:
                pending_items.append((order, item))

        new_waves = []
        while len(pending_items) > 0:
            numero = len(self.waves) + len(new_waves) + 1
            wave = Wave(
                wave_id=prefix + str(numero).zfill(2),
                max_pedidos=self.max_pedidos,
                max_productos=self.max_productos,
            )

            if usar_prioridad:
                # Semilla: ítem del pedido de mayor prioridad. Desempate por id
                # del pedido y luego id del producto, para ser determinista.
                semilla = min(
                    pending_items,
                    key=lambda oi: (-oi[0].prioridad, oi[0].order_id, oi[1].product.product_id),
                )
            else:
                # Semilla: el ítem más cercano a las zonas de despacho
                # (distancia de pasillo + subida z), sin mirar la prioridad.
                dist_zonas = self._distances_from_zones()
                semilla = min(
                    pending_items,
                    key=lambda oi: (self._distance([oi[1]], dist_zonas), oi[0].order_id, oi[1].product.product_id),
                )
            wave.add_items(semilla[0], [semilla[1]], max_peso)
            pending_items.remove(semilla)

            # Distancia de la wave a cada celda: se arma con la fila de la
            # semilla y se actualiza con cada ítem que se agrega.
            dist = self._distances_from_wave(wave)
            racks_sumados = {(semilla[1].product.x, semilla[1].product.y)}

            # Agregar el mejor candidato (más cercano, prioridad manda) mientras entre alguno.
            while True:
                mejor = None
                mejor_clave = None
                for order, item in pending_items:
                    if not wave.can_add_items(order, [item], max_peso):
                        continue
                    d = self._distance([item], dist, incluir_z=True)
                    # Sin prioridad, todos cuentan como prioridad 0 y decide la distancia.
                    prioridad = order.prioridad if usar_prioridad else 0
                    clave = (-prioridad, d, order.order_id)
                    if mejor is None or clave < mejor_clave:
                        mejor = (order, item)
                        mejor_clave = clave
                if mejor is None:
                    break
                wave.add_items(mejor[0], [mejor[1]], max_peso)
                pending_items.remove(mejor)
                if dist is not None:
                    self._acercar(dist, [mejor[1]], racks_sumados)

            new_waves.append(wave)

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

    def _fila_desde(self, celda: tuple[int, int]) -> dict[tuple[int, int], int]:
        """
        Distancia DESDE una celda (donde está un picker) hasta cada celda.
        La primera vez se calcula con un BFS y se guarda; después solo se lee.

        Complejidad: O(V + E) la primera vez por celda, O(1) las siguientes.
        """
        celda = tuple(celda)
        if celda not in self._tabla_desde_pickers:
            self._tabla_desde_pickers[celda] = bfs_distances(self.graph, {celda})
            self.bfs_pickers = self.bfs_pickers + 1
        return self._tabla_desde_pickers[celda]

    def _picker_distance(self, picker: Picker, wave: Wave) -> float:
        """
        Pasos que tiene que caminar el picker desde donde está hasta la parada
        más cercana de la wave. 0 si no hay grafo (todos empatan y decide el
        best fit); infinito si no puede llegar. La altura no se suma: es la
        misma para cualquier picker que vaya.
        """
        if self.graph is None or self.warehouse is None:
            return 0
        fila = self._fila_desde(picker.posicion_actual)
        return self._distance(wave.get_items(), fila, incluir_z=False)

    def _closest_picker(self, candidatos: list[Picker], wave: Wave) -> Picker | None:
        """
        El picker de candidatos más cercano a la wave (desempate: menor
        capacidad, después menor id). None si ninguno puede llegar.
        """
        elegido = None
        mejor_clave = None
        for p in candidatos:
            d = self._picker_distance(p, wave)
            if d == INFINITO:
                continue
            clave = _closer_picker_key(d, p)
            if mejor_clave is None or clave < mejor_clave:
                elegido = p
                mejor_clave = clave
        return elegido

    def _queue_key(self, wave: Wave) -> tuple[int, int]:
        """Orden de la cola: mayor prioridad primero, después la más antigua."""
        return (-wave.priority(), self.waves.index(wave))

    def assign_pickers(self, pickers: list[Picker] | None = None) -> list[Wave]:
        """
        Recorre la cola en orden (mayor prioridad primero) y le da a cada wave
        el picker libre más cercano entre los que la pueden cargar (si empatan,
        el más chico). Una wave que no encuentra picker sigue esperando, y las
        siguientes pueden tomar otros pickers mientras tanto.

        Es greedy: cada wave elige en su turno lo mejor que queda, sin volver
        atrás. Complejidad: O(W * P * c) con la tabla ya llena, donde W son
        las waves en cola, P los pickers libres y c las celdas de recogida de
        la wave; más un BFS O(V + E) por cada celda de picker nueva.

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
            pueden_cargarla = []
            for p in libres:
                if p.capacidad_carga_kg >= wave.total_weight():
                    pueden_cargarla.append(p)
            elegido = self._closest_picker(pueden_cargarla, wave)
            if elegido is None:
                continue
            wave.assign_picker(elegido)
            libres.remove(elegido)
            self.queue.remove(wave)
            assigned.append(wave)

        # Fase 2: pickers sobrantes → refuerzo a las waves más cargadas
        if libres and assigned:
            self._assign_extra_pickers(libres, assigned)
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
    # Asignación multi-picker (Fase 2)
    # ------------------------------------------------------------------

    MAX_PICKERS_POR_WAVE = 3   # tope de pickers simultáneos por wave

    def _wave_stop_count(self, wave: "Wave") -> int:
        """Cantidad de celdas de rack distintas que visita la wave."""
        celdas = set()
        for item in wave.get_items():
            celdas.add((item.product.x, item.product.y))
        return len(celdas)

    def _assign_extra_pickers(
        self, libres: list[Picker], waves_asignadas: list["Wave"]
    ) -> None:
        """
        Asigna pickers sobrantes como refuerzo a las waves con más paradas.

        Una wave solo recibe un picker extra si:
          1. La wave tiene al menos (n_pickers_actuales + 1) celdas de rack
             distintas, garantizando al menos 1 parada por picker.
          2. La wave no supera MAX_PICKERS_POR_WAVE.

        Las waves se recorren en orden descendente de paradas y en rondas
        sucesivas, de modo que la distribución sea equitativa cuando hay
        más pickers sobrantes que waves candidatas. A cada wave se le manda
        el picker sobrante más cercano (mismo criterio que en assign_pickers;
        acá no se mira la capacidad porque el refuerzo lleva solo una parte).
        """
        # Precalcular paradas para no repetir la operación en cada ronda
        waves_por_carga = []
        for wave in waves_asignadas:
            waves_por_carga.append((self._wave_stop_count(wave), wave))
        waves_por_carga.sort(key=lambda t: -t[0])

        sobrantes = list(libres)
        hubo_asignacion = True
        while sobrantes and hubo_asignacion:
            hubo_asignacion = False
            for n_stops, wave in waves_por_carga:
                if not sobrantes:
                    break
                if len(wave.pickers) >= self.MAX_PICKERS_POR_WAVE:
                    continue
                # Cada picker debe tener al menos 1 parada tras agregar el extra
                if n_stops < len(wave.pickers) + 1:
                    continue
                extra = self._closest_picker(sobrantes, wave)
                if extra is None:
                    continue
                wave.assign_picker(extra)
                sobrantes.remove(extra)
                hubo_asignacion = True

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_waves(self) -> list[Wave]:
        return list(self.waves)

    def get_queued_waves(self) -> list[Wave]:
        return list(self.queue)

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

    # El tipo de retorno va entre comillas porque la clase todavía se está
    # definiendo en este punto (Python no la conoce hasta terminar la clase).
    @classmethod
    def from_dict(cls, data: dict, warehouse: Warehouse) -> "WaveManager":
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
