from copy import deepcopy
import unittest

from bot import Bot
from map_state import MapState
from states.bank import Bank
from states.find_any_ore import FindAnyOreState


class OreCollectionTests(unittest.TestCase):
    def setUp(self):
        self.width = self.height = 7
        self.cells = [{"type": "empty"} for _ in range(49)]
        self.worker = {
            "unitId": "worker", "teamId": "ours", "position": {"x": 3, "y": 3},
            "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8, "readyOnTurn": 1,
        }
        self.view = {
            "turn": 1, "map": {"width": 7, "height": 7, "cells": self.cells},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 3}}],
            "teamResources": {"ours": {"gold": 0, "iron": 0}},
            "highGoldArea": {"width": 3, "height": 3, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.bot = Bot("Worker", "worker", "ours", (3, 3))
        self.state = FindAnyOreState(self.view, {"x": 0, "y": 0, "width": 7, "height": 7})
        self.bank = Bank(self.view)
        self.state.states["Bank"] = self.bank

    def ore(self, x, y, amount=4, resource="gold"):
        self.cells[y * 7 + x] = {"type": resource, "amount": amount}

    def position(self, x, y):
        self.bot.update_coordinates((x, y))
        self.worker["position"] = {"x": x, "y": y}

    def step(self, state=None, observation=None):
        state = state or self.state
        observed = self.view if observation is None else observation
        state.update(observed, "ours")
        self.bank.update(observed, "ours")
        action = state.next_action(self.bot)
        if action["type"] == "move":
            delta = {
                "north": (0, -1), "north-east": (1, -1), "east": (1, 0), "south-east": (1, 1),
                "south": (0, 1), "south-west": (-1, 1), "west": (-1, 0), "north-west": (-1, -1),
            }[action["direction"]]
            self.position(self.bot.coordinates[0] + delta[0], self.bot.coordinates[1] + delta[1])
        elif action["type"] == "mine":
            x, y = self.bot.coordinates
            cell = self.cells[y * 7 + x]
            self.assertIn(cell["type"], ("gold", "iron"))
            self.assertGreater(cell["amount"], 0)
            self.assertLess(sum(self.worker["inventory"].values()), 8)
            self.worker["inventory"][cell["type"]] += 1
            cell["amount"] -= 1
            if cell["amount"] == 0:
                self.cells[y * 7 + x] = {"type": "empty"}
        elif action["type"] == "deposit":
            self.assertEqual(self.bot.coordinates, (0, 3))
            for resource in ("gold", "iron"):
                self.view["teamResources"]["ours"][resource] += self.worker["inventory"][resource]
                self.worker["inventory"][resource] = 0
        self.view["turn"] += 1
        return action

    def test_empty_explored_area_does_not_wiggle(self):
        for _ in range(12):
            self.assertEqual(self.step(), {"type": "pass"})
        self.assertEqual(self.bot.coordinates, (3, 3))

    def test_reaches_empty_assigned_area_then_stays_there(self):
        self.position(0, 0)
        state = FindAnyOreState(self.view, {"x": 4, "y": 4, "width": 2, "height": 2})
        for _ in range(4):
            self.assertEqual(self.step(state)["type"], "move")
        arrival = self.bot.coordinates
        for _ in range(5):
            self.assertEqual(self.step(state)["type"], "pass")
            self.assertEqual(self.bot.coordinates, arrival)

    def test_adjacent_ore_is_mined_until_full_and_banked(self):
        self.ore(4, 3, amount=12)
        self.assertEqual(self.step(), {"type": "move", "direction": "east"})
        for _ in range(8):
            self.assertEqual(self.step(), {"type": "mine"})
        for _ in range(10):
            self.step()
            if self.view["teamResources"]["ours"]["gold"]:
                break
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 8)

    def test_depleted_deposit_banks_partial_cargo(self):
        self.ore(4, 3, amount=2)
        for _ in range(12):
            self.step()
            if self.view["teamResources"]["ours"]["gold"]:
                break
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 2)

    def test_new_closer_deposit_does_not_reverse_an_existing_ore_trip(self):
        self.position(0, 3)
        self.ore(6, 3, amount=8)
        self.step()
        x, y = self.bot.coordinates
        self.ore(x - 1, y, amount=4)
        self.step()
        self.assertGreaterEqual(self.bot.coordinates[0], x)

    def test_returning_partial_cargo_does_not_reverse_for_new_ore(self):
        self.worker["inventory"]["gold"] = 2
        self.step()
        x, y = self.bot.coordinates
        self.ore(x + 1, y, amount=5)
        for _ in range(8):
            self.step()
            if self.view["teamResources"]["ours"]["gold"]:
                break
        self.assertEqual(self.view["teamResources"]["ours"]["gold"], 2)

    def test_unseen_search_area_is_explored_until_ore_is_collected(self):
        self.position(0, 3)
        self.ore(6, 3, amount=4)
        area = {"x": 4, "y": 2, "width": 3, "height": 3}
        memory = None
        state = None
        for _ in range(24):
            visible = deepcopy(self.view)
            x, y = self.bot.coordinates
            visible["map"]["cells"] = [
                deepcopy(cell) if abs(index % 7 - x) + abs(index // 7 - y) <= 3 else {"type": "hidden"}
                for index, cell in enumerate(self.cells)
            ]
            if memory is None:
                memory = MapState(visible)
                state = FindAnyOreState(memory, area)
            else:
                memory.update(visible)
            # Select with remembered terrain, then apply the action to the real world.
            self.step(state, dict(visible, map=memory.map))
            if self.worker["inventory"]["gold"]:
                break
        self.assertGreater(self.worker["inventory"]["gold"], 0)

    def test_disappearing_target_is_replaced_without_stale_mining(self):
        self.position(0, 3)
        self.ore(6, 3, amount=8)
        self.step()
        self.cells[3 * 7 + 6] = {"type": "empty"}
        self.ore(1, 0, amount=4)
        for _ in range(8):
            action = self.step()
            if action["type"] == "mine":
                break
        self.assertEqual(self.worker["inventory"]["gold"], 1)
        self.assertEqual(self.bot.coordinates, (1, 0))

    def test_new_search_area_invalidates_previous_target(self):
        self.ore(6, 3, amount=8)
        self.step()
        self.ore(2, 2, amount=4)
        new_state = FindAnyOreState(self.view, {"x": 1, "y": 1, "width": 2, "height": 2})
        self.step(new_state)
        self.assertEqual(self.bot.ore_target, (2, 2))

    def test_shared_state_keeps_each_rovers_target_independent(self):
        self.position(1, 1)
        self.ore(1, 0, amount=8)
        self.ore(5, 6, amount=8)
        other = Bot("Other", "other", "ours", (5, 5))
        self.view["units"].append({
            "unitId": "other", "teamId": "ours", "position": {"x": 5, "y": 5},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0},
        })
        self.state.update(self.view, "ours")
        self.state.next_action(self.bot)
        self.state.next_action(other)
        self.assertEqual(self.bot.ore_target, (1, 0))
        self.assertEqual(other.ore_target, (5, 6))


if __name__ == "__main__":
    unittest.main()
