from copy import deepcopy
import unittest
from unittest.mock import patch

from manager import Manager


class OreCoordinationTests(unittest.TestCase):
    def setUp(self):
        # These compact-map fixtures exercise construction behavior. Keep their
        # quotas explicit; production quota scaling is tested separately.
        quotas = patch.multiple("manager", BASE_TARGET_AREA=10, WORKER_TARGET_AREA=25)
        quotas.start()
        self.addCleanup(quotas.stop)
        self.view = {
            "turn": 1,
            "map": {"width": 9, "height": 9, "cells": [{"type": "empty"} for _ in range(81)]},
            "units": [self.worker("alpha", 4, 4), self.worker("beta", 4, 4)],
            "bases": [
                {"baseId": str(y), "teamId": "ours", "position": {"x": 0, "y": y}}
                for y in range(3)
            ],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "test"}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    @staticmethod
    def worker(name, x, y):
        return {"unitId": name, "teamId": "ours", "position": {"x": x, "y": y},
                "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0}}

    def ore(self, x, y, amount, resource="gold"):
        self.view["map"]["cells"][y * 9 + x] = {"type": resource, "amount": amount}

    def test_small_deposits_get_separate_miners_and_targets_stay_stable(self):
        self.ore(5, 4, 2)
        self.ore(4, 6, 8)
        original = deepcopy(self.snapshot)
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["alpha"].ore_target, (5, 4))
        self.assertEqual(manager.bots["beta"].ore_target, (4, 6))
        self.assertEqual(self.snapshot, original)
        self.view["turn"] += 1
        self.view["units"].insert(0, self.worker("aaa-new", 4, 4))
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["alpha"].ore_target, (5, 4))
        self.assertEqual(manager.bots["beta"].ore_target, (4, 6))
        self.assertIsNone(manager.bots["aaa-new"].ore_target)

    def test_large_deposit_can_support_multiple_miners(self):
        self.ore(5, 4, 12)
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual([bot.ore_target for bot in manager.bots.values()], [(5, 4), (5, 4)])

    def test_depleted_target_does_not_steal_another_rovers_existing_trip(self):
        self.ore(5, 4, 2)
        self.ore(4, 6, 8)
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.view["map"]["cells"][4 * 9 + 5] = {"type": "empty"}
        self.view["units"][0]["position"] = {"x": 5, "y": 4}
        self.view["units"][1]["position"] = {"x": 4, "y": 5}
        self.view["turn"] += 1
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["beta"].ore_target, (4, 6))
        self.assertIsNone(manager.bots["alpha"].ore_target)

    def test_reservations_use_remaining_capacity_and_refresh_after_banking(self):
        self.ore(5, 4, 3)
        self.view["units"][0]["inventory"]["iron"] = 7
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["beta"].ore_target, (5, 4))
        self.view["units"][0]["inventory"]["iron"] = 8
        self.view["turn"] += 1
        actions = manager.calculate_actions(self.snapshot)
        self.assertTrue(manager.bots["alpha"].ore_returning)
        self.assertEqual(actions["beta"]["type"], "move")
        self.assertEqual(manager.bots["beta"].ore_target, (5, 4))

    def test_rover_already_mining_reserves_before_new_arrivals(self):
        self.ore(5, 4, 2)
        self.ore(4, 6, 8)
        self.view["units"][1]["position"] = {"x": 5, "y": 4}
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(actions["beta"], {"type": "mine"})
        self.assertEqual(manager.bots["alpha"].ore_target, (4, 6))

    def test_construction_gatherers_share_deposit_reservations(self):
        self.view["bases"] = self.view["bases"][:1]
        self.view["units"][1]["position"] = {"x": 3, "y": 3}
        self.ore(4, 3, 2, "iron")
        self.ore(1, 0, 8, "iron")
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["alpha"].state, "FindAnyOreState")
        self.assertEqual(manager.bots["alpha"].ore_target, (4, 3))
        self.assertEqual(manager.bots["beta"].ore_target, (1, 0))


if __name__ == "__main__":
    unittest.main()
