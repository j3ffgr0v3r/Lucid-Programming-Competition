from copy import deepcopy
import unittest

from manager import Manager


class SpawnPriorityTests(unittest.TestCase):
    def setUp(self):
        self.view = {
            "turn": 1,
            "map": {"width": 9, "height": 9, "cells": [{"type": "empty"} for _ in range(81)]},
            "units": [self.worker("center", 4, 4), self.worker("north", 0, 0), self.worker("south", 8, 8)],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 1}}],
            "teamResources": {"ours": {"gold": 0, "iron": 28}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "test"}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    @staticmethod
    def worker(unit_id, x, y, ready=1):
        return {"unitId": unit_id, "teamId": "ours", "position": {"x": x, "y": y}, "readyOnTurn": ready,
                "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8}

    def test_spawns_as_many_as_affordable_at_successive_prices(self):
        original = deepcopy(self.snapshot)
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual([action["type"] for action in list(actions.values())[:2]], ["spawn", "spawn"])
        self.assertEqual(sum(action["type"] == "spawn" for action in actions.values()), 2)
        self.assertFalse(any(action["type"] == "build-base" for action in actions.values()))
        self.assertEqual(manager.next_bot_cost, 11)
        self.assertEqual(manager.calculate_actions(self.snapshot), actions)
        self.assertEqual(manager.next_bot_cost, 11)
        self.assertEqual(self.snapshot, original)

    def test_affordable_spawns_override_every_workers_other_task(self):
        self.view["teamResources"]["ours"]["iron"] = 56  # 11 + 17 + 28
        manager = Manager(self.snapshot, self.identity)
        self.assertTrue(all(action["type"] == "spawn" for action in manager.calculate_actions(self.snapshot).values()))

    def test_base_uses_only_iron_left_after_spawn_reservations(self):
        self.view["teamResources"]["ours"]["iron"] = 16  # spawn 11 leaves only 5
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(sum(action["type"] == "spawn" for action in actions.values()), 1)
        self.assertNotEqual(actions["center"]["type"], "build-base")
        self.view["teamResources"]["ours"]["iron"] = 17  # spawn 11 and build 6
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(next(iter(actions.values())), {"type": "spawn"})
        self.assertEqual(actions["center"], {"type": "build-base"})

    def test_cooldown_workers_are_not_selected_to_spawn(self):
        self.view["units"][1]["readyOnTurn"] = 4
        self.view["units"][2]["readyOnTurn"] = 4
        self.view["teamResources"]["ours"]["iron"] = 100
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(actions["center"], {"type": "spawn"})
        self.assertEqual(actions["north"], {"type": "pass"})
        self.assertEqual(actions["south"], {"type": "pass"})

    def test_confirmed_recruits_advance_price_failed_spawns_do_not(self):
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.view["teamResources"]["ours"]["iron"] = 10
        self.assertFalse(any(action["type"] == "spawn" for action in manager.calculate_actions(self.snapshot).values()))
        self.assertEqual(manager.next_bot_cost, 11)
        self.view["units"].append(self.worker("new", 0, 0))
        self.view["teamResources"]["ours"]["iron"] = 17
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.next_bot_cost, 17)
        self.assertEqual(sum(action["type"] == "spawn" for action in actions.values()), 1)

    def test_single_starting_worker_prioritizes_spawn_over_base(self):
        self.view["units"] = [self.worker("center", 5, 5)]
        self.view["teamResources"]["ours"]["iron"] = 6
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot), {"center": {"type": "spawn"}})


if __name__ == "__main__":
    unittest.main()
