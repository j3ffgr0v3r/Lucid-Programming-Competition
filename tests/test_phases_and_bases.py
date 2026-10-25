from math import hypot
import unittest

from base_planner import BasePlanner
from manager import Manager
from map_state import MapState


def worker(name, x, y):
    return {"unitId": name, "teamId": "ours", "position": {"x": x, "y": y},
            "readyOnTurn": 0, "inventory": {"gold": 0, "iron": 0}, "inventoryCapacity": 8}


def base(name, x, y):
    return {"baseId": name, "teamId": "ours", "position": {"x": x, "y": y}}


def snapshot(width=30, height=30):
    return {"match": {"matchId": "phases", "maxTurns": 480}, "view": {
        "turn": 1, "map": {"width": width, "height": height,
                              "cells": [{"type": "empty"} for _ in range(width * height)]},
        "units": [worker("center-a", width // 2, height // 2),
                  worker("center-b", width // 2 - 1, height // 2),
                  worker("outside", 2, 2)],
        "bases": [base("home", 2, 3)], "teamResources": {"ours": {"gold": 0, "iron": 0}},
        "highGoldArea": {"width": 6, "height": 6, "min": 12, "max": 18, "spawnPercent": 35},
    }}


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()
        self.view = self.snapshot["view"]
        self.manager = Manager(self.snapshot, {"teamId": "ours", "displayName": "Test"})

    def act(self):
        return self.manager.calculate_actions(self.snapshot)

    def test_quotas_round_up_and_scale_to_map(self):
        small = Manager(snapshot(17, 19), {"teamId": "ours"})
        self.assertEqual((small.base_target, small.worker_target), (4, 2))
        normal = Manager(snapshot(50, 50), {"teamId": "ours"})
        self.assertEqual((normal.base_target, normal.worker_target, normal.construction_end_turn), (25, 10, 288))

    def test_small_map_enters_mining_when_rounded_quotas_are_already_met(self):
        small = snapshot(9, 9)
        small["view"]["units"] = small["view"]["units"][:1]
        small["view"]["teamResources"]["ours"]["iron"] = 100
        manager = Manager(small, {"teamId": "ours"})
        actions = manager.calculate_actions(small)
        self.assertEqual((manager.base_target, manager.worker_target), (1, 1))
        self.assertEqual(manager.phase, "mining")
        self.assertFalse(any(a["type"] in ("spawn", "build-base") for a in actions.values()))

    def test_both_quotas_required_for_early_transition_and_phase_never_reverses(self):
        self.manager.base_target = 1
        self.manager.worker_target = 4
        self.act()
        self.assertEqual(self.manager.phase, "construction")
        self.view["units"].append(worker("fourth", 27, 27))
        self.act()
        self.assertEqual(self.manager.phase, "mining")
        self.view["units"].pop()
        self.act()
        self.assertEqual(self.manager.phase, "mining")

    def test_worker_quota_alone_does_not_end_construction(self):
        self.manager.worker_target = 3
        self.act()
        self.assertEqual(self.manager.phase, "construction")

    def test_construction_gold_converts_in_batches_before_deposit(self):
        rover = self.view["units"][2]
        rover["position"] = {"x": 2, "y": 3}
        rover["inventory"] = {"gold": 7, "iron": 0}
        for gold, iron in ((7, 0), (4, 1)):
            rover["inventory"] = {"gold": gold, "iron": iron}
            self.assertEqual(self.act()["outside"], {"type": "trade", "from": "gold"})
        rover["inventory"] = {"gold": 1, "iron": 2}
        self.assertEqual(self.act()["outside"], {"type": "deposit"})

    def test_cutoff_cancels_pending_build_and_converts_iron(self):
        self.view["teamResources"]["ours"]["iron"] = 100
        self.act()
        self.assertTrue(self.manager._build_assignments)
        self.view["turn"] = 288
        for rover in self.view["units"]:
            rover["inventory"] = {"gold": 0, "iron": 3}
        actions = self.act()
        self.assertEqual(self.manager.phase, "mining")
        self.assertFalse(self.manager._build_assignments)
        self.assertTrue(all(a == {"type": "trade", "from": "iron"} for a in actions.values()))

    def test_far_rover_returns_earlier_than_near_rover(self):
        self.view["turn"] = 464
        self.view["units"][0]["inventory"]["gold"] = 1
        actions = self.act()
        self.assertEqual(self.manager.bots["center-a"].state, "Ending")
        self.assertEqual(actions["center-a"]["type"], "move")
        self.assertFalse(self.manager.bots["outside"].ending)

    def test_return_budget_includes_current_cooldown_and_conversion(self):
        self.view["turn"] = 470
        rover = self.view["units"][2]
        rover["position"] = {"x": 7, "y": 3}  # Five moves, one deposit.
        rover["inventory"]["iron"] = 6
        rover["readyOnTurn"] = 472
        self.assertEqual(self.act()["outside"], {"type": "pass"})
        self.assertTrue(self.manager.bots["outside"].ending)

    def test_ending_skips_ore_and_stays_home_after_banking(self):
        self.view["turn"] = 477
        rover = self.view["units"][2]
        rover["inventory"]["gold"] = 1
        self.view["map"]["cells"][2 * 30 + 2] = {"type": "gold", "amount": 12}
        self.assertEqual(self.act()["outside"]["type"], "move")
        rover["position"] = {"x": 2, "y": 3}
        self.view["turn"] += 1
        self.assertEqual(self.act()["outside"], {"type": "deposit"})
        rover["inventory"]["gold"] = 0
        self.view["turn"] += 1
        self.assertEqual(self.act()["outside"], {"type": "pass"})
        self.assertEqual(self.manager.phase, "ending")

    def test_trip_rejected_if_it_would_be_abandoned_by_return_buffer(self):
        self.view["turn"] = 474
        self.view["units"][2]["position"] = {"x": 3, "y": 3}
        self.view["map"]["cells"][5 * 30 + 5] = {"type": "gold", "amount": 8}
        self.act()
        self.assertIsNone(self.manager.bots["outside"].ore_target)

    def test_build_target_stays_fixed_and_ore_invalidates_site(self):
        self.view["teamResources"]["ours"]["iron"] = 6
        self.act()
        uid, target = next(iter(self.manager._build_assignments.items()))
        self.view["turn"] += 1
        self.act()
        self.assertEqual(self.manager._build_assignments[uid], target)
        self.view["map"]["cells"][target[1] * 30 + target[0]] = {"type": "gold", "amount": 8}
        self.act()
        self.assertNotIn(target, self.manager._build_assignments.values())

    def test_two_center_bases_then_outside_even_before_third_center_base(self):
        self.view["bases"].extend([base("c1", 12, 12), base("c2", 17, 17)])
        self.view["units"].append(worker("fourth", 27, 27))
        self.view["teamResources"]["ours"]["iron"] = 6
        self.act()
        self.assertTrue(self.manager._build_assignments)
        self.assertTrue(all(not self.manager.base_planner.in_center(p)
                            for p in self.manager._build_assignments.values()))

    def test_sectors_partition_patrol_without_overlap_and_remain_balanced(self):
        self.view["units"].extend(worker(str(i), 27, 27) for i in range(4))
        self.act()
        patrol = self.manager.states["PatrolOre"]
        outsiders = [b for b in self.manager.bots.values() if b.id not in self.manager._center_ids]
        lengths = [b.patrol_sector[1] - b.patrol_sector[0] for b in outsiders]
        self.assertLessEqual(max(lengths) - min(lengths), 1)
        for point in patrol.circuit:
            self.assertEqual(sum(patrol.in_sector(point, b) for b in outsiders), 1)
        for point in ((0, 0), (9, 8), (29, 29), (21, 20)):
            self.assertEqual(sum(patrol.in_sector(point, b) for b in outsiders), 1)

    def test_mining_searches_inward_of_patrol_band_and_excludes_center(self):
        self.view["turn"] = 300
        self.view["units"][2]["position"] = {"x": 8, "y": 8}
        self.view["map"]["cells"][8 * 30 + 8] = {"type": "gold", "amount": 8}
        self.assertEqual(self.act()["outside"], {"type": "mine"})
        sector = self.manager.states["SectorOre"]
        bot = self.manager.bots["outside"]
        self.assertFalse(sector._owns((15, 15), bot))
        self.assertEqual(len(self.manager._center_ids), 2)

    def test_patrol_stays_two_tiles_from_wall_inside_its_sector(self):
        self.view["units"].extend([worker("east", 27, 2), worker("south", 27, 27)])
        self.act()
        patrol = self.manager.states["PatrolOre"]
        delta = {"north": (0, -1), "north-east": (1, -1), "east": (1, 0),
                 "south-east": (1, 1), "south": (0, 1), "south-west": (-1, 1),
                 "west": (-1, 0), "north-west": (-1, -1)}
        outsiders = [b for b in self.manager.bots.values() if b.id not in self.manager._center_ids]
        for bot in outsiders:
            bot.update_coordinates(patrol.circuit[bot.patrol_sector[0]])
            bot.patrol_cursor = bot.patrol_sector[0]
            rover = next(u for u in self.view["units"] if u["unitId"] == bot.id)
            history = []
            for _ in range(75):
                rover["position"] = {"x": bot.coordinates[0], "y": bot.coordinates[1]}
                action = patrol.next_action(bot)
                self.assertEqual(action["type"], "move")
                dx, dy = delta[action["direction"]]
                bot.update_coordinates((bot.coordinates[0] + dx, bot.coordinates[1] + dy))
                self.assertTrue(patrol.in_sector(bot.coordinates, bot))
                self.assertEqual(patrol._edge_depth(bot.coordinates), 2)
                history.append(bot.coordinates)
                if len(history) >= 5:
                    self.assertFalse(history[-1] == history[-3] == history[-5]
                                     and history[-2] == history[-4])

    def test_return_estimate_matches_paths_with_obstacles_and_multiple_bases(self):
        self.view["bases"].append(base("second", 26, 26))
        for y in range(30):
            self.view["map"]["cells"][y * 30 + 8] = {"type": "mountain"}
            self.view["map"]["cells"][y * 30 + 10] = {"type": "hidden"}
        self.act()
        bank = self.manager.states["Bank"]
        bot = self.manager.bots["outside"]
        for x, y in ((8, 15), (7, 16), (0, 0), (29, 29), (10, 3), (2, 3)):
            bot.update_coordinates((x, y))
            paths = [bank._path_through_hidden(bank.grid, {"x": x, "y": y}, b["position"],
                                              self.view["bases"], "ours") for b in self.view["bases"]]
            expected = min(bank._path_cost(bank.grid, path, hidden_penalty=1) + 1
                           for path in paths if path is not None)
            self.assertEqual(bank.turns_to_bank(bot), expected)


class BasePlannerTests(unittest.TestCase):
    def make_planner(self, view):
        return BasePlanner(MapState(view))

    def test_large_unserved_gap_beats_land_near_existing_base(self):
        view = snapshot(50, 50)["view"]
        planner = self.make_planner(view)
        first = planner.ranked_sites("ours", center=False)[0]
        self.assertGreater(first[0], 35)
        self.assertGreater(first[1], 35)
        second = planner.ranked_sites("ours", center=False, reserved=[first])[0]
        self.assertGreater(hypot(second[0] - first[0], second[1] - first[1]), 30)

    def test_known_ore_improves_score_at_comparable_gap(self):
        view = snapshot(40, 40)["view"]
        view["bases"] = [base("home", 20, 20)]
        view["map"]["cells"][5 * 40 + 5] = {"type": "gold", "amount": 12}
        first = self.make_planner(view).ranked_sites("ours", center=False)[0]
        self.assertLessEqual(max(abs(first[0] - 5), abs(first[1] - 5)), 4)

    def test_barren_farmland_and_isolated_plain_are_not_valuable(self):
        view = snapshot()["view"]
        view["map"]["cells"] = [{"type": "mountain"} for _ in range(900)]
        for y in range(3, 10):
            for x in range(18, 25):
                view["map"]["cells"][y * 30 + x] = {"type": "empty"}
        view["map"]["cells"][28 * 30 + 28] = {"type": "empty"}
        view["map"]["cells"][4 * 30 + 20] = {"type": "crater"}
        points = self.make_planner(view).ranked_sites("ours", center=False)
        self.assertTrue(points)
        self.assertNotIn((28, 28), points)
        self.assertNotIn((20, 4), points)
        self.assertTrue(all(18 <= x < 25 and 3 <= y < 10 for x, y in points))

    def test_spacing_enemy_claims_reserved_sites_and_center_cap(self):
        view = snapshot()["view"]
        view["bases"].extend([base("a", 12, 12), base("b", 17, 12), base("c", 15, 17)])
        enemy = base("enemy", 27, 27)
        enemy["teamId"] = "enemy"
        view["bases"].append(enemy)
        planner = self.make_planner(view)
        self.assertEqual(planner.ranked_sites("ours", center=True), [])
        reserved = (25, 5)
        points = planner.ranked_sites("ours", center=False, reserved=[reserved])
        self.assertTrue(points)
        for x, y in points:
            self.assertGreaterEqual(hypot(x - reserved[0], y - reserved[1]), 10)
            self.assertGreater(abs(x - 27) + abs(y - 27), 2)
            for b in view["bases"][:-1]:
                self.assertGreaterEqual(hypot(x - b["position"]["x"], y - b["position"]["y"]), 10)


if __name__ == "__main__":
    unittest.main()
