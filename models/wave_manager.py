from __future__ import annotations

from typing import TYPE_CHECKING
from models.order import Order, OrderItem, OrderStatus
from models.wave import Wave, WaveStatus

if TYPE_CHECKING:
    from models.warehouse import Warehouse, Picker


class WaveManager:
    """
    Gestiona la formación de waves a partir de pedidos pendientes y la
    asignación voraz y determinista de pickers disponibles.

    Novedades respecto a la versión anterior:
    - Se permite dividir pedidos entre varias waves a nivel de OrderItem
      (líneas completas; no se parten unidades de un mismo ítem).
    - Cada wave puede tener varios pickers asignados.
    - La asignación de pickers prioriza las waves de mayor peso total y
      acumula pickers por capacidad descendente hasta cubrir el peso.

    ADVERTENCIA sobre la capacidad múltiple de pickers:
        La suma de capacidades de los pickers de una wave se usa como
        estimación operativa. No garantiza que cualquier distribución
        de productos sea transportable, dado que cada picker solo puede
        cargar individualmente hasta su límite. La distribución real de
        carga entre pickers queda a cargo del módulo de pathfinding.

    Atributos:
        warehouse             (Warehouse | None)         : Warehouse asociado.
        max_pedidos           (int)                      : Límite de pedidos distintos por wave.
        max_productos         (int)                      : Límite de unidades totales por wave.
        orders                (list[Order])              : Registro total de pedidos.
        waves                 (list[Wave])               : Waves con al menos un picker asignado.
        unassigned_waves      (list[Wave])               : Waves sin picker suficiente.
        unprocessable_orders  (list[tuple[Order, str]])  : Ítems/pedidos irrecuperables con motivo.
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
    # Gestión de pedidos
    # ------------------------------------------------------------------

    def add_order(self, order: Order) -> None:
        """Agrega un pedido al registro del manager."""
        self.orders.append(order)

    def add_orders(self, orders: list[Order]) -> None:
        """Agrega una lista de pedidos al registro del manager."""
        for order in orders:
            self.add_order(order)

    def get_pending_orders(self) -> list[Order]:
        """Retorna los pedidos con al menos un ítem pendiente (PENDIENTE o PARCIAL)."""
        return [
            o for o in self.orders
            if o.status in (OrderStatus.PENDIENTE, OrderStatus.PARCIAL)
            and o.items_pendientes
        ]

    def _validate_item_feasibility(
        self, order: Order, item: OrderItem, max_picker_cap: float
    ) -> tuple[bool, str]:
        """
        Verifica si un OrderItem individual puede caber en alguna wave.

        Un ítem es inviable si su peso solo, con el mayor picker disponible,
        supera la capacidad provisional, o si su cantidad sola supera max_productos.

        Returns:
            (es_factible, motivo_si_no)
        """
        if item.cantidad > self.max_productos:
            return (
                False,
                f"El ítem '{item.product.product_id}' del pedido '{order.order_id}' "
                f"tiene {item.cantidad} unidades, que superan el máximo por wave "
                f"({self.max_productos}).",
            )
        if max_picker_cap > 0 and item.peso_total > max_picker_cap:
            return (
                False,
                f"El ítem '{item.product.product_id}' del pedido '{order.order_id}' "
                f"pesa {item.peso_total:.2f} kg, superando la capacidad del picker "
                f"más capaz ({max_picker_cap:.2f} kg).",
            )
        return True, ""

    # ------------------------------------------------------------------
    # Generación de waves
    # ------------------------------------------------------------------

    def generate_waves(
        self,
        pickers: list[Picker] | None = None,
        prefix: str = "WAVE_",
    ) -> list[Wave]:
        """
        Genera waves a partir de pedidos pendientes (con posibilidad de dividirlos)
        y luego asigna pickers disponibles.

        Estrategia de formación (voraz, determinista):
            1. Determina los pickers libres y el límite provisional de peso
               (mayor capacidad individual entre ellos).
            2. Valida viabilidad de cada ítem individual. Los ítems que
               individualmente superan los límites configurados se reportan como
               inasimilables y se excluyen sin generar bucles infinitos.
            3. Ordena los pedidos por prioridad descendente, con desempate por
               order_id ascendente (determinista).
            4. En cada wave, recorre los pedidos en orden e intenta incorporar
               todos sus ítems pendientes. Si el pedido completo no entra, intenta
               incorporar los ítems que sí quepan (greedy por ítem). Si ningún ítem
               entra, el pedido se omite para esta wave y se evalúa en la siguiente.
               La wave se cierra cuando no hay más ítems que incorporar.
            5. Si al terminar un ciclo completo sobre todos los pedidos ningún ítem
               se incorporó, se rompe el loop para evitar bucles infinitos.

        Estrategia de asignación de pickers (voraz, determinista):
            1. Las waves se ordenan por peso total descendente (las más pesadas primero).
            2. Para cada wave, se acumulan pickers libres en orden de capacidad
               descendente hasta que la suma de capacidades cubra el peso total de la wave.
            3. Un picker que no alcanza por sí solo a cubrir el peso restante de la wave
               puede combinarse con otros.
            4. Si no hay suficiente capacidad disponible, la wave queda sin asignar.
            5. La estrategia NO garantiza una asignación globalmente óptima; es heurística.

        Args:
            pickers: Lista de pickers a considerar. Si es None usa los del warehouse.
            prefix:  Prefijo de los IDs generados de las waves.

        Returns:
            Lista de waves con al menos un picker asignado.
        """
        # ── Paso 1: pickers libres y límite provisional de peso ────────
        if pickers is not None:
            available_pickers = [p for p in pickers if not p.is_busy]
        elif self.warehouse is not None:
            available_pickers = [p for p in self.warehouse.pickers if not p.is_busy]
        else:
            available_pickers = []

        max_provisional_peso = max(
            (p.capacidad_carga_kg for p in available_pickers), default=0.0
        )

        # ── Paso 2: Validar ítems individuales ────────────────────────
        # Separamos los ítems inviables del resto. Solo los ítems viables
        # participan en la formación de waves.
        # Pedidos que pierden todos sus ítems pendientes por inviabilidad
        # se reportan pero no se modifican (permanecen PENDIENTE).
        viable_items_by_order: dict[str, list[OrderItem]] = {}
        for order in self.get_pending_orders():
            viable = []
            for item in order.items_pendientes:
                ok, reason = self._validate_item_feasibility(
                    order, item, max_provisional_peso
                )
                if not ok:
                    self.unprocessable_orders.append((order, reason))
                else:
                    viable.append(item)
            if viable:
                viable_items_by_order[order.order_id] = viable

        if not viable_items_by_order:
            return []

        # ── Paso 3: Ordenar pedidos (prioridad desc, order_id asc) ────
        pending_orders = [
            o for o in self.get_pending_orders()
            if o.order_id in viable_items_by_order
        ]
        pending_orders.sort(key=lambda o: (-o.prioridad, o.order_id))

        # ── Paso 4: Formación voraz de waves ──────────────────────────
        generated_waves: list[Wave] = []
        wave_seq = len(self.waves) + len(self.unassigned_waves) + 1

        # Trabajamos con los ítems viables pendientes por pedido
        # (copia para no alterar viable_items_by_order que puede necesitarse)
        remaining_viable: dict[str, list[OrderItem]] = {
            oid: list(items) for oid, items in viable_items_by_order.items()
        }

        while any(remaining_viable.values()):
            wave_id = f"{prefix}{wave_seq:02d}"
            wave = Wave(
                wave_id=wave_id,
                max_pedidos=self.max_pedidos,
                max_productos=self.max_productos,
            )

            added_any_in_wave = False

            for order in pending_orders:
                oid = order.order_id
                if oid not in remaining_viable or not remaining_viable[oid]:
                    continue

                candidate_items = remaining_viable[oid]

                # Intentar meter todos los ítems pendientes del pedido
                if wave.can_add_items(order, candidate_items, max_peso=max_provisional_peso):
                    wave.add_items(order, candidate_items, max_peso=max_provisional_peso)
                    remaining_viable[oid] = []
                    added_any_in_wave = True
                else:
                    # División: intentar meter los ítems que quepan uno a uno
                    items_to_add: list[OrderItem] = []
                    for item in candidate_items:
                        if wave.can_add_items(order, [item], max_peso=max_provisional_peso):
                            # Verificar que sumando este ítem a los ya seleccionados sigue cabiendo
                            if wave.can_add_items(order, items_to_add + [item], max_peso=max_provisional_peso):
                                items_to_add.append(item)

                    if items_to_add:
                        wave.add_items(order, items_to_add, max_peso=max_provisional_peso)
                        remaining_viable[oid] = [
                            it for it in candidate_items if it not in items_to_add
                        ]
                        added_any_in_wave = True

            # Salvaguarda: si no se agregó nada en este ciclo, salir
            if not added_any_in_wave:
                break

            if wave.entries:
                generated_waves.append(wave)
            wave_seq += 1

        # ── Paso 5: Asignación de pickers ─────────────────────────────
        # Ordenar waves por peso total descendente (las más pesadas primero)
        generated_waves_sorted = sorted(
            generated_waves, key=lambda w: (-w.peso_total(), w.wave_id)
        )

        free_pickers_pool = sorted(
            available_pickers,
            key=lambda p: (-p.capacidad_carga_kg, p.picker_id),
        )

        assigned_waves: list[Wave] = []

        for wave in generated_waves_sorted:
            peso_restante = wave.peso_total()
            pickers_for_wave: list[Picker] = []
            used: list[Picker] = []

            for picker in free_pickers_pool:
                if peso_restante <= 0:
                    break
                pickers_for_wave.append(picker)
                used.append(picker)
                peso_restante -= picker.capacidad_carga_kg

            if peso_restante <= 0:
                # Asignación exitosa
                for picker in pickers_for_wave:
                    wave.add_picker(picker)
                    free_pickers_pool.remove(picker)
                self.waves.append(wave)
                assigned_waves.append(wave)
            else:
                # Capacidad insuficiente
                self.unassigned_waves.append(wave)
                # Revertir los ítems de pedidos PARCIAL o EN_WAVE a PENDIENTE
                # para que puedan incluirse en futuras invocaciones
                for entry in wave.entries:
                    order = entry.order
                    # Devolver los ítems asignados en esta wave a items_pendientes
                    for it in entry.items:
                        if it not in order.items_pendientes:
                            order.items_pendientes.append(it)
                    # Ajustar estado
                    if order.esta_completamente_asignado() is False:
                        if not order.items_pendientes:
                            pass  # mantener EN_WAVE
                        else:
                            order.status = OrderStatus.PENDIENTE if len(order.items_pendientes) == len(order.items) else OrderStatus.PARCIAL

        # Reordenar this.waves por orden de creación (wave_id) para consistencia
        self.waves.sort(key=lambda w: w.wave_id)
        assigned_waves.sort(key=lambda w: w.wave_id)

        return assigned_waves

    # ------------------------------------------------------------------
    # Consultas y resumen
    # ------------------------------------------------------------------

    def get_waves(self) -> list[Wave]:
        """Retorna las waves asignadas a al menos un picker."""
        return list(self.waves)

    def get_unassigned_waves(self) -> list[Wave]:
        """Retorna las waves sin asignación de picker suficiente."""
        return list(self.unassigned_waves)

    def get_unprocessable_orders(self) -> list[tuple[Order, str]]:
        """Retorna los ítems/pedidos descartados por inviabilidad con su motivo."""
        return list(self.unprocessable_orders)

    def __repr__(self) -> str:
        return (
            f"WaveManager(pedidos_totales={len(self.orders)}, "
            f"con_pendientes={len(self.get_pending_orders())}, "
            f"waves_asignadas={len(self.waves)}, "
            f"waves_sin_picker={len(self.unassigned_waves)})"
        )
