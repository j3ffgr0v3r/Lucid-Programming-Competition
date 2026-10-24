from copy import deepcopy
from importlib import import_module
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import ore_fallback
from manager import Manager


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.view = {
            "turn": 1,
            "map": {"width": 9, "height": 9, "cells": [{"type": "empty"} for _ in range(81)]},
            "units": [self.worker("center", 4, 4), self.worker("north", 0, 0), self.worker("south", 8, 8)],
            "bases": [self.base("home", 0, 1)],
            "teamResources": {"ours": {"gold": 0, "iron": 6}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "test"}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    @staticmethod
    def worker(unit_id, x, y):
        return {"unitId": unit_id, "teamId": "ours", "position": {"x": x, "y": y},
                "readyOnTurn": 1, "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8}

    @staticmethod
    def base(base_id, x, y, team="ours"):
        return {"baseId": base_id, "teamId": team, "position": {"x": x, "y": y}}

    def ore(self, x, y, resource):
        self.view["map"]["cells"][y * 9 + x] = {"type": resource, "amount": 4}

    def test_builder_counts_toward_two_center_bots_and_other_rovers_patrol(self):
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.assertEqual(actions["center"], {"type": "build-base"})
        self.assertEqual(manager.bots["center"].build_target, {"x": 4, "y": 4})
        self.assertEqual(manager.bots["north"].state, "FindIronState")
        self.assertEqual(manager.bots["south"].state, "PatrolOre")
        self.assertEqual(manager._center_ids, {"center", "north"})
        self.assertEqual(manager.states["PatrolOre"].resource, "iron")

    def test_builder_falls_back_to_nearest_any_ore_and_resumes_building(self):
        self.view["teamResources"]["ours"]["iron"] = 5
        self.ore(4, 3, "gold")
        self.ore(7, 7, "iron")
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(actions["center"], {"type": "move", "direction": "north"})
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.assertEqual(manager.bots["center"].build_target, {"x": 4, "y": 4})
        self.view["teamResources"]["ours"]["iron"] = 6
        self.assertEqual(manager.calculate_actions(self.snapshot)["center"], {"type": "build-base"})

    def test_after_three_friendly_bases_two_search_center_and_others_patrol_for_any_ore(self):
        self.view["bases"].extend([self.base("second", 4, 4), self.base("third", 5, 4)])
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(sum(bot.state == "FindAnyOreState" for bot in manager.bots.values()), 2)
        self.assertEqual(sum(bot.state == "PatrolOre" for bot in manager.bots.values()), 1)
        self.assertIsNone(manager.states["PatrolOre"].resource)
        hidden = deepcopy(self.snapshot)
        hidden["view"]["bases"] = []
        manager.calculate_actions(hidden)
        self.assertEqual(len(manager.map_state.bases), 3)
        self.assertEqual(sum(bot.state == "FindAnyOreState" for bot in manager.bots.values()), 2)

    def test_three_bases_redirect_ore_search_to_center_plus_three_tile_buffer(self):
        self.view["map"] = {"width": 20, "height": 20, "cells": [{"type": "empty"} for _ in range(400)]}
        self.view["highGoldArea"].update(width=4, height=4)
        self.view["bases"].extend([self.base("second", 8, 9), self.base("third", 11, 10)])
        self.view["map"]["cells"][1] = {"type": "gold", "amount": 5}
        self.view["map"]["cells"][9 * 20 + 9] = {"type": "gold", "amount": 5}
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.center_search_area, {"x": 5, "y": 5, "width": 10, "height": 10})
        self.assertEqual(actions["north"], {"type": "move", "direction": "east"})
        self.assertEqual(manager.bots["north"].state, "PatrolOre")
        self.assertEqual(manager._center_ids, {"center", "south"})

    def test_center_buffer_is_clipped_to_the_map(self):
        self.view["highGoldArea"].update(width=8, height=8)
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.center_search_area, {"x": 0, "y": 0, "width": 9, "height": 9})

    def test_builder_stays_assigned_until_unavailable_and_enemy_bases_do_not_count(self):
        self.view["bases"].extend([self.base("enemy-1", 8, 0, "enemy"), self.base("enemy-2", 8, 1, "enemy")])
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.view["units"][0]["position"] = {"x": 0, "y": 0}
        self.view["units"][1]["position"] = {"x": 4, "y": 4}
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.assertEqual(manager.bots["north"].state, "FindIronState")
        self.view["units"] = self.view["units"][1:]
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["north"].state, "BuildBase")

    def test_existing_regions_survive_spawning_and_new_rover_ids(self):
        self.view["teamResources"]["ours"]["iron"] = 0
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        original = {name: manager.bots[name].search_area_index for name in ("north", "south")}
        self.view["teamResources"]["ours"]["iron"] = 11
        self.assertEqual(manager.calculate_actions(self.snapshot)["north"]["type"], "spawn")
        self.view["units"].append(self.worker("aaa-new", 0, 0))
        self.view["teamResources"]["ours"]["iron"] = 0
        manager.calculate_actions(self.snapshot)
        for name, region in original.items():
            self.assertEqual(manager.bots[name].search_area_index, region)
        self.assertEqual(manager.bots["aaa-new"].state, "PatrolOre")
        self.assertEqual(manager._center_ids, {"center", "north"})

    def test_confirmed_second_base_starts_next_build_without_resetting_pending_attempts(self):
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.view["bases"].append(self.base("second", 4, 4))
        action = manager.calculate_actions(self.snapshot)["center"]
        self.assertEqual(action["type"], "move")
        self.assertNotEqual(manager.bots["center"].build_site, {"x": 4, "y": 4})

    def test_memory_is_used_by_all_state_instances_and_caches_are_shared(self):
        manager = Manager(self.snapshot, self.identity)
        instances = tuple(manager._all_states)
        hidden = deepcopy(self.snapshot)
        hidden["view"]["map"]["cells"][10] = {"type": "hidden"}
        manager.calculate_actions(hidden)
        for state in manager._all_states:
            self.assertIs(state.grid, manager.map_state.map)
            self.assertEqual(state.grid["cells"][10]["type"], "empty")
            self.assertIs(state._route_cache, manager.states["BuildBase"]._route_cache)
        manager.calculate_actions(hidden)
        self.assertEqual(tuple(manager._all_states), instances)

    def test_empty_team_and_cooldown_are_safe(self):
        self.view["units"][0]["readyOnTurn"] = 4
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["center"], {"type": "pass"})
        self.view["units"] = []
        self.assertEqual(manager.calculate_actions(self.snapshot), {})

    def test_iron_search_collects_gold_along_the_way_and_full_inventory_deposits(self):
        self.ore(0, 0, "gold")
        self.ore(1, 0, "iron")
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["north"], {"type": "mine"})
        self.view["units"][1]["position"] = {"x": 0, "y": 1}
        self.view["units"][1]["inventory"] = {"gold": 0, "iron": 8}
        self.assertEqual(manager.calculate_actions(self.snapshot)["north"], {"type": "deposit"})

    def test_teammate_ore_class_and_search_area_take_precedence(self):
        module = ModuleType("states.teammate_ore")

        class SearchArea(ore_fallback.SearchArea):
            pass

        class FindAnyOreState(ore_fallback.FindAnyOreState):
            def __init__(self, map_state, search_area):
                self.received_area = search_area
                super().__init__(map_state, search_area)

        FindAnyOreState.__module__ = module.__name__
        module.FindAnyOreState = FindAnyOreState
        module.SearchArea = SearchArea
        names = ["states.build_base", "states.spawn_bot", module.__name__]
        entries = [SimpleNamespace(name=name) for name in names]
        def load(name):
            return module if name == module.__name__ else import_module(name)

        with patch("manager.iter_modules", return_value=entries), patch("manager.import_module", side_effect=load):
            manager = Manager(self.snapshot, self.identity)
        self.assertIsInstance(manager.states["FindAnyOreState"], FindAnyOreState)
        self.assertIsInstance(manager.states["FindAnyOreState"].received_area, SearchArea)
        self.assertIs(manager.states["FindAnyOreState"].map_state, manager.map_state)
        self.assertTrue(all(isinstance(state, FindAnyOreState) for state in manager.ore_states["FindAnyOreState"]))


if __name__ == "__main__":
    unittest.main()
