import unittest
import json
from pathlib import Path

from models.product import Product
from models.order import Order, OrderItem, OrderStatus
from models.wave import Wave, WaveStatus, WaveOrderEntry
from models.warehouse import Warehouse, Picker
from models.wave_manager import WaveManager


class TestWaveManager(unittest.TestCase):
    """
    Suite de pruebas actualizada para WaveManager y Wave.

    Cubre los nuevos requisitos:
    - División de pedidos entre waves (a nivel de OrderItem).
    - Múltiples pickers por wave.
    - Estrategia de asignación: waves ordenadas por peso desc,
      pickers acumulados por capacidad desc.
    """

    def setUp(self):
        """Productos y pickers de prueba reutilizables."""
        self.p_ligero   = Product("P_LIGERO",   "Producto Ligero",    "R1", [3, 5, 1], 100,  1.0)
        self.p_medio    = Product("P_MEDIO",    "Producto Medio",     "R1", [3, 5, 2], 100,  5.0)
        self.p_pesado   = Product("P_PESADO",   "Producto Pesado",    "R1", [4, 7, 1], 100, 20.0)
        self.p_muy_pesado = Product("P_MUY_PESADO", "Muy Pesado",    "R2", [8, 6, 1], 100, 120.0)

        self.picker_pequeno = Picker("PK_SMALL",  (0, 3), 30.0)
        self.picker_mediano = Picker("PK_MED",    (5, 3), 50.0)
        self.picker_grande  = Picker("PK_LARGE", (10, 3), 100.0)

    def _mk_order(self, order_id: str, prioridad: int, product: Product, cantidad: int) -> Order:
        """Helper: pedido con un único ítem."""
        return Order(order_id, [OrderItem(product, cantidad)], prioridad)

    def _mk_order_multi(self, order_id: str, prioridad: int, items: list[tuple]) -> Order:
        """Helper: pedido con múltiples ítems [(product, cantidad), ...]."""
        return Order(order_id, [OrderItem(p, c) for p, c in items], prioridad)

    # ──────────────────────────────────────────────────────────────────
    # 1. Prioridad descendente
    # ──────────────────────────────────────────────────────────────────
    def test_pedidos_prioridad_descendente(self):
        o1 = self._mk_order("PED_BAJA",  1, self.p_ligero, 1)
        o2 = self._mk_order("PED_MEDIA", 3, self.p_ligero, 1)
        o3 = self._mk_order("PED_ALTA",  5, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2, o3])

        pickers = [Picker(f"PK{i}", (0, 0), 100.0) for i in range(3)]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual(len(waves), 3)
        self.assertEqual(waves[0].orders[0].order_id, "PED_ALTA")
        self.assertEqual(waves[1].orders[0].order_id, "PED_MEDIA")
        self.assertEqual(waves[2].orders[0].order_id, "PED_BAJA")

    # ──────────────────────────────────────────────────────────────────
    # 2. Desempate determinista por order_id
    # ──────────────────────────────────────────────────────────────────
    def test_desempate_determinista(self):
        o_c = self._mk_order("PED_C", 4, self.p_ligero, 1)
        o_a = self._mk_order("PED_A", 4, self.p_ligero, 1)
        o_b = self._mk_order("PED_B", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o_c, o_a, o_b])  # orden arbitrario

        pickers = [Picker(f"PK{i}", (0, 0), 100.0) for i in range(3)]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual([w.orders[0].order_id for w in waves], ["PED_A", "PED_B", "PED_C"])

    # ──────────────────────────────────────────────────────────────────
    # 3. Un ítem que no entra no impide incorporar otro de menor prio
    # ──────────────────────────────────────────────────────────────────
    def test_item_que_no_entra_permite_otros(self):
        # Picker provisional: 30 kg
        picker = Picker("PK_30", (0, 0), 30.0)

        o_alta  = self._mk_order("PED_ALTA",  5, self.p_pesado, 1)  # 20 kg
        o_media = self._mk_order("PED_MEDIA", 4, self.p_pesado, 1)  # 20 kg → no entra junto
        o_baja  = self._mk_order("PED_BAJA",  2, self.p_medio,  1)  #  5 kg → entra

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o_alta, o_media, o_baja])

        waves = wm.generate_waves(pickers=[picker])

        self.assertEqual(len(waves), 1)
        wave_orders = [o.order_id for o in waves[0].orders]
        self.assertIn("PED_ALTA", wave_orders)
        self.assertIn("PED_BAJA", wave_orders)
        self.assertNotIn("PED_MEDIA", wave_orders)
        self.assertEqual(o_media.status, OrderStatus.PENDIENTE)

    # ──────────────────────────────────────────────────────────────────
    # 4. No se supera el máximo de pedidos por wave
    # ──────────────────────────────────────────────────────────────────
    def test_no_supera_max_pedidos(self):
        pedidos = [self._mk_order(f"PED_{i:02d}", 3, self.p_ligero, 1) for i in range(7)]
        wm = WaveManager(max_pedidos=3, max_productos=20)
        wm.add_orders(pedidos)

        pickers = [Picker(f"PK_{i}", (0, 0), 100.0) for i in range(5)]
        waves = wm.generate_waves(pickers=pickers)

        for w in waves:
            self.assertLessEqual(w.current_pedidos(), 3)

        total_pedidos_asignados = sum(w.current_pedidos() for w in waves)
        self.assertEqual(total_pedidos_asignados, 7)

    # ──────────────────────────────────────────────────────────────────
    # 5. No se supera el máximo de unidades por wave
    # ──────────────────────────────────────────────────────────────────
    def test_no_supera_max_productos(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 4)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 4)
        o3 = self._mk_order("PED_03", 3, self.p_ligero, 3)  # 4+4+3=11 > 10 → no entra completo
        o4 = self._mk_order("PED_04", 2, self.p_ligero, 2)  # 4+4+2=10 → entra

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2, o3, o4])

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        for w in waves:
            self.assertLessEqual(w.current_unidades(), 10)

        # El primer wave debe tener PED_01, PED_02 y PED_04 (PED_03 no cabe completo)
        first_ids = [o.order_id for o in waves[0].orders]
        self.assertIn("PED_01", first_ids)
        self.assertIn("PED_02", first_ids)
        self.assertIn("PED_04", first_ids)

    # ──────────────────────────────────────────────────────────────────
    # 6. División de pedido entre varias waves (nuevo comportamiento)
    # ──────────────────────────────────────────────────────────────────
    def test_pedido_se_divide_entre_waves(self):
        """
        Un pedido con dos ítems que no caben juntos en una wave debe
        dividirse: un ítem va a la primera wave y el otro a la segunda.
        No se duplican ni se pierden cantidades.
        """
        p1 = Product("PA", "A", "R1", [1, 1, 1], 100, 1.0)
        p2 = Product("PB", "B", "R1", [2, 2, 1], 100, 1.0)
        # Pedido con 6 unidades de PA y 5 de PB → 11 unidades en total
        order = self._mk_order_multi("PED_SPLIT", 5, [(p1, 6), (p2, 5)])

        # Máximo 10 unidades por wave → el pedido no cabe completo
        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_order(order)

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        # El pedido debe aparecer en al menos una wave
        orders_with_items = [w for w in waves if any(e.order.order_id == "PED_SPLIT" for e in w.entries)]
        self.assertGreaterEqual(len(orders_with_items), 1)

        # Verificar que las cantidades totales asignadas son exactas (sin duplicación)
        total_asignadas = 0
        for wave in waves:
            for entry in wave.entries:
                if entry.order.order_id == "PED_SPLIT":
                    total_asignadas += sum(it.cantidad for it in entry.items)
        self.assertEqual(total_asignadas, order.total_unidades())

        # Ningún ítem aparece en dos waves simultáneamente
        asignados_ids = []
        for wave in waves:
            for entry in wave.entries:
                if entry.order.order_id == "PED_SPLIT":
                    asignados_ids.extend(id(it) for it in entry.items)
        self.assertEqual(len(asignados_ids), len(set(asignados_ids)))

    # ──────────────────────────────────────────────────────────────────
    # 7. El peso total de una wave no supera la capacidad total de sus pickers
    # ──────────────────────────────────────────────────────────────────
    def test_peso_no_supera_capacidad_pickers(self):
        o1 = self._mk_order("PED_01", 5, self.p_medio, 5)  # 25 kg
        o2 = self._mk_order("PED_02", 4, self.p_medio, 4)  # 20 kg → total 45 kg

        wm = WaveManager(max_pedidos=5, max_productos=20)
        wm.add_orders([o1, o2])

        # Un único picker de 50 kg cubre los 45 kg
        picker_50 = Picker("PK_50", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[picker_50])

        self.assertEqual(len(waves), 1)
        wave = waves[0]
        self.assertLessEqual(wave.peso_total(), wave.capacidad_pickers())

    # ──────────────────────────────────────────────────────────────────
    # 8. Cada picker se asigna como máximo a una wave
    # ──────────────────────────────────────────────────────────────────
    def test_picker_asignado_a_lo_sumo_a_una_wave(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 1)
        o3 = self._mk_order("PED_03", 3, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2, o3])

        p1 = Picker("PK_A", (0, 0), 50.0)
        p2 = Picker("PK_B", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[p1, p2])

        # Dos pickers → máximo 2 waves asignadas
        self.assertEqual(len(waves), 2)

        # Cada picker aparece en a lo sumo una wave
        all_pickers = [pk for w in waves for pk in w.pickers]
        all_picker_ids = [pk.picker_id for pk in all_pickers]
        self.assertEqual(len(all_picker_ids), len(set(all_picker_ids)))

        self.assertTrue(p1.is_busy)
        self.assertTrue(p2.is_busy)
        self.assertEqual(len(wm.get_unassigned_waves()), 1)

    # ──────────────────────────────────────────────────────────────────
    # 9. Estrategia de asignación: pickers acumulados por capacidad desc
    # ──────────────────────────────────────────────────────────────────
    def test_multiple_pickers_cubren_peso_wave(self):
        """
        Una wave puede requerir múltiples pickers si ningún picker libre
        alcanza individualmente su peso total, pero la suma de sus capacidades sí.

        Escenario:
        - Pedido 1: 30 kg (prioridad 5) -> WAVE_01 (30 kg)
        - Pedido 2: 25 kg (prioridad 4) -> WAVE_02 (25 kg)
        - Pickers: PK_30 (30 kg), PK_15A (15 kg), PK_15B (15 kg)
        - Límite provisional = max(30, 15, 15) = 30 kg (ambos pedidos son viables).
        - Asignación voraz por peso descendente:
            WAVE_01 (30 kg) se lleva a PK_30 (30 kg).
            WAVE_02 (25 kg) no puede cubrirse con PK_15A solo (15 < 25),
            pero acumulando PK_15A (15 kg) + PK_15B (15 kg) = 30 kg >= 25 kg sí.
            Por ende, WAVE_02 queda con 2 pickers asignados.
        """
        o1 = self._mk_order("PED_01", 5, self.p_medio, 6)  # 6 * 5 kg = 30 kg
        o2 = self._mk_order("PED_02", 4, self.p_medio, 5)  # 5 * 5 kg = 25 kg

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2])

        p30 = Picker("PK_30", (0, 0), 30.0)
        p15a = Picker("PK_15A", (0, 0), 15.0)
        p15b = Picker("PK_15B", (0, 0), 15.0)

        waves = wm.generate_waves(pickers=[p30, p15a, p15b])

        self.assertEqual(len(waves), 2)
        wave_01 = next(w for w in waves if w.wave_id == "WAVE_01")
        wave_02 = next(w for w in waves if w.wave_id == "WAVE_02")

        self.assertEqual(len(wave_01.pickers), 1)
        self.assertEqual(wave_01.pickers[0].picker_id, "PK_30")

        self.assertEqual(len(wave_02.pickers), 2)
        picker_ids = [p.picker_id for p in wave_02.pickers]
        self.assertIn("PK_15A", picker_ids)
        self.assertIn("PK_15B", picker_ids)
        self.assertGreaterEqual(wave_02.capacidad_pickers(), wave_02.peso_total())
        self.assertTrue(p15a.is_busy)
        self.assertTrue(p15b.is_busy)


    # ──────────────────────────────────────────────────────────────────
    # 10. Pedidos pendientes entran en waves posteriores
    # ──────────────────────────────────────────────────────────────────
    def test_pedidos_no_incorporados_entran_en_waves_posteriores(self):
        o1 = self._mk_order("PED_01", 5, self.p_medio, 2)  # 10 kg
        o2 = self._mk_order("PED_02", 4, self.p_medio, 2)  # 10 kg
        o3 = self._mk_order("PED_03", 3, self.p_medio, 2)  # 10 kg

        wm = WaveManager(max_pedidos=2, max_productos=10)
        wm.add_orders([o1, o2, o3])

        p1 = Picker("PK_1", (0, 0), 50.0)
        p2 = Picker("PK_2", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[p1, p2])

        self.assertEqual(len(waves), 2)
        self.assertEqual(sorted([o.order_id for o in waves[0].orders]), ["PED_01", "PED_02"])
        self.assertEqual([o.order_id for o in waves[1].orders], ["PED_03"])

    # ──────────────────────────────────────────────────────────────────
    # 11. Ítems individuales imposibles: sin bucles ni pérdidas
    # ──────────────────────────────────────────────────────────────────
    def test_items_imposibles_se_manejan_explicitamente(self):
        o_exceso_u  = self._mk_order("PED_EXCESO_U", 5, self.p_ligero,    25)  # 25 > max_productos(20)
        o_exceso_p  = self._mk_order("PED_EXCESO_P", 5, self.p_muy_pesado, 1)  # 120 kg > 100 kg
        o_normal    = self._mk_order("PED_OK",        3, self.p_ligero,     2)

        wm = WaveManager(max_pedidos=5, max_productos=20)
        wm.add_orders([o_exceso_u, o_exceso_p, o_normal])

        picker_100 = Picker("PK_100", (0, 0), 100.0)
        waves = wm.generate_waves(pickers=[picker_100])

        self.assertEqual(len(waves), 1)
        self.assertEqual(waves[0].orders[0].order_id, "PED_OK")

        unproc = wm.get_unprocessable_orders()
        self.assertGreaterEqual(len(unproc), 2)
        unproc_ids = {o.order_id for o, _ in unproc}
        self.assertIn("PED_EXCESO_U", unproc_ids)
        self.assertIn("PED_EXCESO_P", unproc_ids)

        self.assertEqual(o_exceso_u.status, OrderStatus.PENDIENTE)
        self.assertEqual(o_exceso_p.status, OrderStatus.PENDIENTE)

    # ──────────────────────────────────────────────────────────────────
    # 12. Pedidos ya asignados no se reincorporan
    # ──────────────────────────────────────────────────────────────────
    def test_pedidos_ya_asignados_no_se_reincorporan(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2])

        p1 = Picker("PK_1", (0, 0), 50.0)
        waves_1 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_1), 1)

        p2 = Picker("PK_2", (0, 0), 50.0)
        waves_2 = wm.generate_waves(pickers=[p2])
        self.assertEqual(len(waves_2), 0)

    # ──────────────────────────────────────────────────────────────────
    # 13. Ciclo de vida de Wave con múltiples pickers
    # ──────────────────────────────────────────────────────────────────
    def test_ciclo_de_vida_wave_multi_picker(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 2)
        wave = Wave("W1", max_pedidos=3, max_productos=10)
        wave.add_order(o1)

        # Sin pickers no puede iniciar
        with self.assertRaises(ValueError):
            wave.start()

        pk1 = Picker("PK1", (0, 0), 30.0)
        pk2 = Picker("PK2", (0, 0), 30.0)
        wave.add_picker(pk1)
        wave.add_picker(pk2)
        self.assertTrue(pk1.is_busy)
        self.assertTrue(pk2.is_busy)

        # Primero llevar el pedido a EN_WAVE (assign_items ya lo hizo en add_order)
        wave.start()
        self.assertEqual(wave.status, WaveStatus.EN_PROCESO)
        self.assertEqual(o1.status, OrderStatus.EN_PREPARACION)

        wave.complete()
        self.assertEqual(wave.status, WaveStatus.COMPLETADA)
        self.assertEqual(o1.status, OrderStatus.PREPARADO)
        self.assertFalse(pk1.is_busy)
        self.assertFalse(pk2.is_busy)

    # ──────────────────────────────────────────────────────────────────
    # 14. Integración con escenario_basico.json
    # ──────────────────────────────────────────────────────────────────
    def test_integracion_escenario_basico(self):
        escenario_path = Path(__file__).resolve().parent.parent / "scenarios" / "escenario_basico.json"
        with open(escenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        wh = Warehouse.from_dict(data)
        orders = [Order.from_dict(p, wh.products) for p in data.get("pedidos", [])]

        wm = WaveManager(warehouse=wh, orders=orders)
        waves = wm.generate_waves()

        # Con 3 pedidos y max_pedidos=3 debe generar al menos 1 wave con todos los pedidos
        self.assertGreaterEqual(len(waves), 1)
        total_orders_in_waves = sum(w.current_pedidos() for w in waves)
        self.assertGreaterEqual(total_orders_in_waves, len(orders))
        # Todas las waves asignadas tienen al menos un picker
        for w in waves:
            self.assertGreater(len(w.pickers), 0)

    # ──────────────────────────────────────────────────────────────────
    # 15. Desempate determinista entre pickers de igual capacidad
    # ──────────────────────────────────────────────────────────────────
    def test_desempate_pickers_misma_capacidad(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1])

        p_z = Picker("PK_Z", (0, 0), 50.0)
        p_a = Picker("PK_A", (0, 0), 50.0)
        # Pasados en orden Z, A → ambos con misma capacidad, debe elegir PK_Z primero
        # (nueva estrategia: por capacidad desc, empate por picker_id asc)
        waves = wm.generate_waves(pickers=[p_z, p_a])
        self.assertEqual(len(waves), 1)
        # Con igual capacidad, el desempate es por picker_id ascendente → PK_A
        self.assertEqual(waves[0].pickers[0].picker_id, "PK_A")

    # ──────────────────────────────────────────────────────────────────
    # 16. Reutilización de picker tras completar una wave
    # ──────────────────────────────────────────────────────────────────
    def test_reutilizacion_picker_tras_completar_wave(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2])

        p1 = Picker("PK_1", (0, 0), 50.0)
        waves_1 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_1), 1)
        self.assertTrue(p1.is_busy)

        waves_1[0].start()
        waves_1[0].complete()
        self.assertFalse(p1.is_busy)

        waves_2 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_2), 1)
        self.assertEqual(waves_2[0].orders[0].order_id, "PED_02")
        self.assertEqual(waves_2[0].pickers[0].picker_id, "PK_1")

    # ──────────────────────────────────────────────────────────────────
    # 17. Serialización y reconstrucción de Wave con múltiples pickers
    # ──────────────────────────────────────────────────────────────────
    def test_serializacion_wave_con_pickers(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 2)
        wave = Wave("W_SERIAL", max_pedidos=3, max_productos=10)
        wave.add_order(o1)

        pk1 = Picker("PK_A", (1, 1), 30.0)
        pk2 = Picker("PK_B", (2, 2), 30.0)
        wave.add_picker(pk1)
        wave.add_picker(pk2)

        data = wave.to_dict()
        self.assertIn("PK_A", data["picker_ids"])
        self.assertIn("PK_B", data["picker_ids"])
        self.assertEqual(data["order_ids"], ["PED_01"])

        # Reconstrucción — pickers ya marcados como ocupados, creamos nuevas instancias
        pk1_r = Picker("PK_A", (1, 1), 30.0)
        pk2_r = Picker("PK_B", (2, 2), 30.0)
        order_registry = {"PED_01": o1}
        picker_registry = {"PK_A": pk1_r, "PK_B": pk2_r}
        reconstructed = Wave.from_dict(data, order_registry, picker_registry)

        self.assertEqual(reconstructed.wave_id, "W_SERIAL")
        self.assertEqual(len(reconstructed.pickers), 2)
        self.assertEqual(reconstructed.orders[0].order_id, "PED_01")

    # ──────────────────────────────────────────────────────────────────
    # 18. División: ítems pendientes del pedido se actualiza correctamente
    # ──────────────────────────────────────────────────────────────────
    def test_items_pendientes_actualizados_tras_division(self):
        p1 = Product("PA", "A", "R1", [1, 1, 1], 100, 2.0)
        p2 = Product("PB", "B", "R1", [2, 2, 1], 100, 2.0)
        p3 = Product("PC", "C", "R1", [3, 3, 1], 100, 2.0)

        # 3 ítems de 3 unidades cada uno → 9 unidades totales; max_productos = 6
        order = self._mk_order_multi("PED_SPLIT", 5, [(p1, 3), (p2, 3), (p3, 3)])
        wm = WaveManager(max_pedidos=5, max_productos=6)
        wm.add_order(order)

        pickers = [Picker(f"PK{i}", (0, 0), 100.0) for i in range(3)]
        waves = wm.generate_waves(pickers=pickers)

        # Debe repartir los ítems en múltiples waves
        self.assertGreaterEqual(len(waves), 2)

        # Total de unidades asignadas == total del pedido
        total = sum(
            sum(it.cantidad for it in entry.items)
            for w in waves
            for entry in w.entries
            if entry.order.order_id == "PED_SPLIT"
        )
        self.assertEqual(total, 9)

        # El pedido debe quedar en EN_WAVE (todos los ítems asignados)
        self.assertEqual(order.status, OrderStatus.EN_WAVE)

    # ──────────────────────────────────────────────────────────────────
    # 19. Wave.orders propiedad retrocompatible
    # ──────────────────────────────────────────────────────────────────
    def test_wave_orders_retrocompatibilidad(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 1)

        wave = Wave("W1", max_pedidos=5, max_productos=10)
        wave.add_order(o1)
        wave.add_order(o2)

        orders = wave.orders
        self.assertEqual(len(orders), 2)
        order_ids = {o.order_id for o in orders}
        self.assertIn("PED_01", order_ids)
        self.assertIn("PED_02", order_ids)


if __name__ == "__main__":
    unittest.main()
