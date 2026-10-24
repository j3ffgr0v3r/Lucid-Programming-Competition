"""Team-level coordination of one Bot per friendly worker."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from inspect import getmembers, isabstract, isclass
from pkgutil import iter_modules

import states
from bot import Bot
from bot_client import ActionsByEntity, BotState, Identity, mars_view
from states.state import State



def bot_costs() -> Iterator[int]:
    """Yield successive worker prices in banked iron: 5, 6, 11, 17, ..."""
    current, following = 5, 6
    while True:
        yield current
        current, following = following, current + following


class Manager:
    """Keep one manager per match; call calculate_actions each turn."""

    def __init__(self, game_state: BotState, identity: Identity) -> None:
        view = mars_view(game_state)
        if view is None:
            raise ValueError("Initialize Manager with an LPC game view.")

        self.team_id = identity["teamId"]
        self.match_id = game_state["match"]["matchId"]
        self.bots: dict[str, Bot] = {}
        self._bot_costs = bot_costs()
        self._recruited_workers = 0
        self.next_bot_cost = next(self._bot_costs)
        self.game_map = view["map"]

        # State classes in states/*.py share the State(grid) constructor.
        # Each manager owns one instance per class, keyed by class name.
        self.states: dict[str, State] = {}
        for module_info in iter_modules(states.__path__, states.__name__ + "."):
            module = import_module(module_info.name)
            for name, state_class in getmembers(module, isclass):
                if (
                    state_class.__module__ == module.__name__
                    and issubclass(state_class, State)
                    and not isabstract(state_class)
                ):
                    if name in self.states:
                        raise ValueError(f"Duplicate state class name: {name}")
                    self.states[name] = state_class(self.game_map)

    def strategize(self):
        """
        Choose each bot's role with bot.set_state("StateClassName").
        Use self.bank and self.next_bot_cost when planning recruitment.
        Keep its existing state until a change of role is needed.
        """
        for bot in self.bots.values():
            # Recruitment is a one-turn assignment; reassess affordability.
            if bot.state == "SpawnBot":
                bot.set_state(None)

        # Assign one ready builder so bots do not all spend the same iron.
        if self.bank["iron"] >= self.next_bot_cost:
            for unit_id, bot in self.bots.items():
                if bot.state is None and self.workers[unit_id]["readyOnTurn"] <= self.turn:
                    bot.set_state("SpawnBot")
                    break
        

    def calculate_actions(self, game_state: BotState) -> ActionsByEntity:
        """Refresh bots, assign their states, then collect their actions."""
        if game_state["match"]["matchId"] != self.match_id:
            raise ValueError("Create a new Manager for each match.")
        view = mars_view(game_state)
        if view is None:
            return {}

        self.turn = view["turn"]
        self.game_map = view["map"]
        self.bank = view["teamResources"][self.team_id]
        workers = self.workers = {
            worker["unitId"]: worker
            for worker in view["units"]
            if worker["teamId"] == self.team_id
        }

        # One starting worker is free. Advance only for confirmed recruits.
        while self._recruited_workers < len(workers) - 1:
            self.next_bot_cost = next(self._bot_costs)
            self._recruited_workers += 1

        # Refresh every bot before any bot chooses an action.
        self.bots = {unit_id: bot for unit_id, bot in self.bots.items() if unit_id in workers}
        for unit_id, worker in workers.items():
            position = worker["position"]
            coordinates = (position["x"], position["y"])
            if unit_id not in self.bots:
                self.bots[unit_id] = Bot(name=unit_id, id=unit_id, coordinates=coordinates)
            else:
                self.bots[unit_id].update_coordinates(coordinates)

        for state in self.states.values():
            state.update(view, self.team_id)

        self.strategize()

        actions: ActionsByEntity = {}
        for unit_id, bot in self.bots.items():
            if workers[unit_id]["readyOnTurn"] > self.turn or bot.state is None:
                actions[unit_id] = {"type": "pass"}
            else:
                _, action = self.states[bot.state].next_action(bot)
                actions[unit_id] = action
                # Coordinates come from the next server snapshot, not the
                # requested destination: movement may fail or be interrupted.
        return actions
