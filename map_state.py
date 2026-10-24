"""Persistent map data copied from a Mars view."""

from typing import cast

from bot_client import Base, GameMap, HighGoldSettings, MapCell, MarsView


class MapState:
    """Keep the map-related subset of a ``MarsView`` between turns.

    Map cells are stored in row-major order, at ``y * width + x``. The map
    and its cells are copied on construction so updates to this state do not
    modify the source view.
    """

    def __init__(self, view: MarsView) -> None:
        game_map = view["map"]
        self.map: GameMap = {
            "width": game_map["width"],
            "height": game_map["height"],
            "cells": list(game_map["cells"]),
        }
        self.bases: list[Base] = list(view["bases"])
        self.highGoldArea: HighGoldSettings = cast(
            HighGoldSettings, dict(view["highGoldArea"])
        )

    def update(self, view: MarsView) -> None:
        """Merge a new view, retaining known cells hidden in its map."""
        updated_map = view["map"]
        width = self.map["width"]
        height = self.map["height"]
        if updated_map["width"] != width or updated_map["height"] != height:
            raise ValueError("Updated map dimensions do not match the stored map.")

        cells = cast(list[MapCell], self.map["cells"])
        updated_cells = updated_map["cells"]
        if len(updated_cells) != width * height:
            raise ValueError("Updated map cell count does not match its dimensions.")

        for index, updated_cell in enumerate(updated_cells):
            if updated_cell["type"] == "hidden":
                continue
            if cells[index] != updated_cell:
                cells[index] = updated_cell

        for base in view["bases"]:
            if base not in self.bases:
                self.bases.append(base)
