from copy import deepcopy
import unittest
from unittest.mock import patch

from manager import Manager


class SpawnPriorityTests(unittest.TestCase):
    def setUp(self):
        # These compact-map fixtures exercise construction behavior. Keep their
        # quotas explicit; production quota scaling is tested separately.
        quotas = patch.multiple("manager", BASE_TARGET_AREA=10, WORKER_TARGET_AREA=25)
        quotas.start()
        self.addCleanup(quotas.stop)
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

    def test_base_reservation_and_worker_quota_limit_spawns(self):
        original = deepcopy(self.snapshot)
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(next(iter(actions.values())), {"type": "spawn"})
        self.assertEqual(sum(a["type"] == "spawn" for a in actions.values()), 1)
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.assertEqual(manager.worker_target, 4)
        self.assertEqual(manager.next_bot_cost, 11)
        self.assertEqual(manager.calculate_actions(self.snapshot), actions)
        self.assertEqual(manager.next_bot_cost, 11)
        self.assertEqual(self.snapshot, original)

    def test_successive_prices_respect_reserved_base_funds(self):
        self.view["teamResources"]["ours"]["iron"] = 34  # Base 6 + recruits 11 + 17.
        manager = Manager(self.snapshot, self.identity)
        manager.worker_target = 10
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(sum(a["type"] == "spawn" for a in actions.values()), 2)
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.view["teamResources"]["ours"]["iron"] = 33
        self.assertEqual(sum(a["type"] == "spawn" for a in manager.calculate_actions(self.snapshot).values()), 1)

    def test_base_funding_survives_spawning(self):
        self.view["teamResources"]["ours"]["iron"] = 16
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertFalse(any(a["type"] == "spawn" for a in actions.values()))
        self.assertEqual(manager.bots["center"].state, "BuildBase")
        self.view["units"][0]["position"] = manager.bots["center"].build_target.copy()
        self.view["teamResources"]["ours"]["iron"] = 17
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(next(iter(actions.values())), {"type": "spawn"})
        self.assertEqual(actions["center"], {"type": "build-base"})

    def test_cooldown_workers_are_not_selected_to_spawn(self):
        self.view["units"][0]["readyOnTurn"] = 4
        self.view["units"][1]["readyOnTurn"] = 4
        self.view["teamResources"]["ours"]["iron"] = 100
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(actions["south"], {"type": "spawn"})
        self.assertEqual(actions["north"], {"type": "pass"})
        self.assertEqual(actions["center"], {"type": "pass"})

    def test_confirmed_recruits_advance_price_failed_spawns_do_not(self):
        manager = Manager(self.snapshot, self.identity)
        manager.worker_target = 10
        manager.calculate_actions(self.snapshot)
        self.view["teamResources"]["ours"]["iron"] = 10
        self.assertFalse(any(a["type"] == "spawn" for a in manager.calculate_actions(self.snapshot).values()))
        self.assertEqual(manager.next_bot_cost, 11)
        self.view["units"].append(self.worker("new", 0, 0))
        self.view["teamResources"]["ours"]["iron"] = 23  # Base 6 + next recruit 17.
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.next_bot_cost, 17)
        self.assertEqual(sum(a["type"] == "spawn" for a in actions.values()), 1)

    def test_single_starting_worker_prioritizes_spawn_over_base(self):
        self.view["units"] = [self.worker("center", 5, 5)]
        self.view["teamResources"]["ours"]["iron"] = 6
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot), {"center": {"type": "spawn"}})


if __name__ == "__main__":
    unittest.main()
