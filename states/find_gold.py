from bot_client import MarsView
from find_ore import FindOreState, SearchArea

class FindAnyOreState(FindOreState):
    """Greedily seek the closest gold deposit."""

    def __init__(self, view: MarsView, area: SearchArea | None = None) -> None:
        super().__init__(view, "gold", area)