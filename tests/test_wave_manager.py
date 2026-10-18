import unittest
import json
from pathlib import Path

from models.product import Product
from models.order import Order, OrderItem, OrderStatus
from models.wave import Wave, WaveStatus
from models.warehouse import Warehouse, Picker
from models.wave_manager import WaveManager


class TestWaveManager(unittest.TestCase):
    """
    Suite de pruebas exhaustiva para WaveManager y Wave.
    Verifica los requisitos funcionales, la estrategia voraz determinista
    y la asignación óptima de pickers.
    """

    def setUp(self):
        """Crea productos y pickers de prueba reutilizables."""
        # Productos de diferentes pesos y volúmenes
        self.p_ligero = Product("P_LIGERO", "Producto Ligero", "R1", [3, 5, 1], 100, 1.0)
        self.p_medio = Product("P_MEDIO", "Producto Medio", "R1", [3, 5, 2], 100, 5.0)
        self.p_pesado = Product("P_PESADO", "Producto Pesado", "R1", [4, 7, 1], 100, 20.0)
        self.p_muy_pesado = Product("P_MUY_PESADO", "Producto Muy Pesado", "R2", [8, 6, 1], 100, 120.0)

        # Pickers con diferentes capacidades
        self.picker_pequeno = Picker("PK_SMALL", (0, 3), 30.0)
        self.picker_mediano = Picker("PK_MED", (5, 3), 50.0)
        self.picker_grande = Picker("PK_LARGE", (10, 3), 100.0)

    def _create_order(self, order_id: str, prioridad: int, product: Product, cantidad: int) -> Order:
        """Helper para crear rápidamente pedidos de prueba."""
        items = [OrderItem(product, cantidad)]
        return Order(order_id, items, prioridad)

    # 1. Los pedidos se consideran por prioridad descendente
    def test_pedidos_prioridad_descendente(self):
        o1 = self._create_order("PED_BAJA", 1, self.p_ligero, 1)
        o2 = self._create_order("PED_MEDIA", 3, self.p_ligero, 1)
        o3 = self._create_order("PED_ALTA", 5, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2, o3])

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0), Picker("PK3", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual(len(waves), 3)
        self.assertEqual(waves[0].orders[0].order_id, "PED_ALTA")
        self.assertEqual(waves[1].orders[0].order_id, "PED_MEDIA")
        self.assertEqual(waves[2].orders[0].order_id, "PED_BAJA")

    # 2. Los empates de prioridad se resuelven determinísticamente
    def test_desempate_determinista(self):
        o_c = self._create_order("PED_C", 4, self.p_ligero, 1)
        o_a = self._create_order("PED_A", 4, self.p_ligero, 1)
        o_b = self._create_order("PED_B", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        # Se ingresan en orden arbitrario (C, A, B)
        wm.add_orders([o_c, o_a, o_b])

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0), Picker("PK3", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual([w.orders[0].order_id for w in waves], ["PED_A", "PED_B", "PED_C"])

    # 3. Un pedido que no entra por peso no impide incorporar uno posterior de menor prioridad que sí entra
    def test_pedido_que_no_entra_por_peso_permite_otros(self):
        # Picker con capacidad 30 kg
        picker = Picker("PK_30", (0, 0), 30.0)

        # o_alta: prioridad 5, peso 20 kg
        o_alta = self._create_order("PED_ALTA", 5, self.p_pesado, 1)  # 20 kg
        # o_media: prioridad 4, peso 20 kg -> sumaría 40 kg, supera los 30 kg provisionales
        o_media = self._create_order("PED_MEDIA", 4, self.p_pesado, 1) # 20 kg
        # o_baja: prioridad 2, peso 5 kg -> sumaría 25 kg, entra
        o_baja = self._create_order("PED_BAJA", 2, self.p_medio, 1)    # 5 kg

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o_alta, o_media, o_baja])

        waves = wm.generate_waves(pickers=[picker])

        self.assertEqual(len(waves), 1)
        wave_orders = [o.order_id for o in waves[0].orders]
        self.assertIn("PED_ALTA", wave_orders)
        self.assertIn("PED_BAJA", wave_orders)
        self.assertNotIn("PED_MEDIA", wave_orders)
        self.assertEqual(o_media.status, OrderStatus.PENDIENTE)

    # 4. No se supera el máximo de pedidos por wave
    def test_no_supera_max_pedidos(self):
        pedidos = [self._create_order(f"PED_{i:02d}", 3, self.p_ligero, 1) for i in range(7)]
        wm = WaveManager(max_pedidos=3, max_productos=20)
        wm.add_orders(pedidos)

        pickers = [Picker(f"PK_{i}", (0, 0), 100.0) for i in range(5)]
        waves = wm.generate_waves(pickers=pickers)

        for w in waves:
            self.assertLessEqual(w.current_pedidos(), 3)
        self.assertEqual(len(waves[0].orders), 3)
        self.assertEqual(len(waves[1].orders), 3)
        self.assertEqual(len(waves[2].orders), 1)

    # 5. No se supera el máximo de productos por wave
    def test_no_supera_max_productos(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 4)
        o2 = self._create_order("PED_02", 4, self.p_ligero, 4)
        o3 = self._create_order("PED_03", 3, self.p_ligero, 3) # Si entra, sumaría 11 > 10
        o4 = self._create_order("PED_04", 2, self.p_ligero, 2) # Suma 4 + 4 + 2 = 10, entra

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2, o3, o4])

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        first_wave_orders = [o.order_id for o in waves[0].orders]
        self.assertIn("PED_01", first_wave_orders)
        self.assertIn("PED_02", first_wave_orders)
        self.assertIn("PED_04", first_wave_orders)
        self.assertNotIn("PED_03", first_wave_orders)
        self.assertLessEqual(waves[0].current_unidades(), 10)

    # 6. Ningún pedido se divide entre varias waves
    def test_pedido_indivisible(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 6)
        o2 = self._create_order("PED_02", 4, self.p_ligero, 5)

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2])

        pickers = [Picker("PK1", (0, 0), 100.0), Picker("PK2", (0, 0), 100.0)]
        waves = wm.generate_waves(pickers=pickers)

        self.assertEqual(len(waves), 2)
        self.assertEqual(len(waves[0].orders), 1)
        self.assertEqual(waves[0].orders[0].total_unidades(), 6)
        self.assertEqual(len(waves[1].orders), 1)
        self.assertEqual(waves[1].orders[0].total_unidades(), 5)

    # 7. El peso total de una wave nunca supera la capacidad del picker asignado
    def test_peso_total_no_supera_capacidad_picker(self):
        o1 = self._create_order("PED_01", 5, self.p_medio, 5) # 25 kg
        o2 = self._create_order("PED_02", 4, self.p_medio, 4) # 20 kg

        wm = WaveManager(max_pedidos=5, max_productos=20)
        wm.add_orders([o1, o2])

        picker_50 = Picker("PK_50", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[picker_50])

        self.assertEqual(len(waves), 1)
        self.assertLessEqual(waves[0].peso_total(), waves[0].picker.capacidad_carga_kg)
        self.assertEqual(waves[0].peso_total(), 45.0)

    # 8. Cada picker se asigna como máximo a una wave
    def test_picker_asignado_a_lo_sumo_a_una_wave(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._create_order("PED_02", 4, self.p_ligero, 1)
        o3 = self._create_order("PED_03", 3, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2, o3])

        # Solo 2 pickers disponibles para 3 waves necesarias
        p1 = Picker("PK_A", (0, 0), 50.0)
        p2 = Picker("PK_B", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[p1, p2])

        self.assertEqual(len(waves), 2)
        assigned_picker_ids = [w.picker.picker_id for w in waves]
        self.assertEqual(len(set(assigned_picker_ids)), 2)
        self.assertTrue(p1.is_busy)
        self.assertTrue(p2.is_busy)
        self.assertEqual(len(wm.get_unassigned_waves()), 1)

    # 9. Se prefiere el picker de menor capacidad suficiente
    def test_prefiere_picker_menor_capacidad_suficiente(self):
        # Pedido de peso total = 25 kg
        o1 = self._create_order("PED_01", 5, self.p_medio, 5) # 25 kg

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1])

        # Tres pickers: 30kg, 50kg, 100kg
        p30 = Picker("PK_30", (0, 0), 30.0)
        p50 = Picker("PK_50", (0, 0), 50.0)
        p100 = Picker("PK_100", (0, 0), 100.0)

        waves = wm.generate_waves(pickers=[p100, p50, p30]) # Pasados desordenados

        self.assertEqual(len(waves), 1)
        # Debe elegir PK_30 porque es el menor capaz de cargar 25 kg
        self.assertEqual(waves[0].picker.picker_id, "PK_30")
        self.assertFalse(p50.is_busy)
        self.assertFalse(p100.is_busy)

    # 10. Los pedidos que no entran en una wave pueden incorporarse a waves posteriores
    def test_pedidos_no_incorporados_entran_en_waves_posteriores(self):
        o1 = self._create_order("PED_01", 5, self.p_medio, 2) # 10 kg
        o2 = self._create_order("PED_02", 4, self.p_medio, 2) # 10 kg
        o3 = self._create_order("PED_03", 3, self.p_medio, 2) # 10 kg

        # Capacidad max_pedidos = 2
        wm = WaveManager(max_pedidos=2, max_productos=10)
        wm.add_orders([o1, o2, o3])

        p1 = Picker("PK_1", (0, 0), 50.0)
        p2 = Picker("PK_2", (0, 0), 50.0)
        waves = wm.generate_waves(pickers=[p1, p2])

        self.assertEqual(len(waves), 2)
        self.assertEqual([o.order_id for o in waves[0].orders], ["PED_01", "PED_02"])
        self.assertEqual([o.order_id for o in waves[1].orders], ["PED_03"])

    # 11. Pedidos individuales imposibles se manejan sin bucles infinitos ni pérdida silenciosa
    def test_pedidos_imposibles_se_manejan_explicitamente(self):
        # o_imposible_unidades: 25 unidades > max_productos (20)
        o_imposible_unidades = self._create_order("PED_EXCESO_U", 5, self.p_ligero, 25)
        # o_imposible_peso: 120 kg > capacidad del picker más capaz (100 kg)
        o_imposible_peso = self._create_order("PED_EXCESO_P", 5, self.p_muy_pesado, 1)
        # o_normal: entra perfectamente
        o_normal = self._create_order("PED_OK", 3, self.p_ligero, 2)

        wm = WaveManager(max_pedidos=5, max_productos=20)
        wm.add_orders([o_imposible_unidades, o_imposible_peso, o_normal])

        picker_100 = Picker("PK_100", (0, 0), 100.0)
        waves = wm.generate_waves(pickers=[picker_100])

        self.assertEqual(len(waves), 1)
        self.assertEqual(waves[0].orders[0].order_id, "PED_OK")

        # Verificar reporte explícito de inasimilables
        unproc = wm.get_unprocessable_orders()
        self.assertEqual(len(unproc), 2)
        unproc_ids = [o.order_id for o, reason in unproc]
        self.assertIn("PED_EXCESO_U", unproc_ids)
        self.assertIn("PED_EXCESO_P", unproc_ids)
        # Siguen estando en estado PENDIENTE, no desaparecieron en silencio
        self.assertEqual(o_imposible_unidades.status, OrderStatus.PENDIENTE)
        self.assertEqual(o_imposible_peso.status, OrderStatus.PENDIENTE)

    # 12. Pedidos ya asignados no se vuelven a incorporar
    def test_pedidos_ya_asignados_no_se_reincorporan(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._create_order("PED_02", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1, o2])

        p1 = Picker("PK_1", (0, 0), 50.0)
        waves_1 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_1), 1)

        # En una segunda ejecución, los pedidos ya están EN_WAVE
        p2 = Picker("PK_2", (0, 0), 50.0)
        waves_2 = wm.generate_waves(pickers=[p2])
        self.assertEqual(len(waves_2), 0)

    # 13. Ciclo de vida completo de la Wave con Picker (start y complete)
    def test_ciclo_de_vida_wave_con_picker(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 2)
        wave = Wave("W1", max_pedidos=3, max_productos=10)
        wave.add_order(o1)

        # No se puede iniciar sin picker
        with self.assertRaises(ValueError):
            wave.start()

        picker = Picker("PK1", (0, 0), 50.0)
        wave.assign_picker(picker)
        self.assertTrue(picker.is_busy)

        # Iniciar preparación
        wave.start()
        self.assertEqual(wave.status, WaveStatus.EN_PROCESO)
        self.assertEqual(o1.status, OrderStatus.EN_PREPARACION)

        # Completar preparación
        wave.complete()
        self.assertEqual(wave.status, WaveStatus.COMPLETADA)
        self.assertEqual(o1.status, OrderStatus.PREPARADO)
        self.assertFalse(picker.is_busy)  # Picker liberado

    # 14. Integración completa con escenario_basico.json
    def test_integracion_escenario_basico(self):
        escenario_path = Path(__file__).resolve().parent.parent / "scenarios" / "escenario_basico.json"
        with open(escenario_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        wh = Warehouse.from_dict(data)
        orders = [Order.from_dict(p, wh.products) for p in data.get("pedidos", [])]

        wm = WaveManager(warehouse=wh, orders=orders)
        waves = wm.generate_waves()

        self.assertEqual(len(waves), 1)
        self.assertEqual(len(waves[0].orders), 3)
        self.assertIsNotNone(waves[0].picker)
        # El picker de 100 kg (PK_02) debe ser preferido sobre el de 150 kg (PK_01)
        self.assertEqual(waves[0].picker.picker_id, "PK_02")
        self.assertTrue(waves[0].picker.is_busy)
        self.assertFalse(wh.pickers[0].is_busy) # PK_01 quedó libre

    # 15. Desempate determinista entre pickers con igual capacidad
    def test_desempate_pickers_misma_capacidad(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 1)
        wm = WaveManager(max_pedidos=5, max_productos=10)
        wm.add_orders([o1])

        p_z = Picker("PK_Z", (0, 0), 50.0)
        p_a = Picker("PK_A", (0, 0), 50.0)
        # Pasados en orden Z, A
        waves = wm.generate_waves(pickers=[p_z, p_a])
        self.assertEqual(len(waves), 1)
        # Debe elegir determinísticamente PK_A
        self.assertEqual(waves[0].picker.picker_id, "PK_A")

    # 16. Reasignación de picker luego de completar una wave previa
    def test_reutilizacion_picker_tras_completar_wave(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 1)
        o2 = self._create_order("PED_02", 4, self.p_ligero, 1)

        wm = WaveManager(max_pedidos=1, max_productos=10)
        wm.add_orders([o1, o2])

        p1 = Picker("PK_1", (0, 0), 50.0)
        # Solo hay un picker, por ende solo se genera 1 wave con picker
        waves_1 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_1), 1)
        self.assertEqual(waves_1[0].orders[0].order_id, "PED_01")
        self.assertTrue(p1.is_busy)

        # Se prepara y completa la primera wave
        waves_1[0].start()
        waves_1[0].complete()
        self.assertFalse(p1.is_busy) # Picker liberado

        # Ahora el picker liberado puede atender la siguiente wave con el pedido restante
        waves_2 = wm.generate_waves(pickers=[p1])
        self.assertEqual(len(waves_2), 1)
        self.assertEqual(waves_2[0].orders[0].order_id, "PED_02")
        self.assertEqual(waves_2[0].picker.picker_id, "PK_1")

    # 17. Serialización y reconstrucción de Wave con Picker
    def test_serializacion_wave_con_picker(self):
        o1 = self._create_order("PED_01", 5, self.p_ligero, 2)
        wave = Wave("W_SERIAL", max_pedidos=3, max_productos=10)
        wave.add_order(o1)
        pk = Picker("PK_TEST", (1, 1), 60.0)
        wave.assign_picker(pk)

        data = wave.to_dict()
        self.assertEqual(data["picker_id"], "PK_TEST")
        self.assertEqual(data["order_ids"], ["PED_01"])

        order_registry = {"PED_01": o1}
        picker_registry = {"PK_TEST": pk}
        reconstructed = Wave.from_dict(data, order_registry, picker_registry)
        self.assertEqual(reconstructed.wave_id, "W_SERIAL")
        self.assertEqual(reconstructed.picker.picker_id, "PK_TEST")
        self.assertEqual(reconstructed.orders[0].order_id, "PED_01")
        self.assertEqual(reconstructed.peso_total(), wave.peso_total())


if __name__ == "__main__":
    unittest.main()
