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
        self.build_planned = False
        self.trade_from: str | None = None
        self.ending = False
        self.return_buffer = 0
        # A region index selects center mining; None selects perimeter patrol.
        self.search_area_index: int | None = None
        self.ore_search_scope: tuple | None = None
        self.ore_target: tuple[int, int] | None = None
        self.ore_explore_target: tuple[int, int] | None = None
        self.ore_returning = False
        self.patrol_index: int | None = None
        self.patrol_direction = 1
        self.patrol_sector: tuple[int, int] | None = None
        self.patrol_cursor: int | None = None
        self.last_action_type: str | None = None
        self.movement_history: list[tuple[int, int]] = [coordinates]
        self.avoid_steps: dict[tuple[int, int], int] = {}
        
    def set_state(self, state: str | None) -> None:
        self.state = state
        
    def update_coordinates(self, new_coordinates: tuple[int, int]) -> None:
        self.coordinates = new_coordinates
