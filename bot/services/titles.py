from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from bot.config import PROJECT_ROOT
from bot.services.stats import count_user_replies_all_time

PROGRESS_PATH = PROJECT_ROOT / "data" / "user_progress.json"
LEADERBOARD_PATH = PROJECT_ROOT / "data" / "guess_leaderboard.json"

REPLY_TIERS: tuple[tuple[int, str], ...] = (
    (1000, "ну это ваще кто?"),
    (500, "мегаХуй"),
    (100, "ебать хуй"),
    (50, "хуище"),
    (20, "хуеплет"),
)

WIN_TIERS: tuple[tuple[int, str], ...] = (
    (400, "ты кто?"),
    (150, "боженька долбоебов"),
    (50, "ебанат ну пиздец же"),
    (15, "пиздец долбоеб"),
    (5, "долбоеб"),
)

TitleContext = Literal["game", "reply", "both"]


def _load_progress() -> dict[str, dict[str, dict[str, Any]]]:
    if not PROGRESS_PATH.exists():
        return {}
    raw = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return raw.get("chats", raw)


def _save_progress(chats: dict[str, dict[str, dict[str, Any]]]) -> None:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _title_for_count(count: int, tiers: tuple[tuple[int, str], ...]) -> str | None:
    for threshold, title in tiers:
        if count >= threshold:
            return title
    return None


def _next_tier(count: int, tiers: tuple[tuple[int, str], ...]) -> tuple[int, str] | None:
    for threshold, title in reversed(tiers):
        if count < threshold:
            return threshold, title
    return None


def increment_reply_count(chat_id: int, user_id: int) -> int:
    chats = _load_progress()
    chat_key = str(chat_id)
    user_key = str(user_id)
    chat = chats.setdefault(chat_key, {})
    entry = chat.setdefault(user_key, {"replies": 0})
    current = int(entry.get("replies", 0))
    if current == 0:
        current = count_user_replies_all_time(chat_id, user_id)
    entry["replies"] = current + 1
    _save_progress(chats)
    return int(entry["replies"])


def get_reply_count(chat_id: int, user_id: int) -> int:
    entry = _load_progress().get(str(chat_id), {}).get(str(user_id), {})
    stored = int(entry.get("replies", 0))
    if stored > 0:
        return stored
    return count_user_replies_all_time(chat_id, user_id)


def get_win_count(chat_id: int, user_id: int) -> int:
    if not LEADERBOARD_PATH.exists():
        return 0
    raw = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
    board = raw.get("chats", raw).get(str(chat_id), {})
    entry = board.get(str(user_id), {})
    return int(entry.get("wins", 0))


def reply_title(chat_id: int, user_id: int) -> str | None:
    return _title_for_count(get_reply_count(chat_id, user_id), REPLY_TIERS)


def win_title(chat_id: int, user_id: int) -> str | None:
    return _title_for_count(get_win_count(chat_id, user_id), WIN_TIERS)


def format_titled_label(
    chat_id: int,
    user_id: int,
    base_label: str,
    *,
    context: TitleContext = "both",
) -> str:
    rt = reply_title(chat_id, user_id)
    wt = win_title(chat_id, user_id)

    if context == "game":
        title = wt or rt
    elif context == "reply":
        title = rt
    else:
        parts = [part for part in (wt, rt) if part]
        if len(parts) >= 2:
            title = f"{parts[0]} · {parts[1]}"
        elif parts:
            title = parts[0]
        else:
            title = None

    if title:
        return f"{title} {base_label}"
    return base_label


def build_titles_message(chat_id: int, user_id: int, base_label: str) -> str:
    replies = get_reply_count(chat_id, user_id)
    wins = get_win_count(chat_id, user_id)
    rt = reply_title(chat_id, user_id)
    wt = win_title(chat_id, user_id)

    lines = [
        f"Титулы {base_label}",
        "",
        f"Ответов бота на твои сообщения: {replies}",
        f"Титул за ответы: {rt or '—'}",
    ]
    next_reply = _next_tier(replies, REPLY_TIERS)
    if next_reply:
        need, title = next_reply
        lines.append(f"  → ещё {need - replies} до «{title}»")

    lines.extend(
        [
            "",
            f"Побед в «Угадай пародию»: {wins}",
            f"Титул за победы: {wt or '—'}",
        ]
    )
    next_win = _next_tier(wins, WIN_TIERS)
    if next_win:
        need, title = next_win
        lines.append(f"  → ещё {need - wins} до «{title}»")

    lines.extend(
        [
            "",
            "В играх показывается титул за победы (или за ответы, если побед ещё нет).",
        ]
    )
    return "\n".join(lines)
