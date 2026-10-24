"""Temporary ore behaviors used only when the team's state files are absent.

Manager prefers matching classes discovered in states/. Constructors follow
the team's (map_state, search_area) contract; this module stays outside states/
so it cannot collide with those implementations.
"""

from dataclasses import dataclass

from map_state import MapState
from states.state import State


@dataclass(frozen=True)
class SearchArea:
    x: int
    y: int
    width: int
    height: int

    def contains(self, point):
        return self.x <= point[0] < self.x + self.width and self.y <= point[1] < self.y + self.height

    def distance(self, point):
        return max(self.x - point[0], 0, point[0] - (self.x + self.width - 1)) + max(
            self.y - point[1], 0, point[1] - (self.y + self.height - 1)
        )


class _FindOre(State):
    resource = None

    def __init__(self, map_state: MapState, search_area):
        super().__init__(map_state.map)
        self.map_state = map_state
        # Accept the teammate's SearchArea as well as the fallback dataclass.
        self.search_area = SearchArea(search_area.x, search_area.y, search_area.width, search_area.height)

    def next_action(self, bot):
        if self.view is None:
            return None, {"type": "pass"}
        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is None or worker["readyOnTurn"] > self.view["turn"]:
            return None, {"type": "pass"}
        bases = self.view["bases"]
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in bases if base["teamId"] != self.team_id
        }
        distances, previous = self._routes(bot.coordinates, enemy_bases)
        home = [
            (base["position"]["x"], base["position"]["y"])
            for base in bases if base["teamId"] == self.team_id
            and (base["position"]["x"], base["position"]["y"]) in distances
        ]
        inventory = worker.get("inventory", {"gold": 0, "iron": 0})
        carried = inventory["gold"] + inventory["iron"]
        if carried and bot.coordinates in home:
            return None, {"type": "deposit"}
        if carried >= worker.get("inventoryCapacity", 8):
            return self._return_home(bot, home, distances, previous)

        ores = []
        for point in distances:
            cell = self._cell({"x": point[0], "y": point[1]})
            if cell["type"] not in ("gold", "iron") or cell.get("amount", 0) <= 0:
                continue
            if self.resource is not None and cell["type"] != self.resource:
                continue
            owners = {
                base["teamId"] for base in bases
                if abs(base["position"]["x"] - point[0]) + abs(base["position"]["y"] - point[1]) <= 2
            }
            if not owners or self.team_id in owners:
                ores.append(point)
        local_ores = [point for point in ores if self.search_area.contains(point)]
        if local_ores:
            target = min(local_ores, key=lambda point: (distances[point], point))
            if target == bot.coordinates:
                return None, {"type": "mine"}
            return self._move(bot.coordinates, target, previous)

        if carried:
            return self._return_home(bot, home, distances, previous)

        # Explore the assigned region before falling back to ore elsewhere.
        frontier = []
        for point in distances:
            if point == bot.coordinates:
                continue
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                cell = self._cell({"x": point[0] + dx, "y": point[1] + dy})
                if cell is not None and cell["type"] == "hidden":
                    frontier.append(point)
                    break
        if frontier:
            target = min(frontier, key=lambda point: (self.search_area.distance(point), distances[point], point))
            return self._move(bot.coordinates, target, previous)
        if ores:
            target = min(ores, key=lambda point: (distances[point], point))
            if target == bot.coordinates:
                return None, {"type": "mine"}
            return self._move(bot.coordinates, target, previous)
        return None, {"type": "pass"}

    def _return_home(self, bot, home, distances, previous):
        if not home:
            return None, {"type": "pass"}
        target = min(home, key=lambda point: (distances[point], point))
        if target == bot.coordinates:
            return None, {"type": "deposit"}
        return self._move(bot.coordinates, target, previous)


class FindAnyOreState(_FindOre):
    pass


class FindIronState(_FindOre):
    resource = "iron"


class FindGoldState(_FindOre):
    resource = "gold"
