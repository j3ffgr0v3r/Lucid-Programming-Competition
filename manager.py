"""Team-level coordination of one Bot per friendly worker."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from inspect import getmembers, isabstract, isclass
from pkgutil import iter_modules
from math import ceil

import states
import ore_fallback
from bot import Bot
from base_planner import BasePlanner, CENTER_BASE_MIN, CENTER_BASE_MAX
from bot_client import ActionsByEntity, BotState, Identity, mars_view
from map_state import MapState
from states.state import State
from states.patrol_ore import PatrolOre
from states.trade import BANK_TURN_BUFFER
from states.ending import Ending


CONSTRUCTION_FRACTION = 3 / 5
BASE_TARGET_AREA = 100
WORKER_TARGET_AREA = 250
ENDING_RETURN_BUFFER = 2
ENDING_MIN_TURNS = 3
CENTER_SEARCH_BUFFER = 3
CENTER_BOT_COUNT = 2
LOOP_AVOID_TURNS = 4
# Conservative planning estimates, in eventual banked gold per remaining turn.
WORKER_GOLD_RATE = 0.15
BASE_GOLD_RATE = 0.10
FUNDING_GOLD_RATE = 0.15


def bot_costs() -> Iterator[int]:
    """Yield successive worker prices in banked iron: 5, 6, 11, 17, ..."""
    current, following = 5, 6
    while True:
        yield current
        current, following = following, current + following


class Manager:
    """Keep one manager per match; call calculate_actions each turn."""

    def __init__(self, game_state: BotState, identity: Identity) -> None:
        view = mars_view(game_state)
        if view is None:
            raise ValueError("Initialize Manager with an LPC game view.")

        self.team_id = identity["teamId"]
        self.match_id = game_state["match"]["matchId"]
        self.max_turns = game_state["match"].get("maxTurns", 480)
        self.phase = "construction"
        self.construction_end_turn = ceil(self.max_turns * CONSTRUCTION_FRACTION)
        self.base_target = max(1, ceil(view["map"]["width"] * view["map"]["height"] / BASE_TARGET_AREA))
        self.worker_target = max(1, ceil(view["map"]["width"] * view["map"]["height"] / WORKER_TARGET_AREA))
        self.bots: dict[str, Bot] = {}
        self._center_ids: set[str] = set()
        self._patrol_order: list[str] = []
        self._build_assignments: dict[str, tuple[int, int]] = {}
        self.funding_project = None
        self._gold_trade_ids: set[str] = set()
        self._bot_costs = bot_costs()
        self._recruited_workers = 0
        self.next_bot_cost = next(self._bot_costs)
        self.map_state = MapState(view)
        self.game_map = self.map_state.map
        self.base_planner = BasePlanner(self.map_state)

        # Discover the team's implementations before choosing any fallbacks.
        state_classes = {}
        for module_info in iter_modules(states.__path__, states.__name__ + "."):
            module = import_module(module_info.name)
            for name, state_class in getmembers(module, isclass):
                if (
                    state_class.__module__ == module.__name__
                    and issubclass(state_class, State)
                    and not isabstract(state_class)
                    # This configurable base is represented by its ore wrappers.
                    and name != "FindOreState"
                ):
                    if name in state_classes:
                        raise ValueError(f"Duplicate state class name: {name}")
                    state_classes[name] = state_class
        state_classes.setdefault("PatrolOre", PatrolOre)
        state_classes.setdefault("Ending", Ending)

        ore_names = ("FindAnyOreState", "FindIronState", "FindGoldState")
        for name in ore_names:
            state_classes.setdefault(name, getattr(ore_fallback, name))
        ore_module = import_module(state_classes["FindAnyOreState"].__module__)
        search_area_class = getattr(ore_module, "SearchArea", ore_fallback.SearchArea)
        width, height = self.game_map["width"], self.game_map["height"]
        whole_map = search_area_class(x=0, y=0, width=width, height=height)
        rich = self.map_state.highGoldArea
        center_width, center_height = min(width, rich["width"]), min(height, rich["height"])
        center_left, center_top = (width - center_width) // 2, (height - center_height) // 2
        left, top = max(0, center_left - CENTER_SEARCH_BUFFER), max(0, center_top - CENTER_SEARCH_BUFFER)
        right = min(width, center_left + center_width + CENTER_SEARCH_BUFFER)
        bottom = min(height, center_top + center_height + CENTER_SEARCH_BUFFER)
        self.center_search_area = search_area_class(x=left, y=top, width=right - left, height=bottom - top)
        self.center_area_index = 0
        self.search_areas = [self.center_search_area]
        self.states: dict[str, State] = {
            name: state_class(self.map_state, whole_map) if name in ore_names else state_class(self.map_state)
            for name, state_class in state_classes.items()
        }
        # SearchArea is constructor data, so cache one instance per region.
        self.ore_states = {
            name: [state_classes[name](self.map_state, area) for area in self.search_areas]
            for name in ore_names
        }
        self._all_states = list(self.states.values()) + [
            state for instances in self.ore_states.values() for state in instances
        ]
        # Trade resumes either this center search or the perimeter patrol.
        self.states["CenterOre"] = self.ore_states["FindAnyOreState"][self.center_area_index]
        for state in self._all_states:
            state.states = self.states

    def strategize(self):
        """Build the network, mine for gold, then return each rover in time."""
        our_bases = [b for b in self.map_state.bases if b["teamId"] == self.team_id]
        self.funding_project = None
        self._gold_trade_ids.clear()
        if self.phase == "construction" and (
            self.turn >= self.construction_end_turn
            or (len(our_bases) >= self.base_target and len(self.bots) >= self.worker_target)
        ):
            self.phase = "mining"
            self._build_assignments.clear()
        self._assign_search_roles()
        self.states["PatrolOre"].resource = None
        remaining = self.max_turns - self.turn
        for bot in self.bots.values():
            worker = self.workers[bot.id]
            if self.phase != "construction" or not worker.get("inventory", {}).get("iron", 0):
                bot.funding_return = False
            bank_turns = self.states["Bank"].turns_to_bank(bot)
            cooldown = max(0, worker["readyOnTurn"] - self.turn)
            conversions = worker.get("inventory", {}).get("iron", 0) // 3
            return_budget = (bank_turns if bank_turns is not None else 0) + cooldown + conversions + ENDING_RETURN_BUFFER
            bot.ending = bot.ending or remaining <= max(ENDING_MIN_TURNS, return_budget)
            bot.trade_from = None if self.phase == "construction" and not bot.ending else "iron"
            bot.return_buffer = ENDING_RETURN_BUFFER
            bot.set_state("Ending" if bot.ending else (
                "Trade" if self.phase != "construction" else
                "FindAnyOreState" if bot.id in self._center_ids else "PatrolOre"
            ))
        if self.bots and all(bot.ending for bot in self.bots.values()):
            self.phase = "ending"
        if self.phase != "construction":
            self.states["BuildBase"].set_iron_budget(0)
            return

        self._build_assignments = {
            uid: point for uid, point in self._build_assignments.items()
            if uid in self.bots and not self.bots[uid].ending
            and self.base_planner.legal(point, self.team_id)
            and self._can_finish_base(self.bots[uid], point)
        }
        iron = self.bank["iron"]
        # Bootstrap the first few rovers, then reserve base funding so growing
        # worker prices cannot consume every deposit before a depot is built.
        build_slots = min(max(1, len(self.bots) // 3), max(0, self.base_target - len(our_bases)), iron // 6)
        if len(self.bots) < min(3 + len(our_bases) // 3, self.worker_target):
            build_slots = 0
        assigned = []
        for uid in sorted(self._build_assignments):
            if len(assigned) >= build_slots:
                break
            assigned.append(uid)
        while len(assigned) < build_slots:
            reserved = [self._build_assignments[uid] for uid in assigned]
            center_count = sum(self.base_planner.in_center((b["position"]["x"], b["position"]["y"])) for b in our_bases)
            center_count += sum(self.base_planner.in_center(p) for p in reserved)
            outside_count = len(our_bases) + len(reserved) - center_count
            prefer_center = center_count < CENTER_BASE_MIN or (center_count < CENTER_BASE_MAX and outside_count >= 2)
            selected = self._new_build_assignment(assigned, reserved, prefer_center, center_count)
            if selected is None:
                break
            uid, point = selected
            self._build_assignments[uid] = point
            assigned.append(uid)
            self.states["BuildBase"].assign(
                self.bots[uid], {"x": point[0], "y": point[1]},
                center_only=self.base_planner.in_center(point), planned=True,
            )
        for uid in assigned:
            self.bots[uid].set_state("BuildBase")
        iron -= 6 * len(assigned)
        prices = bot_costs()
        for _ in range(self._recruited_workers):
            next(prices)
        price = next(prices)
        recruits = 0
        ready = sorted((bot for bot in self.bots.values()
                        if bot.id not in assigned and not bot.ending
                        and self.workers[bot.id]["readyOnTurn"] <= self.turn),
                       key=lambda bot: (bot.id in self._center_ids, bot.id))
        for bot in ready:
            if (len(self.bots) + recruits >= self.worker_target or iron < price
                    or not self._project_pays_back("worker", price, 0, 0, 0)):
                break
            bot.set_state("SpawnBot")
            recruits += 1
            iron -= price
            price = next(prices)
        self.states["BuildBase"].set_iron_budget(6 * len(assigned))
        self._plan_gold_funding(our_bases, assigned, iron, recruits, price)

    def _project_pays_back(self, kind, cost, converted_iron, funding_turns, travel_turns):
        # Banked/native iron's opportunity cost is one gold per three iron;
        # manufacturing iron consumes three gold per iron instead.
        gold_cost = (cost - converted_iron) / 3 + converted_iron * 3
        rate = WORKER_GOLD_RATE if kind == "worker" else BASE_GOLD_RATE
        productive_turns = self.max_turns - self.turn - funding_turns - travel_turns - 1
        return productive_turns * rate >= gold_cost

    def _can_finish_base(self, bot, point):
        enemies = {(b["position"]["x"], b["position"]["y"])
                   for b in self.map_state.bases if b["teamId"] != self.team_id}
        routes, _ = self.states["BuildBase"]._routes(bot.coordinates, enemies, allow_hidden=True)
        travel = routes.get(point, float("inf")) + max(0, self.workers[bot.id]["readyOnTurn"] - self.turn)
        return (travel + 1 < self.construction_end_turn - self.turn
                and self._project_pays_back("base", 6, 0, 0, travel))

    def _plan_gold_funding(self, bases, assigned, iron, recruits, next_price):
        """Fund one concrete next project, capped by its shared iron shortfall."""
        committed = assigned + [b.id for b in self.bots.values() if b.state == "SpawnBot"]
        free = [b for b in self.bots.values() if b.id not in committed and not b.ending]
        if not free:
            return
        bank = self.states["Bank"]
        deliveries = {}
        for bot in free:
            travel = bank.turns_to_bank(bot)
            if travel is not None:
                deliveries[bot.id] = travel + max(0, self.workers[bot.id]["readyOnTurn"] - self.turn)
        donors = [b for b in free if b.id in deliveries
                  and deliveries[b.id] + 1 < self.construction_end_turn - self.turn]
        carried_iron = sum(self.workers[b.id]["inventory"]["iron"] for b in donors)
        gold_batches = sum(self.workers[b.id]["inventory"]["gold"] // 3 for b in donors)
        if not gold_batches:
            return

        bootstrap = len(self.bots) + recruits < min(3 + len(bases) // 3, self.worker_target)
        projects = []
        if len(self.bots) + recruits < self.worker_target:
            projects.append({"kind": "worker", "cost": next_price, "travel": 0,
                             "worker": min(free, key=lambda b: b.id).id})
        if not bootstrap and len(bases) + len(assigned) < self.base_target and len(assigned) < max(1, len(self.bots) // 3):
            reserved = [self._build_assignments[uid] for uid in assigned]
            center_count = sum(self.base_planner.in_center((b["position"]["x"], b["position"]["y"])) for b in bases)
            center_count += sum(self.base_planner.in_center(p) for p in reserved)
            outside_count = len(bases) + len(reserved) - center_count
            prefer_center = center_count < CENTER_BASE_MIN or (center_count < CENTER_BASE_MAX and outside_count >= 2)
            selected = next(((uid, p) for uid, p in self._build_assignments.items() if uid not in committed), None)
            if selected is None:
                selected = self._new_build_assignment(committed, reserved, prefer_center, center_count)
            if selected is not None:
                uid, point = selected
                enemies = {(b["position"]["x"], b["position"]["y"])
                           for b in self.map_state.bases if b["teamId"] != self.team_id}
                routes, _ = self.states["BuildBase"]._routes(self.bots[uid].coordinates, enemies, allow_hidden=True)
                travel = routes.get(point, float("inf"))
                projects.insert(0, {"kind": "base", "cost": 6, "travel": travel,
                                    "worker": uid, "site": point})

        for project in projects:
            shortfall = max(0, project["cost"] - iron - carried_iron)
            if shortfall == 0:
                # Incoming iron already funds the next project. Do not also
                # count it toward another purchase and convert extra gold.
                self._return_project_iron(donors, deliveries, project["cost"] - iron)
                return
            # Include time to collect missing gold, exchange it, and bank it.
            gather = max(0, shortfall - gold_batches) * 3 / (len(donors) * FUNDING_GOLD_RATE)
            funding_turns = gather + max(deliveries[b.id] for b in donors) + min(shortfall, 2)
            if funding_turns + project["travel"] + 1 >= self.construction_end_turn - self.turn:
                continue
            if not self._project_pays_back(project["kind"], project["cost"], shortfall, funding_turns, project["travel"]):
                continue
            self.funding_project = dict(project, iron_shortfall=shortfall)
            self._return_project_iron(donors, deliveries, project["cost"] - iron)
            if project["kind"] == "base":
                uid, point = project["worker"], project["site"]
                if uid not in self._build_assignments:
                    self._build_assignments[uid] = point
                    bot = self.bots[uid]
                    state = bot.state
                    self.states["BuildBase"].assign(bot, {"x": point[0], "y": point[1]},
                                                  center_only=self.base_planner.in_center(point), planned=True)
                    bot.set_state(state)
            for bot in sorted(donors, key=lambda b: (deliveries[b.id], b.id)):
                worker = self.workers[bot.id]
                if shortfall and worker["inventory"]["gold"] >= 3 and worker["readyOnTurn"] <= self.turn:
                    self._gold_trade_ids.add(bot.id)
                    bot.trade_from = "gold"
                    shortfall -= 1
            return

    def _return_project_iron(self, donors, deliveries, needed):
        for bot in sorted(donors, key=lambda b: (deliveries[b.id], b.id)):
            carried = self.workers[bot.id]["inventory"]["iron"]
            if needed > 0 and carried:
                bot.ore_returning = True
                bot.funding_return = True
                needed -= carried

    def _new_build_assignment(self, assigned, reserved, prefer_center, center_count):
        planner, build = self.base_planner, self.states["BuildBase"]
        enemies = {(b["position"]["x"], b["position"]["y"])
                   for b in self.map_state.bases if b["teamId"] != self.team_id}
        available = [bot for bot in self.bots.values() if bot.id not in assigned and not bot.ending]
        occupied = {}
        for unit in build.view["units"]:
            point = (unit["position"]["x"], unit["position"]["y"])
            occupied.setdefault(point, set()).add(unit["unitId"])
        for center in (prefer_center, not prefer_center):
            if center and center_count >= CENTER_BASE_MAX:
                continue
            candidates = [bot for bot in available if (bot.id in self._center_ids) == center]
            if not candidates:
                continue
            routes = {bot.id: build._routes(bot.coordinates, enemies, allow_hidden=True)[0] for bot in candidates}
            for point in planner.ranked_sites(self.team_id, center=center, reserved=reserved):
                eligible = [bot for bot in candidates
                            if point in routes[bot.id]
                            and not (occupied.get(point, set()) - {bot.id})
                            and (center or self.states["PatrolOre"].in_sector(point, bot))
                            and routes[bot.id][point] + 1 < self.construction_end_turn - self.turn
                            and self._project_pays_back("base", 6, 0, 0, routes[bot.id][point])]
                if eligible:
                    bot = min(eligible, key=lambda bot: (routes[bot.id][point], bot.id))
                    return bot.id, point
        return None

    def _assign_search_roles(self):
        """Keep two center rovers and give every outside rover its own arc."""
        center = (self.game_map["width"] // 2, self.game_map["height"] // 2)
        candidates = sorted(self.bots.values(), key=lambda bot: (
            bot.id not in self._center_ids,
            (bot.coordinates[0] - center[0]) ** 2 + (bot.coordinates[1] - center[1]) ** 2,
            bot.id,
        ))
        self._center_ids = {bot.id for bot in candidates[:CENTER_BOT_COUNT]}
        outside = set(self.bots) - self._center_ids
        patrol = self.states["PatrolOre"]
        order = [uid for uid in self._patrol_order if uid in outside]
        order.extend(sorted(outside - set(order), key=lambda uid: (patrol.sector_index(self.bots[uid].coordinates), uid)))
        self._patrol_order = order
        for bot in self.bots.values():
            bot.search_area_index = self.center_area_index if bot.id in self._center_ids else None
            if bot.id in self._center_ids:
                bot.patrol_sector = None
        for i, uid in enumerate(order):
            bot = self.bots[uid]
            sector = (i * len(patrol.circuit) // len(order), (i + 1) * len(patrol.circuit) // len(order))
            if bot.patrol_sector != sector:
                bot.patrol_sector = sector
                bot.patrol_cursor = None
                bot.ore_target = None
            bot.patrol_direction = bot.patrol_direction or 1

    def _mine_on_the_way(self, bot, worker, action):
        """Pause travel to mine underfoot while preserving the assigned trip."""
        if action["type"] != "move" or bot.ending or (bot.funding_return and bot.ore_returning):
            return action
        inventory = worker.get("inventory", {"gold": 0, "iron": 0})
        room = worker.get("inventoryCapacity", 8) - sum(inventory.values())
        x, y = bot.coordinates
        cell = self.game_map["cells"][y * self.game_map["width"] + x]
        if room <= 0 or cell["type"] not in ("iron", "gold") or cell.get("amount", 0) <= 0:
            return action
        owners = {
            base["teamId"] for base in self.map_state.bases
            if abs(base["position"]["x"] - x) + abs(base["position"]["y"] - y) <= 2
        }
        if owners and self.team_id not in owners:
            return action
        if self.phase != "construction":
            bank_turns = self.states["Bank"].turns_to_bank(bot)
            trades = (inventory["iron"] + (cell["type"] == "iron")) // 3
            if bank_turns is None or self.max_turns - self.turn <= bank_turns + trades + BANK_TURN_BUFFER + 1:
                return action
        reservations = self.states["BuildBase"].ore_reservations
        reserved = sum(amount for unit_id, amount in reservations.get((x, y), {}).items() if unit_id != bot.id)
        if cell["amount"] <= reserved:
            return action
        if not self.states["PatrolOre"].can_finish_ore_trip(
            bot, worker, (x, y), 0, cell["amount"] - reserved
        ):
            return action
        # The proposed move may have reserved a distant deposit. Release it
        # while this rover fills its cargo here, without discarding its target.
        for claims in reservations.values():
            claims.pop(bot.id, None)
        reservations.setdefault((x, y), {})[bot.id] = min(room, cell["amount"] - reserved)
        return {"type": "mine"}

    def calculate_actions(self, game_state: BotState) -> ActionsByEntity:
        """Refresh bots, assign their states, then collect their actions."""
        if game_state["match"]["matchId"] != self.match_id:
            raise ValueError("Create a new Manager for each match.")
        view = mars_view(game_state)
        if view is None:
            return {}

        self.turn = view["turn"]
        self.map_state.update(view)
        self.game_map = self.map_state.map
        self.bank = view["teamResources"][self.team_id]
        workers = self.workers = {
            worker["unitId"]: worker
            for worker in view["units"]
            if worker["teamId"] == self.team_id
        }

        # One starting worker is free. Advance only for confirmed recruits.
        while self._recruited_workers < len(workers) - 1:
            self.next_bot_cost = next(self._bot_costs)
            self._recruited_workers += 1

        # Refresh every bot before any bot chooses an action.
        self.bots = {unit_id: bot for unit_id, bot in self.bots.items() if unit_id in workers}
        for unit_id, worker in workers.items():
            position = worker["position"]
            coordinates = (position["x"], position["y"])
            if unit_id not in self.bots:
                self.bots[unit_id] = Bot(name=unit_id, id=unit_id, team_id=self.team_id, coordinates=coordinates)
            else:
                bot = self.bots[unit_id]
                if coordinates != bot.coordinates:
                    if bot.last_action_type == "move":
                        bot.movement_history = (bot.movement_history + [coordinates])[-5:]
                    else:
                        bot.movement_history = [coordinates]
                elif bot.last_action_type not in ("move", "pass"):
                    bot.movement_history = [coordinates]
                history = bot.movement_history
                if len(history) == 5 and history[0] == history[2] == history[4] and history[1] == history[3]:
                    bot.avoid_steps[history[-2]] = self.turn + LOOP_AVOID_TURNS
                    bot.movement_history = [coordinates]
                bot.update_coordinates(coordinates)
            bot = self.bots[unit_id]
            bot.avoid_steps = {point: until for point, until in bot.avoid_steps.items() if until > self.turn}

        # Route over remembered terrain and bases, with fresh units and bank.
        planning_view = dict(view, map=self.game_map, bases=self.map_state.bases)
        route_cache = {}
        ore_reservations = {}
        for state in self._all_states:
            state.update(planning_view, self.team_id)
            state.turns_left = max(0, self.max_turns - self.turn)
            # All states use the same remembered map this turn.
            state._route_cache = route_cache
            state.ore_reservations = ore_reservations

        self.strategize()

        actions: ActionsByEntity = {}
        # Spawns spend first. Established miners reserve before incoming rovers,
        # and rovers already traveling to ore reserve before choosing new targets.
        def action_order(item):
            unit_id, bot = item
            x, y = bot.coordinates
            cell = self.game_map["cells"][y * self.game_map["width"] + x]
            on_ore = cell["type"] in ("iron", "gold") and cell.get("amount", 0) > 0
            target_cell = (
                self.game_map["cells"][bot.ore_target[1] * self.game_map["width"] + bot.ore_target[0]]
                if bot.ore_target is not None else {}
            )
            has_target = target_cell.get("type") in ("iron", "gold") and target_cell.get("amount", 0) > 0
            return (bot.state != "SpawnBot", not on_ore, not has_target, unit_id)

        ordered_bots = sorted(self.bots.items(), key=action_order)
        for unit_id, bot in ordered_bots:
            if workers[unit_id]["readyOnTurn"] > self.turn or bot.state is None:
                actions[unit_id] = {"type": "pass"}
            else:
                # Recovery belongs to this rover, even when several workers
                # share its tile. Route cache keys include the avoided steps.
                avoidance = {bot.coordinates: frozenset(bot.avoid_steps)} if bot.avoid_steps else {}
                for shared_state in self._all_states:
                    shared_state.route_avoidance = avoidance
                state = self.states[bot.state]
                if bot.state in self.ore_states and bot.search_area_index is not None:
                    state = self.ore_states[bot.state][bot.search_area_index]
                if unit_id in self._gold_trade_ids:
                    action = {"type": "trade", "from": "gold"}
                    bot.ore_returning = True
                    bot.funding_return = True
                else:
                    result = state.next_action(bot)
                    action = result[1] if isinstance(result, tuple) else result
                actions[unit_id] = self._mine_on_the_way(bot, workers[unit_id], action)
                # Coordinates come from the next server snapshot, not the
                # requested destination: movement may fail or be interrupted.
            bot.last_action_type = actions[unit_id]["type"]
        return actions
