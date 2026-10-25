import unittest

from bot import Bot
from manager import Manager
from states.find_any_ore import FindAnyOreState
from states.bank import Bank
from states.patrol_ore import PatrolOre
from test_phases_and_bases import snapshot, base, worker


DELTAS = {"north": (0, -1), "north-east": (1, -1), "east": (1, 0),
          "south-east": (1, 1), "south": (0, 1), "south-west": (-1, 1),
          "west": (-1, 0), "north-west": (-1, -1)}


class AdaptivePatrolTests(unittest.TestCase):
    def test_sector_patrol_skips_mountain_checkpoints_and_rejoins_lane(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                view = snapshot(20, 20)["view"]
                start = (2, 2) if direction == 1 else (9, 2)
                view["units"] = [worker("rover", *start)]
                bot = Bot("rover", "rover", "ours", start)
                bot.patrol_sector = (0, 16)
                bot.patrol_cursor = 0 if direction == 1 else 7
                bot.patrol_direction = direction
                for y in range(3):
                    view["map"]["cells"][y * 20 + 5] = {"type": "mountain"}
                state = PatrolOre(view)
                visited = []
                for _ in range(9):
                    state.update(view, "ours")
                    action = state.next_action(bot)
                    self.assertEqual(action["type"], "move")
                    dx, dy = DELTAS[action["direction"]]
                    bot.update_coordinates((bot.coordinates[0] + dx, bot.coordinates[1] + dy))
                    x, y = bot.coordinates
                    self.assertNotEqual(view["map"]["cells"][y * 20 + x]["type"], "mountain")
                    self.assertTrue(state.in_sector(bot.coordinates, bot))
                    view["units"][0]["position"] = {"x": x, "y": y}
                    visited.append(bot.coordinates)
                self.assertIn((5, 3), visited)
                self.assertIn(bot.coordinates, state.patrol_lane)

    def test_costly_sector_endpoint_does_not_force_mountain_entry(self):
        view = snapshot(20, 20)["view"]
        view["units"] = [worker("rover", 5, 2)]
        view["map"]["cells"][2 * 20 + 6] = {"type": "crater"}
        bot = Bot("rover", "rover", "ours", (5, 2))
        bot.patrol_sector = (0, 5)
        bot.patrol_cursor = 4
        state = PatrolOre(view)
        state.update(view, "ours")
        self.assertEqual(state.next_action(bot), {"type": "move", "direction": "west"})
        self.assertEqual(bot.patrol_direction, -1)


class OreYieldTests(unittest.TestCase):
    def setUp(self):
        self.view = snapshot(15, 15)["view"]
        self.rover = worker("rover", 7, 7)
        self.view["units"] = [self.rover]
        self.view["bases"] = [base("home", 0, 0)]
        self.bot = Bot("rover", "rover", "ours", (7, 7))
        self.bot.state = "Trade"
        self.bot.trade_from = "iron"
        self.state = FindAnyOreState(self.view)

    def ore(self, x, y, resource, amount):
        self.view["map"]["cells"][y * 15 + x] = {"type": resource, "amount": amount}

    def act(self):
        self.state.update(self.view, "ours")
        self.state.turns_left = 150
        return self.state.next_action(self.bot)

    def test_slightly_further_gold_beats_nearest_iron(self):
        self.ore(8, 7, "iron", 4)
        self.ore(7, 9, "gold", 8)
        self.act()
        self.assertEqual(self.bot.ore_target, (7, 9))

    def test_round_trip_cost_beats_distance_to_deposit_alone(self):
        self.ore(8, 7, "gold", 8)
        self.ore(3, 3, "gold", 8)
        self.act()
        self.assertEqual(self.bot.ore_target, (3, 3))

    def test_stock_and_cargo_room_change_the_best_trip(self):
        self.ore(6, 7, "gold", 1)
        self.ore(10, 7, "gold", 8)
        self.act()
        self.assertEqual(self.bot.ore_target, (10, 7))
        self.bot.ore_target = None
        self.rover["inventory"]["gold"] = 7
        self.act()
        self.assertEqual(self.bot.ore_target, (6, 7))

    def test_other_workers_reserved_stock_does_not_inflate_yield(self):
        self.ore(6, 7, "gold", 3)
        self.ore(10, 7, "gold", 8)
        self.state.update(self.view, "ours")
        self.state.turns_left = 150
        self.state.ore_reservations[(10, 7)] = {"other": 7}
        self.state.next_action(self.bot)
        self.assertEqual(self.bot.ore_target, (6, 7))

    def test_existing_iron_counts_toward_a_profitable_batch(self):
        self.rover["inventory"]["iron"] = 2
        self.ore(6, 7, "iron", 1)
        self.ore(14, 14, "gold", 1)
        self.act()
        self.assertEqual(self.bot.ore_target, (6, 7))

    def test_viable_target_stays_fixed_and_mining_underfoot_continues(self):
        self.ore(8, 7, "gold", 8)
        self.act()
        self.ore(6, 7, "gold", 12)
        self.act()
        self.assertEqual(self.bot.ore_target, (8, 7))
        self.ore(7, 7, "iron", 3)
        self.assertEqual(self.act(), {"type": "mine"})


class ConstructionFundingTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = snapshot()
        self.view = self.snapshot["view"]
        self.view["teamResources"]["ours"]["iron"] = 5
        for rover in self.view["units"]:
            rover["inventory"]["gold"] = 6
        self.manager = Manager(self.snapshot, {"teamId": "ours"})

    def act(self):
        return self.manager.calculate_actions(self.snapshot)

    def gold_trades(self, actions):
        return [uid for uid, a in actions.items() if a == {"type": "trade", "from": "gold"}]

    def test_team_only_converts_one_batch_for_one_iron_shortfall(self):
        actions = self.act()
        self.assertEqual(self.gold_trades(actions), ["outside"])
        self.assertEqual(self.manager.funding_project["kind"], "base")
        self.assertEqual(self.manager.funding_project["iron_shortfall"], 1)
        point = self.manager.funding_project["site"]
        self.assertTrue(self.manager.base_planner.legal(point, "ours"))

    def test_existing_carried_iron_funds_project_without_gold_conversion(self):
        self.view["units"][2]["inventory"]["iron"] = 1
        actions = self.act()
        self.assertFalse(self.gold_trades(actions))
        self.assertTrue(self.manager.bots["outside"].ore_returning)

    def test_converted_iron_is_delivered_without_more_conversion_or_ore_detours(self):
        self.act()
        outside = self.view["units"][2]
        outside["inventory"] = {"gold": 3, "iron": 1}
        self.view["map"]["cells"][2 * 30 + 2] = {"type": "gold", "amount": 8}
        self.view["turn"] += 1
        actions = self.act()
        self.assertFalse(self.gold_trades(actions))
        self.assertEqual(actions["outside"]["type"], "move")
        outside["position"] = {"x": 2, "y": 3}
        self.view["turn"] += 1
        self.assertEqual(self.act()["outside"], {"type": "deposit"})
        outside["inventory"] = {"gold": 0, "iron": 0}
        self.view["teamResources"]["ours"]["iron"] = 6
        self.view["turn"] += 1
        self.act()
        self.assertTrue(any(b.state == "BuildBase" for b in self.manager.bots.values()))
        self.assertFalse(self.manager.bots["outside"].funding_return)

    def test_already_funded_build_does_not_consume_gold(self):
        self.manager.worker_target = 3
        self.view["teamResources"]["ours"]["iron"] = 6
        self.assertFalse(self.gold_trades(self.act()))
        self.assertTrue(any(b.state == "BuildBase" for b in self.manager.bots.values()))

    def test_no_viable_site_or_worker_slot_preserves_gold(self):
        self.manager.worker_target = 3
        self.view["map"]["cells"] = [{"type": "mountain"} for _ in range(900)]
        self.assertFalse(self.gold_trades(self.act()))
        self.assertIsNone(self.manager.funding_project)

    def test_late_project_preserves_gold(self):
        self.view["turn"] = 285
        self.assertFalse(self.gold_trades(self.act()))
        self.assertIsNone(self.manager.funding_project)

    def test_expensive_gold_funded_worker_is_rejected_but_native_iron_can_pay(self):
        self.manager.base_target = 1
        self.manager.worker_target = 10
        self.view["units"].extend([worker("four", 2, 3), worker("five", 2, 3)])
        self.view["turn"] = 170
        self.view["teamResources"]["ours"]["iron"] = 0
        actions = self.act()  # Sixth worker costs 28 iron, or 84 converted gold.
        self.assertEqual(self.manager.next_bot_cost, 28)
        self.assertFalse(self.gold_trades(actions))
        self.view["teamResources"]["ours"]["iron"] = 28
        self.assertTrue(any(a["type"] == "spawn" for a in self.act().values()))

    def test_bootstrap_worker_has_a_concrete_funding_project(self):
        self.view["units"] = self.view["units"][:1]
        self.view["teamResources"]["ours"]["iron"] = 4
        actions = self.act()
        self.assertEqual(self.manager.funding_project["kind"], "worker")
        self.assertEqual(self.manager.funding_project["worker"], "center-a")
        self.assertEqual(self.gold_trades(actions), ["center-a"])


class SharedBankRouteTests(unittest.TestCase):
    def test_return_actions_match_shortest_cost_to_any_base(self):
        view = snapshot(15, 15)["view"]
        view["bases"] = [base("left", 0, 0), base("right", 14, 14)]
        enemy = base("enemy", 7, 7)
        enemy["teamId"] = "enemy"
        view["bases"].append(enemy)
        for y in range(15):
            view["map"]["cells"][y * 15 + 4] = {"type": "mountain"}
            view["map"]["cells"][y * 15 + 9] = {"type": "hidden"}
        bank = Bank(view)
        bank.update(view, "ours")
        for start in ((4, 6), (8, 1), (9, 10), (5, 12), (0, 0)):
            bot = Bot("rover", "rover", "ours", start)
            expected = min(bank._path_cost(bank.grid, bank._path_through_hidden(
                bank.grid, {"x": start[0], "y": start[1]}, b["position"], view["bases"], "ours"
            ), hidden_penalty=1) for b in view["bases"] if b["teamId"] == "ours")
            path = []
            for _ in range(50):
                point, action = bank.next_action(bot)
                if action["type"] == "deposit":
                    break
                self.assertEqual(action["type"], "move")
                self.assertNotEqual(point, {"x": 7, "y": 7})
                path.append(point)
                bot.update_coordinates((point["x"], point["y"]))
            else:
                self.fail("Return route did not reach a base")
            self.assertEqual(bank._path_cost(bank.grid, path, hidden_penalty=1), expected)


if __name__ == "__main__":
    unittest.main()
