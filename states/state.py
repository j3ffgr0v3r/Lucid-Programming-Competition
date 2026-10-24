from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from bot_client import Action, Coordinate, MarsView, GameMap

if TYPE_CHECKING:
    from bot import Bot


class State(ABC):
    """Interface for a bot state that selects its next action."""

    def __init__(self, view: MarsView) -> None:
        self.view: MarsView = view
        self.grid: GameMap = view["map"]

    @abstractmethod
    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        """Return a destination tile for moves, or ``None`` for other actions."""
        raise NotImplementedError
