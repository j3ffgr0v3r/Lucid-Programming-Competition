#!/usr/bin/env python3
import os

from bot_client import ActionsByEntity, BotClient, BotState, Identity, solar_view

API_KEY = os.environ.get("API_KEY", "replace-with-api-key")
API_BASE_URL = os.environ.get("LUCID_API_BASE_URL", "http://localhost:5173")


def calculate_actions(game_state: BotState, identity: Identity) -> ActionsByEntity:
    view = solar_view(game_state)

    # Strategy goes here.

    if view is not None and "entityId" in view:
        return {view["entityId"]: {"type": "Earth"}}

    return {}


if __name__ == "__main__":
    print("Edit calculate_actions to choose your rocket's actions.")
    if "LUCID_API_BASE_URL" not in os.environ:
        print(f"LUCID_API_BASE_URL is not set; using {API_BASE_URL}.")

    try:
        BotClient(API_KEY, API_BASE_URL).connect_and_run_bot(calculate_actions)
    except KeyboardInterrupt:
        pass
    except Exception as error:
        print(error)
        raise SystemExit(1)
