from bot_client import MarsView
from states.find_ore import FindOreState, SearchArea
from map_state import MapState

class FindIronState(FindOreState):
    """Compatibility wrapper for finding iron specifically."""

    def __init__(self, view: MapState, area: SearchArea) -> None:
        super().__init__(view, "iron", area)
