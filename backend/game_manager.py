from __future__ import annotations

from typing import Any

from state import store


def create_game(players: list[dict[str, Any]], script: str, storyteller_id: str, name: str = 'Blood on the Clocktower'):
    return store.create_or_update_game(
        storyteller_id=storyteller_id,
        game_name=name,
        script=script,
        players=players,
    )


def get_game():
    return store.current_game()


def clear_game() -> None:
    store.reset_game()
