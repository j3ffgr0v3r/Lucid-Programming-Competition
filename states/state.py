from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot import Bot
from bot_client import (
    Action,
    Coordinate,
    CoordinateGrid,
    GameMap,
    MarsView,
)

class State(ABC):
    """Shared behavior that selects an action for the supplied bot.

    The manager creates each concrete state once and refreshes its grid each
    turn. Keep per-bot progress on the bot, since state instances are shared.
    """

    def __init__(self, grid: CoordinateGrid | GameMap):
        self.grid = grid
        self.view: MarsView | None = None
        self.team_id: str | None = None

    def update(self, view: MarsView, team_id: str) -> None:
        """Refresh shared world data before any bot requests an action."""
        self.grid = view["map"]
        self.view = view
        self.team_id = team_id


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
