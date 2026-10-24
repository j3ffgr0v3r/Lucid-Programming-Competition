from bot_client import Action, Coordinate, SimpleAction
from state import State


class SpawnBot(State):
    def next_action(self, bot) -> tuple[Coordinate | None, Action]:
        return (None, SimpleAction(type="spawn"))