"""Team-level coordination of one Bot per friendly worker."""

from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from inspect import getmembers, isabstract, isclass
from pkgutil import iter_modules

import states
import ore_fallback
from bot import Bot
from bot_client import ActionsByEntity, BotState, Identity, mars_view
from map_state import MapState
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
        self.map_state = MapState(view)
        self.game_map = self.map_state.map

        # Discover the team's implementations before choosing any fallbacks.
        state_classes = {}
        for module_info in iter_modules(states.__path__, states.__name__ + "."):
            module = import_module(module_info.name)
            for name, state_class in getmembers(module, isclass):
                if (
                    state_class.__module__ == module.__name__
                    and issubclass(state_class, State)
                    and not isabstract(state_class)
                    # This configurable base is represented by its ore wrappers.
                    and name != "FindOreState"
                ):
                    if name in state_classes:
                        raise ValueError(f"Duplicate state class name: {name}")
                    state_classes[name] = state_class

        ore_names = ("FindAnyOreState", "FindIronState", "FindGoldState")
        for name in ore_names:
            state_classes.setdefault(name, getattr(ore_fallback, name))
        ore_module = import_module(state_classes["FindAnyOreState"].__module__)
        search_area_class = getattr(ore_module, "SearchArea", ore_fallback.SearchArea)
        width, height = self.game_map["width"], self.game_map["height"]
        half_x, half_y = width // 2, height // 2
        whole_map = search_area_class(x=0, y=0, width=width, height=height)
        # Opposing pairs: north/south, east/west, NE/SW, NW/SE.
        self.search_areas = [search_area_class(x=x, y=y, width=w, height=h) for x, y, w, h in (
            (0, 0, width, max(1, half_y)), (0, half_y, width, height - half_y),
            (half_x, 0, width - half_x, height), (0, 0, max(1, half_x), height),
            (half_x, 0, width - half_x, max(1, half_y)),
            (0, half_y, max(1, half_x), height - half_y),
            (0, 0, max(1, half_x), max(1, half_y)),
            (half_x, half_y, width - half_x, height - half_y),
        )]
        self.states: dict[str, State] = {
            name: state_class(self.map_state, whole_map) if name in ore_names else state_class(self.map_state)
            for name, state_class in state_classes.items()
        }
        # SearchArea is constructor data, so cache one instance per region.
        self.ore_states = {
            name: [state_classes[name](self.map_state, area) for area in self.search_areas]
            for name in ore_names
        }
        self._all_states = list(self.states.values()) + [
            state for instances in self.ore_states.values() for state in instances
        ]
        for state in self._all_states:
            state.states = self.states

    def strategize(self):
        """Send one central builder until we own three bases; spread miners."""
        center = {"x": self.game_map["width"] // 2, "y": self.game_map["height"] // 2}
        our_bases = [base for base in self.map_state.bases if base["teamId"] == self.team_id]
        builder = None
        if len(our_bases) < 3 and self.bots:
            builder = min(
                self.bots.values(),
                key=lambda bot: ((bot.coordinates[0] - center["x"]) ** 2
                                 + (bot.coordinates[1] - center["y"]) ** 2, bot.id),
            )

        ore_state_name = "FindIronState" if len(our_bases) < 3 else "FindAnyOreState"
        miners = 0
        for bot in sorted(self.bots.values(), key=lambda bot: bot.id):
            if bot is builder:
                confirmed = bot.build_requested and any(
                    base["position"] == bot.build_site for base in our_bases
                )
                if bot.state != "BuildBase" or bot.build_target != center or confirmed:
                    self.states["BuildBase"].assign(bot, center)
                bot.search_area_index = None
            else:
                bot.set_state(ore_state_name)
                bot.search_area_index = miners % len(self.search_areas)
                miners += 1
        

    def calculate_actions(self, game_state: BotState) -> ActionsByEntity:
        """Refresh bots, assign their states, then collect their actions."""
        if game_state["match"]["matchId"] != self.match_id:
            raise ValueError("Create a new Manager for each match.")
        view = mars_view(game_state)
        if view is None:
            return {}

        self.turn = view["turn"]
        self.map_state.update(view)
        self.game_map = self.map_state.map
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
                self.bots[unit_id] = Bot(name=unit_id, id=unit_id, team_id=self.team_id, coordinates=coordinates)
            else:
                self.bots[unit_id].update_coordinates(coordinates)

        # Route over remembered terrain and bases, with fresh units and bank.
        planning_view = dict(view, map=self.game_map, bases=self.map_state.bases)
        route_cache = {}
        for state in self._all_states:
            state.update(planning_view, self.team_id)
            # All states use the same remembered map this turn.
            state._route_cache = route_cache

        self.strategize()

        actions: ActionsByEntity = {}
        for unit_id, bot in self.bots.items():
            if workers[unit_id]["readyOnTurn"] > self.turn or bot.state is None:
                actions[unit_id] = {"type": "pass"}
            else:
                state = self.states[bot.state]
                if bot.state in self.ore_states and bot.search_area_index is not None:
                    state = self.ore_states[bot.state][bot.search_area_index]
                result = state.next_action(bot)
                action = result[1] if isinstance(result, tuple) else result
                actions[unit_id] = action
                # Coordinates come from the next server snapshot, not the
                # requested destination: movement may fail or be interrupted.
        return actions
