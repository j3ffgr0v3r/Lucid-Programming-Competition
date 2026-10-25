"""Mine an assigned outside sector, including land inward of the patrol lane."""

from .find_ore import FindOreState
from .patrol_ore import PatrolOre
from .state import State


class SectorOre(PatrolOre):
    def _owns(self, point, bot):
        center = self.states["CenterOre"]._area_bounds()
        return self.in_sector(point, bot) and not self._inside(point, center)

    def _ore_allowed(self, point, bot, bounds):
        return self._owns(point, bot)

    def _ore_routes(self, bot, enemy_bases):
        return State._routes(self, bot.coordinates, enemy_bases, allow_hidden=True)

    def _explore(self, bot, bounds, distances, previous):
        owned = {point: cost for point, cost in distances.items() if self._owns(point, bot)}
        if not owned:
            return {"type": "pass"}
        action = FindOreState._explore(
            self, bot, (0, 0, self.grid["width"], self.grid["height"]), owned, previous
        )
        if action["type"] == "pass":
            # Move toward the middle of the sector instead of clustering on
            # its boundary when all its terrain was recently visible.
            cx = sum(p[0] for p in owned) / len(owned)
            cy = sum(p[1] for p in owned) / len(owned)
            target = min(owned, key=lambda p: ((p[0] - cx) ** 2 + (p[1] - cy) ** 2, owned[p], p))
            if target == bot.coordinates:
                return action
            return self._move(bot.coordinates, target, previous)[1]
        return action
