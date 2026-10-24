from bot_client import Coordinate


class Bot:
    def __init__(
        self,
        name: str,
        id: str,
        team_id: str,
        coordinates: tuple[int, int],
    ) -> None:
        self.name: str = name
        self.id: str = id
        self.team_id: str = team_id
        self.state: str | None = None
        self.coordinates: tuple[int, int] = coordinates
        self.build_target: Coordinate | None = None
        self.build_site: Coordinate | None = None
        self.build_requested = False
        self.build_in_center = False
        # None uses the whole-map ore state; miners get opposing regions.
        self.search_area_index: int | None = None
        
    def set_state(self, state: str | None) -> None:
        self.state = state
        
    def update_coordinates(self, new_coordinates: tuple[int, int]) -> None:
        self.coordinates = new_coordinates
