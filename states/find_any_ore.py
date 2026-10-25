from bot_client import MarsView
from map_state import MapState
from states.find_ore import FindOreState, SearchArea

class FindAnyOreState(FindOreState):
    """Collect either resource, prioritizing banked-gold yield during mining."""

    def __init__(self, view: MarsView | MapState, area: SearchArea | None = None) -> None:
        super().__init__(view, None, area)
