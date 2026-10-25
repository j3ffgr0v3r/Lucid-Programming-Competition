import unittest

from bot import Bot
from states.bank import Bank
from states.build_base import BuildBase
from states.find_any_ore import FindAnyOreState
from states.patrol_ore import PatrolOre


DELTAS = {
    "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
    "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
}


class MatchOreSearchTests(unittest.TestCase):
    def setUp(self):
        self.cells = [{"type": "empty"} for _ in range(400)]
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 10, "y": 10},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0},
        }
        self.view = {
            "turn": 1, "map": {"width": 20, "height": 20, "cells": self.cells},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 4, "height": 4, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.bot = Bot("Worker", "worker", "ours", (10, 10))
        self.bank = Bank(self.view)

    def position(self, x, y):
        self.worker["position"] = {"x": x, "y": y}
        self.bot.update_coordinates((x, y))

    def ore(self, x, y, resource="gold", amount=4):
        self.cells[y * 20 + x] = {"type": resource, "amount": amount}

    def step(self, state):
        state.update(self.view, "ours")
        self.bank.update(self.view, "ours")
        result = state.next_action(self.bot)
        action = result[1] if isinstance(result, tuple) else result
        if action["type"] == "move":
            dx, dy = DELTAS[action["direction"]]
            x, y = self.bot.coordinates
            self.position(x + dx, y + dy)
        elif action["type"] == "mine":
            x, y = self.bot.coordinates
            cell = self.cells[y * 20 + x]
            self.assertGreater(cell["amount"], 0)
            self.worker["inventory"][cell["type"]] += 1
            cell["amount"] -= 1
            if not cell["amount"]:
                self.cells[y * 20 + x] = {"type": "empty"}
        self.view["turn"] += 1
        return action

    def builder(self):
        state = BuildBase(self.view)
        state.states = {"FindAnyOreState": FindAnyOreState(self.view), "Bank": self.bank}
        state.assign(self.bot, {"x": 10, "y": 10}, center_only=True)
        return state

    def patrol(self):
        state = PatrolOre(self.view)
        state.states["Bank"] = self.bank
        return state

    def test_exhausted_builder_patch_expands_without_waiting_or_resetting_target(self):
        self.ore(14, 10)
        state = self.builder()
        for _ in range(4):
            self.assertEqual(self.step(state)["type"], "move")
            self.assertEqual(self.bot.ore_target, (14, 10))
            self.assertEqual(self.bot.build_target, {"x": 10, "y": 10})
        self.assertEqual(self.step(state), {"type": "mine"})
        self.assertEqual(self.bot.coordinates, (14, 10))
        self.view["teamResources"]["ours"]["iron"] = 6
        self.assertEqual(self.step(state)["type"], "move")
        self.assertTrue(8 <= self.bot.build_target["x"] < 12)
        self.assertTrue(8 <= self.bot.build_target["y"] < 12)

    def test_builder_preserves_local_ore_priority_until_patch_is_exhausted(self):
        self.ore(10, 10, amount=1)
        self.ore(14, 10)
        state = self.builder()
        self.assertEqual(self.step(state), {"type": "mine"})
        self.assertEqual(state._ore_searches[self.bot.id][1].area, {"x": 8, "y": 8, "width": 4, "height": 4})

    def test_expanded_builder_search_does_not_leave_center_buffer_for_remote_ore(self):
        self.ore(19, 10)
        state = self.builder()
        for _ in range(3):
            self.assertEqual(self.step(state), {"type": "pass"})
        self.assertIsNone(self.bot.ore_target)
        self.assertEqual(self.bot.coordinates, (10, 10))

    def test_builder_explores_unknown_center_after_exhausting_visible_patch(self):
        self.cells[10 * 20 + 12] = {"type": "hidden"}
        state = self.builder()
        self.assertEqual(self.step(state)["type"], "move")
        self.assertEqual(self.bot.ore_explore_target, (12, 10))

    def test_patrol_collects_ore_on_both_sides_of_two_tile_lane(self):
        for target in ((0, 8), (4, 8)):
            with self.subTest(target=target):
                self.setUp()
                self.position(2, 8)
                self.ore(*target)
                state = self.patrol()
                for _ in range(2):
                    self.assertEqual(self.step(state)["type"], "move")
                    self.assertEqual(self.bot.ore_target, target)
                self.assertEqual(self.step(state), {"type": "mine"})
                self.assertEqual(self.bot.coordinates, target)

    def test_patrol_falls_back_to_gold_before_third_base(self):
        self.position(2, 8)
        self.ore(4, 8)
        state = self.patrol()
        state.resource = "iron"
        for _ in range(2):
            self.assertEqual(self.step(state)["type"], "move")
        self.assertEqual(self.step(state), {"type": "mine"})
        self.assertEqual(self.worker["inventory"]["gold"], 1)

    def test_patrol_prefers_available_iron_but_keeps_a_started_gold_trip(self):
        self.position(2, 8)
        self.ore(3, 8)
        self.ore(2, 11, "iron")
        state = self.patrol()
        state.resource = "iron"
        self.step(state)
        self.assertEqual(self.bot.ore_target, (2, 11))
        self.cells[11 * 20 + 2] = {"type": "empty"}
        self.step(state)
        self.assertEqual(self.bot.ore_target, (3, 8))
        self.ore(2, 11, "iron")
        self.step(state)
        self.assertEqual(self.bot.ore_target, (3, 8))

    def test_patrol_still_skips_enemy_claimed_and_distant_center_ore(self):
        self.position(2, 8)
        self.ore(4, 8)
        self.ore(9, 9)
        self.view["bases"].append({"baseId": "enemy", "teamId": "enemy", "position": {"x": 4, "y": 9}})
        state = self.patrol()
        self.step(state)
        self.assertIsNone(self.bot.ore_target)
        self.assertIn(self.bot.coordinates, state.perimeter)


if __name__ == "__main__":
    unittest.main()
