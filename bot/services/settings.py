from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bot.config import DEFAULT_REPLY_COOLDOWN_SECONDS, PROJECT_ROOT, RANDOM_REPLY_PROBABILITY

SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"
RESET_ALIASES = {"reset", "default", "сброс"}


def _normalize_entry(entry: Any) -> dict[str, Any]:
    if isinstance(entry, (int, float)):
        return {"chance": float(entry)}
    if not isinstance(entry, dict):
        return {}

    result: dict[str, Any] = {}
    if "chance" in entry:
        result["chance"] = float(entry["chance"])
    if "cooldown_seconds" in entry:
        result["cooldown_seconds"] = float(entry["cooldown_seconds"])
    if isinstance(entry.get("users"), dict):
        result["users"] = {str(key): float(value) for key, value in entry["users"].items()}
    return result


def _load_chats() -> dict[str, dict[str, Any]]:
    if not SETTINGS_PATH.exists():
        return {}

    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    source = raw.get("chats", raw)
    return {str(chat_id): _normalize_entry(entry) for chat_id, entry in source.items()}


def _save_chats(chats: dict[str, dict[str, Any]]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _chat_entry(chat_id: int) -> dict[str, Any]:
    return _load_chats().get(str(chat_id), {})


def _user_storage_key(user_id: int | None, username: str | None) -> str | None:
    if user_id is not None:
        return str(user_id)
    if username:
        return f"@{username.lower().lstrip('@')}"
    return None


def _users_map(chat_id: int) -> dict[str, float]:
    users = _chat_entry(chat_id).get("users")
    if not isinstance(users, dict):
        return {}
    return {str(key): float(value) for key, value in users.items()}


def get_reply_probability(chat_id: int) -> float:
    entry = _chat_entry(chat_id)
    if "chance" in entry:
        return float(entry["chance"])
    return RANDOM_REPLY_PROBABILITY


def get_user_reply_probability(
    chat_id: int,
    user_id: int | None,
    username: str | None,
) -> float | None:
    users = _users_map(chat_id)
    if not users:
        return None

    keys: list[str] = []
    if user_id is not None:
        keys.append(str(user_id))
    if username:
        keys.append(f"@{username.lower().lstrip('@')}")

    for key in keys:
        if key in users:
            return users[key]
    return None


def get_effective_reply_probability(
    chat_id: int,
    user_id: int | None,
    username: str | None,
) -> float:
    user_probability = get_user_reply_probability(chat_id, user_id, username)
    if user_probability is not None:
        return user_probability
    return get_reply_probability(chat_id)


def list_user_reply_probabilities(chat_id: int) -> list[tuple[str, float]]:
    return sorted(_users_map(chat_id).items(), key=lambda item: item[0])


def set_reply_probability(chat_id: int, probability: float) -> None:
    chats = _load_chats()
    entry = chats.setdefault(str(chat_id), {})
    entry["chance"] = probability
    _save_chats(chats)


def clear_reply_probability(chat_id: int) -> None:
    chats = _load_chats()
    entry = chats.get(str(chat_id))
    if not entry:
        return
    entry.pop("chance", None)
    if entry:
        chats[str(chat_id)] = entry
    else:
        chats.pop(str(chat_id), None)
    _save_chats(chats)


def set_user_reply_probability(
    chat_id: int,
    user_id: int | None,
    username: str | None,
    probability: float,
) -> str:
    key = _user_storage_key(user_id, username)
    if key is None:
        raise ValueError("user")

    chats = _load_chats()
    entry = chats.setdefault(str(chat_id), {})
    users = entry.setdefault("users", {})
    users[key] = probability
    _save_chats(chats)
    return key


def clear_user_reply_probability(
    chat_id: int,
    user_id: int | None,
    username: str | None,
) -> bool:
    keys = []
    if user_id is not None:
        keys.append(str(user_id))
    if username:
        keys.append(f"@{username.lower().lstrip('@')}")

    chats = _load_chats()
    entry = chats.get(str(chat_id))
    if not entry:
        return False

    users = entry.get("users")
    if not isinstance(users, dict):
        return False

    removed = False
    for key in keys:
        if key in users:
            users.pop(key, None)
            removed = True

    if not users:
        entry.pop("users", None)
    if entry:
        chats[str(chat_id)] = entry
    else:
        chats.pop(str(chat_id), None)
    _save_chats(chats)
    return removed


def get_reply_cooldown(chat_id: int) -> float:
    entry = _chat_entry(chat_id)
    if "cooldown_seconds" in entry:
        return float(entry["cooldown_seconds"])
    return DEFAULT_REPLY_COOLDOWN_SECONDS


def set_reply_cooldown(chat_id: int, cooldown_seconds: float) -> None:
    chats = _load_chats()
    entry = chats.setdefault(str(chat_id), {})
    entry["cooldown_seconds"] = cooldown_seconds
    _save_chats(chats)


def clear_reply_cooldown(chat_id: int) -> None:
    chats = _load_chats()
    entry = chats.get(str(chat_id))
    if not entry:
        return
    entry.pop("cooldown_seconds", None)
    if entry:
        chats[str(chat_id)] = entry
    else:
        chats.pop(str(chat_id), None)
    _save_chats(chats)
