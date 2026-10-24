from abc import ABC, abstractmethod

from bot import Bot
from bot_client import (
    Action,
    Coordinate,
    CoordinateGrid,
    GameMap
)

class State(ABC):
    """Interface for a bot state that selects its next action."""

    def __init__(self, grid: CoordinateGrid | GameMap):
        self.grid = grid


    @abstractmethod
    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        """Return a destination tile for moves, or ``None`` for other actions."""
        raise NotImplementedError


    def _cell(self, point: Coordinate):
        x, y = point["x"], point["y"]
        if not self._is_integer(x) or not self._is_integer(y):
            return None
        if not (0 <= x < self.grid["width"] and 0 <= y < self.grid["height"]):
            return None

        row_start = y * self.grid["width"]
        return self.grid["cells"][row_start + x]


    def _is_integer(self, value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)