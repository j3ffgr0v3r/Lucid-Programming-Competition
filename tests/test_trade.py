from copy import deepcopy
import unittest
from unittest.mock import patch

from manager import Manager


class TradeTests(unittest.TestCase):
    def setUp(self):
        # Leave room to recruit on this small map when testing the time cutoff.
        quota = patch("manager.WORKER_TARGET_AREA", 25)
        quota.start()
        self.addCleanup(quota.stop)
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 0, "y": 0},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 6},
        }
        self.view = {
            "turn": 379,
            "map": {"width": 15, "height": 15, "cells": [{"type": "empty"} for _ in range(225)]},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 100}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "test", "maxTurns": 480}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    def test_exact_cutoff_disables_spawning_and_building(self):
        self.view["turn"] = 287
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "spawn"})
        self.view["turn"] = 288
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "trade", "from": "iron"})
        self.assertEqual(manager.bots["worker"].state, "Trade")
        self.view["turn"] = 479
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "deposit")

    def test_cutoff_uses_match_length_and_configurable_constant(self):
        self.snapshot["match"]["maxTurns"] = 300
        self.view["turn"] = 200
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "trade")
        with patch("manager.CONSTRUCTION_FRACTION", 0.75):
            manager = Manager(self.snapshot, self.identity)
            self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "spawn")
            self.view["turn"] = 225
            self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "trade")

    def test_trade_repeats_until_iron_converted_then_banks_and_searches_center(self):
        self.view["turn"] = 380
        manager = Manager(self.snapshot, self.identity)
        original = deepcopy(self.snapshot)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "trade")
        self.assertEqual(self.snapshot, original)
        self.worker["inventory"] = {"gold": 1, "iron": 3}
        self.view["turn"] += 1
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "trade")
        self.worker["inventory"] = {"gold": 2, "iron": 0}
        self.view["turn"] += 1
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "deposit")
        self.worker["inventory"] = {"gold": 0, "iron": 0}
        self.view["map"]["cells"][7 * 15 + 7] = {"type": "gold", "amount": 5}
        self.view["map"]["cells"][1] = {"type": "gold", "amount": 5}
        self.view["turn"] += 1
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "move", "direction": "south-east"})
        self.assertEqual(manager.bots["worker"].state, "Trade")

    def test_less_than_three_carried_iron_is_banked_not_invalidly_traded(self):
        self.view["turn"] = 380
        self.worker["inventory"] = {"gold": 1, "iron": 2}
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "deposit"})

    def test_all_rovers_switch_and_cooldown_rovers_wait(self):
        self.view["turn"] = 380
        other = deepcopy(self.worker)
        other.update(unitId="other", readyOnTurn=382)
        self.view["units"].append(other)
        manager = Manager(self.snapshot, self.identity)
        actions = manager.calculate_actions(self.snapshot)
        self.assertTrue(all(bot.state == "Trade" for bot in manager.bots.values()))
        self.assertEqual(actions["worker"]["type"], "trade")
        self.assertEqual(actions["other"], {"type": "pass"})

    def test_collects_full_gold_load_before_returning_and_depositing(self):
        self.view["turn"] = 380
        self.worker["position"] = {"x": 7, "y": 7}
        self.worker["inventory"] = {"gold": 1, "iron": 0}
        self.view["map"]["cells"][7 * 15 + 7] = {"type": "gold", "amount": 12}
        manager = Manager(self.snapshot, self.identity)
        for gold in range(1, 8):
            self.worker["inventory"]["gold"] = gold
            self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "mine"})
            self.view["turn"] += 1
        self.worker["inventory"]["gold"] = 8
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertTrue(manager.bots["worker"].ore_returning)
        self.worker["position"] = {"x": 0, "y": 0}
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "deposit"})
        self.worker["inventory"]["gold"] = 0
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertFalse(manager.bots["worker"].ore_returning)

    def test_partial_gold_returns_before_deadline_even_with_ore_underfoot(self):
        self.view["turn"] = 472  # Seven moves plus depositing consume all eight turns.
        self.worker["position"] = {"x": 7, "y": 7}
        self.worker["inventory"] = {"gold": 1, "iron": 0}
        self.view["map"]["cells"][7 * 15 + 7] = {"type": "gold", "amount": 12}
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertTrue(manager.bots["worker"].ore_returning)


if __name__ == "__main__":
    unittest.main()
