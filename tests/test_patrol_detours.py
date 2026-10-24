import unittest

from bot import Bot
from states.patrol_ore import PatrolOre


DELTAS = {
    "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
    "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
}


class PatrolDetourTests(unittest.TestCase):
    def setUp(self):
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 2, "y": 2},
            "readyOnTurn": 1, "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8,
        }
        self.view = {
            "turn": 1,
            "map": {"width": 20, "height": 20, "cells": [{"type": "empty"} for _ in range(400)]},
            "units": [self.worker], "bases": [], "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 4, "height": 4, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.bot = Bot("Worker", "worker", "ours", (2, 2))
        self.state = PatrolOre(self.view)

    def step(self):
        self.state.update(self.view, "ours")
        action = self.state.next_action(self.bot)
        self.assertEqual(action["type"], "move")
        dx, dy = DELTAS[action["direction"]]
        x, y = self.bot.coordinates
        destination = (x + dx, y + dy)
        self.assertNotEqual(self.view["map"]["cells"][destination[1] * 20 + destination[0]]["type"], "void")
        self.bot.update_coordinates(destination)
        self.worker["position"] = {"x": destination[0], "y": destination[1]}
        self.view["turn"] += 1
        return destination

    def test_corner_trap_detours_and_resumes_patrol_in_both_directions(self):
        for direction, checkpoint, next_checkpoint in ((1, 1, 2), (-1, 7, 6)):
            with self.subTest(direction=direction):
                self.setUp()
                for index in range(3):
                    self.view["map"]["cells"][index * 20 + 5] = {"type": "void"}
                    self.view["map"]["cells"][5 * 20 + index] = {"type": "void"}
                self.bot.patrol_direction = direction
                self.bot.patrol_index = checkpoint
                destination = self.state.waypoints[checkpoint]
                visited = []
                for _ in range(20):
                    self.assertEqual(self.bot.patrol_index, checkpoint)
                    visited.append(self.step())
                    if self.bot.coordinates == destination:
                        break
                self.assertEqual(self.bot.coordinates, destination)
                self.assertTrue(any(point not in self.state.perimeter for point in visited))
                self.assertTrue(all(min(x, y, 19 - x, 19 - y) <= 3 for x, y in visited))
                self.assertEqual(len(visited), len(set(visited)))
                for _ in range(12):
                    point = self.step()
                    self.assertIn(point, self.state.perimeter)
                    self.assertEqual(self.bot.patrol_direction, direction)
                    if point == self.state.waypoints[next_checkpoint]:
                        break
                self.assertEqual(self.bot.coordinates, self.state.waypoints[next_checkpoint])

    def test_ordinary_patrol_keeps_using_ring_when_it_is_connected(self):
        self.bot.patrol_index = 4
        for _ in range(35):
            point = self.step()
            self.assertIn(point, self.state.perimeter)
            if point == self.state.waypoints[4]:
                break
        self.assertEqual(self.bot.coordinates, self.state.waypoints[4])

    def test_interior_rover_can_step_deeper_to_escape_to_perimeter(self):
        self.bot.update_coordinates((3, 3))
        self.worker["position"] = {"x": 3, "y": 3}
        self.bot.patrol_index = 1
        for dx, dy in DELTAS.values():
            if (dx, dy) != (1, 1):
                self.view["map"]["cells"][(3 + dy) * 20 + 3 + dx] = {"type": "void"}
        self.state.update(self.view, "ours")
        distances, _ = self.state._routes(self.bot.coordinates, set(), allow_hidden=True)
        self.assertFalse(any(point in self.state.perimeter for point in distances))
        self.assertEqual(self.step(), (4, 4))
        for _ in range(15):
            self.step()
            if self.bot.coordinates == self.state.waypoints[1]:
                break
        self.assertEqual(self.bot.coordinates, self.state.waypoints[1])

    def test_fully_trapped_interior_rover_passes_without_invalid_destination(self):
        self.bot.update_coordinates((3, 3))
        self.worker["position"] = {"x": 3, "y": 3}
        for dx, dy in DELTAS.values():
            self.view["map"]["cells"][(3 + dy) * 20 + 3 + dx] = {"type": "void"}
        self.state.update(self.view, "ours")
        self.assertEqual(self.state.next_action(self.bot), {"type": "pass"})


if __name__ == "__main__":
    unittest.main()
