from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from bot_client import Action, MarsView, GameMap

from map_state import MapState

if TYPE_CHECKING:
    from bot import Bot


class State(ABC):
    """Shared behavior that selects an action for the supplied bot.

    The manager creates each concrete state once and refreshes its grid each
    turn. Keep per-bot progress on the bot, since state instances are shared.
    """

    def __init__(self, view: MapState) -> None:
        self.view: MapState = view

    @abstractmethod
    def next_action(self, bot: Bot) -> Action:
        """Return a destination tile for moves, or ``None`` for other actions."""
        raise NotImplementedError
