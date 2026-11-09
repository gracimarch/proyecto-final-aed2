import copy
import json
import unittest

from algorithms.graph_builder import generate_graph, generate_navigation_graph
from algorithms.routing import dispatch_access_cells
from models.order import Order, OrderItem
from models.product import Product
from models.simulation import Simulation
from models.wave import Wave, WaveStatus
from models.wave_manager import WaveManager
from models.warehouse import Warehouse


class TestNavigationGraph(unittest.TestCase):
    """El grafo de navegación no debe incluir callejones sin retorno."""

    def setUp(self):
        with open("scenarios/escenario_grande.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.wh = Warehouse.from_dict(self.data)
        self.full = generate_graph(self.wh)
        self.nav = generate_navigation_graph(self.wh)

    def test_pasillo_sin_retorno_queda_afuera(self):
        # PAS_VB00 es de sentido S y termina contra ZONA_D: se puede entrar
        # pero no volver. La SCC principal no debe incluirlo.
        for celda in [(0, 19), (0, 20), (1, 20), (2, 20), (3, 20), (3, 29)]:
            self.assertIn(celda, self.full.nodes())
            self.assertNotIn(celda, self.nav.nodes())

        # Las celdas que sí tienen retorno se conservan.
        self.assertIn((4, 19), self.nav.nodes())
        self.assertIn((5, 4), self.nav.nodes())

    def test_acceso_de_zona_no_usa_celdas_trampa(self):
        zona = next(z for z in self.wh.dispatch_zones if z.zone_id == "ZONA_D")
        celdas = set(dispatch_access_cells(zona, self.wh, self.nav))

        self.assertTrue(celdas)
        self.assertFalse(celdas & {(0, 19), (1, 20), (2, 20), (3, 20)})

    def test_picker_en_callejon_no_reintroduce_la_trampa(self):
        # Si un picker arranca dentro del pasillo sin retorno, su celda se
        # conserva como isla, pero la circulación principal no puede entrar.
        data = copy.deepcopy(self.data)
        data["pickers"][0]["posicion_inicial"] = {"x": 3, "y": 25}

        wh = Warehouse.from_dict(data)
        nav = generate_navigation_graph(wh)

        self.assertIn((3, 25), nav.nodes())
        self.assertIn((4, 19), nav.nodes())
        self.assertNotIn((3, 20), nav.nodes())

        # La isla queda desconectada: desde ella no se llega a la circulación
        # principal y las celdas de entrada al pasillo ya no son navegables.
        self.assertNotIn((4, 19), set(nav.bfs((3, 25))))
        self.assertNotIn((3, 26), nav.nodes())
        self.assertNotIn((3, 24), nav.nodes())

    def test_simulacion_solo_cercania_termina(self):
        # Regresión del bloqueo: WAVE10 quedaba sin picker porque PK_01
        # terminaba encerrado en (3,20) descargando en ZONA_D.
        manager = WaveManager.from_dict(self.data, self.wh)
        manager.generate_waves(estrategia_wave="solo_cercania")
        manager.assign_pickers()

        sim = Simulation(
            self.wh, manager, estrategia="cercania", buscador="bfs", max_ticks=3000
        )
        sim.run()

        self.assertIsNone(sim.error)
        for wave in manager.get_waves():
            self.assertEqual(wave.status, WaveStatus.COMPLETADA)


class TestCapacidadOperativa(unittest.TestCase):
    """
    Un picker aislado no debe agrandar las waves ni colgar la simulación.

    El picker de mayor capacidad (PK_01, 150 kg) se coloca a propósito en el
    pasillo sin retorno: los pickers que quedan en circulación cargan como
    máximo 120 kg.
    """

    def setUp(self):
        with open("scenarios/escenario_grande.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.data["pickers"][0]["posicion_inicial"] = {"x": 3, "y": 25}

    def _manager(self, estrategia_wave="solo_cercania"):
        wh = Warehouse.from_dict(self.data)
        manager = WaveManager.from_dict(self.data, wh)
        manager.generate_waves(estrategia_wave=estrategia_wave)
        manager.assign_pickers()
        return wh, manager

    def test_picker_aislado_no_cuenta_para_capacidad(self):
        _, manager = self._manager()

        aislados = [p.picker_id for p in manager.isolated_pickers()]
        self.assertEqual(aislados, ["PK_01"])
        self.assertEqual(manager._max_capacity(manager.pickers), 120.0)

    def test_waves_no_superan_la_capacidad_operativa(self):
        for estrategia in ("por_pedido", "por_cercania", "solo_cercania"):
            _, manager = self._manager(estrategia)
            tope = manager._max_capacity(manager.pickers)

            self.assertEqual(tope, 120.0)
            for wave in manager.get_waves():
                self.assertLessEqual(wave.total_weight(), tope)

    def test_simulacion_con_picker_aislado_termina(self):
        combinaciones = [
            ("por_pedido", "cercania", "bfs"),
            ("solo_cercania", "orden", "astar"),
        ]
        for onda, estrategia, buscador in combinaciones:
            wh, manager = self._manager(onda)
            sim = Simulation(
                wh, manager, estrategia=estrategia, buscador=buscador, max_ticks=3000
            )
            sim.run()

            self.assertIsNone(sim.error)
            for wave in manager.get_waves():
                self.assertEqual(wave.status, WaveStatus.COMPLETADA)

    def test_wave_guardada_demasiado_pesada_falla_rapido(self):
        # Aunque las waves nuevas respetan la capacidad operativa, un JSON
        # guardado puede traer una wave vieja que ya no entra en ningún picker.
        # La simulación debe cortar en el tick 0 con el motivo real.
        wh, manager = self._manager()

        producto = Product("P_TEST", "Pesado", "R1", [1, 4, 1], 10, 60.0)
        pedido = Order("PED_TEST", [OrderItem(producto, 3)], 5)
        wave = Wave("WAVE_X", 5, 10)
        wave.add_order(pedido)
        manager.waves.append(wave)
        manager.queue.append(wave)

        sim = Simulation(wh, manager, "cercania", "bfs", max_ticks=3000)
        sim.run()

        self.assertEqual(sim.tick, 0)
        self.assertIsNotNone(sim.error)
        self.assertIn("WAVE_X", sim.error)
        self.assertIn("120.00 kg", sim.error)
        self.assertIn("PK_01", sim.error)

    def test_sin_pickers_operativos_avisa_al_generar_waves(self):
        wh = Warehouse.from_dict(self.data)
        manager = WaveManager.from_dict(self.data, wh)
        for picker in manager.pickers:
            picker.posicion_actual = (999, 999)

        with self.assertRaises(ValueError) as contexto:
            manager.generate_waves(estrategia_wave="solo_cercania")

        self.assertIn("ninguno puede operar", str(contexto.exception))


if __name__ == "__main__":
    unittest.main()
