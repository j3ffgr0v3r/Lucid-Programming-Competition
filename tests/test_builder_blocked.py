import unittest

from bot import Bot
from states.bank import Bank
from states.build_base import BuildBase
from states.find_any_ore import FindAnyOreState


class BlockedBuilderTests(unittest.TestCase):
    def setUp(self):
        self.cells = [{"type": "empty"} for _ in range(400)]
        self.worker = {
            "unitId": "builder", "teamId": "ours", "position": {"x": 10, "y": 10},
            "readyOnTurn": 1, "inventoryCapacity": 8, "inventory": {"gold": 0, "iron": 0},
        }
        self.view = {
            "turn": 1, "map": {"width": 20, "height": 20, "cells": self.cells},
            "units": [self.worker],
            "bases": [{"baseId": "home", "teamId": "ours", "position": {"x": 0, "y": 0}}],
            "teamResources": {"ours": {"gold": 0, "iron": 6}},
            "highGoldArea": {"width": 4, "height": 4, "min": 12, "max": 18, "spawnPercent": 35},
        }
        self.bot = Bot("Builder", "builder", "ours", (10, 10))
        self.state = BuildBase(self.view)
        self.bank = Bank(self.view)
        self.state.states = {"FindAnyOreState": FindAnyOreState(self.view), "Bank": self.bank}
        self.state.assign(self.bot, {"x": 10, "y": 10}, center_only=True)
        for y in range(8, 12):
            for x in range(8, 12):
                self.cells[y * 20 + x] = {"type": "mountain"}

    def act(self):
        self.state.update(self.view, "ours")
        self.bank.update(self.view, "ours")
        return self.state.next_action(self.bot)[1]

    def position(self, x, y):
        self.bot.update_coordinates((x, y))
        self.worker["position"] = {"x": x, "y": y}

    def ore(self, x, y, amount=4):
        self.cells[y * 20 + x] = {"type": "gold", "amount": amount}

    def test_no_legal_center_site_collects_adjacent_ore_without_moving_build_target(self):
        self.ore(12, 10)
        # Remote ore outside the bounded fallback must be ignored.
        self.ore(19, 10)
        self.assertEqual(self.act()["type"], "move")
        self.assertEqual(self.bot.ore_target, (12, 10))
        self.assertEqual(self.bot.build_target, {"x": 10, "y": 10})
        self.assertIsNone(self.bot.build_site)
        search = self.state._ore_searches[self.bot.id][1]
        self.assertEqual(search.area, {"x": 5, "y": 5, "width": 10, "height": 10})
        self.position(12, 10)
        self.view["turn"] += 1
        self.assertEqual(self.act(), {"type": "mine"})
        self.assertIs(self.state._ore_searches[self.bot.id][1], search)

    def test_newly_available_center_site_resumes_construction_next_turn(self):
        self.ore(12, 10)
        self.cells[10 * 20 + 10] = {"type": "empty"}
        other = dict(self.worker, unitId="other")
        self.view["units"].append(other)
        self.assertEqual(self.act()["type"], "move")
        self.view["units"].remove(other)
        self.view["turn"] += 1
        self.assertEqual(self.act(), {"type": "build-base"})
        self.assertEqual(self.bot.build_site, {"x": 10, "y": 10})

    def test_enemy_claimed_center_uses_unclaimed_ore_in_buffer(self):
        for x, y in ((8, 8), (11, 8), (8, 11), (11, 11)):
            self.view["bases"].append({
                "baseId": f"enemy-{x}-{y}", "teamId": "enemy", "position": {"x": x, "y": y},
            })
        for y in range(8, 12):
            for x in range(8, 12):
                self.cells[y * 20 + x] = {"type": "empty"}
        self.ore(10, 10)
        self.ore(14, 10)
        self.assertEqual(self.act()["type"], "move")
        self.assertEqual(self.bot.ore_target, (14, 10))
        self.assertIsNone(self.bot.build_site)

    def test_partial_cargo_banks_before_resuming_newly_available_build(self):
        self.worker["inventory"]["gold"] = 2
        self.assertEqual(self.act()["type"], "move")
        self.assertTrue(self.bot.ore_returning)
        self.cells[10 * 20 + 10] = {"type": "empty"}
        self.view["turn"] += 1
        self.assertEqual(self.act()["type"], "move")
        self.assertIsNone(self.bot.build_site)
        self.position(0, 0)
        self.assertEqual(self.act(), {"type": "deposit"})
        self.worker["inventory"]["gold"] = 0
        self.assertEqual(self.act()["type"], "move")
        self.assertEqual(self.bot.build_site, {"x": 10, "y": 10})

    def test_full_fallback_cargo_banks_even_when_a_site_just_opened(self):
        self.ore(12, 10)
        self.assertEqual(self.act()["type"], "move")
        self.worker["inventory"]["gold"] = 8
        self.cells[10 * 20 + 10] = {"type": "empty"}
        self.assertEqual(self.act()["type"], "move")
        self.assertTrue(self.bot.ore_returning)
        self.assertIsNone(self.bot.build_site)


if __name__ == "__main__":
    unittest.main()
