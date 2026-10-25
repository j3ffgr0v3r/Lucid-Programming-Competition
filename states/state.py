from __future__ import annotations

from abc import ABC, abstractmethod
from heapq import heappop, heappush
from typing import TYPE_CHECKING
from map_state import MapState

if TYPE_CHECKING:
    from bot import Bot
from bot_client import (
    Action,
    Coordinate,
    CoordinateGrid,
    GameMap,
    MarsView,
    Direction,
)

class State(ABC):
    """Shared behavior that selects an action for the supplied bot.

    The manager creates each concrete state once and refreshes its grid each
    turn. Keep per-bot progress on the bot, since state instances are shared.
    """

    def __init__(self, source: CoordinateGrid | GameMap | MarsView | MapState):
        # Keep persistent map memory separate from the live per-turn snapshot.
        self.map_state = source if isinstance(source, MapState) else None
        if self.map_state is not None:
            source = MarsView(
                turn=0, map=self.map_state.map, bases=self.map_state.bases,
                highGoldArea=self.map_state.highGoldArea, units=[], scores={},
                teamResources={}, warnings=[], info=[], effects=[],
            )
        self.view: MarsView | None = source if "map" in source else None
        self.grid = self.view["map"] if self.view is not None else source
        self.team_id: str | None = None
        self.turns_left: int | None = None
        self.states: dict[str, State] = {}
        self.obstacle_cost = 3
        self._route_cache = {}
        self.ore_reservations: dict[tuple[int, int], dict[str, int]] = {}
        self.route_avoidance: dict[tuple[int, int], frozenset[tuple[int, int]]] = {}

    def update(self, view: MarsView, team_id: str) -> None:
        """Refresh shared world data before any bot requests an action."""
        self.grid = view["map"]
        self.view = view
        self.team_id = team_id
        self._route_cache.clear()
        # Replace rather than clear: other states may still share the old dict.
        self.ore_reservations = {}
        self.route_avoidance = {}


    @abstractmethod
    def next_action(self, bot: Bot) -> Action | tuple[Coordinate | None, Action]:
        """Return an action, optionally paired with a requested move destination."""
        raise NotImplementedError


    def _cell(self, point: Coordinate):
        x, y = point["x"], point["y"]
        if not self._is_integer(x) or not self._is_integer(y):
            return None
        if not (0 <= x < self.grid["width"] and 0 <= y < self.grid["height"]):
            return None

        row_start = y * self.grid["width"]
        return self.grid["cells"][row_start + x]


    def _is_integer(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def _routes(self, origin, enemy_bases, *, allow_hidden=False, allowed_cells=None, preferred_cells=None):
        """Dijkstra distances in turns, including entry cooldowns."""
        blocked = frozenset(enemy_bases) | self.route_avoidance.get(origin, frozenset())
        key = (origin, blocked, self.obstacle_cost, allow_hidden, allowed_cells, preferred_cells)
        if key in self._route_cache:
            return self._route_cache[key]
        distances = {origin: 0}
        deviations = {origin: 0}
        previous = {}
        queue = [(0, 0, origin)]
        width, height, cells = self.grid["width"], self.grid["height"], self.grid["cells"]
        while queue:
            cost, deviation, point = heappop(queue)
            if (cost, deviation) != (distances[point], deviations[point]):
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    neighbor = (point[0] + dx, point[1] + dy)
                    x, y = neighbor
                    if not (0 <= x < width and 0 <= y < height):
                        continue
                    if allowed_cells is not None and neighbor not in allowed_cells:
                        continue
                    # Dijkstra's generated neighbors are already integers.
                    cell = cells[y * width + x]
                    if cell["type"] == "void" or neighbor in blocked:
                        continue
                    if cell["type"] == "hidden" and not allow_hidden:
                        continue
                    # Exploration estimates unknown terrain conservatively.
                    step_cost = self.obstacle_cost if cell["type"] in ("mountain", "crater", "hidden") else 1
                    candidate = cost + step_cost
                    candidate_deviation = deviation + int(preferred_cells is not None and neighbor not in preferred_cells)
                    if (candidate, candidate_deviation) < (distances.get(neighbor, float("inf")), deviations.get(neighbor, 0)):
                        distances[neighbor] = candidate
                        deviations[neighbor] = candidate_deviation
                        previous[neighbor] = point
                        heappush(queue, (candidate, candidate_deviation, neighbor))
        self._route_cache[key] = (distances, previous)
        return self._route_cache[key]

    def _move(self, origin, destination, previous) -> tuple[Coordinate | None, Action]:
        if destination == origin:
            return None, {"type": "pass"}
        step = destination
        while previous[step] != origin:
            step = previous[step]
        dx, dy = step[0] - origin[0], step[1] - origin[1]
        directions: dict[tuple[int, int], Direction] = {
            (0, -1): "north", (1, -1): "north-east", (1, 0): "east",
            (1, 1): "south-east", (0, 1): "south", (-1, 1): "south-west",
            (-1, 0): "west", (-1, -1): "north-west",
        }
        return {"x": step[0], "y": step[1]}, {"type": "move", "direction": directions[(dx, dy)]}
