"""JSON-backed per-user storage, keyed by the WeChat account's own user_id.

user_id is stable across restarts (it comes from ClawBot, not invented by
this app), unlike web_multi.py's login_id — see its module docstring.
"""

import json
from pathlib import Path

DATA_PATH = Path(__file__).parent / "data" / "bindings.json"
DATA_PATH.parent.mkdir(exist_ok=True)


def _load() -> dict:
    if not DATA_PATH.exists():
        return {}
    return json.loads(DATA_PATH.read_text("utf-8"))


def _save(data: dict) -> None:
    DATA_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


async def set_binding(user_id: str, game: str, code: str) -> None:
    data = _load()
    data.setdefault(user_id, {})[game] = code
    _save(data)


async def get_binding(user_id: str, game: str) -> str | None:
    return _load().get(user_id, {}).get(game)
