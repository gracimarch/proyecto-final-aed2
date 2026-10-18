from __future__ import annotations

from typing import TYPE_CHECKING
from models.order import Order, OrderStatus
from models.wave import Wave, WaveStatus

if TYPE_CHECKING:
    from models.warehouse import Warehouse, Picker


class WaveManager:
    """
    Gestiona la formación y administración de waves a partir de pedidos pendientes
    y la asignación voraz y determinista de pickers disponibles.

    Atributos:
        warehouse             (Warehouse | None)          : Instancia del warehouse asociada.
        max_pedidos           (int)                       : Límite máximo de pedidos por wave.
        max_productos         (int)                       : Límite máximo de productos por wave.
        orders                (list[Order])               : Registro total de pedidos en el manager.
        waves                 (list[Wave])                : Waves generadas con picker asignado.
        unassigned_waves      (list[Wave])                : Waves generadas que no pudieron obtener picker.
        unprocessable_orders  (list[tuple[Order, str]])   : Pedidos que no pueden procesarse por exceder
                                                            restricciones individuales (pedido, motivo).
    """

    def __init__(
        self,
        warehouse: Warehouse | None = None,
        orders: list[Order] | None = None,
        max_pedidos: int | None = None,
        max_productos: int | None = None,
    ):
        self.warehouse = warehouse
        self.orders: list[Order] = list(orders) if orders else []
        self.waves: list[Wave] = []
        self.unassigned_waves: list[Wave] = []
        self.unprocessable_orders: list[tuple[Order, str]] = []

        # Determinar límites a partir del warehouse o valores explícitos
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

    # ------------------------------------------------------------------
    # Gestión de Pedidos
    # ------------------------------------------------------------------

    def add_order(self, order: Order) -> None:
        """Agrega un pedido al registro del manager."""
        self.orders.append(order)

    def add_orders(self, orders: list[Order]) -> None:
        """Agrega una lista de pedidos al registro del manager."""
        for order in orders:
            self.add_order(order)

    def get_pending_orders(self) -> list[Order]:
        """Retorna los pedidos que se encuentran en estado PENDIENTE."""
        return [o for o in self.orders if o.status == OrderStatus.PENDIENTE]

    def validate_order_feasibility(
        self, order: Order, max_picker_cap: float
    ) -> tuple[bool, str]:
        """
        Verifica si un pedido individual puede ser procesado por alguna wave
        respetando las restricciones configuradas del sistema.

        Args:
            order: Pedido a evaluar.
            max_picker_cap: Mayor capacidad de carga entre los pickers disponibles (kg).

        Returns:
            (es_factible, motivo_si_no_es_factible)
        """
        if order.total_unidades() > self.max_productos:
            return (
                False,
                f"La cantidad total de unidades ({order.total_unidades()}) supera "
                f"el máximo permitido por wave ({self.max_productos}).",
            )
        if max_picker_cap > 0 and order.peso_total() > max_picker_cap:
            return (
                False,
                f"El peso total ({order.peso_total():.2f} kg) supera la capacidad "
                f"del picker más capaz disponible ({max_picker_cap:.2f} kg).",
            )
        if order.total_lineas() == 0:
            return False, "El pedido no contiene ningún producto."

        return True, ""

    # ------------------------------------------------------------------
    # Generación Voraz de Waves y Asignación de Pickers
    # ------------------------------------------------------------------

    def generate_waves(
        self,
        pickers: list[Picker] | None = None,
        prefix: str = "WAVE_",
        revert_unassigned_orders: bool = True,
    ) -> list[Wave]:
        """
        Genera waves a partir de pedidos pendientes mediante una estrategia voraz
        y determinista, y luego asigna los pickers disponibles según su capacidad.

        Estrategia:
            1. Identifica los pickers libres. Determina como límite provisional de peso
               la capacidad máxima entre ellos.
            2. Obtiene pedidos pendientes y valida su factibilidad individual para evitar
               bucles infinitos con pedidos inasimilables.
            3. Ordena los pedidos factibles por prioridad descendente (5 a 1), resolviendo
               empates determinísticamente por identificador único del pedido.
            4. Forma waves vorazmente: para cada wave incorpora el primer pedido disponible
               y luego evalúa ordenadamente los demás pedidos pendientes. Si un pedido
               no entra por pedidos, productos o peso, se omite para esa wave y se continúa
               evaluando los siguientes.
            5. Finalizada la formación de todas las waves, se ordenan determinísticamente por orden
               de creación y se asigna a cada una el picker libre de menor capacidad suficiente
               (reserva de capacidad para waves más pesadas).

        Args:
            pickers: Lista opcional de pickers a considerar. Si es None, utiliza
                     los pickers del warehouse.
            prefix: Prefijo para los identificadores generados de las waves.
            revert_unassigned_orders: Si es True, revierte el estado a PENDIENTE de
                                      aquellos pedidos en waves que no consiguieron picker.

        Returns:
            Lista de waves asignadas exitosamente a un picker.
        """
        # Paso 1: Identificar pickers libres y límite provisional de peso
        if pickers is not None:
            available_pickers = [p for p in pickers if not p.is_busy]
        elif self.warehouse is not None:
            available_pickers = [p for p in self.warehouse.pickers if not p.is_busy]
        else:
            available_pickers = []

        max_provisional_peso = (
            max((p.capacidad_carga_kg for p in available_pickers), default=0.0)
        )

        # Paso 2: Filtrar pedidos pendientes y validar factibilidad individual
        pending = self.get_pending_orders()
        feasible_orders: list[Order] = []

        for order in pending:
            is_feasible, reason = self.validate_order_feasibility(
                order, max_provisional_peso
            )
            if not is_feasible:
                self.unprocessable_orders.append((order, reason))
            else:
                feasible_orders.append(order)

        # Paso 3: Ordenar determinísticamente:
        # Criterio principal: prioridad descendente (-o.prioridad)
        # Criterio secundario: identificador de pedido en orden ascendente (o.order_id)
        feasible_orders.sort(key=lambda o: (-o.prioridad, o.order_id))

        # Paso 4: Generación voraz de waves
        generated_waves: list[Wave] = []
        remaining_orders = list(feasible_orders)
        wave_seq = len(self.waves) + len(self.unassigned_waves) + 1

        while remaining_orders:
            wave_id = f"{prefix}{wave_seq:02d}"
            wave = Wave(
                wave_id=wave_id,
                max_pedidos=self.max_pedidos,
                max_productos=self.max_productos,
            )

            still_pending: list[Order] = []
            added_any = False

            for order in remaining_orders:
                if wave.has_capacity_for(order, max_peso=max_provisional_peso):
                    wave.add_order(order, max_peso=max_provisional_peso)
                    added_any = True
                else:
                    still_pending.append(order)

            # Salvaguarda contra bucles infinitos
            if not added_any:
                break

            generated_waves.append(wave)
            wave_seq += 1
            remaining_orders = still_pending

        # Paso 5: Asignación posterior de pickers
        # Orden determinista de waves: orden de creación (ya garantizado por la lista)
        free_pickers_pool = list(available_pickers)
        assigned_waves: list[Wave] = []

        for wave in generated_waves:
            # Buscar pickers libres cuya capacidad soporte el peso total de la wave
            compatible = [
                p for p in free_pickers_pool
                if p.capacidad_carga_kg >= wave.peso_total()
            ]

            if compatible:
                # Preferir el picker de menor capacidad suficiente; resolver empates por picker_id
                compatible.sort(key=lambda p: (p.capacidad_carga_kg, p.picker_id))
                chosen_picker = compatible[0]
                wave.assign_picker(chosen_picker)
                free_pickers_pool.remove(chosen_picker)
                self.waves.append(wave)
                assigned_waves.append(wave)
            else:
                # No hay picker compatible libre para esta wave
                self.unassigned_waves.append(wave)
                if revert_unassigned_orders:
                    for order in wave.orders:
                        order.status = OrderStatus.PENDIENTE

        return assigned_waves

    # ------------------------------------------------------------------
    # Consultas y Resumen
    # ------------------------------------------------------------------

    def get_waves(self) -> list[Wave]:
        """Retorna las waves actualmente generadas y asignadas a un picker."""
        return list(self.waves)

    def get_unassigned_waves(self) -> list[Wave]:
        """Retorna las waves que no tienen picker asignado."""
        return list(self.unassigned_waves)

    def get_unprocessable_orders(self) -> list[tuple[Order, str]]:
        """Retorna los pedidos descartados por inviabilidad junto con su motivo."""
        return list(self.unprocessable_orders)

    def __repr__(self) -> str:
        return (
            f"WaveManager(pedidos_totales={len(self.orders)}, "
            f"pendientes={len(self.get_pending_orders())}, "
            f"waves_asignadas={len(self.waves)}, "
            f"waves_sin_picker={len(self.unassigned_waves)})"
        )
