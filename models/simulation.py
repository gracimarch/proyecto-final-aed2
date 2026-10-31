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
    2. Recoger y descargar: al llegar a una parada recoge sus productos y,
       con todo recogido, al llegar a su zona descarga lo que entra. Si le
       sobra carga (la zona se llenó mientras caminaba) busca la próxima
       zona con lugar.
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
    """

    def __init__(self, wave: Wave, path: list[tuple[int, int]]):
        self.wave = wave
        self.paradas = {}
        self.descargas = []
        self.ruta = path
        self.paso = 0
        self.esperas_seguidas = 0


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
    ):
        self.warehouse = warehouse
        self.manager = manager
        self.graph = manager.graph
        self.estrategia = estrategia
        self.buscador = buscador
        self.max_ticks = max_ticks

        self.tick = 0
        self.tasks = {}          # picker_id -> _Task
        self.esperando = set()   # pickers que esperaron en este tick
        self.eventos = []        # lo que pasó en este tick
        self.frames = []
        self.rutas = []
        self.esperas = 0
        self.desvios = 0
        self.nodos_expandidos = 0
        self.error = None

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
        """Celda donde quiere estar en el próximo tick (la suya si no camina)."""
        if picker.picker_id in self.tasks and picker.next_cell is not None:
            return picker.next_cell
        return picker.posicion_actual

    def _crash(self, a: Picker, b: Picker, destino: dict) -> bool:
        """True si a y b quedarían en la misma celda o se cruzarían (§3.6)."""
        misma_celda = destino[a.picker_id] == destino[b.picker_id]
        se_cruzan = (destino[a.picker_id] == b.posicion_actual
                     and destino[b.picker_id] == a.posicion_actual)
        return misma_celda or se_cruzan

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
            if picker.picker_id in self.tasks:
                prioridad = self.tasks[picker.picker_id].wave.priority()
            claves.append((-prioridad, picker.picker_id, picker))
        claves.sort()
        ordenados = []
        for prioridad, picker_id, picker in claves:
            ordenados.append(picker)

        destino = {}
        for picker in ordenados:
            destino[picker.picker_id] = self._destination(picker)

        hubo_cambio = True
        while hubo_cambio:
            hubo_cambio = False
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
        trabados = []
        for picker in ordenados:
            if picker.picker_id not in self.tasks or picker.next_cell is None:
                continue
            task = self.tasks[picker.picker_id]
            if destino[picker.picker_id] != picker.posicion_actual:
                picker.step(self.graph)
                task.paso = task.paso + 1
                task.esperas_seguidas = 0
            else:
                picker.wait()
                self.esperas = self.esperas + 1
                self.esperando.add(picker.picker_id)
                task.esperas_seguidas = task.esperas_seguidas + 1
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
        if self._try_detour(picker, task, ocupadas, self._next_cells_of_others(picker)):
            return True
        return self._try_detour(picker, task, ocupadas, set())

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

        libre = graph_without(self.graph, bloqueadas)
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

            # Recoger los productos de esta parada.
            if celda in task.paradas:
                recogidos = []
                for item in task.wave.get_items():
                    if item.product.product_id in task.paradas[celda]:
                        picker.pick(item)
                        recogidos.append(item.product.product_id)
                del task.paradas[celda]
                self.eventos.append({
                    "tipo": "recoge",
                    "picker": picker.picker_id,
                    "wave": task.wave.wave_id,
                    "productos": recogidos,
                })

            # Descargar (solo cuando ya recogió todo).
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

            # Llegó al final y todavía lleva algo: la zona se llenó mientras
            # caminaba. Busca la próxima zona con lugar desde donde está.
            if picker.route_finished and len(picker.carga) > 0 and len(task.descargas) == 0:
                stats = {"nodos_expandidos": 0}
                path, descargas = plan_unloading(
                    self.warehouse, self.graph, celda, picker.carga, self.buscador, stats
                )
                self.nodos_expandidos = self.nodos_expandidos + stats["nodos_expandidos"]
                task.descargas = []
                for celda_zona, zone_id, product_ids in descargas:
                    task.descargas.append((celda_zona, zone_id))
                self._change_route(picker, task, path)

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
            if picker.picker_id in self.esperando:
                estado = "ESPERANDO"
            paso = None
            if picker.picker_id in self.tasks:
                paso = self.tasks[picker.picker_id].paso
            pickers.append({
                "id": picker.picker_id,
                "x": picker.posicion_actual[0],
                "y": picker.posicion_actual[1],
                "estado": estado,
                "wave": picker.assigned_wave_id,
                "carga_kg": round(picker.carried_weight, 2),
                "paso": paso,
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
