import json
import unittest

from algorithms.graph_builder import generate_graph
from models.order import Order, OrderItem
from models.picker import Picker, PickerStatus
from models.product import Product
from models.simulation import Simulation
from models.warehouse import DispatchZone, Door, Rack, Warehouse
from models.wave import Wave, WaveStatus
from models.wave_manager import WaveManager


class TestSimulation(unittest.TestCase):
    """Pruebas unitarias para la simulación concurrente multi-picker y resolución de conflictos."""

    def setUp(self):
        with open("scenarios/escenario_basico.json", "r", encoding="utf-8") as f:
            self.data = json.load(f)
        self.wh = Warehouse.from_dict(self.data)
        self.wm = WaveManager.from_dict(self.data, self.wh)
        self.wm.generate_waves()

    def test_simulation_runs_to_completion(self):
        sim = Simulation(self.wh, self.wm, estrategia="cercania", buscador="bfs")
        frames = sim.run()

        self.assertIsNone(sim.error)
        self.assertGreater(len(frames), 0)

        # Todas las waves deben haber quedado completadas
        for wave in self.wm.get_waves():
            self.assertEqual(wave.status, WaveStatus.COMPLETADA)

        # Métricas válidas
        metr = sim.metrics()
        self.assertGreater(metr["ticks"], 0)
        self.assertGreater(metr["distancia_total"], 0)
        self.assertIn("esperas", metr)
        self.assertIn("desvios", metr)

    def test_no_vertex_collisions_in_any_frame(self):
        # Dos pickers nunca pueden ocupar la misma celda en el mismo frame (§3.6)
        sim = Simulation(self.wh, self.wm, estrategia="cercania", buscador="bfs")
        frames = sim.run()

        for frame in frames:
            posiciones = set()
            for p in frame["pickers"]:
                pos = (p["x"], p["y"])
                self.assertNotIn(
                    pos,
                    posiciones,
                    f"Colisión en celda {pos} en el tick {frame['tick']}",
                )
                posiciones.add(pos)

    def test_no_swap_collisions_between_consecutive_frames(self):
        # Dos pickers nunca pueden intercambiar celdas en el mismo tick (§3.6)
        sim = Simulation(self.wh, self.wm, estrategia="cercania", buscador="bfs")
        frames = sim.run()

        for i in range(len(frames) - 1):
            f_actual = frames[i]
            f_sig = frames[i + 1]

            pos_actual = {p["id"]: (p["x"], p["y"]) for p in f_actual["pickers"]}
            pos_sig = {p["id"]: (p["x"], p["y"]) for p in f_sig["pickers"]}

            ids = list(pos_actual.keys())
            for idx_a in range(len(ids)):
                for idx_b in range(idx_a + 1, len(ids)):
                    p_a = ids[idx_a]
                    p_b = ids[idx_b]

                    swap = (
                        pos_actual[p_a] == pos_sig[p_b]
                        and pos_actual[p_b] == pos_sig[p_a]
                        and pos_actual[p_a] != pos_actual[p_b]
                    )
                    self.assertFalse(
                        swap,
                        f"Swap ilegal entre {p_a} y {p_b} entre ticks {f_actual['tick']} y {f_sig['tick']}",
                    )

    def test_picker_unit_operations(self):
        p = Picker("PK_TEST", (1, 1), 50.0)
        self.assertEqual(p.status, PickerStatus.LIBRE)
        self.assertEqual(p.posicion_actual, (1, 1))

        # Asignar wave y empezar ruta
        p.assign_wave("W01")
        self.assertEqual(p.status, PickerStatus.ASIGNADO)
        p.start_route([(1, 1), (1, 2), (1, 3)])
        self.assertEqual(p.status, PickerStatus.EN_RECORRIDO)

        # Crear grafo simple para validar step
        wh_mini = Warehouse("WH_MINI", 5, 5)
        graph = generate_graph(wh_mini)

        nueva_pos = p.step(graph)
        self.assertEqual(nueva_pos, (1, 2))
        self.assertEqual(p.pasos, 1)

        # Picker.wait anota espera
        p.wait()
        self.assertEqual(p.esperas, 1)


if __name__ == "__main__":
    unittest.main()

