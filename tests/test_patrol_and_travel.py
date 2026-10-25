from copy import deepcopy
import unittest

from bot import Bot
from manager import Manager
from states.bank import Bank
from states.patrol_ore import PatrolOre


DELTAS = {
    "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
    "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
}


class PatrolAndTravelTests(unittest.TestCase):
    def setUp(self):
        self.worker = self.unit("worker", 2, 2)
        self.view = {
            "turn": 1,
            "map": {"width": 20, "height": 20, "cells": [{"type": "empty"} for _ in range(400)]},
            "units": [self.worker],
            "bases": [self.base("home", 0, 0), self.base("second", 8, 9), self.base("third", 11, 10)],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 4, "height": 4, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "patrol", "maxTurns": 480}, "view": self.view}
        self.identity = {"teamId": "ours", "displayName": "Test"}

    @staticmethod
    def unit(name, x, y):
        return {"unitId": name, "teamId": "ours", "position": {"x": x, "y": y},
                "readyOnTurn": 1, "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8}

    @staticmethod
    def base(name, x, y, team="ours"):
        return {"baseId": name, "teamId": team, "position": {"x": x, "y": y}}

    def ore(self, x, y, amount=4, resource="gold"):
        self.view["map"]["cells"][y * 20 + x] = {"type": resource, "amount": amount}

    def apply(self, action, bot=None):
        x, y = self.worker["position"].values()
        if action["type"] == "move":
            dx, dy = DELTAS[action["direction"]]
            self.worker["position"] = {"x": x + dx, "y": y + dy}
            if bot is not None:
                bot.update_coordinates((x + dx, y + dy))
        elif action["type"] == "mine":
            cell = self.view["map"]["cells"][y * 20 + x]
            self.worker["inventory"][cell["type"]] += 1
            cell["amount"] -= 1
            if not cell["amount"]:
                self.view["map"]["cells"][y * 20 + x] = {"type": "empty"}
        self.view["turn"] += 1

    def test_patrol_completes_circuit_in_both_directions_without_cutting_through_center(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                self.worker["position"] = {"x": 2, "y": 2}
                bot = Bot("Worker", "worker", "ours", (2, 2))
                bot.patrol_index = 0
                bot.patrol_direction = direction
                state = PatrolOre(self.view)
                visited = {bot.coordinates}
                for _ in range(72):
                    state.update(self.view, "ours")
                    action = state.next_action(bot)
                    self.assertEqual(action["type"], "move")
                    self.apply(action, bot)
                    self.assertIn(bot.coordinates, state.perimeter)
                    visited.add(bot.coordinates)
                self.assertTrue(all(point in visited for point in ((2, 2), (17, 2), (17, 17), (2, 17))))

    def test_patrol_mines_nearby_edge_ore_but_does_not_target_center_ore(self):
        bot = Bot("Worker", "worker", "ours", (2, 2))
        state = PatrolOre(self.view)
        self.ore(9, 9, 12)
        self.ore(2, 4, 3)
        for _ in range(3):
            state.update(self.view, "ours")
            action = state.next_action(bot)
            self.apply(action, bot)
        self.assertEqual(action, {"type": "mine"})
        self.assertEqual(bot.ore_target, (2, 4))
        self.assertEqual(self.worker["inventory"]["gold"], 1)

    def test_blocked_checkpoint_is_skipped_and_tiny_map_is_safe(self):
        self.view["map"]["cells"][2 * 20 + 9] = {"type": "void"}
        bot = Bot("Worker", "worker", "ours", (2, 2))
        bot.patrol_index = 1
        state = PatrolOre(self.view)
        visited = set()
        for _ in range(24):
            state.update(self.view, "ours")
            action = state.next_action(bot)
            self.assertEqual(action["type"], "move")
            self.apply(action, bot)
            self.assertNotEqual(bot.coordinates, (9, 2))
            visited.add(bot.coordinates)
        self.assertIn((17, 2), visited)
        tiny = deepcopy(self.view)
        tiny["map"] = {"width": 1, "height": 1, "cells": [{"type": "empty"}]}
        tiny["units"][0]["position"] = {"x": 0, "y": 0}
        tiny["bases"] = []
        state = PatrolOre(tiny)
        state.update(tiny, "ours")
        self.assertEqual(state.next_action(Bot("Worker", "worker", "ours", (0, 0))), {"type": "pass"})

    def test_patrol_banks_full_load_and_resumes_its_checkpoint(self):
        bot = Bot("Worker", "worker", "ours", (2, 2))
        bot.patrol_index = 3
        state, bank = PatrolOre(self.view), Bank(self.view)
        state.states["Bank"] = bank
        self.worker["inventory"]["gold"] = 8
        state.update(self.view, "ours")
        bank.update(self.view, "ours")
        self.assertEqual(state.next_action(bot)["type"], "move")
        self.assertTrue(bot.ore_returning)
        self.assertEqual(bot.patrol_index, 3)
        self.worker["inventory"]["gold"] = 0
        self.worker["position"] = {"x": 0, "y": 0}
        bot.update_coordinates((0, 0))
        state.update(self.view, "ours")
        self.assertEqual(state.next_action(bot)["type"], "move")
        self.assertFalse(bot.ore_returning)
        self.assertEqual(bot.patrol_index, 3)

    def test_only_two_center_assignments_survive_new_rovers_and_trade_cutoff(self):
        self.view["units"] = [self.unit("center-a", 9, 9), self.unit("center-b", 10, 10)] + [
            self.unit(f"edge-{i}", x, y) for i, (x, y) in enumerate(((0, 0), (19, 0), (19, 19), (0, 19)))
        ]
        manager = Manager(self.snapshot, self.identity)
        manager.calculate_actions(self.snapshot)
        self.assertEqual(manager._center_ids, {"center-a", "center-b"})
        self.assertEqual(sum(bot.state == "PatrolOre" for bot in manager.bots.values()), 4)
        sectors = sorted(manager.bots[f"edge-{i}"].patrol_sector for i in range(4))
        self.assertEqual(sectors[0][0], 0)
        self.assertEqual(sectors[-1][1], len(manager.states["PatrolOre"].circuit))
        self.assertTrue(all(left[1] == right[0] for left, right in zip(sectors, sectors[1:])))
        self.view["units"].append(self.unit("aaa-new", 10, 9))
        self.view["turn"] = 380
        actions = manager.calculate_actions(self.snapshot)
        self.assertEqual(manager._center_ids, {"center-a", "center-b"})
        self.assertTrue(all(bot.state == "Trade" for bot in manager.bots.values()))
        self.assertEqual(sum(bot.search_area_index is not None for bot in manager.bots.values()), 2)
        self.assertEqual(actions["edge-0"]["type"], "move")
        self.assertIsNone(manager.states["PatrolOre"].resource)
        self.view["units"] = [unit for unit in self.view["units"] if unit["unitId"] != "center-a"]
        manager.calculate_actions(self.snapshot)
        self.assertEqual(len(manager._center_ids), 2)
        self.assertIn("center-b", manager._center_ids)

    def test_travel_mines_outside_search_area_then_resumes_original_target(self):
        self.ore(2, 2, 2)
        self.ore(9, 9, 12)
        manager = Manager(self.snapshot, self.identity)
        for _ in range(2):
            action = manager.calculate_actions(self.snapshot)["worker"]
            self.assertEqual(action, {"type": "mine"})
            self.assertEqual(manager.bots["worker"].ore_target, (9, 9))
            self.apply(action)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertEqual(self.worker["inventory"]["gold"], 2)
        self.assertEqual(manager.bots["worker"].ore_target, (9, 9))

    def test_mining_on_way_keeps_builder_target_and_respects_capacity(self):
        self.view["bases"] = self.view["bases"][:1]
        self.view["units"].extend([self.unit("other-a", 0, 0), self.unit("other-b", 19, 19)])
        self.view["teamResources"]["ours"]["iron"] = 6
        self.worker["position"] = {"x": 6, "y": 6}
        self.ore(6, 6, 12)
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "mine"})
        target = manager.bots["worker"].build_target.copy()
        self.worker["inventory"]["iron"] = 8
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertEqual(manager.bots["worker"].build_target, target)

    def test_enemy_claim_cooldown_and_urgent_banking_prevent_opportunistic_mining(self):
        self.ore(2, 2, 12)
        self.ore(9, 9, 12)
        self.view["bases"].append(self.base("enemy", 2, 3, "enemy"))
        manager = Manager(self.snapshot, self.identity)
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.worker["readyOnTurn"] = 3
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"], {"type": "pass"})
        self.worker["readyOnTurn"] = 1
        self.worker["position"] = {"x": 4, "y": 4}
        self.worker["inventory"]["gold"] = 2
        self.ore(4, 4, 12)
        self.view["turn"] = 475
        self.assertEqual(manager.calculate_actions(self.snapshot)["worker"]["type"], "move")
        self.assertTrue(manager.bots["worker"].ore_returning)


if __name__ == "__main__":
    unittest.main()
