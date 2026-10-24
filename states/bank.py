from collections.abc import Sequence
from heapq import heappop, heappush

from bot import Bot
from bot_client import (
    Action,
    BaseLocation,
    Coordinate,
    Direction,
    GameMap,
    SimpleAction,
)
from bot_template import path_to

from .state import State

HIDDEN_TERRAIN_PENALTY = 1
OBSTACLE_COST = 3


class Bank(State):
    def turns_to_bank(self, bot: Bot) -> int | None:
        """Estimate travel plus depositing, including terrain cooldowns."""
        if self.view is None or bot.team_id is None:
            return None
        bases = self.map_state.bases if self.map_state is not None else self.view["bases"]
        start = {"x": bot.coordinates[0], "y": bot.coordinates[1]}
        costs = []
        for base in bases:
            if base["teamId"] != bot.team_id:
                continue
            path = self._path_through_hidden(self.grid, start, base["position"], bases, bot.team_id)
            if path is not None:
                costs.append(self._path_cost(self.grid, path, hidden_penalty=HIDDEN_TERRAIN_PENALTY) + 1)
        return min(costs, default=None)

    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        team_id = bot.team_id
        if self.view is None or team_id is None:
            return (None, SimpleAction(type="pass"))

        grid = self.grid
        avoided = self.route_avoidance.get(bot.coordinates, frozenset())
        if avoided:
            # Replan around a confirmed movement loop without changing memory.
            grid = dict(grid, cells=[
                {"type": "void"} if (index % grid["width"], index // grid["width"]) in avoided else cell
                for index, cell in enumerate(grid["cells"])
            ])
        bases = self.map_state.bases if self.map_state is not None else self.view["bases"]
        start: Coordinate = {"x": bot.coordinates[0], "y": bot.coordinates[1]}
        friendly_bases = [
            base for base in bases if base["teamId"] == team_id
        ]

        for base in friendly_bases:
            if base["position"] == start:
                return (None, SimpleAction(type="deposit"))

        candidates: list[tuple[int, list[Coordinate]]] = []
        for base in friendly_bases:
            destination = base["position"]

            # The known-map path avoids hidden terrain.
            known_path = path_to(
                grid,
                start,
                destination,
                bases=bases,
                team_id=team_id,
                obstacle_cost=OBSTACLE_COST,
            )
            if known_path is not None:
                candidates.append((self._path_cost(grid, known_path), known_path))

            # Also consider the shortest route through hidden tiles. Each
            # hidden tile costs extra to account for its unknown terrain.
            hidden_path = self._path_through_hidden(
                grid, start, destination, bases, team_id
            )
            if hidden_path is not None:
                candidates.append(
                    (
                        self._path_cost(
                            grid, hidden_path, hidden_penalty=HIDDEN_TERRAIN_PENALTY
                        ),
                        hidden_path,
                    )
                )

        if not candidates:
            return (None, SimpleAction(type="pass"))

        _, shortest_path = min(candidates, key=lambda candidate: candidate[0])
        if not shortest_path:
            return (None, SimpleAction(type="deposit"))

        destination = shortest_path[0]
        delta = (destination["x"] - start["x"], destination["y"] - start["y"])
        direction_by_delta: dict[tuple[int, int], Direction] = {
            (0, -1): "north",
            (1, -1): "north-east",
            (1, 0): "east",
            (1, 1): "south-east",
            (0, 1): "south",
            (-1, 1): "south-west",
            (-1, 0): "west",
            (-1, -1): "north-west",
        }
        direction = direction_by_delta[delta]
        return (destination, {"type": "move", "direction": direction})

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
