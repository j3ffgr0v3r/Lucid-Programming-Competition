"""Travel to a requested base site, replacing it when it cannot be used."""

from __future__ import annotations

from bot import Bot
from map_state import MapState
from bot_client import Action, Coordinate, CoordinateGrid, Direction, GameMap, MarsView
from .state import State


class BuildBase(State):
    """One shared behavior; each bot keeps its own target and selected site.

    Assign with assign(bot, {"x": 10, "y": 12}). Fallback sites minimize
    Manhattan distance from that target, then travel time from the bot.
    Routes use eight directions and the default three-turn obstacle cost.
    The manager supplies remembered terrain; never-seen targets are approached
    until revealed. Unseen enemy claims can still cause a build to fail.
    With center_only=True, maximize newly claimed center tiles within Manhattan
    distance two, then spread bases apart; every fallback stays in the center.
    """

    def __init__(self, grid: CoordinateGrid | GameMap | MapState, obstacle_cost: int = 3):
        super().__init__(grid)
        if not self._is_integer(obstacle_cost) or obstacle_cost < 1:
            raise ValueError("obstacle_cost must be a positive integer.")
        self.obstacle_cost = obstacle_cost
        self._reserved_sites: dict[str, tuple[int, int]] = {}
        self._remaining_iron = 0
        self._ore_searches = {}

    def update(self, view: MarsView, team_id: str) -> None:
        super().update(view, team_id)
        self._reserved_sites.clear()
        self._remaining_iron = view["teamResources"][team_id]["iron"]

    def set_iron_budget(self, iron: int) -> None:
        """Use only the bank iron left after higher-priority spawn orders."""
        self._remaining_iron = max(0, iron)

    def assign(self, bot: Bot, target: Coordinate, *, center_only: bool = False) -> None:
        """Start a new build task without changing another bot's target."""
        if self._cell(target) is None:
            raise ValueError("The base target must be an integer coordinate on the map.")
        bot.build_target = dict(target)
        bot.build_site = None
        bot.build_requested = False
        bot.build_in_center = center_only
        self._ore_searches.pop(bot.id, None)
        bot.set_state("BuildBase")

    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        if self.view is None or self.team_id is None:
            raise ValueError("Call update(view, team_id) before requesting a build action.")
        if bot.build_target is None:
            return None, {"type": "pass"}

        # Finish only after the server confirms a base, not after submitting.
        if bot.build_requested and any(
            base["teamId"] == self.team_id and base["position"] == bot.build_site
            for base in self.view["bases"]
        ):
            bot.build_requested = False
            bot.set_state(None)
            return None, {"type": "pass"}

        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is None or worker["readyOnTurn"] > self.view["turn"]:
            return None, {"type": "pass"}

        if self._remaining_iron < 6:
            return self._find_ore_near_target(bot, worker)

        origin = bot.coordinates
        target = (bot.build_target["x"], bot.build_target["y"])
        bases = {(base["position"]["x"], base["position"]["y"]): base for base in self.view["bases"]}
        enemy_bases = {point for point, base in bases.items() if base["teamId"] != self.team_id}
        occupied = {
            (unit["position"]["x"], unit["position"]["y"])
            for unit in self.view["units"] if unit["unitId"] != bot.id
        }
        reserved = {point for unit_id, point in self._reserved_sites.items() if unit_id != bot.id}
        distances, previous = self._routes(origin, enemy_bases, allow_hidden=bot.build_in_center)

        if bot.build_in_center:
            area = self.view["highGoldArea"]
            width = min(self.grid["width"], area["width"])
            height = min(self.grid["height"], area["height"])
            left = (self.grid["width"] - width) // 2
            top = (self.grid["height"] - height) // 2
            sites = [
                point for point in distances
                if left <= point[0] < left + width and top <= point[1] < top + height
                and self._cell({"x": point[0], "y": point[1]})["type"] in ("empty", "hidden")
                and point not in bases and point not in occupied and point not in reserved
                and all(abs(point[0] - x) + abs(point[1] - y) > 2 for x, y in enemy_bases)
            ]
            if not sites:
                bot.build_site = None
                bot.build_requested = False
                return None, {"type": "pass"}

            friendly = [point for point, base in bases.items() if base["teamId"] == self.team_id]
            center_tiles = {
                (x, y) for y in range(top, top + height) for x in range(left, left + width)
                if self._cell({"x": x, "y": y})["type"] != "void"
            }
            claimed = {
                point for point in center_tiles
                if any(abs(point[0] - x) + abs(point[1] - y) <= 2 for x, y in friendly + list(reserved))
            }

            def spacing(point):
                newly_claimed = sum(
                    (point[0] + dx, point[1] + dy) in center_tiles
                    and (point[0] + dx, point[1] + dy) not in claimed
                    for dy in range(-2, 3) for dx in range(-2, 3) if abs(dx) + abs(dy) <= 2
                )
                separations = [(point[0] - x) ** 2 + (point[1] - y) ** 2 for x, y in friendly]
                # For equal coverage, spread bases while keeping their claims inside.
                edge_distance = (2 * point[0] - (2 * left + width - 1)) ** 2 + (
                    2 * point[1] - (2 * top + height - 1)
                ) ** 2
                return (newly_claimed, min(separations, default=edge_distance), sum(separations),
                        -distances[point], -point[1], -point[0])

            target = max(sites, key=spacing)
            bot.build_target = {"x": target[0], "y": target[1]}

        target_cell = self._cell(bot.build_target)

        if target_cell is not None and target_cell["type"] == "hidden":
            # Move toward unexplored space without treating fog as empty land.
            destination = min(
                distances,
                key=lambda point: (max(abs(point[0] - target[0]), abs(point[1] - target[1])),
                                   distances[point], point),
            )
            bot.build_site = None
            bot.build_requested = False
            return self._move(origin, destination, previous)

        candidates = [
            point for point in distances
            if (not bot.build_in_center or point == target)
            and self._cell({"x": point[0], "y": point[1]})["type"] == "empty"
            and point not in bases and point not in occupied and point not in reserved
            and all(abs(point[0] - x) + abs(point[1] - y) > 2 for x, y in enemy_bases)
        ]
        if not candidates:
            bot.build_site = None
            bot.build_requested = False
            return None, {"type": "pass"}

        destination = min(
            candidates,
            key=lambda point: (abs(point[0] - target[0]) + abs(point[1] - target[1]),
                               distances[point], point),
        )
        bot.build_site = {"x": destination[0], "y": destination[1]}
        bot.build_requested = False
        self._reserved_sites[bot.id] = destination
        if destination != origin:
            return self._move(origin, destination, previous)
        if self._remaining_iron < 6:
            return None, {"type": "pass"}

        self._remaining_iron -= 6
        bot.build_requested = True
        return None, {"type": "build-base"}

    def _find_ore_near_target(self, bot: Bot, worker) -> tuple[Coordinate | None, Action]:
        """Search around this bot's base destination, preserving its build task."""
        template = self.states.get("FindAnyOreState")
        if template is None:
            return None, {"type": "pass"}
        target = bot.build_site or bot.build_target
        left, top = max(0, target["x"] - 2), max(0, target["y"] - 2)
        right = min(self.grid["width"], target["x"] + 3)
        bottom = min(self.grid["height"], target["y"] + 3)
        if bot.build_in_center:
            rich = self.view["highGoldArea"]
            width = min(self.grid["width"], rich["width"])
            height = min(self.grid["height"], rich["height"])
            center_left = (self.grid["width"] - width) // 2
            center_top = (self.grid["height"] - height) // 2
            left, top = max(left, center_left), max(top, center_top)
            right, bottom = min(right, center_left + width), min(bottom, center_top + height)
        if left >= right or top >= bottom:
            return None, {"type": "pass"}

        # Separate instances keep one bot's search bounds out of other tasks.
        bounds = (left, top, right, bottom)
        cached = self._ore_searches.get(bot.id)
        if cached is None or cached[0] != bounds or type(cached[1]) is not type(template):
            area = {"x": left, "y": top, "width": right - left, "height": bottom - top}
            source = self.map_state if self.map_state is not None else self.view
            cached = (bounds, type(template)(source, area))
            self._ore_searches[bot.id] = cached
        ore_state = cached[1]
        # Detach last turn's shared cache before update clears it.
        ore_state._route_cache = {}
        ore_state.update(self.view, self.team_id)
        ore_state.states = self.states
        ore_state._route_cache = self._route_cache
        ore_state.ore_reservations = self.ore_reservations

        inventory = worker.get("inventory", {"gold": 0, "iron": 0})
        carried = inventory["gold"] + inventory["iron"]
        banking = carried >= worker.get("inventoryCapacity", 8) or (carried > 0 and bot.ore_returning) or (carried > 0 and any(
            base["teamId"] == self.team_id
            and (base["position"]["x"], base["position"]["y"]) == bot.coordinates
            for base in self.view["bases"]
        ))
        x, y = bot.coordinates
        if not banking and not (left <= x < right and top <= y < bottom):
            # Reach the assigned area even when its ore is not visible yet.
            enemy_bases = {
                (base["position"]["x"], base["position"]["y"])
                for base in self.view["bases"] if base["teamId"] != self.team_id
            }
            distances, previous = self._routes(bot.coordinates, enemy_bases, allow_hidden=True)
            candidates = [point for point in distances if left <= point[0] < right and top <= point[1] < bottom]
            if not candidates:
                return None, {"type": "pass"}
            destination = min(candidates, key=lambda point: (
                abs(point[0] - target["x"]) + abs(point[1] - target["y"]), distances[point], point
            ))
            return self._move(bot.coordinates, destination, previous)

        result = ore_state.next_action(bot)
        return result if isinstance(result, tuple) else (None, result)

