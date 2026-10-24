from copy import deepcopy
import unittest

from map_state import MapState
from states.build_base import BuildBase


class MapStateTests(unittest.TestCase):
    def setUp(self):
        self.view = {
            "turn": 1,
            "map": {"width": 5, "height": 1, "cells": [{"type": "empty"} for _ in range(5)]},
            "bases": [{"baseId": "enemy", "teamId": "other", "position": {"x": 4, "y": 0}}],
            "units": [{"unitId": "bot", "teamId": "ours", "position": {"x": 0, "y": 0}, "readyOnTurn": 1}],
            "teamResources": {"ours": {"gold": 0, "iron": 6}},
            "highGoldArea": {"width": 3, "height": 1, "min": 12, "max": 18, "spawnPercent": 35},
        }

    def test_fog_preserves_terrain_and_bases_but_visible_changes_replace_them(self):
        memory = MapState(self.view)
        hidden = deepcopy(self.view)
        hidden["map"]["cells"] = [{"type": "hidden"} for _ in range(5)]
        hidden["bases"] = []
        memory.update(hidden)
        self.assertEqual(memory.map["cells"][1], {"type": "empty"})
        self.assertEqual(len(memory.bases), 1)
        hidden["map"]["cells"][1] = {"type": "gold", "amount": 5}
        memory.update(hidden)
        self.assertEqual(memory.map["cells"][1], {"type": "gold", "amount": 5})
        hidden["map"]["cells"][1] = {"type": "empty"}
        memory.update(hidden)
        self.assertEqual(memory.map["cells"][1], {"type": "empty"})

    def test_memory_does_not_alias_input_snapshots(self):
        memory = MapState(self.view)
        self.view["map"]["cells"][0]["type"] = "mountain"
        self.view["bases"][0]["position"]["x"] = 3
        self.assertEqual(memory.map["cells"][0]["type"], "empty")
        self.assertEqual(memory.bases[0]["position"]["x"], 4)
        memory.update(self.view)
        self.view["map"]["cells"][0]["type"] = "empty"
        self.view["bases"][0]["position"]["x"] = 2
        self.assertEqual(memory.map["cells"][0]["type"], "mountain")
        self.assertEqual(memory.bases[0]["position"]["x"], 3)
        self.assertEqual(len(memory.bases), 1)

    def test_routing_reuses_known_cells_and_remembers_enemy_base_obstacles(self):
        memory = MapState(self.view)
        hidden = deepcopy(self.view)
        hidden["map"]["cells"][1] = {"type": "hidden"}
        hidden["bases"] = []
        memory.update(hidden)
        state = BuildBase(memory.map)
        state.update(dict(hidden, map=memory.map, bases=memory.bases), "ours")
        distances, _ = state._routes((0, 0), {(4, 0)})
        self.assertEqual(distances[(3, 0)], 3)
        self.assertNotIn((4, 0), distances)

    def test_route_cache_reuses_results_and_refreshes_each_turn(self):
        state = BuildBase(self.view["map"])
        state.update(self.view, "ours")
        first = state._routes((0, 0), {(4, 0)})
        self.assertIs(state._routes((0, 0), {(4, 0)}), first)
        self.view["map"]["cells"][1] = {"type": "mountain"}
        state.update(self.view, "ours")
        second = state._routes((0, 0), {(4, 0)})
        self.assertIsNot(second, first)
        self.assertEqual(second[0][(3, 0)], 5)


if __name__ == "__main__":
    unittest.main()
