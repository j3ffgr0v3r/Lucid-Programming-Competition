from __future__ import annotations

from abc import ABC, abstractmethod
from heapq import heappop, heappush
from typing import TYPE_CHECKING

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

    def __init__(self, source: CoordinateGrid | GameMap | MarsView):
        # Older movement states supply a grid; ore states supply a full view.
        self.view: MarsView | None = source if "map" in source else None
        self.grid = self.view["map"] if self.view is not None else source
        self.team_id: str | None = None
        self.states: dict[str, State] = {}
        self.obstacle_cost = 3
        self._route_cache = {}

    def update(self, view: MarsView, team_id: str) -> None:
        """Refresh shared world data before any bot requests an action."""
        self.grid = view["map"]
        self.view = view
        self.team_id = team_id
        self._route_cache.clear()


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

    def _routes(self, origin, enemy_bases):
        """Dijkstra distances in turns, including entry cooldowns."""
        key = (origin, frozenset(enemy_bases), self.obstacle_cost)
        if key in self._route_cache:
            return self._route_cache[key]
        distances = {origin: 0}
        previous = {}
        queue = [(0, origin)]
        while queue:
            cost, point = heappop(queue)
            if cost != distances[point]:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    neighbor = (point[0] + dx, point[1] + dy)
                    cell = self._cell({"x": neighbor[0], "y": neighbor[1]})
                    if cell is None or cell["type"] in ("hidden", "void") or neighbor in enemy_bases:
                        continue
                    step_cost = self.obstacle_cost if cell["type"] in ("mountain", "crater") else 1
                    candidate = cost + step_cost
                    if candidate < distances.get(neighbor, float("inf")):
                        distances[neighbor] = candidate
                        previous[neighbor] = point
                        heappush(queue, (candidate, neighbor))
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
