from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.config import PROJECT_ROOT

STATS_PATH = PROJECT_ROOT / "data" / "stats.json"

PERIOD_SECONDS: dict[str, int | None] = {
    "day": 24 * 60 * 60,
    "week": 7 * 24 * 60 * 60,
    "month": 30 * 24 * 60 * 60,
    "all": None,
}

DEFAULT_PERIOD = "week"
PERIOD_LABELS = {
    "day": "за 24 часа",
    "week": "за 7 дней",
    "month": "за 30 дней",
    "all": "за всё время",
}


@dataclass(frozen=True)
class ReplyRecord:
    ts: float
    user_id: int
    user_label: str
    source: str
    trigger_words: tuple[str, ...]


def _load_records() -> dict[str, list[dict[str, Any]]]:
    if not STATS_PATH.exists():
        return {}
    raw = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    chats = raw.get("chats", raw)
    return {str(chat_id): list(entries) for chat_id, entries in chats.items()}


def _save_records(chats: dict[str, list[dict[str, Any]]]) -> None:
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_reply(
    chat_id: int,
    user_id: int,
    user_label: str,
    source: str,
    trigger_words: list[str] | tuple[str, ...] | None = None,
) -> None:
    from bot.services.titles import increment_reply_count

    increment_reply_count(chat_id, user_id)
    chats = _load_records()
    entries = chats.setdefault(str(chat_id), [])
    entries.append(
        {
            "ts": time.time(),
            "user_id": user_id,
            "user_label": user_label,
            "source": source,
            "trigger_words": list(trigger_words or ()),
        }
    )
    if len(entries) > 5000:
        chats[str(chat_id)] = entries[-5000:]
    _save_records(chats)


def count_user_replies_all_time(chat_id: int, user_id: int) -> int:
    return sum(
        1
        for entry in _load_records().get(str(chat_id), [])
        if int(entry.get("user_id", 0)) == user_id
    )


def _filter_records(
    chat_id: int,
    period: str,
) -> list[ReplyRecord]:
    seconds = PERIOD_SECONDS.get(period, PERIOD_SECONDS[DEFAULT_PERIOD])
    now = time.time()
    cutoff = None if seconds is None else now - seconds

    records: list[ReplyRecord] = []
    for entry in _load_records().get(str(chat_id), []):
        ts = float(entry.get("ts", 0))
        if cutoff is not None and ts < cutoff:
            continue
        records.append(
            ReplyRecord(
                ts=ts,
                user_id=int(entry.get("user_id", 0)),
                user_label=str(entry.get("user_label", "?")),
                source=str(entry.get("source", "text")),
                trigger_words=tuple(str(word) for word in entry.get("trigger_words", [])),
            )
        )
    return records


def _format_top(counter: Counter[str], limit: int = 5) -> str:
    if not counter:
        return "  —"
    lines = []
    for index, (label, count) in enumerate(counter.most_common(limit), start=1):
        lines.append(f"  {index}. {label} — {count}")
    return "\n".join(lines)


def build_stats_message(chat_id: int, period: str = DEFAULT_PERIOD) -> str:
    if period not in PERIOD_SECONDS:
        period = DEFAULT_PERIOD

    records = _filter_records(chat_id, period)
    label = PERIOD_LABELS[period]

    if not records:
        return f"Статистика {label}: пока пусто."

    by_user: Counter[str] = Counter()
    by_word: Counter[str] = Counter()
    by_source: Counter[str] = Counter()

    for record in records:
        by_user[record.user_label] += 1
        by_source[record.source] += 1
        for word in record.trigger_words:
            by_word[word.lower()] += 1

    source_names = {
        "text": "текст",
        "attachment": "вложения",
        "streak": "серии",
        "rare": "редкие",
        "reply_context": "контекст",
        "edit": "редактуры",
    }
    source_lines = []
    for source, count in by_source.most_common():
        name = source_names.get(source, source)
        source_lines.append(f"  {name}: {count}")

    return (
        f"Статистика {label}\n\n"
        f"Ответов бота: {len(records)}\n\n"
        f"Кого дразнили чаще:\n{_format_top(by_user)}\n\n"
        f"Топ слов:\n{_format_top(by_word)}\n\n"
        f"По типам:\n" + ("\n".join(source_lines) if source_lines else "  —")
    )


def stats_period_help() -> str:
    return (
        "Периоды:\n"
        "/stats — за 7 дней\n"
        "/stats day — за 24 часа\n"
        "/stats week — за 7 дней\n"
        "/stats month — за 30 дней\n"
        "/stats all — за всё время"
    )
