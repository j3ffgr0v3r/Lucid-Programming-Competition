from copy import deepcopy
import unittest

from bot import Bot
from manager import Manager
from states.patrol_ore import PatrolOre


DELTAS = {
    "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
    "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
}


class MovementLoopTests(unittest.TestCase):
    def setUp(self):
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 3, "y": 3},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0},
        }
        self.view = {
            "turn": 1,
            "map": {"width": 7, "height": 7, "cells": [{"type": "empty"} for _ in range(49)]},
            "units": [self.worker],
            "bases": [{"baseId": str(y), "teamId": "ours", "position": {"x": 0, "y": y}} for y in range(3)],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.snapshot = {"match": {"matchId": "loops", "maxTurns": 480}, "view": self.view}
        self.manager = Manager(self.snapshot, {"teamId": "ours", "displayName": "Test"})

    def move(self, action):
        self.assertEqual(action["type"], "move")
        dx, dy = DELTAS[action["direction"]]
        self.worker["position"]["x"] += dx
        self.worker["position"]["y"] += dy
        self.view["turn"] += 1

    def test_alternating_targets_cannot_reverse_the_same_step_indefinitely(self):
        # Newly revealed/depleted ore can keep reversing a rover's destination.
        for turn in range(4):
            self.view["map"]["cells"][2 * 7 + 2] = {"type": "empty"}
            self.view["map"]["cells"][5 * 7 + 5] = {"type": "empty"}
            target = (5, 5) if turn % 2 == 0 else (2, 2)
            self.view["map"]["cells"][target[1] * 7 + target[0]] = {"type": "gold", "amount": 8}
            self.move(self.manager.calculate_actions(self.snapshot)["worker"])
        self.assertEqual(self.worker["position"], {"x": 3, "y": 3})
        self.view["map"]["cells"][2 * 7 + 2] = {"type": "empty"}
        self.view["map"]["cells"][5 * 7 + 5] = {"type": "gold", "amount": 8}
        original = deepcopy(self.snapshot)
        action = self.manager.calculate_actions(self.snapshot)["worker"]
        self.assertEqual(self.snapshot, original)
        self.move(action)
        self.assertNotEqual(self.worker["position"], {"x": 4, "y": 4})
        for _ in range(8):
            action = self.manager.calculate_actions(self.snapshot)["worker"]
            if action["type"] == "mine":
                break
            self.move(action)
        self.assertEqual(action, {"type": "mine"})
        self.assertEqual(self.worker["position"], {"x": 5, "y": 5})

    def test_failed_moves_and_cooldowns_do_not_create_fake_movement_loops(self):
        self.view["map"]["cells"][5 * 7 + 5] = {"type": "gold", "amount": 8}
        for _ in range(8):
            self.manager.calculate_actions(self.snapshot)
            self.view["turn"] += 1
        bot = self.manager.bots["worker"]
        self.assertFalse(bot.avoid_steps)
        self.assertEqual(bot.movement_history, [(3, 3)])
        self.worker["readyOnTurn"] = self.view["turn"] + 3
        for _ in range(3):
            self.assertEqual(self.manager.calculate_actions(self.snapshot)["worker"], {"type": "pass"})
            self.view["turn"] += 1
        self.assertFalse(bot.avoid_steps)

    def test_bank_routes_honor_loop_recovery_without_changing_map_memory(self):
        self.worker["inventory"]["gold"] = 8
        self.manager.calculate_actions(self.snapshot)
        bot = self.manager.bots["worker"]
        bot.avoid_steps[(2, 2)] = self.view["turn"] + 4
        original = deepcopy(self.view["map"])
        action = self.manager.calculate_actions(self.snapshot)["worker"]
        self.move(action)
        self.assertNotEqual(self.worker["position"], {"x": 2, "y": 2})
        self.assertEqual(self.manager.map_state.map, original)

    def test_recovery_only_affects_the_rover_that_was_looping(self):
        other = deepcopy(self.worker)
        other["unitId"] = "other"
        self.view["units"].append(other)
        self.view["map"]["cells"][5 * 7 + 5] = {"type": "gold", "amount": 20}
        self.manager.calculate_actions(self.snapshot)
        self.manager.bots["worker"].avoid_steps[(4, 4)] = self.view["turn"] + 4
        actions = self.manager.calculate_actions(self.snapshot)
        self.assertEqual(actions["other"], {"type": "move", "direction": "south-east"})
        self.assertNotEqual(actions["worker"], actions["other"])

    def test_patrol_follows_two_tile_offset_on_all_four_sides(self):
        self.view["map"] = {"width": 20, "height": 20, "cells": [{"type": "empty"} for _ in range(400)]}
        self.view["bases"] = []
        for direction in (1, -1):
            with self.subTest(direction=direction):
                state = PatrolOre(self.view)
                bot = Bot("Worker", "worker", "ours", (2, 2))
                bot.patrol_index = 0
                bot.patrol_direction = direction
                visited = {bot.coordinates}
                for _ in range(64):
                    state.update(self.view, "ours")
                    action = state.next_action(bot)
                    self.assertEqual(action["type"], "move")
                    dx, dy = DELTAS[action["direction"]]
                    x, y = bot.coordinates
                    bot.update_coordinates((x + dx, y + dy))
                    x, y = bot.coordinates
                    self.assertEqual(min(x, y, 19 - x, 19 - y), 2)
                    visited.add(bot.coordinates)
                self.assertTrue(set(state.waypoints).issubset(visited))


if __name__ == "__main__":
    unittest.main()
