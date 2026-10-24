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
    """

    def __init__(self, grid: CoordinateGrid | GameMap | MapState, obstacle_cost: int = 3):
        super().__init__(grid)
        if not self._is_integer(obstacle_cost) or obstacle_cost < 1:
            raise ValueError("obstacle_cost must be a positive integer.")
        self.obstacle_cost = obstacle_cost
        self._reserved_sites: dict[str, tuple[int, int]] = {}
        self._remaining_iron = 0

    def update(self, view: MarsView, team_id: str) -> None:
        super().update(view, team_id)
        self._reserved_sites.clear()
        self._remaining_iron = view["teamResources"][team_id]["iron"]

    def assign(self, bot: Bot, target: Coordinate) -> None:
        """Start a new build task without changing another bot's target."""
        if self._cell(target) is None:
            raise ValueError("The base target must be an integer coordinate on the map.")
        bot.build_target = dict(target)
        bot.build_site = None
        bot.build_requested = False
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
            # Keep the build assignment and target so we resume after banking.
            # The whole-map instance finds the nearest ore of either resource.
            ore_state = self.states.get("FindAnyOreState")
            if ore_state is None:
                return None, {"type": "pass"}
            result = ore_state.next_action(bot)
            return result if isinstance(result, tuple) else (None, result)

        origin = bot.coordinates
        target = (bot.build_target["x"], bot.build_target["y"])
        bases = {(base["position"]["x"], base["position"]["y"]): base for base in self.view["bases"]}
        enemy_bases = {point for point, base in bases.items() if base["teamId"] != self.team_id}
        occupied = {
            (unit["position"]["x"], unit["position"]["y"])
            for unit in self.view["units"] if unit["unitId"] != bot.id
        }
        reserved = {point for unit_id, point in self._reserved_sites.items() if unit_id != bot.id}
        distances, previous = self._routes(origin, enemy_bases)
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
            if self._cell({"x": point[0], "y": point[1]})["type"] == "empty"
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

