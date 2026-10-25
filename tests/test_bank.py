from copy import deepcopy
import unittest
from unittest.mock import patch

from bot import Bot
from manager import Manager
from map_state import MapState
from states.bank import Bank


class BankTests(unittest.TestCase):
    def setUp(self):
        self.view = {
            "turn": 1,
            "map": {"width": 5, "height": 1, "cells": [{"type": "empty"} for _ in range(5)]},
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "units": [{"unitId": "worker", "teamId": "ours", "position": {"x": 4, "y": 0},
                       "readyOnTurn": 1, "inventory": {"gold": 0, "iron": 8}, "inventoryCapacity": 8}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 1, "height": 1, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.bot = Bot("Worker", "worker", "ours", (4, 0))

    def test_constructs_from_map_memory_and_deposits_at_home(self):
        memory = MapState(self.view)
        bank = Bank(memory)
        self.assertIs(bank.map_state, memory)
        self.assertEqual(bank.next_action(self.bot), ({"x": 3, "y": 0}, {"type": "move", "direction": "west"}))
        self.bot.update_coordinates((0, 0))
        self.assertEqual(bank.next_action(self.bot), (None, {"type": "deposit"}))

    def test_remembered_base_survives_new_live_view(self):
        memory = MapState(self.view)
        bank = Bank(memory)
        hidden = deepcopy(self.view)
        hidden["bases"] = []
        hidden["map"]["cells"][0] = {"type": "hidden"}
        memory.update(hidden)
        bank.update(dict(hidden, map=memory.map, bases=memory.bases), "ours")
        self.assertIs(bank.map_state, memory)
        self.assertEqual(bank.next_action(self.bot)[1], {"type": "move", "direction": "west"})

    def test_direct_view_constructor_remains_supported(self):
        bank = Bank(self.view)
        self.assertEqual(bank.next_action(self.bot)[1], {"type": "move", "direction": "west"})

    def test_manager_ore_fallback_delegates_full_cargo_to_bank(self):
        self.view["map"]["cells"][2] = {"type": "hidden"}
        snapshot = {"match": {"matchId": "test"}, "view": self.view}
        manager = Manager(snapshot, {"teamId": "ours", "displayName": "Test"})
        manager.base_target = 2  # Keep this cargo-return test in construction.
        bank = manager.states["Bank"]
        with patch.object(bank, "next_action", wraps=bank.next_action) as request:
            actions = manager.calculate_actions(snapshot)
        request.assert_called_once_with(manager.bots["worker"])
        self.assertEqual(actions["worker"], {"type": "move", "direction": "west"})
        self.assertTrue(all(state.map_state is manager.map_state for state in manager._all_states))


if __name__ == "__main__":
    unittest.main()
