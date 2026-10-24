import unittest

from bot import Bot
from bot_client import MarsView
from states.find_any_ore import FindAnyOreState
from states.find_gold import FindGoldState
from states.find_iron import FindIronState
from states.find_ore import FindOreState, SearchArea


class OreStateTests(unittest.TestCase):
    width = 5
    height = 5

    def make_view(
        self,
        ores: dict[tuple[int, int], tuple[str, int]] | None = None,
        *,
        area_size: tuple[int, int] = (1, 1),
    ) -> MarsView:
        cells: list[dict[str, object]] = [
            {"type": "empty"} for _ in range(self.width * self.height)
        ]
        for (x, y), (resource, amount) in (ores or {}).items():
            cells[y * self.width + x] = {"type": resource, "amount": amount}

        return MarsView(
            turn=1,
            map={"width": self.width, "height": self.height, "cells": cells},
            units=[],
            bases=[],
            scores={},
            teamResources={},
            highGoldArea={
                "width": area_size[0],
                "height": area_size[1],
                "min": 1,
                "max": 1,
                "spawnPercent": 35,
            },
            warnings=[],
            info=[],
            effects=[],
        )

    @staticmethod
    def make_bot(x: int, y: int) -> Bot:
        return Bot("worker", "unit-1", "team-1", (x, y))

    @staticmethod
    def full_map_area() -> SearchArea:
        return {"x": 0, "y": 0, "width": 5, "height": 5}

    def test_find_iron_state_targets_iron_instead_of_closer_gold(self) -> None:
        view = self.make_view({(2, 1): ("gold", 2), (1, 2): ("iron", 2)})
        action = FindIronState(view, self.full_map_area()).next_action(self.make_bot(1, 1))

        self.assertEqual(action, {"type": "move", "direction": "south"})

    def test_find_gold_state_targets_gold_instead_of_closer_iron(self) -> None:
        view = self.make_view({(2, 1): ("gold", 2), (1, 2): ("iron", 2)})
        action = FindGoldState(view).next_action(self.make_bot(1, 1))

        self.assertEqual(action, {"type": "move", "direction": "east"})

    def test_find_any_ore_state_chooses_nearest_deposit(self) -> None:
        view = self.make_view({(1, 0): ("gold", 2), (2, 0): ("iron", 2)})
        action = FindAnyOreState(view).next_action(self.make_bot(0, 0))

        self.assertEqual(action, {"type": "move", "direction": "east"})

    def test_find_any_ore_state_mines_when_standing_on_an_ore(self) -> None:
        view = self.make_view({(2, 2): ("gold", 2), (3, 2): ("iron", 2)})
        action = FindAnyOreState(view).next_action(self.make_bot(2, 2))

        self.assertEqual(action, {"type": "mine"})

    def test_generic_state_filters_by_resource_and_search_area(self) -> None:
        view = self.make_view(
            {
                (1, 2): ("gold", 2),
                (2, 1): ("gold", 2),
                (1, 0): ("iron", 2),
            }
        )
        area: SearchArea = {"x": 2, "y": 1, "width": 1, "height": 1}
        action = FindOreState(view, "gold", area).next_action(self.make_bot(1, 1))

        self.assertEqual(action, {"type": "move", "direction": "east"})

    def test_depleted_ore_is_ignored_and_search_falls_back(self) -> None:
        view = self.make_view({(1, 0): ("iron", 0)})
        action = FindAnyOreState(view).next_action(self.make_bot(0, 0))

        self.assertEqual(action["type"], "move")

    def test_invalid_search_area_returns_pass(self) -> None:
        view = self.make_view({(2, 2): ("iron", 2)})
        area: SearchArea = {"x": 1, "y": 1, "width": 0, "height": 2}
        action = FindOreState(view, "iron", area).next_action(self.make_bot(0, 0))

        self.assertEqual(action, {"type": "pass"})

    def test_any_ore_state_passes_when_already_at_center_without_visible_ore(self) -> None:
        view = self.make_view()
        action = FindAnyOreState(view).next_action(self.make_bot(2, 2))

        self.assertEqual(action, {"type": "pass"})


if __name__ == "__main__":
    unittest.main()
