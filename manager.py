"""Team-level planning and coordination of one Bot per friendly worker."""

from __future__ import annotations

from typing import Optional

from bot import Bot
from bot_client import (
    Action,
    ActionsByEntity,
    Base,
    BotState,
    GameMap,
    Identity,
    Inventory,
    MarsView,
    Unit,
    mars_view,
)


class Manager:
    """Keep one instance per match so plans and bots persist between turns.

    Construct with the first LPC game state and the client's identity, then
    call calculate_actions(game_state) for each turn. Strategy and Bot hooks
    are placeholders; this scaffold currently returns pass for every worker.
    """

    def __init__(self, game_state: BotState, identity: Identity) -> None:
        self.team_id: str = identity["teamId"]
        self.match_id: str = game_state["match"]["matchId"]

        # Persistent decision-making state, separate from server snapshots.
        self.bots: dict[str, Bot] = {}
        self.strategy: Optional[str] = None

        self.update_state(game_state)

    def update_state(self, game_state: BotState) -> None:
        """Refresh server data while preserving bot objects and strategy.

        Enemy lists contain only currently visible entities. Map cells are
        indexed by y * width + x; hidden cells are not known empty terrain.
        Treat this snapshot as read-only, not as persistent map memory.
        """
        if game_state["match"]["matchId"] != self.match_id:
            raise ValueError("Create a new Manager for each match.")

        view = mars_view(game_state)
        if view is None:
            raise ValueError("Manager requires an LPC game state with a view.")

        self.game_state: BotState = game_state
        self.view: MarsView = view
        self.turn: int = view["turn"]
        self.max_turns: int = game_state["match"]["maxTurns"]
        self.game_map: GameMap = view["map"]
        self.bank: Inventory = view["teamResources"][self.team_id]
        self.workers: dict[str, Unit] = {
            worker["unitId"]: worker
            for worker in view["units"]
            if worker["teamId"] == self.team_id
        }
        self.enemy_workers: dict[str, Unit] = {
            worker["unitId"]: worker
            for worker in view["units"]
            if worker["teamId"] != self.team_id
        }
        self.bases: dict[str, Base] = {
            base["baseId"]: base
            for base in view["bases"]
            if base["teamId"] == self.team_id
        }
        self.enemy_bases: dict[str, Base] = {
            base["baseId"]: base
            for base in view["bases"]
            if base["teamId"] != self.team_id
        }

    def calculate_actions(self, game_state: BotState) -> ActionsByEntity:
        """Run the manager's turn pipeline and return the client's payload."""
        self.update_state(game_state)
        self.sync_bots()
        self.plan_strategy()
        self.assign_bot_states()
        return self.collect_actions()

    def sync_bots(self) -> None:
        """Create bots for new workers and refresh existing bots' snapshots."""
        # TODO: Once Bot has an initializer, create one per worker ID in
        # self.workers, preserving existing instances and their local state.
        # Update their worker data and remove bots whose workers are gone.
        pass

    def plan_strategy(self) -> None:
        """Choose team priorities using the bank, map, workers, and time left."""
        # TODO: Decide when to explore, gather iron/gold, expand, or return
        # cargo before the match ends. Record the plan in self.strategy.
        pass

    def assign_bot_states(self) -> None:
        """Translate the team plan into each bot's role and target."""
        # TODO: Tell bots what to do (for example, mine gold or build a base).
        # Coordinate targets and budget shared bank iron across builders;
        # iron deposited this turn cannot fund construction this turn.
        pass

    def collect_actions(self) -> ActionsByEntity:
        """Ask each ready worker's bot for one action, keyed by worker ID."""
        actions: ActionsByEntity = {}
        for unit_id, worker in self.workers.items():
            if worker["readyOnTurn"] > self.turn:
                actions[unit_id] = {"type": "pass"}
            else:
                actions[unit_id] = self.get_bot_action(unit_id)
        return actions

    def get_bot_action(self, unit_id: str) -> Action:
        """Bot integration hook: obtain an action for a ready friendly worker."""
        # TODO: Query self.bots[unit_id] once Bot's action method is defined.
        # The bot should own movement/pathfinding and execution of its role.
        return {"type": "pass"}
