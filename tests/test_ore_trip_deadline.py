import unittest
from unittest.mock import patch

from manager import Manager


class OreTripDeadlineTests(unittest.TestCase):
    def setUp(self):
        # Exercise exact trip arithmetic independently of the configurable
        # safety margin, covered by the phase/ending integration tests.
        for name, value in (("ENDING_RETURN_BUFFER", 0), ("ENDING_MIN_TURNS", 1)):
            setting = patch("manager." + name, value)
            setting.start()
            self.addCleanup(setting.stop)
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 3, "y": 3},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0},
        }
        self.cells = [{"type": "empty"} for _ in range(49)]
        self.view = {
            "turn": 474, "map": {"width": 7, "height": 7, "cells": self.cells},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "trip", "maxTurns": 480}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    def ore(self, x, y, resource="gold", amount=4):
        self.cells[y * 7 + x] = {"type": resource, "amount": amount}

    def step(self, manager):
        action = manager.calculate_actions(self.snapshot)["worker"]
        inventory = self.worker["inventory"]
        if action["type"] == "move":
            dx, dy = {
                "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
                "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
            }[action["direction"]]
            self.worker["position"]["x"] += dx
            self.worker["position"]["y"] += dy
            cell = self.cells[self.worker["position"]["y"] * 7 + self.worker["position"]["x"]]
            self.assertNotEqual(cell["type"], "void")
            if cell["type"] in ("mountain", "crater"):
                self.worker["readyOnTurn"] = self.view["turn"] + 3
        elif action["type"] == "mine":
            cell = self.cells[self.worker["position"]["y"] * 7 + self.worker["position"]["x"]]
            self.assertGreater(cell["amount"], 0)
            self.assertLess(sum(inventory.values()), 8)
            inventory[cell["type"]] += 1
            cell["amount"] -= 1
        elif action["type"] == "trade":
            self.assertGreaterEqual(inventory["iron"], 3)
            inventory["iron"] -= 3
            inventory["gold"] += 1
        elif action["type"] == "deposit":
            self.assertTrue(any(base["position"] == self.worker["position"] for base in self.view["bases"]))
            for resource in ("gold", "iron"):
                self.view["teamResources"]["ours"][resource] += inventory[resource]
                inventory[resource] = 0
        self.view["turn"] += 1
        return action["type"]

    def finish(self, manager):
        actions = []
        while self.view["turn"] < 480:
            actions.append(self.step(manager))
        return actions

    def test_six_turn_trip_chooses_further_ore_with_shorter_return_and_banks_gold(self):
        self.ore(4, 3)  # Seven turns including returning and depositing.
        self.ore(1, 2)  # Six turns including returning and depositing.
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["worker"].ore_target, (1, 2))
        actions = self.finish(manager)
        self.assertEqual(actions.count("mine"), 1)
        self.assertEqual(actions[-1], "deposit")
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 1)

    def test_revalidates_existing_target_when_trip_no_longer_fits(self):
        self.view["turn"] = 470
        self.ore(4, 3)
        self.ore(1, 2)
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        # Simulate a previously selected trip; the new scoring prefers the
        # other deposit even before this trip becomes too long.
        manager.bots["worker"].ore_target = (4, 3)
        self.view["turn"] = 474
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager.bots["worker"].ore_target, (1, 2))

    def test_iron_batch_requires_mining_trading_and_deposit_time(self):
        self.worker["position"] = {"x": 1, "y": 0}
        self.ore(1, 0, "iron", 3)
        manager = Manager(self.snapshot, self.identity)
        actions = self.finish(manager)
        self.assertEqual(actions, ["mine", "mine", "mine", "move", "trade", "deposit"])
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 1)

    def test_one_turn_short_iron_trip_is_rejected(self):
        self.view["turn"] = 475
        self.worker["position"] = {"x": 1, "y": 0}
        self.ore(1, 0, "iron", 3)
        manager = Manager(self.snapshot, self.identity)
        self.assertNotEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "mine")
        self.assertIsNone(manager.bots["worker"].ore_target)

    def test_existing_iron_needs_only_one_more_pickup(self):
        self.view["turn"] = 476
        self.worker["position"] = {"x": 1, "y": 0}
        self.worker["inventory"]["iron"] = 2
        self.ore(1, 0, "iron", 1)
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(self.finish(manager), ["mine", "move", "trade", "deposit"])
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 1)

    def test_insufficient_iron_stock_or_cargo_room_does_not_start_trip(self):
        self.worker["position"] = {"x": 1, "y": 0}
        self.ore(1, 0, "iron", 2)
        manager = Manager(self.snapshot, self.identity)
        self.assertNotEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "mine")
        self.ore(1, 0, "iron", 4)
        self.worker["inventory"]["gold"] = 7
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertTrue(manager.bots["worker"].ore_returning)

    def test_return_estimate_includes_obstacle_cooldown_and_alternate_base(self):
        self.view["turn"] = 475
        self.worker["position"] = {"x": 2, "y": 0}
        for y in range(7):
            for x in range(7):
                self.cells[y * 7 + x] = {"type": "void"}
        self.cells[0] = {"type": "empty"}
        self.cells[1] = {"type": "mountain"}
        self.ore(2, 0)
        manager = Manager(self.snapshot, self.identity)
        # One mine + mountain entry/cooldown (3) + move home + deposit = 6.
        self.assertNotEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "mine")
        self.cells[3] = {"type": "empty"}
        self.view["bases"].append({"baseId": "near", "teamId": "ours", "position": {"x": 3, "y": 0}})
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "mine"})
        self.finish(manager)
        self.assertGreater(self.view["teamResources"]["ours"]["gold"], 0)

    def test_no_reachable_base_prevents_unbankable_mining(self):
        self.ore(3, 3)
        for x, y in ((1, 0), (0, 1), (1, 1)):
            self.cells[y * 7 + x] = {"type": "void"}
        manager = Manager(self.snapshot, self.identity)
        self.assertNotEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "mine")
        self.assertIsNone(manager.bots["worker"].ore_target)

    def test_opportunistic_mining_does_not_interrupt_profitable_trip_for_untradable_iron(self):
        self.view["turn"] = 470
        self.worker["position"] = {"x": 0, "y": 1}
        self.ore(0, 1, "iron", 1)
        self.ore(4, 4, "gold", 4)
        manager = Manager(self.snapshot, self.identity)
        action = manager.calculate_actions(self.snapshot)["worker"]
        self.assertEqual(action["type"], "move")
        self.assertEqual(manager.bots["worker"].ore_target, (4, 4))
        self.finish(manager)
        self.assertGreater(self.view["teamResources"]["ours"]["gold"], 0)


if __name__ == "__main__":
    unittest.main()
