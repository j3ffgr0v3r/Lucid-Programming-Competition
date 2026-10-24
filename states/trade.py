"""Convert carried iron into gold, bank the cargo, then collect more ore."""

from bot import Bot
from bot_client import Action
from .state import State


class Trade(State):
    def next_action(self, bot: Bot) -> Action:
        if self.view is None:
            return {"type": "pass"}
        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is None or worker["readyOnTurn"] > self.view["turn"]:
            return {"type": "pass"}
        inventory = worker.get("inventory", {"gold": 0, "iron": 0})
        if inventory["iron"] >= 3:
            # Trades use inventory, not shared bank iron, and consume one turn.
            return {"type": "trade", "from": "iron"}

        # One or two remaining iron cannot be traded. Deposit it with the gold.
        next_state = "Bank" if inventory["gold"] or inventory["iron"] else "CenterOre"
        state = self.states.get(next_state)
        if state is None:
            return {"type": "pass"}
        result = state.next_action(bot)
        return result[1] if isinstance(result, tuple) else result
