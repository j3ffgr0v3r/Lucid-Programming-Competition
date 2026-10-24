from copy import deepcopy
import unittest
from unittest.mock import patch

import bot_template
from bot import Bot
from manager import Manager
from map_state import MapState
from states.find_any_ore import FindAnyOreState


class FinalChecks(unittest.TestCase):
    def setUp(self):
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 0, "y": 0},
            "readyOnTurn": 1, "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8,
        }
        self.view = {
            "turn": 380, "map": {"width": 7, "height": 7, "cells": [{"type": "empty"} for _ in range(49)]},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "one", "maxTurns": 480}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    def test_trade_collects_enough_iron_for_a_trade_instead_of_banking_one_kg(self):
        self.worker["position"] = {"x": 3, "y": 3}
        self.worker["inventory"] = {"gold": 0, "iron": 1}
        self.view["map"]["cells"][3 * 7 + 3] = {"type": "iron", "amount": 4}
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "mine"})
        self.worker["inventory"]["iron"] = 2
        self.view["turn"] += 1
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "mine"})
        self.worker["inventory"]["iron"] = 3
        self.view["turn"] += 1
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "trade", "from": "iron"})

    def test_final_turn_deposits_existing_gold_before_trading(self):
        self.view["turn"] = 479
        self.worker["inventory"] = {"gold": 5, "iron": 3}
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "deposit"})

    def test_returns_to_bank_in_time_instead_of_using_last_turns_to_trade(self):
        self.view["turn"] = 476
        self.worker["position"] = {"x": 2, "y": 0}
        self.worker["inventory"] = {"gold": 2, "iron": 6}
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")

    def test_revisits_unobserved_known_tiles_for_respawned_ore(self):
        self.view["turn"] = 1
        memory = MapState(self.view)
        later = deepcopy(self.view)
        later["turn"] = 50
        for index in range(49):
            if index % 7 + index // 7 > 3:
                later["map"]["cells"][index] = {"type": "hidden"}
        memory.update(later)
        state = FindAnyOreState(memory, {"x": 0, "y": 0, "width": 7, "height": 7})
        state.update(dict(later, map=memory.map), "ours")
        self.assertEqual(state.next_action(Bot("Worker", "worker", "ours", (0, 0)))["type"], "move")

    def test_callback_replaces_manager_for_a_new_match(self):
        with patch.object(bot_template, "manager", Manager(self.snapshot, self.identity), create=True):
            previous = bot_template.manager
            bot_template.calculate_actions(self.snapshot, self.identity)
            self.assertIs(bot_template.manager, previous)
            next_match = deepcopy(self.snapshot)
            next_match["match"]["matchId"] = "two"
            bot_template.calculate_actions(next_match, self.identity)
            self.assertEqual(bot_template.manager.match_id, "two")
            self.assertIsNot(bot_template.manager, previous)


if __name__ == "__main__":
    unittest.main()
