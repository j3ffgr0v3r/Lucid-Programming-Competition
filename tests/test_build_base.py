import unittest

from bot import Bot
from manager import Manager
from states.build_base import BuildBase


class BuildBaseTests(unittest.TestCase):
    def setUp(self):
        self.grid = {"width": 7, "height": 5, "cells": [{"type": "empty"} for _ in range(35)]}
        self.worker = self.unit("builder", 0, 2)
        self.view = {
            "turn": 1, "map": self.grid, "units": [self.worker], "bases": [],
            "teamResources": {"ours": {"gold": 0, "iron": 20}},
        }
        self.bot = Bot("Builder", "builder", (0, 2))
        self.state = BuildBase(self.grid)

    @staticmethod
    def unit(unit_id, x, y, team="ours"):
        return {"unitId": unit_id, "teamId": team, "position": {"x": x, "y": y}, "readyOnTurn": 1}

    def cell(self, x, y, kind):
        self.grid["cells"][y * self.grid["width"] + x] = {"type": kind}

    def base(self, x, y, team="ours"):
        self.view["bases"].append({"baseId": f"{team}-{x}-{y}", "teamId": team, "position": {"x": x, "y": y}})

    def act(self):
        self.state.update(self.view, "ours")
        return self.state.next_action(self.bot)

    def test_travel_then_build_then_confirm(self):
        self.state.assign(self.bot, {"x": 2, "y": 2})
        for _ in range(2):
            step, action = self.act()
            self.assertEqual(action["type"], "move")
            self.bot.update_coordinates((step["x"], step["y"]))
            self.worker["position"] = step
        self.assertEqual(self.act(), (None, {"type": "build-base"}))
        self.assertEqual(self.bot.state, "BuildBase")
        # A failed attempt is retried; submission alone does not complete it.
        self.assertEqual(self.act()[1]["type"], "build-base")
        self.base(2, 2)
        self.assertEqual(self.act()[1]["type"], "pass")
        self.assertIsNone(self.bot.state)

    def test_fastest_route_avoids_obstacle_delays(self):
        for kind in ("mountain", "crater"):
            with self.subTest(kind=kind):
                for x in (1, 2, 3):
                    self.cell(x, 2, kind)
                self.state.assign(self.bot, {"x": 4, "y": 2})
                travel_time = 0
                while self.bot.coordinates != (4, 2):
                    step, action = self.act()
                    self.assertEqual(action["type"], "move")
                    terrain = self.grid["cells"][step["y"] * 7 + step["x"]]["type"]
                    travel_time += 3 if terrain in ("mountain", "crater") else 1
                    self.bot.update_coordinates((step["x"], step["y"]))
                    self.worker["position"] = step
                    self.assertLess(travel_time, 10)
                self.assertEqual(travel_time, 4)
                self.bot.update_coordinates((0, 2))
                self.worker["position"] = {"x": 0, "y": 2}

    def test_illegal_terrain_falls_back_to_nearest_site(self):
        for kind in ("gold", "iron", "mountain", "crater", "void"):
            with self.subTest(kind=kind):
                self.cell(3, 2, kind)
                self.state.assign(self.bot, {"x": 3, "y": 2})
                self.act()
                self.assertEqual(self.bot.build_site, {"x": 2, "y": 2})

    def test_enemy_territory_and_bases_are_excluded(self):
        self.base(3, 2, "enemy")
        self.state.assign(self.bot, {"x": 3, "y": 2})
        self.act()
        site = self.bot.build_site
        self.assertEqual(abs(site["x"] - 3) + abs(site["y"] - 2), 3)
        self.assertEqual(site, {"x": 0, "y": 2})

    def test_friendly_base_is_not_a_build_site(self):
        self.base(3, 2)
        self.state.assign(self.bot, {"x": 3, "y": 2})
        self.act()
        self.assertEqual(self.bot.build_site, {"x": 2, "y": 2})

    def test_other_workers_block_building_but_not_travel(self):
        self.view["units"].append(self.unit("other", 0, 2, "enemy"))
        self.state.assign(self.bot, {"x": 0, "y": 2})
        self.assertEqual(self.act()[1]["type"], "move")
        self.assertNotEqual(self.bot.build_site, {"x": 0, "y": 2})

    def test_unreachable_target_falls_back_on_reachable_side(self):
        for y in range(5):
            self.cell(3, y, "void")
        self.state.assign(self.bot, {"x": 5, "y": 2})
        self.act()
        self.assertEqual(self.bot.build_site, {"x": 2, "y": 2})

    def test_hidden_target_is_approached_without_building_early(self):
        for x in range(3, 7):
            for y in range(5):
                self.cell(x, y, "hidden")
        self.state.assign(self.bot, {"x": 5, "y": 2})
        step, action = self.act()
        self.assertEqual(action["type"], "move")
        self.assertEqual(step["x"], 1)
        self.assertIsNone(self.bot.build_site)

    def test_insufficient_iron_waits_at_site(self):
        self.view["teamResources"]["ours"]["iron"] = 5
        self.state.assign(self.bot, {"x": 0, "y": 2})
        self.assertEqual(self.act()[1]["type"], "pass")
        self.view["teamResources"]["ours"]["iron"] = 6
        self.assertEqual(self.act()[1]["type"], "build-base")

    def test_no_legal_site_or_cooldown_passes(self):
        self.state.assign(self.bot, {"x": 0, "y": 2})
        self.worker["readyOnTurn"] = 3
        self.assertEqual(self.act()[1]["type"], "pass")
        self.worker["readyOnTurn"] = 1
        for x in range(7):
            for y in range(5):
                self.cell(x, y, "mountain")
        self.assertEqual(self.act()[1]["type"], "pass")

    def test_shared_state_keeps_independent_tasks_and_sites(self):
        other = Bot("Other", "other", (1, 2))
        self.view["units"].append(self.unit("other", 1, 2))
        target = {"x": 4, "y": 2}
        self.state.assign(self.bot, target)
        self.state.assign(other, target)
        target["x"] = 6
        self.state.update(self.view, "ours")
        self.state.next_action(self.bot)
        self.state.next_action(other)
        self.assertEqual(self.bot.build_target, {"x": 4, "y": 2})
        self.assertNotEqual(self.bot.build_site, other.build_site)

    def test_multiple_builders_do_not_spend_same_iron(self):
        other = Bot("Other", "other", (6, 2))
        self.view["units"].append(self.unit("other", 6, 2))
        self.view["teamResources"]["ours"]["iron"] = 6
        self.state.assign(self.bot, {"x": 0, "y": 2})
        self.state.assign(other, {"x": 6, "y": 2})
        self.state.update(self.view, "ours")
        self.assertEqual(self.state.next_action(self.bot)[1]["type"], "build-base")
        self.assertEqual(self.state.next_action(other)[1]["type"], "pass")

    def test_manager_discovers_state_and_preserves_build_assignment(self):
        snapshot = {"match": {"matchId": "test"}, "view": self.view}
        manager = Manager(snapshot, {"teamId": "ours", "displayName": "Test"})
        manager.calculate_actions(snapshot)
        manager.states["BuildBase"].assign(manager.bots["builder"], {"x": 0, "y": 2})
        self.assertEqual(manager.calculate_actions(snapshot)["builder"], {"type": "build-base"})

    def test_invalid_target_is_rejected(self):
        for target in ({"x": -1, "y": 0}, {"x": 7, "y": 0}, {"x": 0.5, "y": 0}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.state.assign(self.bot, target)


if __name__ == "__main__":
    unittest.main()
