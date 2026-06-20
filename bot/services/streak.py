from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.config import PROJECT_ROOT

STREAK_PATH = PROJECT_ROOT / "data" / "streaks.json"

STREAK_MILESTONES: dict[int, str] = {
    5: "опять ты",
    10: "ну всё, опять ты",
    20: "бро, это уже просто система",
    30: "да сколько можно, заебал",
}


def _load_state() -> dict[str, dict[str, Any]]:
    if not STREAK_PATH.exists():
        return {}
    raw = json.loads(STREAK_PATH.read_text(encoding="utf-8"))
    chats = raw.get("chats", raw)
    return {str(chat_id): entry for chat_id, entry in chats.items()}


def _save_state(chats: dict[str, dict[str, Any]]) -> None:
    STREAK_PATH.parent.mkdir(parents=True, exist_ok=True)
    STREAK_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def next_streak_count(chat_id: int, user_id: int) -> int:
    entry = _load_state().get(str(chat_id), {})
    if entry.get("user_id") == user_id:
        return int(entry.get("count", 0)) + 1
    return 1


def streak_reply_for_count(count: int) -> str | None:
    return STREAK_MILESTONES.get(count)


def peek_streak_reply(chat_id: int, user_id: int) -> str | None:
    return streak_reply_for_count(next_streak_count(chat_id, user_id))


def record_streak(chat_id: int, user_id: int) -> int:
    chats = _load_state()
    entry = chats.setdefault(str(chat_id), {})
    if entry.get("user_id") == user_id:
        count = int(entry.get("count", 0)) + 1
    else:
        count = 1
    entry["user_id"] = user_id
    entry["count"] = count
    _save_state(chats)
    return count


def get_current_streak(chat_id: int) -> tuple[int | None, int]:
    entry = _load_state().get(str(chat_id), {})
    user_id = entry.get("user_id")
    count = int(entry.get("count", 0))
    if user_id is None or count <= 0:
        return None, 0
    return int(user_id), count
