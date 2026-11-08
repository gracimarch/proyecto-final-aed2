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

    def test_paradas_pendientes_se_actualizan_al_recoger(self):
        """
        El backend debe avisar qué paradas siguen pendientes.

        Regresión: PK_02 recoge la Impresora Láser en (12, 8) y más tarde su
        recorrido vuelve a pasar por esa celda como tránsito. El frontend
        conservaba la parada vieja y dibujaba el círculo otra vez.
        """
        sim = Simulation(self.wh, self.wm, estrategia="cercania", buscador="bfs")
        frames = sim.run()
        self.assertIsNone(sim.error)

        pendientes = {}
        recogio_p006 = False
        volvio_a_pasar = False

        for frame in frames:
            for evento in frame["eventos"]:
                picker_id = evento.get("picker")
                if evento["tipo"] == "ruta":
                    self.assertIn("paradas", evento)
                    pendientes[picker_id] = {
                        tuple(parada["celda"]) for parada in evento["paradas"]
                    }
                elif evento["tipo"] == "parada_recogida":
                    self.assertIn("paradas", evento)
                    celda = tuple(evento["celda"])
                    pendientes[picker_id] = {
                        tuple(parada["celda"]) for parada in evento["paradas"]
                    }
                    # La parada consumida no puede seguir anunciada.
                    self.assertNotIn(celda, pendientes[picker_id])
                    if (picker_id, celda) == ("PK_02", (12, 8)):
                        recogio_p006 = True

            picker = next(p for p in frame["pickers"] if p["id"] == "PK_02")
            if (picker["x"], picker["y"]) == (12, 8) and frame["tick"] > 9:
                volvio_a_pasar = True
            if recogio_p006:
                self.assertNotIn(
                    (12, 8),
                    pendientes.get("PK_02", set()),
                    f"PK_02 vuelve a pasar por (12, 8) en el tick "
                    f"{frame['tick']} y todavía figura como parada pendiente",
                )

        self.assertTrue(recogio_p006)
        self.assertTrue(volvio_a_pasar)

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


class TestChoquesEnTodosLosEscenarios(unittest.TestCase):
    """
    §3.6 en todos los escenarios: nunca dos pickers en la misma celda, nunca
    un intercambio de celdas y nunca un paso que no sea una arista del grafo
    (respeta los sentidos). Antes solo se probaba escenario_basico, donde no
    aparecían los choques al recoger.
    """

    ESCENARIOS = [
        "scenarios/escenario_basico.json",
        "scenarios/escenario_cercania.json",
        "scenarios/escenario_cuello_de_botella.json",
        "scenarios/escenario_despacho_multiple.json",
        "scenarios/escenario_niveles_z_y_sentidos.json",
    ]

    def _correr(self, data, estrategia_wave, recorrido):
        wh = Warehouse.from_dict(data)
        wm = WaveManager.from_dict(data, wh)
        wm.generate_waves(estrategia_wave=estrategia_wave)
        sim = Simulation(wh, wm, estrategia=recorrido, buscador="bfs")
        frames = sim.run()
        return sim, wm, frames

    def _revisar(self, sim, frames, nombre):
        anterior = None
        for frame in frames:
            pos = {p["id"]: (p["x"], p["y"]) for p in frame["pickers"]}
            self.assertEqual(
                len(set(pos.values())), len(pos),
                f"{nombre}: dos pickers en la misma celda en el tick {frame['tick']}",
            )
            if anterior is not None:
                for a in pos:
                    if anterior[a] != pos[a]:
                        self.assertTrue(
                            sim.graph.has_edge(anterior[a], pos[a]),
                            f"{nombre}: {a} saltó de {anterior[a]} a {pos[a]} en el tick {frame['tick']}",
                        )
                    for b in pos:
                        if a < b:
                            self.assertFalse(
                                anterior[a] == pos[b] and anterior[b] == pos[a],
                                f"{nombre}: {a} y {b} se cruzaron en el tick {frame['tick']}",
                            )
            anterior = pos

    def test_sin_choques_ni_saltos(self):
        for ruta in self.ESCENARIOS:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            for estrategia_wave in ("por_pedido", "por_cercania", "solo_cercania"):
                for recorrido in ("cercania", "orden"):
                    nombre = f"{ruta} {estrategia_wave} {recorrido}"
                    with self.subTest(nombre):
                        sim, wm, frames = self._correr(data, estrategia_wave, recorrido)
                        self.assertIsNone(sim.error, nombre)
                        self._revisar(sim, frames, nombre)

    def _pickers(self, posiciones):
        pickers = []
        for i, (x, y, cap) in enumerate(posiciones):
            pickers.append({"id": f"PK{i}", "posicion_inicial": {"x": x, "y": y},
                            "capacidad_carga_kg": cap})
        return pickers

    def test_cuello_de_botella_frente_a_frente_no_se_traba(self):
        # Tres pickers con tarea en un pasillo de una celda: dos van hacia el
        # oeste y uno sale de una celda de un solo sentido hacia el este.
        # Antes el while de choques giraba hasta el tope y nadie se movía.
        with open("scenarios/escenario_cuello_de_botella.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        data["pickers"] = self._pickers([(13, 7, 80.0), (7, 9, 80.0), (0, 9, 300.0)])
        sim, wm, frames = self._correr(data, "por_pedido", "cercania")
        self.assertIsNone(sim.error)
        for wave in wm.get_waves():
            self.assertEqual(wave.status, WaveStatus.COMPLETADA)
        self._revisar(sim, frames, "cuello_de_botella con 3 pickers")

    def test_picker_que_espera_no_se_estaciona_atravesando_a_otro(self):
        # Un picker que terminó su parte esperaba en la celda de descarga y su
        # plan de estacionamiento pasaba a través del compañero que venía a
        # descargar: iban y venían para siempre.
        with open("scenarios/escenario_niveles_z_y_sentidos.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        data["pickers"] = self._pickers([
            (2, 14, 300.0), (7, 7, 80.0), (12, 15, 150.0), (0, 12, 300.0), (1, 2, 80.0),
        ])
        sim, wm, frames = self._correr(data, "por_pedido", "cercania")
        self.assertIsNone(sim.error)
        for wave in wm.get_waves():
            self.assertEqual(wave.status, WaveStatus.COMPLETADA)
        self._revisar(sim, frames, "niveles_z con 5 pickers")


if __name__ == "__main__":
    unittest.main()

