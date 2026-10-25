from collections.abc import Sequence
from heapq import heapify, heappop, heappush

from bot import Bot
from bot_client import (
    Action,
    BaseLocation,
    Coordinate,
    GameMap,
    SimpleAction,
)

from .state import State

HIDDEN_TERRAIN_PENALTY = 1
OBSTACLE_COST = 3


class Bank(State):
    def turns_to_bank(self, bot: Bot) -> int | None:
        """Estimate travel plus depositing, including terrain cooldowns."""
        if self.view is None or bot.team_id is None:
            return None
        costs, _ = self._bank_routes(bot.team_id)
        return costs.get(bot.coordinates)

    def travel_turns_from(self, point, team_id, *, hidden_penalty=HIDDEN_TERRAIN_PENALTY):
        costs, _ = self._bank_routes(team_id, hidden_penalty=hidden_penalty)
        return costs.get(point, float("inf")) - 1

    def _bank_routes(self, team_id, avoided=frozenset(), hidden_penalty=HIDDEN_TERRAIN_PENALTY):
        bases = self.map_state.bases if self.map_state is not None else self.view["bases"]
        key = ("bank_return_routes", team_id, avoided, hidden_penalty)
        if key not in self._route_cache:
            # One reverse search from every depot serves all workers. Reverse
            # edges pay for entering the current tile, not the neighbor.
            width, height = self.grid["width"], self.grid["height"]
            blocked = {(b["position"]["x"], b["position"]["y"])
                       for b in bases if b["teamId"] != team_id} | avoided
            costs = {(b["position"]["x"], b["position"]["y"]): 1
                     for b in bases if b["teamId"] == team_id
                     and (b["position"]["x"], b["position"]["y"]) not in blocked
                     and self.grid["cells"][b["position"]["y"] * width + b["position"]["x"]]["type"] != "void"}
            steps = {}
            queue = [(cost, point) for point, cost in costs.items()]
            heapify(queue)
            while queue:
                cost, point = heappop(queue)
                if costs[point] != cost:
                    continue
                kind = self.grid["cells"][point[1] * width + point[0]]["type"]
                step = OBSTACLE_COST if kind in ("mountain", "crater") else 1 + (hidden_penalty if kind == "hidden" else 0)
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        neighbor = (point[0] + dx, point[1] + dy)
                        x, y = neighbor
                        if not (dx or dy) or not (0 <= x < width and 0 <= y < height):
                            continue
                        if neighbor in blocked or self.grid["cells"][y * width + x]["type"] == "void":
                            continue
                        if cost + step < costs.get(neighbor, float("inf")):
                            costs[neighbor] = cost + step
                            steps[neighbor] = point
                            heappush(queue, (cost + step, neighbor))
            self._route_cache[key] = costs, steps
        return self._route_cache[key]

    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        team_id = bot.team_id
        if self.view is None or team_id is None:
            return (None, SimpleAction(type="pass"))

        bases = self.map_state.bases if self.map_state is not None else self.view["bases"]
        if any(b["teamId"] == team_id and
               (b["position"]["x"], b["position"]["y"]) == bot.coordinates for b in bases):
            return None, {"type": "deposit"}
        avoided = self.route_avoidance.get(bot.coordinates, frozenset())
        _, steps = self._bank_routes(team_id, avoided)
        destination = steps.get(bot.coordinates)
        if destination is None:
            return None, {"type": "pass"}
        return self._move(bot.coordinates, destination, {destination: bot.coordinates})

    @staticmethod
    def _path_cost(
        grid: GameMap,
        path: list[Coordinate],
        *,
        hidden_penalty: int = 0,
    ) -> int:
        width = grid["width"]
        cells = grid["cells"]
        cost = 0
        for point in path:
            cell = cells[point["y"] * width + point["x"]]
            if cell["type"] == "hidden":
                cost += 1 + hidden_penalty
            elif cell["type"] in ("mountain", "crater"):
                cost += OBSTACLE_COST
            else:
                cost += 1
        return cost

    @staticmethod
    def _path_through_hidden(
        grid: GameMap,
        start: Coordinate,
        end: Coordinate,
        bases: Sequence[BaseLocation],
        team_id: str,
    ) -> list[Coordinate] | None:
        width, height = grid["width"], grid["height"]
        cells = grid["cells"]
        base_owners = {
            (base["position"]["x"], base["position"]["y"]): base["teamId"]
            for base in bases
        }
        origin = (start["x"], start["y"])
        target = (end["x"], end["y"])

        def cell_at(position: tuple[int, int]):
            x, y = position
            if not (0 <= x < width and 0 <= y < height):
                return None
            if base_owners.get(position, team_id) != team_id:
                return None
            cell = cells[y * width + x]
            return None if cell["type"] == "void" else cell

        if cell_at(origin) is None or cell_at(target) is None:
            return None

        distances = {origin: 0}
        previous: dict[tuple[int, int], tuple[int, int]] = {}
        queue = [(0, origin)]
        while queue:
            distance, position = heappop(queue)
            if distance != distances[position]:
                continue
            if position == target:
                break

            x, y = position
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    if dx == 0 and dy == 0:
                        continue
                    neighbor = (x + dx, y + dy)
                    cell = cell_at(neighbor)
                    if cell is None:
                        continue

                    if cell["type"] == "hidden":
                        step_cost = 1 + HIDDEN_TERRAIN_PENALTY
                    elif cell["type"] in ("mountain", "crater"):
                        step_cost = OBSTACLE_COST
                    else:
                        step_cost = 1
                    candidate = distance + step_cost
                    if candidate < distances.get(neighbor, float("inf")):
                        distances[neighbor] = candidate
                        previous[neighbor] = position
                        heappush(queue, (candidate, neighbor))

        if target not in distances:
            return None

        path: list[Coordinate] = []
        position = target
        while position != origin:
            path.append({"x": position[0], "y": position[1]})
            position = previous[position]
        return list(reversed(path))
