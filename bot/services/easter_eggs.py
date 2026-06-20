from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from bot.config import PROJECT_ROOT

REGISTRY_PATH = PROJECT_ROOT / "rules" / "easter_eggs.json"
STATE_PATH = PROJECT_ROOT / "data" / "easter_eggs.json"

STREAK_MILESTONES: tuple[int, ...] = (5, 10, 20, 30)


@dataclass(frozen=True)
class EasterProgress:
    completed: int
    total: int


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _load_state() -> dict[str, dict[str, dict[str, Any]]]:
    if not STATE_PATH.exists():
        return {}
    raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return raw.get("chats", raw)


def _save_state(chats: dict[str, dict[str, dict[str, Any]]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _default_user_state() -> dict[str, Any]:
    return {
        "unlocked": [],
        "streak_level": 0,
        "rare_seen": [],
        "attachments_seen": [],
    }


def _user_state(chat_id: int, user_id: int) -> dict[str, Any]:
    chats = _load_state()
    state = chats.setdefault(str(chat_id), {}).setdefault(str(user_id), _default_user_state())
    for key, default in _default_user_state().items():
        state.setdefault(key, default.copy() if isinstance(default, list) else default)
    return state


def _persist_user(chat_id: int, user_id: int, state: dict[str, Any]) -> None:
    chats = _load_state()
    chats.setdefault(str(chat_id), {})[str(user_id)] = state
    _save_state(chats)


def _unlock_in_state(state: dict[str, Any], egg_id: str) -> None:
    unlocked: list[str] = state.setdefault("unlocked", [])
    if egg_id not in unlocked:
        unlocked.append(egg_id)


def stop_word_egg_id(text: str) -> str | None:
    from bot.services.rules import extract_words

    words = extract_words(text)
    if not words:
        return None
    last = words[-1].lower()
    for egg in _registry().get("eggs", []):
        if egg.get("kind") != "single" or not str(egg.get("id", "")).startswith("stop_"):
            continue
        triggers = {str(word).lower() for word in egg.get("words", [])}
        if last in triggers:
            return str(egg["id"])
    return None


def _registry_stop_word_trigger(text: str, chat_id: int) -> str | None:
    from bot.services.rules import _NAME_REPLIES, _last_word, get_custom_rule

    last = _last_word(text)
    if not last:
        return None
    normalized = last.lower()
    for names, _reply in _NAME_REPLIES:
        if normalized in names:
            return None
    if get_custom_rule(chat_id, normalized):
        return None
    return stop_word_egg_id(text)


def is_two_word_parody(text: str, reply: str) -> bool:
    from bot.services.rules import _parody_two_words, extract_words

    words = extract_words(text)
    if len(words) != 2:
        return False
    two_word = _parody_two_words(words)
    return two_word is not None and two_word == reply


def on_text_reply(chat_id: int, user_id: int, text: str, reply: str, source: str) -> None:
    if source in {"rare", "streak", "edit", "reply_context"}:
        return

    state = _user_state(chat_id, user_id)

    if is_two_word_parody(text, reply):
        _unlock_in_state(state, "parody_two_words")

    stop_id = _registry_stop_word_trigger(text, chat_id)
    if stop_id:
        _unlock_in_state(state, stop_id)

    _persist_user(chat_id, user_id, state)


def on_rare_reply(chat_id: int, user_id: int, rare_text: str) -> None:
    valid = set(_registry().get("rare_replies", []))
    if rare_text not in valid:
        return

    state = _user_state(chat_id, user_id)
    seen: list[str] = state.setdefault("rare_seen", [])
    if rare_text not in seen:
        seen.append(rare_text)

    _unlock_in_state(state, "rare_first")

    required = 12
    for egg in _registry().get("eggs", []):
        if egg.get("id") == "rare_all":
            required = int(egg.get("requires", 12))
            break
    if len(seen) >= required:
        _unlock_in_state(state, "rare_all")

    _persist_user(chat_id, user_id, state)


def on_streak_milestone(chat_id: int, user_id: int, streak_count: int) -> None:
    if streak_count not in STREAK_MILESTONES:
        return
    state = _user_state(chat_id, user_id)
    level = STREAK_MILESTONES.index(streak_count) + 1
    if int(state.get("streak_level", 0)) < level:
        state["streak_level"] = level
    _persist_user(chat_id, user_id, state)


def on_attachment_reply(chat_id: int, user_id: int, attachment_type: str) -> None:
    state = _user_state(chat_id, user_id)
    seen: list[str] = state.setdefault("attachments_seen", [])
    if attachment_type not in seen:
        seen.append(attachment_type)

    for egg in _registry().get("eggs", []):
        if egg.get("id") != "attach_all":
            continue
        required_types = list(egg.get("attachment_types", []))
        if all(item in seen for item in required_types):
            _unlock_in_state(state, "attach_all")
        break

    _persist_user(chat_id, user_id, state)


def on_edit_reaction(chat_id: int, user_id: int) -> None:
    state = _user_state(chat_id, user_id)
    _unlock_in_state(state, "edit_reaction")
    _persist_user(chat_id, user_id, state)


def on_game_first_win(chat_id: int, user_id: int) -> None:
    from bot.services.titles import get_win_count

    if get_win_count(chat_id, user_id) != 0:
        return
    state = _user_state(chat_id, user_id)
    _unlock_in_state(state, "game_first_win")
    _persist_user(chat_id, user_id, state)


def get_progress(chat_id: int, user_id: int) -> EasterProgress:
    state = _load_state().get(str(chat_id), {}).get(str(user_id), {})
    unlocked = set(state.get("unlocked", []))
    streak_level = int(state.get("streak_level", 0))

    completed = 0
    total = 0

    for egg in _registry().get("eggs", []):
        kind = egg.get("kind")
        egg_id = str(egg.get("id", ""))

        if kind == "single":
            total += 1
            if egg_id in unlocked:
                completed += 1
        elif kind == "tiered":
            levels = len(egg.get("levels", STREAK_MILESTONES))
            total += levels
            completed += min(streak_level, levels)
        elif kind == "collection":
            total += 1
            if egg_id in unlocked:
                completed += 1

    return EasterProgress(completed=completed, total=total)


def format_progress_line(chat_id: int, user_id: int) -> str:
    progress = get_progress(chat_id, user_id)
    label = _registry().get("display", {}).get("profile_label", "Пасхалки")
    return f"{label}: {progress.completed} / {progress.total}"
