import unittest

from algorithms.graph_builder import generate_graph
from models.order import Order, OrderItem, OrderStatus
from models.picker import Picker
from models.product import Product
from models.warehouse import Warehouse, Rack, Door, DispatchZone, Aisle
from models.wave import Wave, WaveStatus
from models.wave_manager import WaveManager


class TestWaveManager(unittest.TestCase):
    """Pruebas unitarias para la generación de waves, división de pedidos y asignación de pickers."""

    def setUp(self):
        # Productos de prueba
        self.p_ligero = Product("P_LIGERO", "Ligero", "R1", [1, 4, 1], 100, 1.0)
        self.p_medio = Product("P_MEDIO", "Medio", "R1", [1, 4, 2], 100, 5.0)
        self.p_pesado = Product("P_PESADO", "Pesado", "R1", [2, 5, 1], 100, 20.0)

        # Pickers de prueba
        self.pk_chico = Picker("PK_CHICO", (0, 3), 30.0)
        self.pk_medio = Picker("PK_MEDIO", (0, 3), 60.0)
        self.pk_grande = Picker("PK_GRANDE", (0, 3), 120.0)

    def _mk_order(self, order_id: str, prioridad: int, product: Product, cantidad: int) -> Order:
        return Order(order_id, [OrderItem(product, cantidad)], prioridad)

    def _mk_order_multi(self, order_id: str, prioridad: int, items: list[tuple[Product, int]]) -> Order:
        return Order(order_id, [OrderItem(p, c) for p, c in items], prioridad)

    def test_pedidos_prioridad_descendente(self):
        o_baja = self._mk_order("PED_BAJA", 1, self.p_ligero, 1)
        o_media = self._mk_order("PED_MEDIA", 3, self.p_ligero, 1)
        o_alta = self._mk_order("PED_ALTA", 5, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o_baja, o_media, o_alta])

        waves = wm.generate_waves(pickers=[self.pk_grande])

        self.assertEqual(len(waves), 3)
        self.assertEqual(waves[0].orders[0].order_id, "PED_ALTA")
        self.assertEqual(waves[1].orders[0].order_id, "PED_MEDIA")
        self.assertEqual(waves[2].orders[0].order_id, "PED_BAJA")

    def test_desempate_determinista_por_id(self):
        o_c = self._mk_order("PED_C", 4, self.p_ligero, 1)
        o_a = self._mk_order("PED_A", 4, self.p_ligero, 1)
        o_b = self._mk_order("PED_B", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o_c, o_a, o_b])

        waves = wm.generate_waves(pickers=[self.pk_grande])

        ids_generados = [w.orders[0].order_id for w in waves]
        self.assertEqual(ids_generados, ["PED_A", "PED_B", "PED_C"])

    def test_division_pedido_por_capacidad_de_wave(self):
        # 3 ítems de 3 unidades = 9 unidades totales; límite max_productos=5
        p1 = Product("PA", "A", "R1", [1, 4, 1], 100, 1.0)
        p2 = Product("PB", "B", "R1", [1, 4, 2], 100, 1.0)
        p3 = Product("PC", "C", "R1", [2, 5, 1], 100, 1.0)

        order = self._mk_order_multi("PED_GRANDE", 5, [(p1, 3), (p2, 3), (p3, 3)])
        wm = WaveManager(max_pedidos=5, max_productos=5)
        wm.add_order(order)

        waves = wm.generate_waves(pickers=[self.pk_grande])

        # Se deben haber creado al menos 2 waves
        self.assertGreaterEqual(len(waves), 2)

        # La suma total de unidades en las waves debe ser exactamente 9
        total_unidades = sum(
            sum(item.cantidad for item in entry.items)
            for w in waves
            for entry in w.entries
            if entry.order.order_id == "PED_GRANDE"
        )
        self.assertEqual(total_unidades, 9)

        # Cuando todos los ítems fueron asignados a waves, el pedido pasa a EN_WAVE
        self.assertEqual(order.status, OrderStatus.EN_WAVE)

    def test_asignacion_picker_best_fit(self):
        # Wave de 25 kg: debe elegir al picker chico (cap 30) en vez del mediano (cap 60)
        o1 = self._mk_order("PED_01", 5, self.p_pesado, 1)  # 20 kg
        o2 = self._mk_order("PED_02", 4, self.p_medio, 1)   # 5 kg  -> total 25 kg

        wm = WaveManager(max_pedidos=2, max_productos=10)
        wm.add_orders([o1, o2])

        pickers = [self.pk_grande, self.pk_medio, self.pk_chico]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual(len(waves), 1)
        self.assertEqual(waves[0].picker.picker_id, "PK_CHICO")

    def test_cola_de_espera_y_liberacion_de_picker(self):
        o1 = self._mk_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._mk_order("PED_02", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2])

        # Solo tenemos 1 picker disponible
        p1 = Picker("PK_SOLO", (0, 3), 50.0)
        waves = wm.generate_waves(pickers=[p1])

        self.assertEqual(len(waves), 2)
        # La primera wave (prioridad 5) recibe al picker
        self.assertIsNotNone(waves[0].picker)
        self.assertEqual(waves[0].picker.picker_id, "PK_SOLO")
        # La segunda wave queda en espera en la cola
        self.assertIsNone(waves[1].picker)
        self.assertIn(waves[1], wm.queue)

        # Iniciar la primera wave
        waves[0].start()
        self.assertEqual(waves[0].status, WaveStatus.EN_PROCESO)
        self.assertEqual(o1.status, OrderStatus.EN_PREPARACION)

        # Al completar la wave mediante complete_wave, se completa la wave,
        # se libera al picker y se reasigna la cola automáticamente
        wm.complete_wave(waves[0])
        self.assertEqual(waves[0].status, WaveStatus.COMPLETADA)
        self.assertEqual(o1.status, OrderStatus.PREPARADO)

        # Ahora la segunda wave ya tiene asignado al picker liberado
        self.assertIsNotNone(waves[1].picker)
        self.assertEqual(waves[1].picker.picker_id, "PK_SOLO")
        self.assertTrue(p1.is_busy)
        self.assertEqual(p1.assigned_wave_id, waves[1].wave_id)
        self.assertEqual(len(wm.queue), 0)

    def test_distancia_heuristica_agrupa_cercanos(self):
        # Crear un pequeño warehouse con dos racks separados
        wh = Warehouse("WH_DIST", 12, 10)
        wh.add_door(Door("D1", (5, 0), "OUTBOUND"))
        wh.add_dispatch_zone(DispatchZone("Z1", "D1", 4, 1, 3, 2, 500.0))
        r_cerca = Rack("R_CERCA", 1, 4, 2, 4)
        r_lejos = Rack("R_LEJOS", 9, 4, 2, 4)
        wh.add_rack(r_cerca)
        wh.add_rack(r_lejos)
        wh.add_aisle(Aisle("P_AMBOS", 0, 3, 12, 1, "AMBOS"))

        p_semilla = Product("P_SEM", "Semilla", "R_CERCA", [1, 4, 1], 10, 1.0)
        p_cerca = Product("P_CERCA", "Cerca", "R_CERCA", [2, 5, 1], 10, 1.0)
        p_lejos = Product("P_LEJOS", "Lejos", "R_LEJOS", [9, 5, 1], 10, 1.0)

        wh.add_product(p_semilla)
        wh.add_product(p_cerca)
        wh.add_product(p_lejos)

        graph = generate_graph(wh)

        # Semilla prio 5, los otros dos con igual prioridad (prio 3)
        o_semilla = self._mk_order("PED_SEM", 5, p_semilla, 1)
        o_lejos = self._mk_order("PED_LEJOS", 3, p_lejos, 1)
        o_cerca = self._mk_order("PED_CERCA", 3, p_cerca, 1)

        wm = WaveManager(warehouse=wh, graph=graph, max_pedidos=2, max_productos=10)
        wm.add_orders([o_semilla, o_lejos, o_cerca])

        waves = wm.generate_waves(pickers=[self.pk_grande])

        # En la primera wave (donde está PED_SEM) debe haberse elegido PED_CERCA por cercanía
        pedidos_w1 = [o.order_id for o in waves[0].orders]
        self.assertIn("PED_SEM", pedidos_w1)
        self.assertIn("PED_CERCA", pedidos_w1)
        self.assertNotIn("PED_LEJOS", pedidos_w1)


if __name__ == "__main__":
    unittest.main()
