from bot_client import MarsView
from map_state import MapState
from states.find_ore import FindOreState, SearchArea

class FindAnyOreState(FindOreState):
    """Greedily seek the closest reachable iron or gold deposit."""

    def __init__(self, view: MarsView | MapState, area: SearchArea | None = None) -> None:
        super().__init__(view, None, area)
