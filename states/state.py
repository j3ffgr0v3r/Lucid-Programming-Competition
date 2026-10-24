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
