from bot import Bot
from typing import TypedDict

from bot_client import Action, Coordinate, Direction, MarsView, MoveAction, Resource, SimpleAction
from map_state import MapState
from states.state import State


_DIRECTION_BY_DELTA: dict[tuple[int, int], Direction] = {
    (0, -1): "north",
    (1, -1): "north-east",
    (1, 0): "east",
    (1, 1): "south-east",
    (0, 1): "south",
    (-1, 1): "south-west",
    (-1, 0): "west",
    (-1, -1): "north-west",
}


class SearchArea(TypedDict):
    """Rectangular search area, with a top-left coordinate and dimensions."""

    x: int
    y: int
    width: int
    height: int


class FindOreState(State):
    """Move to visible ore, optionally filtering for one resource."""

    def __init__(
        self, view: MarsView | MapState, resource: Resource | None, area: SearchArea | None = None
    ) -> None:
        if resource is not None and resource not in ("iron", "gold"):
            raise ValueError(f"Unsupported ore resource: {resource}")
        super().__init__(view)
        self.resource = resource
        self.area = area

    def next_action(self, bot: Bot) -> Action:
        start: Coordinate = {"x": bot.coordinates[0], "y": bot.coordinates[1]}
        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is not None:
            if worker["readyOnTurn"] > self.view["turn"]:
                return SimpleAction(type="pass")
            inventory = worker.get("inventory", {"gold": 0, "iron": 0})
            carried = inventory["gold"] + inventory["iron"]
            home_bases = [base for base in self.view["bases"] if base["teamId"] == bot.team_id]
            if carried and any(base["position"] == start for base in home_bases):
                return SimpleAction(type="deposit")
            if carried >= worker.get("inventoryCapacity", 8):
                bank_state = self.states.get("Bank")
                if bank_state is not None:
                    result = bank_state.next_action(bot)
                    return result[1] if isinstance(result, tuple) else result
                routes = [self._path_to(start, base["position"], bot.team_id) for base in home_bases]
                reachable = [route for route in routes if route is not None]
                if reachable:
                    route = min(reachable, key=self._travel_time)
                    return self._move_action(start, route[0]) if route else SimpleAction(type="deposit")
                return SimpleAction(type="pass")
        bounds = self._area_bounds()
        if self.area is not None and bounds is None:
            return SimpleAction(type="pass")
        best_ore_path: list[Coordinate] | None = None
        best_ore_index: int | None = None

        for index, cell in enumerate(self.grid["cells"]):
            if cell["type"] not in ("iron", "gold"):
                continue
            if self.resource is not None and cell["type"] != self.resource:
                continue
            if cell.get("amount", 0) <= 0:
                continue

            x = index % self.grid["width"]
            y = index // self.grid["width"]
            if bounds is not None:
                left, top, right, bottom = bounds
                if not (left <= x < right and top <= y < bottom):
                    continue

            target: Coordinate = {
                "x": x,
                "y": y,
            }
            owners = {
                base["teamId"] for base in self.view["bases"]
                if abs(base["position"]["x"] - x) + abs(base["position"]["y"] - y) <= 2
            }
            if owners and bot.team_id not in owners:
                continue
            route = self._path_to(start, target, bot.team_id)
            if route is None:
                continue
            if best_ore_path is None or (self._travel_time(route), index) < (
                self._travel_time(best_ore_path),
                best_ore_index if best_ore_index is not None else index,
            ):
                best_ore_path = route
                best_ore_index = index

        if best_ore_path is not None:
            if not best_ore_path:
                return SimpleAction(type="mine")
            return self._move_action(start, best_ore_path[0])

        if bounds is not None:
            return self._move_into_area(bot, start, bounds)
        return self._move_toward_rich_center(bot, start)

    def _area_bounds(self) -> tuple[int, int, int, int] | None:
        if self.area is None:
            return None
        map_width = self.grid["width"]
        map_height = self.grid["height"]
        left = max(0, self.area["x"])
        top = max(0, self.area["y"])
        right = min(map_width, self.area["x"] + self.area["width"])
        bottom = min(map_height, self.area["y"] + self.area["height"])
        if self.area["width"] <= 0 or self.area["height"] <= 0 or left >= right or top >= bottom:
            return None
        return left, top, right, bottom

    def _move_into_area(
        self, bot: Bot, start: Coordinate, bounds: tuple[int, int, int, int]
    ) -> Action:
        left, top, right, bottom = bounds
        candidates: list[tuple[int, int, Coordinate]] = []
        for index, cell in enumerate(self.grid["cells"]):
            if cell["type"] in ("hidden", "void"):
                continue
            x = index % self.grid["width"]
            y = index // self.grid["width"]
            if left <= x < right and top <= y < bottom:
                target: Coordinate = {"x": x, "y": y}
                distance = abs(x - start["x"]) + abs(y - start["y"])
                candidates.append((distance, index, target))

        for _, _, target in sorted(candidates):
            route = self._path_to(start, target, bot.team_id)
            if route:
                return self._move_action(start, route[0])
        return SimpleAction(type="pass")

    def _move_toward_rich_center(self, bot: Bot, start: Coordinate) -> Action:
        area = self.view["highGoldArea"]
        map_width = self.grid["width"]
        map_height = self.grid["height"]
        area_width = min(area["width"], map_width)
        area_height = min(area["height"], map_height)
        left = (map_width - area_width) // 2
        top = (map_height - area_height) // 2
        center_x = left + (area_width - 1) / 2
        center_y = top + (area_height - 1) / 2

        def center_distance(point: Coordinate) -> float:
            return (point["x"] - center_x) ** 2 + (point["y"] - center_y) ** 2

        start_distance = center_distance(start)
        candidates: list[tuple[float, int, Coordinate]] = []
        for index, cell in enumerate(self.grid["cells"]):
            if cell["type"] in ("hidden", "void"):
                continue
            target: Coordinate = {
                "x": index % map_width,
                "y": index // map_width,
            }
            distance = center_distance(target)
            if distance < start_distance:
                candidates.append((distance, index, target))

        for _, _, target in sorted(candidates):
            route = self._path_to(start, target, bot.team_id)
            if route:
                return self._move_action(start, route[0])

        return SimpleAction(type="pass")

    def _path_to(self, start: Coordinate, target: Coordinate, team_id: str) -> list[Coordinate] | None:
        """Reuse the shared travel-time search for every candidate ore tile."""
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != team_id
        }
        origin = (start["x"], start["y"])
        destination = (target["x"], target["y"])
        distances, previous = self._routes(origin, enemy_bases)
        if destination not in distances:
            return None
        path = []
        while destination != origin:
            path.append({"x": destination[0], "y": destination[1]})
            destination = previous[destination]
        return list(reversed(path))

    def _travel_time(self, path: list[Coordinate]) -> int:
        return sum(
            self.obstacle_cost if self._cell(point)["type"] in ("mountain", "crater") else 1
            for point in path
        )

    @staticmethod
    def _move_action(start: Coordinate, destination: Coordinate) -> MoveAction:
        delta = (
            destination["x"] - start["x"],
            destination["y"] - start["y"],
        )
        direction = _DIRECTION_BY_DELTA[delta]
        return MoveAction(type="move", direction=direction)
