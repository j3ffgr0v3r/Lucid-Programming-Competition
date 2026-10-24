"""Collect ore while making repeated circuits around the map's outer edge."""

from .find_ore import FindOreState


PATROL_WALL_DISTANCE = 2
PERIMETER_WIDTH = PATROL_WALL_DISTANCE + 1
PATROL_ORE_RADIUS = 4


class PatrolOre(FindOreState):
    def __init__(self, source):
        super().__init__(source, None)
        width, height = self.grid["width"], self.grid["height"]
        # Stay near the edge while seeing tiles on both sides of the route.
        inset_x = min(PATROL_WALL_DISTANCE, (width - 1) // 2)
        inset_y = min(PATROL_WALL_DISTANCE, (height - 1) // 2)
        left, right = inset_x, width - 1 - inset_x
        top, bottom = inset_y, height - 1 - inset_y
        mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
        self.waypoints = list(dict.fromkeys([
            (left, top), (mid_x, top), (right, top), (right, mid_y),
            (right, bottom), (mid_x, bottom), (left, bottom), (left, mid_y),
        ]))
        self.patrol_lane = frozenset(
            (x, y) for y in range(top, bottom + 1) for x in range(left, right + 1)
            if x in (left, right) or y in (top, bottom)
        )
        self.perimeter = frozenset(
            (x, y) for y in range(height) for x in range(width)
            if min(x, y, width - 1 - x, height - 1 - y) < PERIMETER_WIDTH
        )
        self._bands = {PERIMETER_WIDTH: self.perimeter}

    def _edge_depth(self, point):
        x, y = point
        return min(x, y, self.grid["width"] - 1 - x, self.grid["height"] - 1 - y)

    def _band(self, width):
        if width not in self._bands:
            self._bands[width] = frozenset(
                (x, y) for y in range(self.grid["height"]) for x in range(self.grid["width"])
                if self._edge_depth((x, y)) < width
            )
        return self._bands[width]

    def _ore_allowed(self, point, bot, bounds) -> bool:
        return point in self.perimeter and (
            point == bot.ore_target
            or max(abs(point[0] - bot.coordinates[0]), abs(point[1] - bot.coordinates[1])) <= PATROL_ORE_RADIUS
        )

    def _routes(self, origin, enemy_bases, *, allow_hidden=False, allowed_cells=None, preferred_cells=None):
        # Keep a rover on the ring, or within its current detour depth until
        # it rejoins. An interior starting position can still reach the edge.
        band_width = max(PERIMETER_WIDTH, self._edge_depth(origin) + 1)
        return super()._routes(
            origin, enemy_bases, allow_hidden=allow_hidden,
            allowed_cells=self._band(band_width) if allowed_cells is None else allowed_cells,
            preferred_cells=self.patrol_lane if preferred_cells is None else preferred_cells,
        )

    def _checkpoint_route(self, bot, waypoint, distances, previous):
        def nearest(routes):
            return min((point for point in routes if point in self.perimeter), key=lambda point: (
                max(abs(point[0] - waypoint[0]), abs(point[1] - waypoint[1])),
                routes[point], point,
            ), default=None)

        target = nearest(distances)
        if target == waypoint:
            return target, previous
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != bot.team_id
        }
        # Distinguish a genuinely unreachable checkpoint from one blocked only
        # by our patrol boundary. Do not advance the circuit prematurely.
        full_distances, full_previous = super()._routes(
            bot.coordinates, enemy_bases, allow_hidden=True, preferred_cells=self.patrol_lane
        )
        detour_target = nearest(full_distances)
        if detour_target is None or (target is not None and
            max(abs(target[0] - waypoint[0]), abs(target[1] - waypoint[1])) <=
            max(abs(detour_target[0] - waypoint[0]), abs(detour_target[1] - waypoint[1]))):
            return target, previous

        # Widen one tile at a time so a local obstacle detour does not turn
        # into a shortcut across the map. All paths still honor terrain costs.
        start_width = max(PERIMETER_WIDTH, self._edge_depth(bot.coordinates) + 1)
        max_width = (min(self.grid["width"], self.grid["height"]) + 1) // 2
        for width in range(start_width + 1, max_width):
            detour_distances, detour_previous = super()._routes(
                bot.coordinates, enemy_bases, allow_hidden=True, allowed_cells=self._band(width),
                preferred_cells=self.patrol_lane,
            )
            if detour_target in detour_distances:
                return detour_target, detour_previous
        return detour_target, full_previous

    def _explore(self, bot, bounds, distances, previous):
        if bot.patrol_index is None:
            bot.patrol_index = min(range(len(self.waypoints)), key=lambda index: (
                max(abs(self.waypoints[index][0] - bot.coordinates[0]),
                    abs(self.waypoints[index][1] - bot.coordinates[1])), index
            ))
        for _ in self.waypoints:
            waypoint = self.waypoints[bot.patrol_index]
            target, route = self._checkpoint_route(bot, waypoint, distances, previous)
            if target is None:
                return {"type": "pass"}
            if target != bot.coordinates:
                return self._move(bot.coordinates, target, route)[1]
            bot.patrol_index = (bot.patrol_index + bot.patrol_direction) % len(self.waypoints)
        return {"type": "pass"}
