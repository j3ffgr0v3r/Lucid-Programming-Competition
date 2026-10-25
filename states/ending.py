"""Return home, finish useful conversions, and deposit before the deadline."""

from .state import State


class Ending(State):
    def next_action(self, bot):
        worker = next((u for u in self.view["units"] if u["unitId"] == bot.id), None)
        if worker is None or worker["readyOnTurn"] > self.view["turn"]:
            return {"type": "pass"}
        inventory = worker["inventory"]
        at_home = any(b["teamId"] == bot.team_id and
                      (b["position"]["x"], b["position"]["y"]) == bot.coordinates
                      for b in self.view["bases"])
        if at_home:
            if inventory["iron"] >= 3 and self.turns_left >= 2:
                return {"type": "trade", "from": "iron"}
            return {"type": "deposit" if sum(inventory.values()) else "pass"}
        bot.ore_returning = True
        bot.ore_target = None
        bot.ore_explore_target = None
        result = self.states["Bank"].next_action(bot)
        return result[1] if isinstance(result, tuple) else result
