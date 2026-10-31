"""
models/picker.py

Operario que recorre el warehouse para preparar una wave (consigna §3.6).

Cada regla de la consigna la controla un método:
    Capacidad (§3.6)       : pick no deja cargar más de capacidad_carga_kg.
    Movimiento (§3.6)      : step solo acepta un paso que sea una arista del
                             grafo. Eso ya asegura que la celda es pasillo, que
                             el paso no es diagonal y que respeta el sentido.
    Acceso (§3.6)          : pick exige estar al lado del rack del producto, y
                             unload al lado de la zona de despacho.
    No chocar (§3.6)       : collides_with avisa si dos pickers terminarían en
                             la misma celda o se cruzarían. Quién espera lo
                             decide la simulación (wait o change_route).
    Peso de la zona (§3.4) : unload deja solo los ítems que entran en la zona;
                             lo que no entra sigue en la carga para llevarlo
                             a otra zona con lugar.

El picker no calcula recorridos (los recibe de algorithms/routing.py) ni
modifica el stock de los productos.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from algorithms.graph import Graph
from models.order import OrderItem

if TYPE_CHECKING:
    # Solo para las anotaciones de tipo. Python no ejecuta este bloque, así que
    # estos imports no pueden armar un import circular (ver GUIA.md).
    from models.warehouse import DispatchZone


class PickerStatus(Enum):
    """Estados posibles de un picker."""
    LIBRE        = "LIBRE"         # sin wave
    ASIGNADO     = "ASIGNADO"      # tiene wave, todavía no empezó a caminar
    EN_RECORRIDO = "EN_RECORRIDO"  # recorriendo el warehouse


class Picker:
    """
    Operario que recolecta los productos de una wave.

    Ciclo de vida:
        LIBRE --assign_wave--> ASIGNADO --start_route--> EN_RECORRIDO
        EN_RECORRIDO --release--> LIBRE   (release lo llama Wave.complete)

    Datos del escenario:
        picker_id          (str)   : Identificador.
        posicion_inicial   (tuple) : Celda de pasillo (x, y) donde arranca.
        capacidad_carga_kg (float) : Peso máximo que puede llevar (kg).

    Estado durante la simulación:
        status           (PickerStatus)    : LIBRE, ASIGNADO o EN_RECORRIDO.
        assigned_wave_id (str o None)      : Wave que está preparando.
        posicion_actual  (tuple)           : Celda en la que está ahora.
        carga            (list[OrderItem]) : Ítems que lleva encima.
        entregados       (list[OrderItem]) : Ítems ya dejados en la zona en esta wave.
        historial        (list[tuple])     : Celda en cada instante (para dibujar el rastro).
        pasos            (int)             : Movimientos hechos (distancia recorrida).
        esperas          (int)             : Instantes que esperó por un choque.
        plan             (list[tuple])     : Celdas que le faltan recorrer, en orden.
    """

    def __init__(
        self,
        picker_id: str,
        posicion_inicial: tuple[int, int],
        capacidad_carga_kg: float,
    ):
        if capacidad_carga_kg <= 0:
            raise ValueError(
                f"La capacidad de carga debe ser positiva: {capacidad_carga_kg}"
            )
        self.picker_id = picker_id
        self.posicion_inicial = tuple(posicion_inicial)
        self.capacidad_carga_kg = capacidad_carga_kg

        self.status = PickerStatus.LIBRE
        self.assigned_wave_id = None
        self.posicion_actual = self.posicion_inicial
        self.carga = []
        self.entregados = []
        self.historial = [self.posicion_actual]
        self.pasos = 0
        self.esperas = 0
        self.plan = []

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        """True si el picker tiene una wave (asignada o en recorrido)."""
        return self.status != PickerStatus.LIBRE

    @property
    def carried_weight(self) -> float:
        """Peso de lo que lleva encima (kg)."""
        total = 0
        for item in self.carga:
            total = total + item.total_weight
        return total

    @property
    def available_capacity(self) -> float:
        """Cuántos kg más puede cargar."""
        return self.capacidad_carga_kg - self.carried_weight

    @property
    def next_cell(self) -> tuple[int, int] | None:
        """Próxima celda de su recorrido, o None si ya no le quedan pasos."""
        if len(self.plan) == 0:
            return None
        return self.plan[0]

    @property
    def route_finished(self) -> bool:
        """True si ya recorrió todas las celdas de su recorrido."""
        return len(self.plan) == 0

    @property
    def visited_cells(self) -> int:
        """Cantidad de celdas distintas por las que pasó."""
        return len(set(self.historial))

    # ------------------------------------------------------------------
    # Asignación de wave (la usan Wave.assign_picker y Wave.complete)
    # ------------------------------------------------------------------

    def assign_wave(self, wave_id: str) -> None:
        """
        Le asigna una wave. El control de peso lo hace Wave.assign_picker antes.

        Raises:
            ValueError: Si el picker ya tiene una wave.
        """
        if self.is_busy:
            raise ValueError(
                f"El picker '{self.picker_id}' ya está ocupado con la wave "
                f"'{self.assigned_wave_id}'."
            )
        self.status = PickerStatus.ASIGNADO
        self.assigned_wave_id = wave_id

    def release(self) -> None:
        """
        Libera al picker al terminar su wave. Se queda donde está (al lado de
        la zona de despacho), que es desde donde arranca la próxima wave.

        Raises:
            ValueError: Si todavía lleva productos sin descargar.
        """
        if len(self.carga) > 0:
            raise ValueError(
                f"El picker '{self.picker_id}' no puede liberarse: todavía lleva "
                f"{len(self.carga)} ítem(s) sin descargar."
            )
        self.status = PickerStatus.LIBRE
        self.assigned_wave_id = None
        self.entregados = []
        self.plan = []

    # ------------------------------------------------------------------
    # Movimiento (consigna §3.6)
    # ------------------------------------------------------------------

    def start_route(self, path: list[tuple[int, int]]) -> None:
        """
        Le da el recorrido a seguir y lo pone en marcha.

        Args:
            path: Lista de celdas (x, y). La primera tiene que ser su
                  posición actual.

        Raises:
            ValueError: Si no tiene wave o el camino no empieza donde está.
        """
        if self.status != PickerStatus.ASIGNADO:
            raise ValueError(
                f"El picker '{self.picker_id}' debe tener una wave asignada y no "
                f"haber empezado para iniciar un recorrido: {self.status.value}."
            )
        self._set_plan(path)
        self.status = PickerStatus.EN_RECORRIDO

    def change_route(self, path: list[tuple[int, int]]) -> None:
        """
        Cambia lo que le falta recorrer por otro camino (por ejemplo, para
        esquivar a otro picker).

        Raises:
            ValueError: Si no está en recorrido o el camino no empieza donde está.
        """
        if self.status != PickerStatus.EN_RECORRIDO:
            raise ValueError(f"El picker '{self.picker_id}' no está en recorrido.")
        self._set_plan(path)

    def _set_plan(self, path: list[tuple[int, int]]) -> None:
        """Guarda el camino sin su primera celda (que es donde ya está)."""
        celdas = []
        for cell in path:
            celdas.append(tuple(cell))
        if len(celdas) == 0 or celdas[0] != self.posicion_actual:
            raise ValueError(
                f"El recorrido del picker '{self.picker_id}' debe empezar en su "
                f"posición actual {self.posicion_actual}."
            )
        self.plan = celdas[1:]

    def step(self, graph: Graph) -> tuple[int, int]:
        """
        Avanza un paso hacia la próxima celda de su recorrido.

        El paso es válido solo si existe la arista (actual -> próxima) en el
        grafo dirigido.

        Returns:
            La nueva posición.

        Raises:
            ValueError: Si no está en recorrido, no le quedan pasos o el paso
                        no es una arista del grafo.
        """
        if self.status != PickerStatus.EN_RECORRIDO:
            raise ValueError(f"El picker '{self.picker_id}' no está en recorrido.")
        if len(self.plan) == 0:
            raise ValueError(f"El picker '{self.picker_id}' ya terminó su recorrido.")

        destino = self.plan[0]
        if not graph.has_edge(self.posicion_actual, destino):
            raise ValueError(
                f"Movimiento inválido del picker '{self.picker_id}': "
                f"{self.posicion_actual} -> {destino} no es un paso permitido "
                f"(no es adyacente, no es pasillo o va contra el sentido)."
            )
        self.plan.pop(0)
        self.posicion_actual = destino
        self.historial.append(destino)
        self.pasos = self.pasos + 1
        return destino

    def wait(self) -> None:
        """
        Se queda quieto un instante para dejar pasar a otro picker. También
        se anota en el historial, así los instantes de todos los pickers
        quedan alineados.
        """
        self.historial.append(self.posicion_actual)
        self.esperas = self.esperas + 1

    def stay(self) -> None:
        """
        Se queda quieto un instante (por ejemplo, recogiendo un producto).
        Se anota en el historial para mantener los instantes alineados sin
        contar como espera por colisión.
        """
        self.historial.append(self.posicion_actual)

    def collides_with(self, other: Picker) -> bool:
        """
        Consigna §3.6: True si en el próximo instante este picker y other
        quedarían en la misma celda o se cruzarían (cambiarían de lugar).

        Si a un picker no le quedan pasos, se queda donde está.

        Complejidad: O(1).
        """
        mi_destino = self.next_cell
        if mi_destino is None:
            mi_destino = self.posicion_actual
        su_destino = other.next_cell
        if su_destino is None:
            su_destino = other.posicion_actual

        misma_celda = mi_destino == su_destino
        se_cruzan = (mi_destino == other.posicion_actual
                     and su_destino == self.posicion_actual)
        return misma_celda or se_cruzan

    # ------------------------------------------------------------------
    # Recoger y descargar (consigna §3.6 y §3.4)
    # ------------------------------------------------------------------

    def _adjacent(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        """True si las celdas a y b están pegadas (arriba, abajo, izquierda o derecha)."""
        distancia = abs(a[0] - b[0]) + abs(a[1] - b[1])
        return distancia == 1

    def _already_picked(self, item: OrderItem) -> bool:
        """True si el ítem ya está en la carga o ya se entregó."""
        for otro in self.carga:
            if otro is item:
                return True
        for otro in self.entregados:
            if otro is item:
                return True
        return False

    def pick(self, item: OrderItem) -> None:
        """
        Recoge un ítem de su wave desde la celda en la que está.

        Raises:
            ValueError: Si no está en recorrido, el ítem no es de su wave o
                        ya lo recogió, no está al lado del rack del producto,
                        o con este ítem pasaría su capacidad de carga.
        """
        if self.status != PickerStatus.EN_RECORRIDO:
            raise ValueError(f"El picker '{self.picker_id}' no está en recorrido.")
        if item.wave is None or item.wave.wave_id != self.assigned_wave_id:
            raise ValueError(
                f"El ítem '{item.product.product_id}' no pertenece a la wave "
                f"'{self.assigned_wave_id}' del picker '{self.picker_id}'."
            )
        if self._already_picked(item):
            raise ValueError(
                f"El ítem '{item.product.product_id}' ya fue recogido por el "
                f"picker '{self.picker_id}'."
            )
        celda_rack = (item.product.x, item.product.y)
        if not self._adjacent(self.posicion_actual, celda_rack):
            raise ValueError(
                f"El picker '{self.picker_id}' está en {self.posicion_actual} y no "
                f"puede alcanzar el producto '{item.product.product_id}' en "
                f"{celda_rack}: tiene que estar en una celda de pasillo adyacente."
            )
        if self.carried_weight + item.total_weight > self.capacidad_carga_kg:
            raise ValueError(
                f"El picker '{self.picker_id}' superaría su capacidad: lleva "
                f"{self.carried_weight:.2f} kg, el ítem pesa {item.total_weight:.2f} kg "
                f"y su máximo es {self.capacidad_carga_kg:.2f} kg."
            )
        self.carga.append(item)

    def _is_next_to_zone(self, zone: DispatchZone) -> bool:
        """True si alguna de las 4 celdas vecinas pertenece a la zona."""
        x = self.posicion_actual[0]
        y = self.posicion_actual[1]
        vecinas = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        for celda in vecinas:
            if zone.contains_cell(celda[0], celda[1]):
                return True
        return False

    def can_unload(self, zone: DispatchZone) -> bool:
        """True si está al lado de la zona y en la zona entra al menos uno de sus ítems."""
        if not self._is_next_to_zone(zone):
            return False
        for item in self.carga:
            if zone.has_room_for(item.total_weight):
                return True
        return False

    def unload(self, zone: DispatchZone) -> list[OrderItem]:
        """
        Deja en la zona de despacho los ítems que entran, en el orden en que
        los recogió. Los que no entran siguen en la carga para llevarlos a
        otra zona con lugar.

        Returns:
            Los ítems descargados.

        Raises:
            ValueError: Si no está en recorrido, no está al lado de la zona,
                        o en la zona no entra ninguno de sus ítems (§3.4).
        """
        if self.status != PickerStatus.EN_RECORRIDO:
            raise ValueError(f"El picker '{self.picker_id}' no está en recorrido.")
        if not self._is_next_to_zone(zone):
            raise ValueError(
                f"El picker '{self.picker_id}' está en {self.posicion_actual} y no "
                f"está al lado de la zona '{zone.zone_id}'."
            )
        if len(self.carga) > 0 and not self.can_unload(zone):
            raise ValueError(
                f"En la zona '{zone.zone_id}' no entra ningún ítem del picker "
                f"'{self.picker_id}': tiene {zone.peso_actual:.2f} kg de "
                f"{zone.peso_max_kg:.2f} kg."
            )

        descargados = []
        quedan = []
        for item in self.carga:
            if zone.has_room_for(item.total_weight):
                zone.receive(item.total_weight)
                descargados.append(item)
                self.entregados.append(item)
            else:
                quedan.append(item)
        self.carga = quedan
        return descargados

    # ------------------------------------------------------------------
    # Reiniciar simulación (consigna §12)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Vuelve al estado inicial del escenario: posición inicial, sin carga ni wave."""
        self.status = PickerStatus.LIBRE
        self.assigned_wave_id = None
        self.posicion_actual = self.posicion_inicial
        self.carga = []
        self.entregados = []
        self.historial = [self.posicion_actual]
        self.pasos = 0
        self.esperas = 0
        self.plan = []

    # ------------------------------------------------------------------
    # Lectura y escritura
    # ------------------------------------------------------------------

    def state_to_dict(self) -> dict:
        """Estado actual del picker, para que el front lo dibuje."""
        carga_dict = []
        for item in self.carga:
            carga_dict.append({"producto_id": item.product.product_id, "cantidad": item.cantidad})
        return {
            "id": self.picker_id,
            "estado": self.status.value,
            "wave_id": self.assigned_wave_id,
            "posicion": {"x": self.posicion_actual[0], "y": self.posicion_actual[1]},
            "peso_cargado": round(self.carried_weight, 3),
            "capacidad_carga_kg": self.capacidad_carga_kg,
            "carga": carga_dict,
            "entregados": len(self.entregados),
            "pasos": self.pasos,
            "esperas": self.esperas,
        }

    def to_dict(self) -> dict:
        """
        El picker en el formato del escenario JSON (Anexo A). Si ya se movió,
        también se guarda su posición actual para poder continuar (§17).
        """
        data = {
            "id": self.picker_id,
            "posicion_inicial": {"x": self.posicion_inicial[0], "y": self.posicion_inicial[1]},
            "capacidad_carga_kg": self.capacidad_carga_kg,
        }
        if self.posicion_actual != self.posicion_inicial:
            data["posicion_actual"] = {"x": self.posicion_actual[0], "y": self.posicion_actual[1]}
        return data

    @classmethod
    def from_dict(cls, data: dict) -> Picker:
        """Crea un Picker a partir del JSON (posicion_actual es opcional)."""
        pos = data["posicion_inicial"]
        picker = cls(
            picker_id=data["id"],
            posicion_inicial=(pos["x"], pos["y"]),
            capacidad_carga_kg=data["capacidad_carga_kg"],
        )
        if "posicion_actual" in data:
            actual = data["posicion_actual"]
            picker.posicion_actual = (actual["x"], actual["y"])
            picker.historial = [picker.posicion_actual]
        return picker

    def __repr__(self) -> str:
        return (
            f"Picker(id='{self.picker_id}', pos={self.posicion_actual}, "
            f"estado={self.status.value}, carga={self.carried_weight:.2f}/"
            f"{self.capacidad_carga_kg}kg)"
        )
