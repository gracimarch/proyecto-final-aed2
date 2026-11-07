"""
models/simulation.py

Simulación de todos los pickers a la vez (consigna §12).

El back hace todo el trabajo y devuelve una lista de "frames": cómo está el
warehouse en cada instante (tick). El front solo los dibuja uno por uno.

En cada tick:
    1. Mover: se decide quién avanza. Si dos pickers quedarían en la misma
       celda o se cruzarían (§3.6), espera el de wave con menor prioridad.
       Si un picker espera varios ticks seguidos, busca un camino
       alternativo hasta su próxima parada esquivando a los demás.
    2. Recoger y descargar: al llegar a una parada recoge sus productos y se
       detiene por 1 tick base más 1 tick adicional por cada diferencia z de
       altura del producto (z=1 -> 1 tick, z=2 -> 2 ticks, etc.), permitiendo
       que los demás pickers continúen trabajando. Con todo recogido, al
       llegar a su zona descarga lo que entra. Si le sobra carga (la zona se
       llenó mientras caminaba) busca la próxima zona con lugar.
    3. Terminar: el picker que ya descargó todo termina su wave y el
       WaveManager le da la siguiente de la cola.
    4. Arrancar: cada picker que recibió una wave calcula su recorrido desde
       donde está (plan_route con inicio) y empieza a caminar.
    5. Se guarda el frame.

Termina cuando no quedan waves por preparar o se llega a max_ticks.
"""

import time

from algorithms.graph import bfs_to_any
from algorithms.routing import plan_route, plan_unloading, graph_without

from models.picker import Picker
from models.warehouse import DispatchZone, Warehouse
from models.wave import Wave, WaveStatus
from models.wave_manager import WaveManager


class _Task:
    """
    Lo que le falta hacer a un picker con su wave.

    Atributos:
        wave            (Wave)  : Wave que está preparando.
        paradas         (dict)  : {celda: [product_id, ...]} que faltan recoger.
        descargas       (list)  : [(celda, zone_id), ...] que faltan hacer.
        ruta            (list)  : Camino que está siguiendo (para dibujarlo).
        paso            (int)   : Índice de su posición dentro de ruta.
        esperas_seguidas (int)  : Ticks seguidos que lleva esperando.
        cooldown_recogida (int) : Ticks restantes de pausa por recogida (según altura z).
    """

    def __init__(self, wave: Wave, path: list[tuple[int, int]]):
        self.wave = wave
        self.paradas = {}
        self.descargas = []
        self.descargas_originales = []   # descargas finales planificadas (se restauran tras descarga intermedia)
        self.ruta = path
        self.paso = 0
        self.esperas_seguidas = 0
        self.esperas_totales = 0   # contador de esperas totales (para envejecimiento)
        self.cooldown_recogida = 0
        self.descarga_intermedia = False   # True si el picker está yendo a descargar por haberse llenado


class Simulation:
    """
    Simula la preparación de todas las waves con todos los pickers.

    Uso:
        sim = Simulation(warehouse, manager, "cercania", "bfs")
        frames = sim.run()

    Atributos:
        frames   (list[dict]) : Un frame por tick (ver _save_frame).
        error    (str o None) : Motivo si la simulación no pudo terminar.
        rutas    (list[dict]) : Métricas de cada recorrido calculado (§10).
    """

    ESPERA_MAXIMA = 3    # ticks seguidos esperando antes de buscar otro camino

    def __init__(
        self,
        warehouse: Warehouse,
        manager: WaveManager,
        estrategia: str = "cercania",
        buscador: str = "bfs",
        max_ticks: int = 5000,
        speed_multiplier: int = 1,
    ):
        self.warehouse = warehouse
        self.manager = manager
        self.graph = manager.graph
        self.estrategia = estrategia
        self.buscador = buscador
        self.max_ticks = max_ticks
        self.speed_multiplier = max(1, speed_multiplier)

        self.tick = 0
        self.tasks = {}          # picker_id -> _Task
        self.esperando = set()   # pickers que esperaron en este tick
        self.recogiendo = set()  # pickers que se detuvieron a recoger en este tick
        self.eventos = []        # lo que pasó en este tick
        self.frames = []
        self.rutas = []
        self.esperas = 0
        self.desvios = 0
        self.nodos_expandidos = 0
        self.error = None
        self.cedieron_paso = set()   # pickers que cedieron el paso este tick (necesitan recálculo de ruta)
        self.parking_plans = {}      # picker_id -> camino hacia una celda donde no estorbar

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def run(self) -> list[dict]:
        """
        Corre la simulación completa y devuelve los frames.

        Si algo impide seguir (por ejemplo, ninguna zona tiene lugar), se
        corta, se guarda el motivo en self.error y se devuelven los frames
        hasta ese momento.
        """
        inicio = time.perf_counter()
        try:
            self._start_assigned_waves()
            self._save_frame()
            while not self._finished() and self.tick < self.max_ticks:
                # Procesar speed_multiplier ticks internos por frame guardado.
                # Con speed_multiplier=10 la simulación avanza 10 veces más
                # rápido en cantidad de frames devueltos.
                for _ in range(self.speed_multiplier):
                    if self._finished() or self.tick >= self.max_ticks:
                        break
                    self.tick = self.tick + 1
                    self._move_pickers()
                    self._pick_and_unload()
                    self._finish_waves()
                    self._start_assigned_waves()
                self._save_frame()
            if not self._finished():
                self.error = (
                    f"La simulación no terminó en {self.max_ticks} ticks "
                    f"(posible bloqueo entre pickers)."
                )
        except ValueError as e:
            self.error = str(e)
            self._save_frame()
        self.tiempo_ms = (time.perf_counter() - inicio) * 1000
        return self.frames

    def _finished(self) -> bool:
        """True si ningún picker tiene wave y no quedan waves esperando."""
        if len(self.tasks) > 0:
            return False
        for wave in self.manager.get_waves():
            if wave.status != WaveStatus.COMPLETADA:
                return False
        return True

    # ------------------------------------------------------------------
    # 1. Mover
    # ------------------------------------------------------------------

    def _destination(self, picker: Picker) -> tuple[int, int]:
        """Celda donde quiere estar en el próximo tick (la suya si no camina o está recogiendo)."""
        # Los pickers libres que estorban siguen su plan de estacionamiento.
        if picker.picker_id in self.parking_plans:
            plan = self.parking_plans[picker.picker_id]
            if plan:
                return plan[0]
        if picker.picker_id in self.tasks:
            task = self.tasks[picker.picker_id]
            if task.cooldown_recogida > 0:
                return picker.posicion_actual
            if picker.next_cell is not None:
                return picker.next_cell
        return picker.posicion_actual

    def _crash(self, a: Picker, b: Picker, destino: dict) -> bool:
        """True si a y b quedarían en la misma celda o se cruzarían (§3.6)."""
        misma_celda = destino[a.picker_id] == destino[b.picker_id]
        se_cruzan = (destino[a.picker_id] == b.posicion_actual
                     and destino[b.picker_id] == a.posicion_actual)
        return misma_celda or se_cruzan

    def _inamovible(self, picker: Picker) -> bool:
        """
        True si el picker no se puede mover en este tick porque está
        recogiendo (pausa por altura). A un picker así no se le puede pedir
        que se aparte ni que retroceda: no se movería y el otro entraría a
        su celda (dos pickers en la misma celda, prohibido por §3.6).
        """
        task = self.tasks.get(picker.picker_id)
        return task is not None and task.cooldown_recogida > 0

    def _movimiento_posible(self, picker: Picker, celda: tuple[int, int]) -> bool:
        """
        True si el picker de verdad puede ir a celda en este tick: quedarse
        siempre se puede; moverse, solo si no está recogiendo, si existe la
        arista (respeta los sentidos) y, si tiene tarea, si tiene un plan.
        La fase de movimiento de _move_pickers hace exactamente esto.
        """
        if celda == picker.posicion_actual:
            return True
        if self._inamovible(picker):
            return False
        if not self.graph.has_edge(picker.posicion_actual, celda):
            return False
        if not self._puede_apartarse(picker) and picker.next_cell is None:
            return False
        return True

    def _puede_apartarse(self, picker: Picker) -> bool:
        """
        True si el picker no tiene nada que hacer y puede correrse para dejar
        pasar a otro: está libre, o ya terminó su parte de una wave con varios
        pickers (sin paradas ni carga) y solo espera a sus compañeros.

        Sin esto, un picker que terminó su parte y quedó parado en la celda
        de descarga bloquea para siempre al compañero que tiene que descargar
        ahí, y la wave nunca se completa.
        """
        task = self.tasks.get(picker.picker_id)
        if task is None:
            return True
        return len(task.paradas) == 0 and len(picker.carga) == 0 and picker.next_cell is None

    # ------------------------------------------------------------------
    # Estacionamiento de pickers libres
    # ------------------------------------------------------------------
    #
    # Un picker que ya terminó su parte (o que no tiene wave) puede quedar
    # parado justo en una celda que otro todavía necesita. Si el pasillo es
    # de una sola celda de ancho y sin salida lateral, empujarlo "al costado"
    # lo mete cada vez más al fondo y termina trabado. Para evitarlo le
    # calculamos un camino hasta una celda segura (fuera de los recorridos
    # de los pickers activos) y lo seguimos tick a tick. El picker con tarea
    # cede el paso mientras el libre sale del pasillo.

    def _update_parking_plans(self) -> None:
        """
        Calcula/actualiza el plan de estacionamiento de los pickers libres.

        Un picker necesita estacionarse si su celda actual está dentro del
        recorrido pendiente de algún picker activo (con tarea). Se busca la
        celda segura más cercana que no esté en ningún recorrido activo ni
        ocupada por otro picker.
        """
        activos = [
            p for p in self.warehouse.pickers
            if p.picker_id in self.tasks and not self._puede_apartarse(p)
        ]
        celdas_activas = set()
        posiciones_activos = set()
        for p in activos:
            celdas_activas.update(p.plan)
            posiciones_activos.add(p.posicion_actual)
        if not celdas_activas:
            self.parking_plans.clear()
            return

        ocupadas = {p.posicion_actual for p in self.warehouse.pickers}

        for picker in self.warehouse.pickers:
            # Solo los pickers libres se estacionan.
            if not self._puede_apartarse(picker):
                self.parking_plans.pop(picker.picker_id, None)
                continue
            # Si ya tiene un plan, lo conservamos (se va consumiendo al
            # caminar). Se recalcula si quedó vacío o si dejó de servir: pasa
            # por donde está ahora un picker con tarea o termina en una celda
            # que ahora está en el recorrido de alguien.
            if picker.picker_id in self.parking_plans:
                plan = self.parking_plans[picker.picker_id]
                sigue_sirviendo = (
                    len(plan) > 0
                    and plan[-1] not in celdas_activas
                    and not any(c in posiciones_activos for c in plan)
                )
                if sigue_sirviendo:
                    continue
                del self.parking_plans[picker.picker_id]
            # Si no está en el camino de nadie, no hace falta moverse.
            if picker.posicion_actual not in celdas_activas:
                continue
            camino = self._parking_path(
                picker, celdas_activas, ocupadas, posiciones_activos
            )
            if camino:
                self.parking_plans[picker.picker_id] = camino

    def _parking_path(
        self,
        picker: Picker,
        celdas_activas: set[tuple[int, int]],
        ocupadas: set[tuple[int, int]],
        posiciones_activos: set[tuple[int, int]] = frozenset(),
    ) -> list[tuple[int, int]]:
        """
        BFS desde la posición del picker hasta la celda segura más cercana.

        Se puede atravesar cualquier celda del grafo (aunque esté en el
        recorrido de otro picker o la ocupe un picker libre: el resto de la
        simulación coordina el paso), salvo las que ocupa un picker con tarea:
        pasar "a través" de él lo obliga a retroceder y los dos terminan
        yendo y viniendo para siempre en un pasillo angosto. La celda final no puede estar en un
        recorrido activo ni ocupada, y se prefiere que no sea un callejón
        sin salida.

        Devuelve las celdas a recorrer (sin incluir la posición actual), o []
        si no hay ninguna celda segura alcanzable.
        """
        from collections import deque

        inicio = picker.posicion_actual
        cola: deque[tuple[tuple[int, int], list[tuple[int, int]]]] = deque()
        cola.append((inicio, []))
        visitados = {inicio}
        primera_segura: list[tuple[int, int]] | None = None

        while cola:
            celda, camino = cola.popleft()
            # ¿Es una celda segura donde estacionarse?
            if camino:
                seguro = (
                    celda not in celdas_activas
                    and celda not in ocupadas
                )
                if seguro:
                    if len(self.graph.neighbors(celda)) >= 2:
                        return camino
                    if primera_segura is None:
                        primera_segura = camino
            x, y = celda
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cand = (x + dx, y + dy)
                if cand in visitados or not self.graph.has_edge(celda, cand):
                    continue
                if cand in posiciones_activos:
                    continue
                visitados.add(cand)
                cola.append((cand, camino + [cand]))

        return primera_segura if primera_segura is not None else []

    def _cede_el_paso(self, picker: Picker, destino: dict) -> bool:
        """
        Hace retroceder una celda al picker para que otro pueda salir del
        paso. Devuelve True si pudo ceder.
        """
        if self._inamovible(picker):
            return False
        anterior = picker.celda_anterior()
        if anterior is None:
            return False
        if not self.graph.has_edge(picker.posicion_actual, anterior):
            return False
        for otro in self.warehouse.pickers:
            if otro is not picker and otro.posicion_actual == anterior:
                return False
        destino[picker.picker_id] = anterior
        self.cedieron_paso.add(picker.picker_id)
        return True

    def _sacar_libre_del_paso(
        self,
        libre: Picker,
        tarea: Picker,
        destino: dict,
    ) -> bool:
        """
        Decide a dónde mover al picker libre para que no estorbe al picker
        con tarea.

        Orden de preferencia:
            1. Seguir su plan de estacionamiento (la celda que no estorba).
            2. Si el primer paso del plan está ocupado por un picker con
               tarea que puede retroceder, hacer una rotación: ese picker
               retrocede una celda y el libre ocupa la celda que dejó.
            3. Si no hay plan o no se puede seguir, usar la lógica clásica de
               apartarse a una celda adyacente libre / cadena.

        Devuelve True si le asignó al picker libre una celda distinta de la
        actual.
        """
        plan = self.parking_plans.get(libre.picker_id)
        if plan:
            paso = plan[0]
            ocupante = self._picker_at_posicion(paso, excluir=libre)
            # 1. El paso está libre ahora: seguirlo.
            if ocupante is None:
                destino[libre.picker_id] = paso
                self.cedieron_paso.add(libre.picker_id)
                return True
            # 2a. El paso lo ocupa un picker con tarea que puede retroceder:
            #     rotación directa (el de tarea retrocede y el libre avanza).
            if (
                not self._puede_apartarse(ocupante)
                and ocupante.picker_id not in self.cedieron_paso
                and self._cede_el_paso(ocupante, destino)
            ):
                destino[libre.picker_id] = paso
                self.cedieron_paso.add(libre.picker_id)
                return True
            # 2b. Probar una rotación con cualquier vecino con tarea que sí
            #     pueda retroceder (aunque no sea el paso elegido por el
            #     plan). Así el libre sale del paso aunque el plan apunte a
            #     una salida tapada por un picker que no puede moverse.
            x, y = libre.posicion_actual
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cand = (x + dx, y + dy)
                if not self.graph.has_edge(libre.posicion_actual, cand):
                    continue
                otro = self._picker_at_posicion(cand, excluir=libre)
                if otro is None or self._puede_apartarse(otro):
                    continue
                if otro.picker_id in self.cedieron_paso:
                    continue
                if self._cede_el_paso(otro, destino):
                    destino[libre.picker_id] = cand
                    self.cedieron_paso.add(libre.picker_id)
                    return True
        # 3. Sin plan o sin rotación posible: lógica clásica.
        apartada = self._apartar_picker_libre(
            libre, destino, tarea.posicion_actual
        )
        if apartada is not None:
            destino[libre.picker_id] = apartada
            if apartada != libre.posicion_actual:
                self.cedieron_paso.add(libre.picker_id)
            return True
        return False

    def _celda_adyacente_libre(
        self,
        picker_libre: Picker,
        destino: dict,
        posicion_otro: tuple[int, int],
    ) -> tuple[int, int] | None:
        """
        Busca una celda adyacente libre (arriba, abajo, izquierda, derecha) a
        la posición actual del picker libre, que no sea el destino de ningún
        otro picker ni la posición del picker con tarea.

        Devuelve la celda encontrada o None si no hay ninguna disponible.
        """
        if self._inamovible(picker_libre):
            return None
        x, y = picker_libre.posicion_actual
        ocupadas = set(destino.values())
        ocupadas.add(posicion_otro)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cand = (x + dx, y + dy)
            if self.graph.has_edge(picker_libre.posicion_actual, cand) and cand not in ocupadas:
                return cand
        # Si no hay celda libre inmediatamente, intentar resolver en cadena:
        # un picker libre que ocupe una celda adyacente puede moverse a su vez
        # si a él le queda una celda libre (u otro picker libre, y así).
        return self._celda_adyacente_libre_en_cadena(picker_libre, destino, posicion_otro)

    def _picker_en_celda(
        self, celda: tuple[int, int], destino: dict
    ) -> Picker | None:
        """Devuelve el picker cuyo destino asignado es `celda`, o None."""
        for picker in self.warehouse.pickers:
            if picker.picker_id in destino and destino[picker.picker_id] == celda:
                return picker
        return None

    def _picker_at_posicion(
        self, celda: tuple[int, int], excluir: Picker | None = None
    ) -> Picker | None:
        """Devuelve el picker que ocupa actualmente `celda`, o None."""
        for picker in self.warehouse.pickers:
            if picker is not excluir and picker.posicion_actual == celda:
                return picker
        return None

    def _celda_adyacente_libre_en_cadena(
        self,
        picker_libre: Picker,
        destino: dict,
        posicion_otro: tuple[int, int],
        profundidad: int = 3,
    ) -> tuple[int, int] | None:
        """
        Busca una secuencia de pickers libres que puedan moverse para liberar
        una celda adyacente a `picker_libre`.

        Usa BFS: del picker_libre miramos sus celdas adyacentes. Si una está
        ocupada por un picker libre, miramos si ese picker puede moverse a
        otra celda (libre o ocupada por otro picker libre), y así hasta
        encontrar una celda realmente libre o agotar `profundidad`.

        Si se encuentra una cadena, actualiza `destino` de todos los pickers
        intermedios y devuelve la celda a la que debe moverse `picker_libre`.

        La cadena queda así:
            picker_libre -> posicion_de_picker1
            picker1      -> posicion_de_picker2
            ...
            pickerN      -> celda_libre

        Devuelve None si no se puede resolver la cadena.
        """
        from collections import deque

        x, y = picker_libre.posicion_actual
        visitados = {picker_libre.picker_id}
        # cola: (ocupante_actual, camino_de_ids_desde_picker1_hasta_este)
        cola: deque[tuple[Picker, list[str]]] = deque()

        # Nivel 1: celdas adyacentes a picker_libre
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cand = (x + dx, y + dy)
            if not self.graph.has_edge(picker_libre.posicion_actual, cand) or cand == posicion_otro:
                continue
            ocupante = self._picker_en_celda(cand, destino)
            if ocupante is None:
                continue  # celda libre: ya se manejó arriba
            if not self._puede_apartarse(ocupante):
                continue
            if ocupante.picker_id in visitados:
                continue
            visitados.add(ocupante.picker_id)
            cola.append((ocupante, [ocupante.picker_id]))

        while cola:
            ocupante, camino = cola.popleft()
            if len(camino) >= profundidad:
                continue
            ox, oy = ocupante.posicion_actual
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cand = (ox + dx, oy + dy)
                if not self.graph.has_edge(ocupante.posicion_actual, cand) or cand == posicion_otro:
                    continue
                if cand == picker_libre.posicion_actual:
                    continue  # no volver atrás sobre el origen
                ocupante2 = self._picker_en_celda(cand, destino)
                if ocupante2 is None:
                    # Celda libre encontrada: armar la cadena.
                    # picker_libre va a la posición del primero de la cadena.
                    # Cada picker intermedio va a la posición del siguiente.
                    # El último va a `cand` (la celda libre).
                    primero_id = camino[0]
                    primero = next(
                        p for p in self.warehouse.pickers if p.picker_id == primero_id
                    )
                    # El último de la cadena se mueve a la celda libre.
                    destino[ocupante.picker_id] = cand
                    # Los intermedios (de derecha a izquierda) se mueven a la
                    # posición del siguiente.
                    prev_celda = ocupante.posicion_actual
                    for pid in reversed(camino[1:]):
                        p = next(
                            pp
                            for pp in self.warehouse.pickers
                            if pp.picker_id == pid
                        )
                        destino[p.picker_id] = prev_celda
                        prev_celda = p.posicion_actual
                    # picker1 se mueve a la posición de picker2 (o a cand si
                    # no hay picker2), y picker_libre se mueve a la de picker1.
                    return primero.posicion_actual
                if (
                    self._puede_apartarse(ocupante2)
                    and ocupante2.picker_id not in visitados
                ):
                    visitados.add(ocupante2.picker_id)
                    cola.append((ocupante2, camino + [ocupante2.picker_id]))

        return None

    def _apartar_picker_libre(
        self,
        picker_libre: Picker,
        destino: dict,
        posicion_otro: tuple[int, int],
    ) -> tuple[int, int] | None:
        """
        Intenta mover a un picker libre para liberar el paso de un picker con
        tarea. Prueba en orden: celda adyacente libre, step_back (retroceder
        por historial) y cadena de pickers libres.
        """
        if self._inamovible(picker_libre):
            return None
        libre = self._celda_adyacente_libre(picker_libre, destino, posicion_otro)
        if libre is not None:
            return libre
        anterior = picker_libre.celda_anterior()
        if (
            anterior is not None
            and anterior not in destino.values()
            and anterior != posicion_otro
            and self.graph.has_edge(picker_libre.posicion_actual, anterior)
            and not any(
                otro.posicion_actual == anterior
                for otro in self.warehouse.pickers
                if otro is not picker_libre
            )
        ):
            return anterior
        cadena = self._celda_adyacente_libre_en_cadena(
            picker_libre, destino, posicion_otro
        )
        if cadena is not None:
            return cadena
        # 4. Último recurso: mover a cualquier celda adyacente del grafo que
        #    no esté ocupada por otro picker ni sea el destino de otro. (Si se
        #    ignoraran los destinos, dos pickers se pisan el lugar una y otra
        #    vez dentro del mismo tick y al final nadie se mueve.)
        x, y = picker_libre.posicion_actual
        ocupadas_actuales = set()
        for p in self.warehouse.pickers:
            if p is not picker_libre:
                ocupadas_actuales.add(p.posicion_actual)
                if p.picker_id in destino:
                    ocupadas_actuales.add(destino[p.picker_id])
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cand = (x + dx, y + dy)
            if (
                self.graph.has_edge(picker_libre.posicion_actual, cand)
                and cand not in ocupadas_actuales
                and cand != posicion_otro
            ):
                return cand
        return None

    def _emergencia_step_back(
        self, picker: Picker, destino: dict
    ) -> tuple[int, int] | None:
        """
        Regla de emergencia para romper deadlocks: permite retroceder al
        picker aunque la celda anterior esté ocupada como destino de otro
        (se resuelve en el siguiente pase del while), o moverse a cualquier
        celda adyacente válida del grafo que no esté ocupada por la posición
        actual de otro picker.

        Solo se usa cuando los métodos normales fallaron.
        Devuelve la celda a la que moverse, o None.
        """
        if self._inamovible(picker):
            return None
        # 1. Retroceder por historial (aunque haya arista o destino ocupado).
        anterior = picker.celda_anterior()
        if anterior is not None and self.graph.has_edge(
            picker.posicion_actual, anterior
        ):
            # No mover a la posición actual de otro picker.
            if not any(
                otro.posicion_actual == anterior
                for otro in self.warehouse.pickers
                if otro is not picker
            ):
                return anterior
        # 2. Cualquier celda adyacente válida del grafo no ocupada ahora.
        x, y = picker.posicion_actual
        ocupadas_actuales = {
            p.posicion_actual for p in self.warehouse.pickers if p is not picker
        }
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cand = (x + dx, y + dy)
            if self.graph.has_edge(picker.posicion_actual, cand) and cand not in ocupadas_actuales:
                return cand
        return None

    def _puede_step_back_para_ceder(
        self, picker: Picker, destino: dict
    ) -> bool:
        """
        True si el picker puede retroceder una celda (step_back) para ceder el
        paso en un cruce cara a cara. La celda anterior no puede estar ocupada
        como destino de otro picker ni ser la posición actual de otro picker,
        y debe existir la arista en el grafo.
        """
        if self._inamovible(picker):
            return False
        anterior = picker.celda_anterior()
        if anterior is None:
            return False
        if anterior in destino.values():
            return False
        for otro in self.warehouse.pickers:
            if otro is not picker and otro.posicion_actual == anterior:
                return False
        return self.graph.has_edge(picker.posicion_actual, anterior)

    def _move_pickers(self) -> None:
        """
        Decide quién avanza y quién espera, y mueve a los que avanzan.

        Se revisan todos los pares de pickers, ordenados por prioridad de su
        wave. Si un par choca, espera el de menor prioridad; si ese ya estaba
        quieto, espera el otro. Se repite hasta que no quede ningún choque,
        porque al hacer esperar a uno puede aparecer un choque nuevo.

        Complejidad: O(P²) por pasada, con P pickers.
        """
        # Orden para decidir quién pasa primero: mayor prioridad de wave y,
        # si empatan, por id. Se ordenan tuplas (-prioridad, id, picker).
        claves = []
        for picker in self.warehouse.pickers:
            prioridad = 0
            bonus_espera = 0
            if picker.picker_id in self.tasks:
                task = self.tasks[picker.picker_id]
                prioridad = task.wave.priority()
                # Envejecimiento: esperas totales y esperas seguidas suman
                # prioridad efectiva. Así un picker que lleva muchas esperas
                # (aunque no sean seguidas) deja de ser siempre el perdedor
                # en las colisiones y puede avanzar para romper el bloqueo.
                bonus_esperas_totales = min(task.esperas_totales // 20, 10)
                bonus_espera_seguidas = min(task.esperas_seguidas // 5, 5)
                bonus_espera = max(bonus_esperas_totales, bonus_espera_seguidas)
            claves.append((-(prioridad + bonus_espera), picker.picker_id, picker))
        claves.sort()
        ordenados = []
        for prioridad, picker_id, picker in claves:
            ordenados.append(picker)

        # Antes de decidir movimientos, calculamos si algún picker libre está
        # estorbando en el recorrido de otro y hacia dónde puede estacionarse.
        self._update_parking_plans()

        destino = {}
        for picker in ordenados:
            destino[picker.picker_id] = self._destination(picker)

        hubo_cambio = True
        _iter = 0
        _max_iter = max(50, len(ordenados) * len(ordenados) * 8)
        while hubo_cambio:
            _iter += 1
            if _iter > _max_iter:
                # Salvaguarda: no dejar que la resolución de choques entre en
                # un ciclo infinito. Si se agota, todos esperan este tick.
                for _p in ordenados:
                    destino[_p.picker_id] = _p.posicion_actual
                break
            hubo_cambio = False
            for i in range(len(ordenados)):
                for j in range(i + 1, len(ordenados)):
                    a = ordenados[i]
                    b = ordenados[j]
                    if not self._crash(a, b, destino):
                        continue
                    # Solución 1: picker con tarea tiene prioridad, pero el
                    # picker libre se aparta a una celda adyacente libre para
                    # no atravesarlo y respetar la regla de no colisión (§3.6).
                    a_tiene_tarea = not self._puede_apartarse(a)
                    b_tiene_tarea = not self._puede_apartarse(b)
                    if a_tiene_tarea and not b_tiene_tarea:
                        # b está libre y estorba a a.
                        if not self._sacar_libre_del_paso(b, a, destino):
                            # b no tiene dónde ir: a retrocede para abrirle
                            # paso, o espera si tampoco puede.
                            if not self._cede_el_paso(a, destino):
                                destino[a.picker_id] = a.posicion_actual
                        hubo_cambio = True
                        continue
                    if b_tiene_tarea and not a_tiene_tarea:
                        # a está libre y estorba a b.
                        if not self._sacar_libre_del_paso(a, b, destino):
                            if not self._cede_el_paso(b, destino):
                                destino[b.picker_id] = b.posicion_actual
                        hubo_cambio = True
                        continue
                    # Ambos tienen tarea o ambos son libres: lógica original.
                    # Si es un cruce cara a cara sin escape lateral, el de menor
                    # prioridad (b) cede el paso: primero intenta retroceder una
                    # celda (step_back) y, si no puede (sin historial o pasillo
                    # de un solo sentido), se aparta a una celda adyacente libre.
                    se_cruzan = (
                        destino[a.picker_id] == b.posicion_actual
                        and destino[b.picker_id] == a.posicion_actual
                    )
                    if se_cruzan:
                        # 1. Intentar step_back del de menor prioridad (b).
                        if self._puede_step_back_para_ceder(b, destino):
                            destino[b.picker_id] = b.celda_anterior()
                            self.cedieron_paso.add(b.picker_id)
                            hubo_cambio = True
                            continue
                        # 2. Intentar apartarse a celda adyacente libre.
                        apartada = self._celda_adyacente_libre(b, destino, a.posicion_actual)
                        if apartada is not None:
                            destino[b.picker_id] = apartada
                            self.cedieron_paso.add(b.picker_id)
                            hubo_cambio = True
                            continue
                        # 3. Último recurso: step_back forzado de b aunque la
                        #    celda anterior esté en destino.values() (se resuelve
                        #    en el siguiente pase del while) o intente desvío.
                        anterior = b.celda_anterior()
                        if (
                            anterior is not None
                            and not self._inamovible(b)
                            and self.graph.has_edge(b.posicion_actual, anterior)
                        ):
                            destino[b.picker_id] = anterior
                            self.cedieron_paso.add(b.picker_id)
                            hubo_cambio = True
                            continue
                        # 4. Si ni siquiera se puede retroceder: intentar
                        #    desvío inmediato para romper el deadlock.
                        if self._detour(b, self.tasks[b.picker_id]):
                            hubo_cambio = True
                            continue
                        # 5. Nada funciona: a espera.
                        destino[a.picker_id] = a.posicion_actual
                        hubo_cambio = True
                        continue

                    # Si alguno ya cedió el paso en este tick (step_back o
                    # apartarse), no se toca su destino para no deshacer la
                    # resolución del cruce: espera el OTRO. Si el otro ya
                    # estaba quieto, el que cedió vuelve a quedarse en su
                    # lugar. (Antes acá no se cambiaba nada: el choque seguía,
                    # el while giraba hasta el tope de iteraciones y en ese
                    # tick no se movía nadie, para siempre.)
                    a_cedio = a.picker_id in self.cedieron_paso
                    b_cedio = b.picker_id in self.cedieron_paso
                    if a_cedio or b_cedio:
                        if a_cedio and b_cedio:
                            otro, cedio = a, b
                        elif a_cedio:
                            otro, cedio = b, a
                        else:
                            otro, cedio = a, b
                        if destino[otro.picker_id] != otro.posicion_actual:
                            destino[otro.picker_id] = otro.posicion_actual
                        else:
                            destino[cedio.picker_id] = cedio.posicion_actual
                            self.cedieron_paso.discard(cedio.picker_id)
                        hubo_cambio = True
                        continue

                    # Detectar bloqueo en cadena: A quiere moverse a la celda
                    # de B y B se queda quieto (o viceversa). Esto no es un
                    # cruce cara a cara, pero deja a A bloqueado para siempre.
                    a_quiere_ir_a_b = destino[a.picker_id] == b.posicion_actual
                    b_quiere_ir_a_a = destino[b.picker_id] == a.posicion_actual
                    b_quieto = destino[b.picker_id] == b.posicion_actual
                    a_quieto = destino[a.picker_id] == a.posicion_actual

                    if a_quiere_ir_a_b and b_quieto:
                        # A quiere ocupar la celda de B, pero B no se mueve.
                        # Intentar mover a B para liberar el paso.
                        apartada = self._apartar_picker_libre(
                            b, destino, a.posicion_actual
                        )
                        if apartada is not None:
                            destino[b.picker_id] = apartada
                            if apartada != b.posicion_actual:
                                self.cedieron_paso.add(b.picker_id)
                            hubo_cambio = True
                            continue
                        # Emergencia: B lleva mucho esperando. Forzar un
                        # retroceso (step_back) aunque la celda anterior esté
                        # en destino.values(), para romper el deadlock.
                        apuro = self._emergencia_step_back(b, destino)
                        if apuro is not None:
                            destino[b.picker_id] = apuro
                            self.cedieron_paso.add(b.picker_id)
                            hubo_cambio = True
                            continue
                        # No se puede mover a B: A espera.
                        destino[a.picker_id] = a.posicion_actual
                        hubo_cambio = True
                        continue

                    if b_quiere_ir_a_a and a_quieto:
                        apartada = self._apartar_picker_libre(
                            a, destino, b.posicion_actual
                        )
                        if apartada is not None:
                            destino[a.picker_id] = apartada
                            if apartada != a.posicion_actual:
                                self.cedieron_paso.add(a.picker_id)
                            hubo_cambio = True
                            continue
                        apuro = self._emergencia_step_back(a, destino)
                        if apuro is not None:
                            destino[a.picker_id] = apuro
                            self.cedieron_paso.add(a.picker_id)
                            hubo_cambio = True
                            continue
                        destino[b.picker_id] = b.posicion_actual
                        hubo_cambio = True
                        continue

                    if destino[b.picker_id] != b.posicion_actual:
                        destino[b.picker_id] = b.posicion_actual
                    else:
                        destino[a.picker_id] = a.posicion_actual
                    hubo_cambio = True

        # Red de seguridad (§3.6): la resolución de arriba puede pedirle a un
        # picker un movimiento que en la fase de movimiento no se hace (está
        # recogiendo, la arista no existe por el sentido del pasillo, o no
        # tiene plan). Si pasa, el otro entraría a su celda igual. Por eso,
        # antes de mover, se fija en su lugar a todo picker cuyo movimiento
        # no es posible y se vuelven a revisar los choques con la regla
        # simple: espera el que se iba a mover. Termina siempre, porque en
        # cada vuelta un picker más queda quieto y dos quietos no chocan.
        hubo_cambio = True
        while hubo_cambio:
            hubo_cambio = False
            for picker in ordenados:
                if not self._movimiento_posible(picker, destino[picker.picker_id]):
                    destino[picker.picker_id] = picker.posicion_actual
                    hubo_cambio = True
            for i in range(len(ordenados)):
                for j in range(i + 1, len(ordenados)):
                    a = ordenados[i]
                    b = ordenados[j]
                    if not self._crash(a, b, destino):
                        continue
                    if destino[b.picker_id] != b.posicion_actual:
                        destino[b.picker_id] = b.posicion_actual
                    else:
                        destino[a.picker_id] = a.posicion_actual
                    hubo_cambio = True

        self.esperando = set()
        self.recogiendo = set()
        trabados = []
        for picker in ordenados:
            task = self.tasks.get(picker.picker_id)

            # Los pickers libres (o que ya terminaron su parte de la wave)
            # también se mueven si se les asignó un destino diferente, por
            # ejemplo al apartarse para dejar pasar a un picker con tarea.
            if task is None or self._puede_apartarse(picker):
                if destino[picker.picker_id] == picker.posicion_actual:
                    continue
                if self.graph.has_edge(
                    picker.posicion_actual, destino[picker.picker_id]
                ):
                    movido = destino[picker.picker_id]
                    picker.posicion_actual = movido
                    picker.historial.append(movido)
                    picker.pasos = picker.pasos + 1
                    # Consumir el plan de estacionamiento si avanzó por él.
                    plan = self.parking_plans.get(picker.picker_id)
                    if plan is not None:
                        if plan and plan[0] == movido:
                            plan.pop(0)
                            if not plan:
                                del self.parking_plans[picker.picker_id]
                        else:
                            # Se movió por una resolución de choque distinta:
                            # recalculamos el plan en el próximo tick.
                            del self.parking_plans[picker.picker_id]
                continue

            if task.cooldown_recogida > 0:
                task.cooldown_recogida -= 1
                task.esperas_seguidas = 0
                picker.stay()
                self.recogiendo.add(picker.picker_id)
                continue

            if picker.next_cell is None:
                continue

            if destino[picker.picker_id] != picker.posicion_actual:
                anterior = picker.celda_anterior()
                if destino[picker.picker_id] == picker.next_cell:
                    # Avanza por su plan (aunque el plan vuelva a la celda
                    # anterior: eso no es ceder el paso).
                    picker.step(self.graph)
                elif anterior is not None and destino[picker.picker_id] == anterior:
                    # Cediendo el paso: retroceder por historial (step_back)
                    picker.step_back(self.graph)
                else:
                    # Cediendo el paso: apartarse a celda adyacente libre
                    # (no es el próximo del plan, se mueve directamente y se
                    # recalculará la ruta al final del tick).
                    picker.posicion_actual = destino[picker.picker_id]
                    picker.historial.append(destino[picker.picker_id])
                    picker.pasos = picker.pasos + 1
                task.paso = task.paso + 1
                task.esperas_seguidas = 0
            else:
                picker.wait()
                self.esperas = self.esperas + 1
                self.esperando.add(picker.picker_id)
                task.esperas_seguidas = task.esperas_seguidas + 1
                task.esperas_totales = task.esperas_totales + 1
                if task.esperas_seguidas == 1:
                    self.eventos.append({"tipo": "espera", "picker": picker.picker_id})
                if task.esperas_seguidas >= self.ESPERA_MAXIMA:
                    trabados.append(picker)

        # Se desvía uno solo por tick: el de menor prioridad (el último de la
        # lista). Si se desviaran dos a la vez podrían volver a chocar.
        for i in range(len(trabados) - 1, -1, -1):
            picker = trabados[i]
            if self._detour(picker, self.tasks[picker.picker_id]):
                break

        # Recalcular ruta de quien retrocedió para ceder el paso: su plan
        # todavía apunta desde la celda donde estaba antes. Si el siguiente
        # paso ya no es alcanzable desde acá, buscamos de nuevo hacia la
        # próxima parada importante (sin bloquear nada: el conflicto ya se
        # resolvió con el retroceso o el apartarse).
        for picker in self.warehouse.pickers:
            if picker.picker_id not in self.tasks:
                continue
            task = self.tasks[picker.picker_id]
            if picker.route_finished:
                continue
            if picker.next_cell is not None and not self.graph.has_edge(
                picker.posicion_actual, picker.next_cell
            ):
                self._try_detour(picker, task, set(), set())

        self.cedieron_paso.clear()

    def _detour(self, picker: Picker, task: _Task) -> bool:
        """
        Camino alternativo: busca con BFS cómo llegar a su próxima parada
        (o descarga, o al final del camino) sin pasar por donde están los
        demás pickers ni por las próximas celdas que van a pisar. Si así no
        hay camino, prueba esquivando solo las celdas donde están.

        Si ya recogió todo, en vez de eso recalcula la descarga esquivando
        a los demás: así, si otro picker está parado justo en la celda de su
        zona, va a otra celda de acceso o a otra zona con lugar.

        Returns:
            True si encontró un camino alternativo; False si sigue esperando.
        """
        ocupadas = set()
        for otro in self.warehouse.pickers:
            if otro is not picker:
                ocupadas.add(otro.posicion_actual)
        if len(task.paradas) == 0:
            return self._detour_unloading(picker, task, ocupadas)
        # Intento 1: evitar posiciones actuales y próximas celdas de los demás.
        if self._try_detour(picker, task, ocupadas, self._next_cells_of_others(picker)):
            return True
        # Intento 2: evitar solo las posiciones actuales de los demás (menos restrictivo).
        if self._try_detour(picker, task, ocupadas, set()):
            return True
        # Intento 3 (último recurso): no bloquear celdas de otros pickers; solo se
        # busca llegar a la próxima parada importante del propio plan. Si hay choque,
        # se resuelve en el siguiente tick, pero al menos el picker avanza y no se
        # queda esperando para siempre.
        if self._try_detour(picker, task, set(), set()):
            return True
        return False

    def _detour_unloading(
        self,
        picker: Picker,
        task: _Task,
        ocupadas: set[tuple[int, int]],
    ) -> bool:
        """Recalcula la descarga sin pasar por las celdas ocupadas."""
        libre = graph_without(self.graph, ocupadas)
        stats = {"nodos_expandidos": 0}
        try:
            path, descargas = plan_unloading(
                self.warehouse, libre, picker.posicion_actual, picker.carga,
                self.buscador, stats,
            )
        except ValueError:
            return False    # por ahora no hay otra forma: sigue esperando
        self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
        task.descargas = []
        for celda, zone_id, product_ids in descargas:
            task.descargas.append((celda, zone_id))
        self._change_route(picker, task, path)
        self.desvios = self.desvios + 1
        self.eventos.append({"tipo": "desvio", "picker": picker.picker_id})
        return True

    def _next_cells_of_others(self, picker: Picker) -> set[tuple[int, int]]:
        """Las próximas celdas que van a pisar los demás pickers."""
        celdas = set()
        for otro in self.warehouse.pickers:
            if otro is picker:
                continue
            for celda in otro.plan[:self.ESPERA_MAXIMA]:
                celdas.add(celda)
        return celdas

    def _try_detour(
        self,
        picker: Picker,
        task: _Task,
        ocupadas: set[tuple[int, int]],
        a_evitar: set[tuple[int, int]],
    ) -> bool:
        """Intenta el camino alternativo sin pasar por ocupadas ni por a_evitar."""
        bloqueadas = set()
        for celda in ocupadas:
            bloqueadas.add(celda)
        for celda in a_evitar:
            if celda != picker.posicion_actual:
                bloqueadas.add(celda)

        importantes = set()
        for celda in task.paradas:
            importantes.add(celda)
        for celda, zone_id in task.descargas:
            importantes.add(celda)
        importantes.add(picker.plan[-1])

        objetivo = None
        for i in range(len(picker.plan)):
            celda = picker.plan[i]
            if celda in importantes and celda not in bloqueadas:
                objetivo = i
                break
        if objetivo is None:
            return False

        # Sin celdas bloqueadas, la copia sería igual al grafo: no se copia.
        if bloqueadas:
            libre = graph_without(self.graph, bloqueadas)
        else:
            libre = self.graph
        stats = {"nodos_expandidos": 0}
        camino, distancia, llegada = bfs_to_any(
            libre, picker.posicion_actual, {picker.plan[objetivo]}, stats
        )
        self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
        if llegada is None:
            return False

        nuevo = camino + picker.plan[objetivo + 1:]
        self._change_route(picker, task, nuevo)
        self.desvios = self.desvios + 1
        self.eventos.append({"tipo": "desvio", "picker": picker.picker_id})
        return True

    def _change_route(self, picker: Picker, task: _Task, path: list[tuple[int, int]]) -> None:
        """Le da un camino nuevo al picker y lo anota para dibujarlo."""
        picker.change_route(path)
        task.ruta = path
        task.paso = 0
        task.esperas_seguidas = 0
        self.eventos.append({
            "tipo": "ruta",
            "picker": picker.picker_id,
            "path": _cells_to_lists(path),
        })

    # ------------------------------------------------------------------
    # 2. Recoger y descargar
    # ------------------------------------------------------------------

    def _zone(self, zone_id: str) -> DispatchZone:
        for zona in self.warehouse.dispatch_zones:
            if zona.zone_id == zone_id:
                return zona
        raise ValueError(f"No existe la zona '{zone_id}'.")

    def _pick_and_unload(self) -> None:
        for picker in self.warehouse.pickers:
            if picker.picker_id not in self.tasks:
                continue
            task = self.tasks[picker.picker_id]
            celda = picker.posicion_actual

            # ------------------------------------------------------------------
            # 1. Descarga intermedia: el picker llegó a una zona de despacho
            #    porque se llenó de capacidad. Descarga lo que pueda y, si
            #    todavía quedan paradas, vuelve a ellas.
            # ------------------------------------------------------------------
            if task.descarga_intermedia and len(task.descargas) > 0 and celda == task.descargas[0][0]:
                zona = self._zone(task.descargas[0][1])
                task.descargas.pop(0)
                if picker.can_unload(zona):
                    dejados = picker.unload(zona)
                    productos = []
                    for item in dejados:
                        productos.append(item.product.product_id)
                    self.eventos.append({
                        "tipo": "descarga",
                        "picker": picker.picker_id,
                        "wave": task.wave.wave_id,
                        "zona": zona.zone_id,
                        "productos": productos,
                    })
                    # Si todavía hay descargas intermedias pendientes, seguir.
                    if len(task.descargas) > 0:
                        continue
                    # Ya no hay descargas intermedias: restaurar las descargas
                    # finales originales y volver a las paradas si quedan.
                    task.descarga_intermedia = False
                    task.descargas = list(task.descargas_originales)
                    if len(task.paradas) > 0:
                        # Recalcular camino desde aquí hacia la próxima parada.
                        stats = {"nodos_expandidos": 0}
                        paradas_celdas = set(task.paradas.keys())
                        camino, distancia, llegada = bfs_to_any(
                            self.graph, celda, paradas_celdas, stats
                        )
                        self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
                        if llegada is not None:
                            self._change_route(picker, task, camino)
                        else:
                            picker.wait()
                            self.esperas = self.esperas + 1
                            self.esperando.add(picker.picker_id)
                            task.esperas_seguidas = task.esperas_seguidas + 1
                            if task.esperas_seguidas == 1:
                                self.eventos.append({"tipo": "espera", "picker": picker.picker_id})
                        continue

            # ------------------------------------------------------------------
            # 2. Recoger los productos de esta parada.
            #    Antes de hacer pick(), se verifica que el ítem quepa en la
            #    capacidad restante del picker. Si no cabe, el picker debe
            #    ir a descargar antes de seguir recogiendo (Solución 4).
            # ------------------------------------------------------------------
            if celda in task.paradas:
                recogidos = []
                mayor_altura = 0    # costo_altura del producto más alto de la parada
                items_en_parada = []
                for item in task.wave.get_items():
                    if item.product.product_id in task.paradas[celda]:
                        items_en_parada.append(item)

                hubo_no_cabe = False
                for item in items_en_parada:
                    if picker.carried_weight + item.total_weight > picker.capacidad_carga_kg:
                        hubo_no_cabe = True
                        break
                    picker.pick(item)
                    recogidos.append(item.product.product_id)
                    recogido_algunos = True
                    if item.product.costo_altura() > mayor_altura:
                        mayor_altura = item.product.costo_altura()

                if recogidos:
                    # 1 tick base por recoger + lo que cuesta llegar al más alto
                    # (los de la misma celda se recogen en la misma subida).
                    task.cooldown_recogida = 1 + mayor_altura
                    self.eventos.append({
                        "tipo": "recoge",
                        "picker": picker.picker_id,
                        "wave": task.wave.wave_id,
                        "productos": recogidos,
                    })

                # ¿Quedan ítems sin recoger en esta parada?
                recogidos_set = set(recogidos)
                quedan = [pid for pid in task.paradas[celda] if pid not in recogidos_set]

                if quedan:
                    # Todavía hay ítems en esta parada pero el picker se llenó.
                    # Debe ir a descargar antes de seguir recogiendo.
                    stats = {"nodos_expandidos": 0}
                    try:
                        path, descargas = plan_unloading(
                            self.warehouse, self.graph, celda, picker.carga, self.buscador, stats
                        )
                        picker.change_route(path)
                        task.ruta = path
                        task.paso = 0
                        task.descargas = []
                        for celda_zona, zone_id, product_ids in descargas:
                            task.descargas.append((celda_zona, zone_id))
                        task.descarga_intermedia = True
                        self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
                        continue
                    except ValueError:
                        # Ninguna zona tiene lugar ahora. Esperar.
                        picker.wait()
                        self.esperas = self.esperas + 1
                        self.esperando.add(picker.picker_id)
                        task.esperas_seguidas = task.esperas_seguidas + 1
                        task.esperas_totales = task.esperas_totales + 1
                        if task.esperas_seguidas == 1:
                            self.eventos.append({"tipo": "espera", "picker": picker.picker_id})
                        continue

                # Todos los ítems de esta parada se recogieron: borrarla.
                del task.paradas[celda]

            # ------------------------------------------------------------------
            # 3. Si terminó el camino pero todavía faltan paradas de recogida
            #    (por colisiones o porque el picker se llenó y tuvo que ir a
            #    descargar), recalculamos un camino hacia esas paradas.
            # ------------------------------------------------------------------
            if picker.route_finished and len(task.paradas) > 0:
                stats = {"nodos_expandidos": 0}
                paradas_celdas = set(task.paradas.keys())
                camino, distancia, llegada = bfs_to_any(
                    self.graph, celda, paradas_celdas, stats
                )
                self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
                if llegada is not None:
                    self._change_route(picker, task, camino)
                else:
                    picker.wait()
                    self.esperas = self.esperas + 1
                    self.esperando.add(picker.picker_id)
                    task.esperas_seguidas = task.esperas_seguidas + 1
                    if task.esperas_seguidas == 1:
                        self.eventos.append({"tipo": "espera", "picker": picker.picker_id})
                continue

            # ------------------------------------------------------------------
            # 4. Descargar final: ya no quedan paradas, solo descargas.
            # ------------------------------------------------------------------
            if len(task.paradas) > 0:
                continue
            if len(task.descargas) > 0 and celda == task.descargas[0][0]:
                zona = self._zone(task.descargas[0][1])
                task.descargas.pop(0)
                if picker.can_unload(zona):
                    dejados = picker.unload(zona)
                    productos = []
                    for item in dejados:
                        productos.append(item.product.product_id)
                    self.eventos.append({
                        "tipo": "descarga",
                        "picker": picker.picker_id,
                        "wave": task.wave.wave_id,
                        "zona": zona.zone_id,
                        "productos": productos,
                    })

            # ------------------------------------------------------------------
            # 5. Llegó al final y todavía lleva algo: ir a descargar.
            # ------------------------------------------------------------------
            if len(task.paradas) == 0 and len(picker.carga) > 0:
                descargado_algo = False
                for zona in self.warehouse.dispatch_zones:
                    if picker.can_unload(zona):
                        dejados = picker.unload(zona)
                        descargado_algo = True
                        productos = []
                        for item in dejados:
                            productos.append(item.product.product_id)
                        self.eventos.append({
                            "tipo": "descarga",
                            "picker": picker.picker_id,
                            "wave": task.wave.wave_id,
                            "zona": zona.zone_id,
                            "productos": productos,
                        })
                if descargado_algo:
                    continue

                stats = {"nodos_expandidos": 0}
                try:
                    path, descargas = plan_unloading(
                        self.warehouse, self.graph, celda, picker.carga, self.buscador, stats
                    )
                    self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
                    task.descargas = []
                    for celda_zona, zone_id, product_ids in descargas:
                        task.descargas.append((celda_zona, zone_id))
                    self._change_route(picker, task, path)
                except ValueError:
                    picker.wait()
                    self.esperas = self.esperas + 1
                    self.esperando.add(picker.picker_id)
                    task.esperas_seguidas = task.esperas_seguidas + 1
                    if task.esperas_seguidas == 1:
                        self.eventos.append({"tipo": "espera", "picker": picker.picker_id})

    # ------------------------------------------------------------------
    # 3. Terminar waves
    # ------------------------------------------------------------------

    def _finish_waves(self) -> None:
        """
        Detecta pickers que terminaron su parte de la wave (sin paradas
        pendientes ni carga). Una wave solo se completa cuando TODOS sus
        pickers finalizaron: en waves multi-picker el primero en terminar
        espera al resto antes de que el manager libere la wave.
        """
        # Agrupar pickers "terminados" por wave_id
        done_by_wave: dict[str, list] = {}
        for picker in self.warehouse.pickers:
            if picker.picker_id not in self.tasks:
                continue
            task = self.tasks[picker.picker_id]
            if len(task.paradas) == 0 and len(picker.carga) == 0:
                wid = task.wave.wave_id
                if wid not in done_by_wave:
                    done_by_wave[wid] = []
                done_by_wave[wid].append(picker)

        for wave_id, pickers_done in done_by_wave.items():
            wave = self.tasks[pickers_done[0].picker_id].wave

            # Solo completar si TODOS los pickers de la wave terminaron
            todos_done = True
            for p in wave.pickers:
                if p.picker_id in self.tasks:
                    task = self.tasks[p.picker_id]
                    if len(task.paradas) > 0 or len(p.carga) > 0:
                        todos_done = False
                        break

            if not todos_done:
                continue

            # Registrar eventos y limpiar tasks antes de completar la wave
            for p in wave.pickers:
                if p.picker_id in self.tasks:
                    self.eventos.append({
                        "tipo": "fin_wave",
                        "picker": p.picker_id,
                        "wave": wave_id,
                    })
                    del self.tasks[p.picker_id]

            self.manager.complete_wave(wave)    # libera a todos y reparte la cola

    # ------------------------------------------------------------------
    # 4. Arrancar waves
    # ------------------------------------------------------------------

    def _partition_items(self, items: list, pickers: list) -> list[list]:
        """
        Divide los ítems de una wave entre N pickers por zona espacial.

        Ordena todos los ítems por coordenada x (de oeste a este) y los
        reparte en franjas verticales, una por picker. Así cada picker
        trabaja en su propia sección del almacén con mínimo solapamiento.

        Los ítems con la misma celda de rack siempre quedan en la misma
        franja: si un rack está en el límite de dos franjas, el orden de
        inserción garantiza que sus ítems no se dividen entre pickers.
        """
        n = len(pickers)
        if n <= 1:
            return [items]

        items_sorted = sorted(
            items,
            key=lambda it: (it.product.x, it.product.y),
        )

        size = max(1, len(items_sorted) // n)
        grupos = []
        for i in range(n):
            inicio = i * size
            fin = inicio + size if i < n - 1 else len(items_sorted)
            grupos.append(items_sorted[inicio:fin])

        # Rellenar con listas vacías si hay más pickers que ítems
        while len(grupos) < n:
            grupos.append([])

        return grupos

    def _start_assigned_waves(self) -> None:
        """
        Las waves que tienen picker/s pero no empezaron calculan su
        recorrido y arrancan. Si la wave tiene varios pickers, los ítems
        se dividen espacialmente y cada picker planifica su sub-ruta
        de forma independiente.
        """
        for wave in self.manager.get_waves():
            if not wave.pickers or wave.status != WaveStatus.ABIERTA:
                continue

            pickers = wave.pickers
            all_items = wave.get_items()
            partitions = self._partition_items(all_items, pickers)

            # Planificar una ruta por picker antes de marcar la wave como
            # iniciada, así todos parten desde su posición actual.
            rutas_por_picker: dict[str, object] = {}
            for picker, items_subset in zip(pickers, partitions):
                if not items_subset:
                    continue    # picker sin ítems asignados: no genera tarea
                ruta = plan_route(
                    wave, self.warehouse, self.graph,
                    self.estrategia, self.buscador,
                    inicio=picker.posicion_actual,
                    items=items_subset if len(pickers) > 1 else None,
                )
                self.rutas.append(ruta.metrics())
                self.nodos_expandidos = self.nodos_expandidos + ruta.nodos_expandidos
                rutas_por_picker[picker.picker_id] = ruta

            if not rutas_por_picker:
                continue

            # La ruta guardada en la wave es la del primer picker (visualización)
            primera_ruta = next(iter(rutas_por_picker.values()))
            wave.set_route(primera_ruta.path)
            wave.start()

            for picker in pickers:
                if picker.picker_id not in rutas_por_picker:
                    continue
                ruta = rutas_por_picker[picker.picker_id]
                picker.start_route(ruta.path)

                task = _Task(wave, ruta.path)
                for celda, product_ids in ruta.paradas:
                    if celda not in task.paradas:
                        task.paradas[celda] = []
                    for product_id in product_ids:
                        task.paradas[celda].append(product_id)
                for celda, zone_id, product_ids in ruta.descargas:
                    task.descargas.append((celda, zone_id))
                # Guardar las descargas finales originales para restaurarlas
                # después de una descarga intermedia por capacidad (Solución 4).
                task.descargas_originales = list(task.descargas)
                self.tasks[picker.picker_id] = task

                self.eventos.append({
                    "tipo": "inicio_wave",
                    "picker": picker.picker_id,
                    "wave": wave.wave_id,
                })
                self.eventos.append({
                    "tipo": "ruta",
                    "picker": picker.picker_id,
                    "path": _cells_to_lists(ruta.path),
                    "paradas": ruta.to_dict()["paradas"],
                })

    # ------------------------------------------------------------------
    # 5. Frames

    # ------------------------------------------------------------------
    # Helpers de serialización de frame
    # ------------------------------------------------------------------

    def _build_proximo_objetivo(self, picker, task, estado: str) -> dict:
        """
        Calcula el próximo objetivo inmediato del picker para mostrarlo
        en el tooltip del frontend.
        Devuelve: { "tipo": "PICKING"|"DESPACHO"|"ESPERA"|"FIN",
                    "destino": [x, y] | None,
                    "descripcion": str }
        """
        # Sin tarea asignada → libre
        if task is None:
            return {"tipo": "FIN", "destino": None, "descripcion": "En espera / sin wave"}

        # Esperando por tráfico
        if estado == "ESPERANDO":
            return {"tipo": "ESPERA", "destino": None, "descripcion": "Esperando paso libre (tráfico)"}

        # Aún tiene paradas de picking pendientes
        if task.paradas:
            # Primera celda que falta visitar
            primera_celda = next(iter(task.paradas))
            product_ids   = task.paradas[primera_celda]
            # Intentar obtener nombres desde el warehouse
            nombres = []
            for pid in product_ids:
                prod = self.warehouse.get_product(pid) if hasattr(self.warehouse, "get_product") else None
                nombres.append(prod.name if prod else pid)
            desc = f"Recoger: {', '.join(nombres)} en ({primera_celda[0]}, {primera_celda[1]})"
            return {
                "tipo":       "PICKING",
                "destino":    list(primera_celda),
                "descripcion": desc,
            }

        # Ya recogió todo; tiene descargas pendientes
        if task.descargas:
            celda, zone_id = task.descargas[0]
            return {
                "tipo":       "DESPACHO",
                "destino":    list(celda),
                "descripcion": f"Descargar en: {zone_id} ({celda[0]}, {celda[1]})",
            }

        # Carga en tránsito pero sin descargas programadas aún (recalculando)
        if picker.carga:
            return {"tipo": "DESPACHO", "destino": None, "descripcion": "Buscando zona de despacho..."}

        # Todo completado
        return {"tipo": "FIN", "destino": None, "descripcion": "Ruta completada / En espera"}

    # ------------------------------------------------------------------

    def _save_frame(self) -> None:
        """
        Guarda cómo está todo en este tick:
            {"tick": 3,
             "pickers": [{"id", "x", "y", "estado", "wave", "carga_kg", "paso"}, ...],
             "zonas":   {"ZONA_A": 12.5, ...},
             "eventos": [...]}

        Los eventos dicen qué pasó en este tick: "inicio_wave", "ruta"
        (camino nuevo para dibujar), "recoge", "descarga", "espera",
        "desvio" y "fin_wave". El estado de las waves no se repite en cada
        frame: el front lo actualiza con inicio_wave y fin_wave.
        """
        pickers = []
        for picker in self.warehouse.pickers:
            estado = picker.status.value
            if picker.picker_id in self.recogiendo:
                estado = "RECOGIENDO"
            elif picker.picker_id in self.esperando:
                estado = "ESPERANDO"
            paso = None
            task = self.tasks.get(picker.picker_id)
            if task is not None:
                paso = task.paso

            # ── Carga actual: ítems que el picker lleva en tránsito ──────
            carga_items = []
            for item in picker.carga:
                carga_items.append({
                    "producto_id": item.product.product_id,
                    "nombre":      item.product.name,
                    "cantidad":    item.cantidad,
                    "peso_kg":     round(item.total_weight, 3),
                })

            # ── Próximo objetivo inmediato ───────────────────────────────
            proximo_objetivo = self._build_proximo_objetivo(picker, task, estado)

            pickers.append({
                "id":       picker.picker_id,
                "x":        picker.posicion_actual[0],
                "y":        picker.posicion_actual[1],
                "estado":   estado,
                "wave":     picker.assigned_wave_id,
                "carga_kg": round(picker.carried_weight, 2),
                "paso":     paso,
                # Datos enriquecidos para el tooltip del picker
                "carga":            carga_items,
                "proximo_objetivo": proximo_objetivo,
            })

        zonas = {}
        for zona in self.warehouse.dispatch_zones:
            zonas[zona.zone_id] = round(zona.peso_actual, 2)

        self.frames.append({
            "tick": self.tick,
            "pickers": pickers,
            "zonas": zonas,
            "eventos": self.eventos,
        })
        self.eventos = []

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------

    def metrics(self) -> dict:
        """Métricas de toda la simulación."""
        distancia = 0
        celdas = set()    # celdas distintas por las que pasó algún picker
        for picker in self.warehouse.pickers:
            distancia = distancia + picker.pasos
            for celda in picker.historial:
                celdas.add(celda)
        return {
            "ticks": self.tick,
            "distancia_total": distancia,
            "aristas_recorridas": distancia,
            "nodos_visitados": len(celdas),
            "esperas": self.esperas,
            "desvios": self.desvios,
            "recorridos_calculados": len(self.rutas),
            "nodos_expandidos": self.nodos_expandidos,
            "tiempo_ms": round(self.tiempo_ms, 3),
        }

    def to_dict(self) -> dict:
        return {
            "frames": self.frames,
            "metricas": self.metrics(),
            "rutas": self.rutas,
            "error": self.error,
        }


def _cells_to_lists(path: list[tuple[int, int]]) -> list[list[int]]:
    """Convierte [(x, y), ...] en [[x, y], ...] para mandarlo como JSON."""
    celdas = []
    for celda in path:
        celdas.append([celda[0], celda[1]])
    return celdas
