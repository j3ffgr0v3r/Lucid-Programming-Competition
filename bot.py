class Bot:
    def __init__(self, name: str, id: str, coordinates: tuple[int, int]) -> None:
        self.name: str = name
        self.id: str = id
        self.state: str | None = None
        self.coordinates: tuple[int, int] = coordinates
        
    def set_state(self, state: str | None) -> None:
        self.state = state
        
    def update_coordinates(self, new_coordinates: tuple[int, int]) -> None:
        self.coordinates = new_coordinates
