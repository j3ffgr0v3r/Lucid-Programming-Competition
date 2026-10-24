from bot import Bot
from typing import TypedDict

from bot_client import Action, Coordinate, Direction, MarsView, MoveAction, Resource, SimpleAction
from bot_template import path_to
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
        self, view: MarsView, resource: Resource | None, area: SearchArea | None = None
    ) -> None:
        if resource is not None and resource not in ("iron", "gold"):
            raise ValueError(f"Unsupported ore resource: {resource}")
        super().__init__(view)
        self.resource = resource
        self.area = area

    def next_action(self, bot: Bot) -> Action:
        start: Coordinate = {"x": bot.coordinates[0], "y": bot.coordinates[1]}
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
            route = path_to(
                self.grid,
                start,
                target,
                bases=self.view["bases"],
                team_id=bot.team_id,
            )
            if route is None:
                continue
            if best_ore_path is None or (len(route), index) < (
                len(best_ore_path),
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
            route = path_to(
                self.grid,
                start,
                target,
                bases=self.view["bases"],
                team_id=bot.team_id,
            )
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
            route = path_to(
                self.grid,
                start,
                target,
                bases=self.view["bases"],
                team_id=bot.team_id,
            )
            if route:
                return self._move_action(start, route[0])

        return SimpleAction(type="pass")

    @staticmethod
    def _move_action(start: Coordinate, destination: Coordinate) -> MoveAction:
        delta = (
            destination["x"] - start["x"],
            destination["y"] - start["y"],
        )
        direction = _DIRECTION_BY_DELTA[delta]
        return MoveAction(type="move", direction=direction)
