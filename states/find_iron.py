from bot_client import MarsView
from states.find_ore import FindOreState, SearchArea


class FindIronState(FindOreState):
    """Compatibility wrapper for finding iron specifically."""

    def __init__(self, view: MarsView, area: SearchArea) -> None:
        super().__init__(view, "iron", area)
