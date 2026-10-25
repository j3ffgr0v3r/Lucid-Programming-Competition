"""Collect ore while making repeated circuits around the map's outer edge."""

from .find_ore import FindOreState


PATROL_WALL_DISTANCE = 2
PERIMETER_WIDTH = PATROL_WALL_DISTANCE + 1
PATROL_ORE_RADIUS = 4
PATROL_DETOUR_DEPTH = 2
PATROL_OBSTACLE_LOOKAHEAD = 4


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
        self.circuit = list(dict.fromkeys(
            [(x, top) for x in range(left, right + 1)]
            + [(right, y) for y in range(top + 1, bottom + 1)]
            + [(x, bottom) for x in range(right - 1, left - 1, -1)]
            + [(left, y) for y in range(bottom - 1, top, -1)]
        ))
        self._sector_indices = {}
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
        search_band = self._band(PATROL_WALL_DISTANCE + PATROL_ORE_RADIUS + 1)
        return self.in_sector(point, bot) and point in search_band and (
            point == bot.ore_target
            or max(abs(point[0] - bot.coordinates[0]), abs(point[1] - bot.coordinates[1])) <= PATROL_ORE_RADIUS
        )

    def sector_index(self, point):
        if point not in self._sector_indices:
            self._sector_indices[point] = min(range(len(self.circuit)), key=lambda index: (
                (self.circuit[index][0] - point[0]) ** 2 + (self.circuit[index][1] - point[1]) ** 2, index
            ))
        return self._sector_indices[point]

    def in_sector(self, point, bot):
        return bot.patrol_sector is None or bot.patrol_sector[0] <= self.sector_index(point) < bot.patrol_sector[1]

    def _resource_allowed(self, cell) -> bool:
        # Construction makes iron preferable, not a reason to ignore nearby gold.
        return cell["type"] in ("iron", "gold")

    def _ore_priority(self, point, distances, bot=None, worker=None, amount=None):
        cell = self.grid["cells"][point[1] * self.grid["width"] + point[0]]
        return (self.resource is not None and cell["type"] != self.resource,
                *super()._ore_priority(point, distances, bot, worker, amount))

    def _ore_routes(self, bot, enemy_bases):
        # Collection may step to either side of the normal patrol lane. Keep
        # the same search band throughout the trip so targets stay reachable.
        width = max(PATROL_WALL_DISTANCE + PATROL_ORE_RADIUS + 1, self._edge_depth(bot.coordinates) + 1)
        return self._routes(bot.coordinates, enemy_bases, allow_hidden=True, allowed_cells=self._band(width))

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
            return min((point for point in routes if point in self.perimeter and self.in_sector(point, bot)), key=lambda point: (
                max(abs(point[0] - waypoint[0]), abs(point[1] - waypoint[1])),
                routes[point], point,
            ), default=None)

        target = nearest(distances)
        if target == waypoint:
            # Widen a connected route only when it actually crosses costly
            # terrain. Ordinary open-ground patrols keep their usual lane.
            step = target
            costly = False
            while step != bot.coordinates:
                if self._cell({"x": step[0], "y": step[1]})["type"] in ("mountain", "crater", "hidden"):
                    costly = True
                    break
                step = previous[step]
            if costly:
                enemies = {(b["position"]["x"], b["position"]["y"])
                           for b in self.view["bases"] if b["teamId"] != bot.team_id}
                width = max(PERIMETER_WIDTH + PATROL_DETOUR_DEPTH, self._edge_depth(bot.coordinates) + 1)
                wider, route = super()._routes(
                    bot.coordinates, enemies, allow_hidden=True,
                    allowed_cells=self._band(width), preferred_cells=self.patrol_lane,
                )
                if wider.get(target, float("inf")) < distances[target]:
                    return target, route
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
        enemy_bases = {
            (base["position"]["x"], base["position"]["y"])
            for base in self.view["bases"] if base["teamId"] != bot.team_id
        }
        # Search detours must not widen the route used for ordinary patrols.
        distances, previous = self._routes(bot.coordinates, enemy_bases, allow_hidden=True)
        if bot.patrol_sector is not None:
            start, stop = bot.patrol_sector
            if start >= stop:
                return {"type": "pass"}
            if bot.patrol_cursor is None or not start <= bot.patrol_cursor < stop:
                bot.patrol_cursor = min(range(start, stop), key=lambda index: (
                    max(abs(self.circuit[index][0] - bot.coordinates[0]), abs(self.circuit[index][1] - bot.coordinates[1])), index
                ))
            for _ in range(stop - start):
                # A checkpoint is for coverage, not a requirement to stand on
                # a mountain. Look ahead within this arc to a cheaper tile.
                for ahead in range(1, PATROL_OBSTACLE_LOOKAHEAD + 1):
                    point = self.circuit[bot.patrol_cursor]
                    if self._cell({"x": point[0], "y": point[1]})["type"] not in ("mountain", "crater"):
                        break
                    index = bot.patrol_cursor + bot.patrol_direction * ahead
                    if not start <= index < stop:
                        if stop - start > 1:
                            bot.patrol_cursor -= bot.patrol_direction
                            bot.patrol_direction *= -1
                        break
                    point = self.circuit[index]
                    if self._cell({"x": point[0], "y": point[1]})["type"] in ("empty", "iron", "gold"):
                        bot.patrol_cursor = index
                        break
                target, route = self._checkpoint_route(bot, self.circuit[bot.patrol_cursor], distances, previous)
                if target is None:
                    return {"type": "pass"}
                if target != bot.coordinates:
                    return self._move(bot.coordinates, target, route)[1]
                if stop - start <= 2:
                    return {"type": "pass"}
                next_index = bot.patrol_cursor + bot.patrol_direction
                if not start <= next_index < stop:
                    bot.patrol_direction *= -1
                    next_index = bot.patrol_cursor + bot.patrol_direction
                bot.patrol_cursor = next_index
            return {"type": "pass"}
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
