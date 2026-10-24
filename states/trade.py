"""Convert carried iron into gold, bank the cargo, then collect more ore."""

from bot import Bot
from bot_client import Action
from .state import State

BANK_TURN_BUFFER = 2


class Trade(State):
    def next_action(self, bot: Bot) -> Action:
        if self.view is None:
            return {"type": "pass"}
        worker = next((unit for unit in self.view["units"] if unit["unitId"] == bot.id), None)
        if worker is None or worker["readyOnTurn"] > self.view["turn"]:
            return {"type": "pass"}
        inventory = worker.get("inventory", {"gold": 0, "iron": 0})
        carried = inventory["gold"] + inventory["iron"]
        bank = self.states.get("Bank")
        search_state = "CenterOre" if bot.search_area_index is not None else "PatrolOre"
        at_base = any(
            base["teamId"] == bot.team_id
            and (base["position"]["x"], base["position"]["y"]) == bot.coordinates
            for base in self.view["bases"]
        )
        if at_base and inventory["iron"] >= 3:
            # Already home: no travel uncertainty remains. Spend one turn on
            # each profitable trade, retaining the final turn for depositing.
            if self.turns_left is None or self.turns_left >= 2:
                return {"type": "trade", "from": "iron"}
            return self._delegate("Bank", bot)
        if carried and self.turns_left is not None and bank is not None:
            bank_turns = bank.turns_to_bank(bot)
            if bank_turns is not None and self.turns_left <= bank_turns + inventory["iron"] // 3 + BANK_TURN_BUFFER:
                if not bot.ore_returning and inventory["iron"] < 3:
                    # Allow another pickup only if its whole trip still fits.
                    # The ore state rechecks stock, terrain, and time;
                    # otherwise it sends the existing cargo home.
                    return self._delegate(search_state, bot)
                # Carried gold does not score: leave enough time to deposit it.
                bot.ore_returning = True
                return self._delegate("Bank", bot)
        if inventory["iron"] >= 3:
            # Trades use inventory, not shared bank iron, and consume one turn.
            return {"type": "trade", "from": "iron"}

        # Resume this rover's assigned search after trading or banking.
        next_state = "Bank" if (
            carried >= worker.get("inventoryCapacity", 8)
            or (carried and bot.ore_returning)
        ) else search_state
        return self._delegate(next_state, bot)

    def _delegate(self, next_state: str, bot: Bot) -> Action:
        if next_state == "Bank":
            bot.ore_returning = True
            bot.ore_target = None
            bot.ore_explore_target = None
        state = self.states.get(next_state)
        if state is None:
            return {"type": "pass"}
        result = state.next_action(bot)
        return result[1] if isinstance(result, tuple) else result
