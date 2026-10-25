"""Place productive bases in the largest gaps in our depot network."""

from math import hypot, sqrt

BASE_SPACING = 10
CENTER_BASE_MIN = 2
CENTER_BASE_MAX = 3
SITE_RADIUS = 4


class BasePlanner:
    def __init__(self, memory):
        self.memory = memory

    def in_center(self, point):
        grid, rich = self.memory.map, self.memory.highGoldArea
        width, height = min(grid["width"], rich["width"]), min(grid["height"], rich["height"])
        left, top = (grid["width"] - width) // 2, (grid["height"] - height) // 2
        return left <= point[0] < left + width and top <= point[1] < top + height

    def legal(self, point, team_id):
        grid = self.memory.map
        x, y = point
        if not (0 <= x < grid["width"] and 0 <= y < grid["height"]):
            return False
        if grid["cells"][y * grid["width"] + x]["type"] != "empty":
            return False
        for base in self.memory.bases:
            bx, by = base["position"]["x"], base["position"]["y"]
            if (x, y) == (bx, by) or (base["teamId"] != team_id and abs(x - bx) + abs(y - by) <= 2):
                return False
        return True

    def ranked_sites(self, team_id, *, center, reserved=()):
        grid = self.memory.map
        friendly = [(b["position"]["x"], b["position"]["y"])
                    for b in self.memory.bases if b["teamId"] == team_id]
        depots = friendly + list(reserved)
        occupied = {(b["position"]["x"], b["position"]["y"]) for b in self.memory.bases} | set(reserved)
        if center and sum(self.in_center(p) for p in depots) >= CENTER_BASE_MAX:
            return []
        desired = max(BASE_SPACING, max(grid["width"], grid["height"]) / sqrt(len(depots) + 1))
        enemy_claims = {
            (x, y) for b in self.memory.bases if b["teamId"] != team_id
            for x in range(b["position"]["x"] - 2, b["position"]["x"] + 3)
            for y in range(b["position"]["y"] - 2, b["position"]["y"] + 3)
            if abs(x - b["position"]["x"]) + abs(y - b["position"]["y"]) <= 2
        }
        scores = []
        for y in range(grid["height"]):
            for x in range(grid["width"]):
                point = (x, y)
                if self.in_center(point) != center or not self.legal(point, team_id):
                    continue
                gap = min((hypot(x - bx, y - by) for bx, by in depots), default=desired)
                if gap < (3 if center else BASE_SPACING):
                    continue
                fertility = ore_value = 0.0
                for dy in range(-SITE_RADIUS, SITE_RADIUS + 1):
                    for dx in range(-SITE_RADIUS, SITE_RADIUS + 1):
                        px, py = x + dx, y + dy
                        if not (0 <= px < grid["width"] and 0 <= py < grid["height"]) or (px, py) in enemy_claims or (px, py) in occupied:
                            continue
                        if center and not self.in_center((px, py)):
                            continue
                        cell = grid["cells"][py * grid["width"] + px]
                        # Unknown land and obstacles contribute no spawn value.
                        if cell["type"] not in ("empty", "iron", "gold"):
                            continue
                        weight = 1 / (1 + max(abs(dx), abs(dy)))
                        fertility += weight
                        if cell["type"] in ("iron", "gold"):
                            ore_value += weight * min(cell.get("amount", 0), 12)
                if fertility <= 1:
                    continue
                gap_weight = min(gap / (4 if center else desired), 2.0)
                scores.append(((fertility + 2 * ore_value) * gap_weight, gap, point))
        return [point for _, _, point in sorted(scores, key=lambda row: (-row[0], -row[1], row[2]))]
