from abc import ABC, abstractmethod

from bot import Bot
from bot_client import Action, Coordinate


class State(ABC):
    """Interface for a bot state that selects its next action."""

    @abstractmethod
    def next_action(self, bot: Bot) -> tuple[Coordinate | None, Action]:
        """Return a destination tile for moves, or ``None`` for other actions."""
        raise NotImplementedError
