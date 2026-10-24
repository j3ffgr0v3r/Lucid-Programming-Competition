import unittest

from manager import Manager


class TradeDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 0, "y": 0},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 3},
        }
        self.view = {
            "turn": 477,
            "map": {"width": 7, "height": 7, "cells": [{"type": "empty"} for _ in range(49)]},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "deadline", "maxTurns": 480}, "view": self.view}
        self.manager = Manager(self.snapshot, {"teamId": "ours", "displayName": "Test"})

    def step(self):
        action = self.manager.calculate_actions(self.snapshot)["worker"]
        inventory = self.worker["inventory"]
        if action["type"] == "trade":
            self.assertGreaterEqual(inventory["iron"], 3)
            inventory["iron"] -= 3
            inventory["gold"] += 1
        elif action["type"] == "deposit":
            self.assertEqual(self.worker["position"], {"x": 0, "y": 0})
            for resource in ("gold", "iron"):
                self.view["teamResources"]["ours"][resource] += inventory[resource]
                inventory[resource] = 0
        elif action["type"] == "move":
            delta = {
                "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
                "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
            }[action["direction"]]
            self.worker["position"]["x"] += delta[0]
            self.worker["position"]["y"] += delta[1]
        self.view["turn"] += 1
        return action["type"]

    def test_three_turns_at_home_convert_iron_to_banked_gold(self):
        self.assertEqual(self.step(), "trade")
        self.assertEqual(self.step(), "deposit")
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 1)

    def test_two_turns_still_allow_one_trade_and_deposit(self):
        self.view["turn"] = 478
        self.worker["inventory"] = {"gold": 2, "iron": 6}
        self.assertEqual(self.step(), "trade")
        self.assertEqual(self.step(), "deposit")
        self.assertEqual(self.view["teamResources"]["ours"], {"gold": 3, "iron": 3})

    def test_three_turns_allow_two_trades_then_final_deposit(self):
        self.worker["inventory"]["iron"] = 6
        self.assertEqual([self.step() for _ in range(3)], ["trade", "trade", "deposit"])
        self.assertEqual(self.view["teamResources"]["ours"], {"gold": 2, "iron": 0})

    def test_last_turn_protects_existing_gold(self):
        self.view["turn"] = 479
        self.worker["inventory"] = {"gold": 5, "iron": 3}
        self.assertEqual(self.step(), "deposit")
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 5)

    def test_returning_rover_trades_at_home_without_missing_deposit(self):
        self.view["turn"] = 476
        self.worker["position"] = {"x": 2, "y": 0}
        self.worker["inventory"] = {"gold": 2, "iron": 6}
        self.assertEqual([self.step() for _ in range(4)], ["move", "move", "trade", "deposit"])
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 3)


if __name__ == "__main__":
    unittest.main()
