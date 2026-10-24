from bot_client import Action, Coordinate, SimpleAction
from states.state import State


class Bot:
    def __init__(self, name: str, id: str, coordinates: tuple[int, int]) -> None:
        self.name: str = name
        self.id: str = id
        self.state: State | None = None
        
    def set_state(self, state: State) -> None:
        self.state = state
        
    def calculate_next_action(self) -> tuple[Coordinate | None, Action]:
        if self.state is None:
            return (None, SimpleAction(type="pass"))
        
        return self.state.next_action(self)