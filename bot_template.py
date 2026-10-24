#!/usr/bin/env python3
from __future__ import annotations

import os
from heapq import heappop, heappush
from collections.abc import Sequence
from typing import Optional
from bot_client import (
    ActionsByEntity,
    BaseLocation,
    BotClient,
    BotState,
    Coordinate,
    CoordinateGrid,
    GameMap,
    Identity,
    MarsView,
    MovementState,
    OreState,
    Resource,
    TerritoryState,
    mars_view,
)

# Make sure to set your team token!
API_KEY = os.environ.get("API_KEY", "replace-with-api-key")
API_BASE_URL = os.environ.get("LUCID_API_BASE_URL", "http://localhost:5173")


def calculate_actions(gameState: BotState, identity: Identity) -> ActionsByEntity:
    view = mars_view(gameState)
    if view is None:
        return {}

    # Strategy goes here.

    return {
        worker["unitId"]: {"type": "pass"}
        for worker in view["units"]
        if worker["teamId"] == identity["teamId"]
    }


# Game helpers. Feel free to use, discard, or modify.
# Fill in the strategy section above.

def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _cell(grid: CoordinateGrid | GameMap, point: Coordinate):
    x, y = point["x"], point["y"]
    if not _is_integer(x) or not _is_integer(y):
        return None
    if not (0 <= x < grid["width"] and 0 <= y < grid["height"]):
        return None

    row_start = y * grid["width"]
    return grid["cells"][row_start + x]


def is_claimed(state: TerritoryState | MarsView, coordinate: Coordinate) -> list[str]:
    """Return all known claiming teams, including overlapping claims."""
    teams: list[str] = []

    for base in state["bases"]:
        position = base["position"]
        distance = abs(position["x"] - coordinate["x"]) + abs(position["y"] - coordinate["y"])
        if distance <= 2 and base["teamId"] not in teams:
            teams.append(base["teamId"])

    return teams


def is_base(state: TerritoryState | MarsView, coordinate: Coordinate) -> Optional[str]:
    for base in state["bases"]:
        if base["position"] == coordinate:
            return base["teamId"]
    return None


def is_ore(state: OreState | MarsView, coordinate: Coordinate) -> Optional[Resource]:
    cell = _cell(state["map"], coordinate)
    if cell and cell["type"] in ("gold", "iron") and cell.get("amount", 0) > 0:
        return cell["type"]
    return None


def can_move_onto(
    state: MovementState | MarsView,
    coordinate: Coordinate,
    team_id: Optional[str] = None,
) -> bool:
    """Unknown terrain and enemy bases are excluded; workers do not block."""
    cell = _cell(state["map"], coordinate)
    if cell is None or cell["type"] in ("hidden", "void"):
        return False

    base_owner = is_base(state, coordinate)
    return base_owner is None or base_owner == team_id


def path_to(
    grid: CoordinateGrid | GameMap,
    start: Coordinate,
    end: Coordinate,
    *,
    bases: Sequence[BaseLocation] = (),
    team_id: Optional[str] = None,
    obstacle_cost: int = 3,
) -> Optional[list[Coordinate]]:
    """Cost until ready at destination; start must be ready; None if unreachable."""
    if not _is_integer(obstacle_cost) or obstacle_cost < 1:
        return None

    state: MovementState = {"map": grid, "bases": bases}
    if not can_move_onto(state, start, team_id) or not can_move_onto(state, end, team_id):
        return None

    origin = (start["x"], start["y"])
    target = (end["x"], end["y"])
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
                if not dx and not dy:
                    continue
                point: Coordinate = {"x": x + dx, "y": y + dy}
                if not can_move_onto(state, point, team_id):
                    continue

                neighbor = (point["x"], point["y"])
                cell = _cell(grid, point)
                movement_cost = obstacle_cost if cell and cell["type"] in ("mountain", "crater") else 1
                candidate = distance + movement_cost
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


if __name__ == "__main__":
    print("Edit calculate_actions to choose your workers' actions.")
    if "LUCID_API_BASE_URL" not in os.environ:
        print(f"LUCID_API_BASE_URL is not set; using {API_BASE_URL}.")

    try:
        BotClient(API_KEY, API_BASE_URL).connect_and_run_bot(calculate_actions)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(error)
        raise SystemExit(1)
