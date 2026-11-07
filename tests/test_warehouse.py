import json
import unittest

from algorithms.graph_builder import generate_graph
from models.picker import Picker
from models.product import Product
from models.warehouse import (
    Aisle,
    DispatchZone,
    Door,
    Rack,
    Warehouse,
)


class TestWarehouse(unittest.TestCase):
    """Pruebas unitarias para el modelo del Warehouse, validaciones físicas y generación del grafo."""

    def setUp(self):
        # Warehouse básico de 10x10
        self.wh = Warehouse("WH_TEST", 10, 10)
        self.door = Door("DOOR_1", (4, 0), "OUTBOUND")
        self.wh.add_door(self.door)
        self.zone = DispatchZone("ZONE_1", "DOOR_1", 3, 1, 3, 2, 500.0)
        self.wh.add_dispatch_zone(self.zone)

    def test_dimensions_positive(self):
        with self.assertRaises(ValueError):
            Warehouse("INVALID", 0, 10)
        with self.assertRaises(ValueError):
            Warehouse("INVALID", 10, -5)

    def test_rack_side_2_constraint(self):
        # Uno de los lados debe ser 2 (ancho=2 o alto=2)
        valid_rack_v = Rack("R_V", 1, 4, 2, 4)
        valid_rack_h = Rack("R_H", 4, 4, 4, 2)
        self.wh.add_rack(valid_rack_v)
        self.wh.add_rack(valid_rack_h)

        # Rack 3x3 no cumple la regla de lado 2
        invalid_rack = Rack("R_BAD", 1, 8, 3, 3)
        with self.assertRaises(ValueError):
            self.wh.add_rack(invalid_rack)

    def test_door_must_be_on_border(self):
        # Puerta en celda interior (1, 1) debe fallar
        bad_door = Door("DOOR_BAD", (1, 1), "OUTBOUND")
        with self.assertRaises(ValueError):
            self.wh.add_door(bad_door)

    def test_dispatch_zone_must_face_door(self):
        # Zona en (7, 7) está lejos de DOOR_1 en (4, 0)
        far_zone = DispatchZone("ZONE_FAR", "DOOR_1", 7, 7, 2, 2, 100.0)
        with self.assertRaises(ValueError):
            self.wh.add_dispatch_zone(far_zone)

    def test_overlap_detection(self):
        rack1 = Rack("R1", 1, 4, 2, 4)
        self.wh.add_rack(rack1)

        # Rack que se solapa con R1
        rack_overlap = Rack("R2", 2, 5, 2, 3)
        with self.assertRaises(ValueError):
            self.wh.add_rack(rack_overlap)

    def test_picker_must_be_on_aisle_cell(self):
        rack = Rack("R1", 1, 4, 2, 4)
        self.wh.add_rack(rack)

        # Picker ubicado sobre un rack
        bad_picker = Picker("PK_BAD", (1, 4), 100.0)
        with self.assertRaises(ValueError):
            self.wh.add_picker(bad_picker)

        # Picker ubicado en celda libre de pasillo
        good_picker = Picker("PK_OK", (0, 4), 100.0)
        self.wh.add_picker(good_picker)
        self.assertEqual(len(self.wh.pickers), 1)

    def test_product_in_rack_and_levels(self):
        rack = Rack("R1", 1, 4, 2, 4)
        self.wh.add_rack(rack)

        # Producto dentro del rack
        p1 = Product("P1", "Prod 1", "R1", [1, 4, 1], 10, 1.5)
        p2 = Product("P2", "Prod 2", "R1", [1, 4, 2], 5, 2.0)
        self.wh.add_product(p1)
        self.wh.add_product(p2)
        rack.add_product(p1.x, p1.y, p1.z, p1)
        rack.add_product(p2.x, p2.y, p2.z, p2)

        self.assertEqual(self.wh.products["P1"].z, 1)
        self.assertEqual(self.wh.products["P2"].z, 2)
        self.assertEqual(rack.total_slots, 2)

        # Producto fuera de las celdas del rack
        p_bad = Product("P_BAD", "Bad", "R1", [9, 9, 1], 1, 1.0)
        with self.assertRaises(ValueError):
            rack.add_product(p_bad.x, p_bad.y, p_bad.z, p_bad)

        # Nivel z < 1
        with self.assertRaises(ValueError):
            Product("P_Z0", "Z0", "R1", [1, 4, 0], 1, 1.0)

    def test_graph_builder_aisle_directions(self):
        # Crear un pasillo vertical N en x=0 de y=3 a y=6
        aisle_n = Aisle("PAS_N", 0, 3, 1, 4, "N")
        self.wh.add_aisle(aisle_n)

        graph = generate_graph(self.wh)

        # En sentido N:
        # Se puede avanzar hacia +y: (0, 3) -> (0, 4)
        self.assertTrue(graph.has_edge((0, 3), (0, 4)))
        # No se puede retroceder hacia -y: (0, 4) -> (0, 3)
        self.assertFalse(graph.has_edge((0, 4), (0, 3)))
        # Se permite movimiento lateral hacia +x si la celda es pasillo
        self.assertTrue(graph.has_edge((0, 3), (1, 3)))

    def test_scenario_serialization_roundtrip(self):
        with open("scenarios/escenario_basico.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        wh = Warehouse.from_dict(data)
        self.assertEqual(wh.ancho_x, 18)
        self.assertEqual(wh.largo_y, 16)
        self.assertEqual(len(wh.doors), 2)
        self.assertEqual(len(wh.dispatch_zones), 2)
        self.assertEqual(len(wh.racks), 3)
        self.assertEqual(len(wh.pickers), 2)
        self.assertEqual(len(wh.products), 8)

        data_exported = wh.to_dict()
        self.assertIn("warehouse", data_exported)
        self.assertIn("racks", data_exported["warehouse"])
        self.assertEqual(len(data_exported["warehouse"]["racks"]), 3)


if __name__ == "__main__":
    unittest.main()
