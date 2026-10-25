"""Collect eligible ore, explore unseen tiles, and return cargo without oscillating."""

from bot import Bot
from typing import TypedDict

from bot_client import Action, MarsView, Resource
from map_state import MapState
from states.state import State

ORE_RECHECK_TURNS = 12


class SearchArea(TypedDict):
    """Rectangular search area, with a top-left coordinate and dimensions."""

    x: int
    y: int
    width: int
    height: int


class FindOreState(State):
    """Shared ore behavior; each bot owns its target and banking progress."""

    def __init__(
        self, view: MarsView | MapState, resource: Resource | None, area: SearchArea | None = None
    ) -> None:
        if resource is not None and resource not in ("iron", "gold"):
            raise ValueError(f"Unsupported ore resource: {resource}")
        super().__init__(view)
        self.resource = resource
        self.area = area

    def next_action(self, bot: Bot) -> Action:
        if self.view is None:
            return {"type": "pass"}
        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is not None and worker["readyOnTurn"] > self.view["turn"]:
            return {"type": "pass"}

        inventory = worker.get("inventory", {"gold": 0, "iron": 0}) if worker else {"gold": 0, "iron": 0}
        carried = inventory["gold"] + inventory["iron"]
        capacity = worker.get("inventoryCapacity", 8) if worker else 8
        bounds = self._area_bounds()
        if self.area is not None and bounds is None:
            return {"type": "pass"}

        scope = (self.resource, bounds)
        if bot.ore_search_scope != scope:
            bot.ore_search_scope = scope
            bot.ore_target = None
            bot.ore_explore_target = None
        if not carried:
            bot.ore_returning = False
        if carried and any(
            base["teamId"] == bot.team_id
            and (base["position"]["x"], base["position"]["y"]) == bot.coordinates
            for base in self.view["bases"]
        ):
            return {"type": "deposit"}
        if carried >= capacity or (carried and bot.ore_returning):
            return self._bank_action(bot)

        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != bot.team_id
        }
        # Remembered ore can be reached across unexplored gaps. Replan each turn
        # as terrain becomes visible, while retaining the selected destination.
        distances, previous = self._ore_routes(bot, enemy_bases)
        ores = set()
        for index, cell in enumerate(self.grid["cells"]):
            if cell["type"] not in ("iron", "gold") or cell.get("amount", 0) <= 0:
                continue
            if not self._resource_allowed(cell):
                continue
            point = (index % self.grid["width"], index // self.grid["width"])
            if point not in distances or not self._ore_allowed(point, bot, bounds):
                continue
            owners = {
                base["teamId"] for base in self.view["bases"]
                if abs(base["position"]["x"] - point[0]) + abs(base["position"]["y"] - point[1]) <= 2
            }
            if not owners or bot.team_id in owners:
                ores.add(point)

        def available(point):
            cell = self.grid["cells"][point[1] * self.grid["width"] + point[0]]
            reserved = sum(
                amount for unit_id, amount in self.ore_reservations.get(point, {}).items()
                if unit_id != bot.id
            )
            return max(0, cell["amount"] - reserved)

        # Reserve only the cargo room a miner can fill. Large deposits can
        # support several rovers; small deposits should not draw the whole team.
        ores = {
            point for point in ores if available(point) > 0
            and self.can_finish_ore_trip(bot, worker, point, distances[point], available(point))
        }
        # Keep mining underfoot; do not break the mining streak for another target.
        if bot.coordinates in ores:
            bot.ore_target = bot.coordinates
        elif bot.ore_target not in ores:
            bot.ore_target = min(
                ores, key=lambda point: self._ore_priority(point, distances, bot, worker, available(point)), default=None
            )
        if bot.ore_target is not None:
            self.ore_reservations.setdefault(bot.ore_target, {})[bot.id] = min(
                capacity - carried, available(bot.ore_target)
            )
            bot.ore_explore_target = None
            if bot.ore_target == bot.coordinates:
                return {"type": "mine"}
            return self._move(bot.coordinates, bot.ore_target, previous)[1]

        if carried:
            # A depleted small deposit should still become banked resources.
            return self._bank_action(bot)
        return self._explore(bot, bounds, distances, previous)

    def can_finish_ore_trip(self, bot, worker, point, travel_turns, amount) -> bool:
        """Budget the smallest useful pickup, conversion, return, and deposit."""
        if self.turns_left is None:
            return True
        inventory = worker.get("inventory", {"gold": 0, "iron": 0}) if worker else {"gold": 0, "iron": 0}
        capacity = worker.get("inventoryCapacity", 8) if worker else 8
        cell = self.grid["cells"][point[1] * self.grid["width"] + point[0]]
        mining_turns = 1
        trade_turns = 0
        conversion = bot.trade_from or ("iron" if bot.state == "Trade" else None)
        if conversion is not None:
            if conversion == "iron" and cell["type"] == "iron":
                # One or two iron alone cannot produce banked gold. Account
                # for enough mining to complete a batch of three.
                mining_turns = 3 - inventory["iron"] % 3
            trade_turns = (inventory[conversion] + (mining_turns if cell["type"] == conversion else 0)) // 3
        if mining_turns > amount or mining_turns > capacity - sum(inventory.values()):
            return False

        return_turns = self._return_turns(point, bot)
        return travel_turns + mining_turns + trade_turns + return_turns + 1 + bot.return_buffer <= self.turns_left

    def _return_turns(self, point, bot):
        bank = self.states.get("Bank")
        if bank is not None:
            # Share a reverse search across all deposits and workers; retain
            # the conservative three-turn estimate for unseen terrain.
            return bank.travel_turns_from(point, bot.team_id, hidden_penalty=self.obstacle_cost - 1)
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != bot.team_id
        }
        return_turns = float("inf")
        for base in self.view["bases"]:
            if base["teamId"] != bot.team_id:
                continue
            home = (base["position"]["x"], base["position"]["y"])
            # Ore and base endpoints both take one turn to enter, so travel
            # cost is symmetric. Cache one route map per base for all rovers.
            # Banking may leave a patrol's perimeter to take the fastest route.
            distances, _ = State._routes(self, home, enemy_bases, allow_hidden=True)
            return_turns = min(return_turns, distances.get(point, float("inf")))
        return return_turns

    def _bank_action(self, bot: Bot) -> Action:
        bot.ore_returning = True
        bot.ore_target = None
        bot.ore_explore_target = None
        bank = self.states.get("Bank")
        if bank is not None:
            result = bank.next_action(bot)
            return result[1] if isinstance(result, tuple) else result

        # Standalone ore states also work without a manager-owned Bank instance.
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != bot.team_id
        }
        distances, previous = self._routes(bot.coordinates, enemy_bases, allow_hidden=True)
        destinations = [
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] == bot.team_id
            and (base["position"]["x"], base["position"]["y"]) in distances
        ]
        if not destinations:
            return {"type": "pass"}
        target = min(destinations, key=lambda point: (distances[point], point))
        if target == bot.coordinates:
            return {"type": "deposit"}
        return self._move(bot.coordinates, target, previous)[1]

    def _explore(self, bot: Bot, bounds, distances, previous) -> Action:
        unseen = {
            point for point in distances
            if point != bot.coordinates and self._inside(point, bounds)
            and self._cell({"x": point[0], "y": point[1]})["type"] == "hidden"
        }
        # Explored terrain can receive new ore while outside our vision.
        # Revisit old observations only after exhausting unexplored tiles.
        if not unseen and self.map_state is not None:
            unseen = {
                point for point in distances
                if point != bot.coordinates and self._inside(point, bounds)
                and 0 <= self.map_state.last_seen[point[1] * self.grid["width"] + point[0]]
                <= self.view["turn"] - ORE_RECHECK_TURNS
            }
        if bot.ore_explore_target not in unseen:
            bot.ore_explore_target = min(
                unseen, key=lambda point: (distances[point], point[1], point[0]), default=None
            )
        if bot.ore_explore_target is not None:
            return self._move(bot.coordinates, bot.ore_explore_target, previous)[1]

        # With no unseen or stale tiles or eligible ore, enter the assigned region once
        # and wait for new information. Never pick an adjacent empty tile just
        # because the path to the current tile is empty.
        if bounds is None:
            rich = self.view["highGoldArea"]
            width = min(self.grid["width"], rich["width"])
            height = min(self.grid["height"], rich["height"])
            left, top = (self.grid["width"] - width) // 2, (self.grid["height"] - height) // 2
            bounds = (left, top, left + width, top + height)
        if self._inside(bot.coordinates, bounds):
            return {"type": "pass"}
        candidates = [point for point in distances if self._inside(point, bounds)]
        if not candidates:
            return {"type": "pass"}
        target = min(candidates, key=lambda point: (distances[point], point[1], point[0]))
        return self._move(bot.coordinates, target, previous)[1]

    @staticmethod
    def _inside(point, bounds) -> bool:
        return bounds is None or (bounds[0] <= point[0] < bounds[2] and bounds[1] <= point[1] < bounds[3])

    def _ore_allowed(self, point, bot, bounds) -> bool:
        return self._inside(point, bounds)

    def _resource_allowed(self, cell) -> bool:
        return self.resource is None or cell["type"] == self.resource

    def _ore_priority(self, point, distances, bot=None, worker=None, amount=None):
        if bot is None or not (bot.trade_from == "iron" or bot.state == "Trade"):
            # Construction collects resources for its selected projects.
            return distances[point], point[1], point[0]
        inventory = worker.get("inventory", {"gold": 0, "iron": 0}) if worker else {"gold": 0, "iron": 0}
        capacity = worker.get("inventoryCapacity", 8) if worker else 8
        cell = self.grid["cells"][point[1] * self.grid["width"] + point[0]]
        stock = cell["amount"] if amount is None else amount
        return_turns = self._return_turns(point, bot)
        best_rate = 0.0
        for pickup in range(1, min(stock, capacity - sum(inventory.values())) + 1):
            iron = inventory["iron"] + (pickup if cell["type"] == "iron" else 0)
            trades = iron // 3
            gold = pickup if cell["type"] == "gold" else trades - inventory["iron"] // 3
            turns = distances[point] + pickup + trades + return_turns + 1
            if self.turns_left is None or turns + bot.return_buffer <= self.turns_left:
                best_rate = max(best_rate, gold / turns)
        return -best_rate, distances[point] + return_turns, distances[point], point[1], point[0]

    def _ore_routes(self, bot, enemy_bases):
        return self._routes(bot.coordinates, enemy_bases, allow_hidden=True)

    def _area_bounds(self) -> tuple[int, int, int, int] | None:
        if self.area is None:
            return None
        left = max(0, self.area["x"])
        top = max(0, self.area["y"])
        right = min(self.grid["width"], self.area["x"] + self.area["width"])
        bottom = min(self.grid["height"], self.area["y"] + self.area["height"])
        if self.area["width"] <= 0 or self.area["height"] <= 0 or left >= right or top >= bottom:
            return None
        return left, top, right, bottom
