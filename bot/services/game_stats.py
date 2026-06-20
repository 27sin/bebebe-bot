from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from bot.config import PROJECT_ROOT

GAME_STATS_PATH = PROJECT_ROOT / "data" / "game_stats.json"

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

OUTCOME_LABELS = {
    "winner": "победа",
    "tie_after_breaker": "ничья",
    "silent": "молчали",
    "stopped": "остановлено",
    "no_winner": "без победителя",
}

MAX_EVENTS_PER_CHAT = 5000


def _load_events() -> dict[str, list[dict[str, Any]]]:
    if not GAME_STATS_PATH.exists():
        return {}
    raw = json.loads(GAME_STATS_PATH.read_text(encoding="utf-8"))
    chats = raw.get("chats", raw)
    return {str(chat_id): list(entries) for chat_id, entries in chats.items()}


def _save_events(chats: dict[str, list[dict[str, Any]]]) -> None:
    GAME_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAME_STATS_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _append_event(chat_id: int, event: dict[str, Any]) -> None:
    chats = _load_events()
    entries = chats.setdefault(str(chat_id), [])
    event["ts"] = time.time()
    entries.append(event)
    if len(entries) > MAX_EVENTS_PER_CHAT:
        chats[str(chat_id)] = entries[-MAX_EVENTS_PER_CHAT:]
    _save_events(chats)


def record_session_start(
    chat_id: int,
    user_id: int,
    user_label: str,
    *,
    mode: str,
    rounds: int,
    party_size: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event": "session_start",
        "user_id": user_id,
        "user_label": user_label,
        "mode": mode,
        "rounds": rounds,
    }
    if party_size is not None:
        payload["party_size"] = party_size
    _append_event(chat_id, payload)


def record_correct_guess(chat_id: int, user_id: int, user_label: str) -> None:
    _append_event(
        chat_id,
        {
            "event": "correct_guess",
            "user_id": user_id,
            "user_label": user_label,
        },
    )


def record_guess_attempt(chat_id: int, user_id: int, user_label: str) -> None:
    _append_event(
        chat_id,
        {
            "event": "guess_attempt",
            "user_id": user_id,
            "user_label": user_label,
        },
    )


def record_session_end(
    chat_id: int,
    *,
    mode: str,
    outcome: str,
    rounds_played: int,
    winners: list[tuple[int, str]] | None = None,
) -> None:
    _append_event(
        chat_id,
        {
            "event": "session_end",
            "mode": mode,
            "outcome": outcome,
            "rounds_played": rounds_played,
            "winners": [
                {"user_id": user_id, "user_label": label}
                for user_id, label in (winners or [])
            ],
        },
    )


def _filter_events(chat_id: int, period: str) -> list[dict[str, Any]]:
    seconds = PERIOD_SECONDS.get(period, PERIOD_SECONDS[DEFAULT_PERIOD])
    cutoff = None if seconds is None else time.time() - seconds

    events: list[dict[str, Any]] = []
    for entry in _load_events().get(str(chat_id), []):
        ts = float(entry.get("ts", 0))
        if cutoff is not None and ts < cutoff:
            continue
        events.append(entry)
    return events


def _format_top(counter: Counter[str], limit: int = 5) -> str:
    if not counter:
        return "  —"
    lines = []
    for index, (label, count) in enumerate(counter.most_common(limit), start=1):
        lines.append(f"  {index}. {label} — {count}")
    return "\n".join(lines)


def build_game_stats_message(chat_id: int, period: str = DEFAULT_PERIOD) -> str:
    if period not in PERIOD_SECONDS:
        period = DEFAULT_PERIOD

    events = _filter_events(chat_id, period)
    label = PERIOD_LABELS[period]

    if not events:
        return f"Статистика игр {label}: пока пусто.\nСтарт: /guess или /guessparty"

    sessions_started = 0
    solo_sessions = 0
    party_sessions = 0
    rounds_played = 0
    correct_by_user: Counter[str] = Counter()
    attempts_by_user: Counter[str] = Counter()
    wins_by_user: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()

    for entry in events:
        event_type = str(entry.get("event", ""))
        user_label = str(entry.get("user_label", "?"))

        if event_type == "session_start":
            sessions_started += 1
            if entry.get("mode") == "party":
                party_sessions += 1
            else:
                solo_sessions += 1
        elif event_type == "correct_guess":
            correct_by_user[user_label] += 1
        elif event_type == "guess_attempt":
            attempts_by_user[user_label] += 1
        elif event_type == "session_end":
            rounds_played += int(entry.get("rounds_played", 0))
            outcome = str(entry.get("outcome", ""))
            outcomes[OUTCOME_LABELS.get(outcome, outcome)] += 1
            for winner in entry.get("winners", []):
                wins_by_user[str(winner.get("user_label", "?"))] += 1

    outcome_lines = []
    for name, count in outcomes.most_common():
        outcome_lines.append(f"  {name}: {count}")

    return (
        f"🎮 Статистика игр {label}\n\n"
        f"Сессий: {sessions_started} (solo: {solo_sessions}, party: {party_sessions})\n"
        f"Раундов сыграно: {rounds_played}\n"
        f"Угадываний: {sum(correct_by_user.values())}\n"
        f"Попыток (в т.ч. промахи): {sum(attempts_by_user.values()) + sum(correct_by_user.values())}\n\n"
        f"Кто чаще угадывал:\n{_format_top(correct_by_user)}\n\n"
        f"Побед в сессиях:\n{_format_top(wins_by_user)}\n\n"
        f"Исходы сессий:\n" + ("\n".join(outcome_lines) if outcome_lines else "  —")
    )


def game_stats_period_help() -> str:
    return (
        "Периоды:\n"
        "/gamestats — за 7 дней\n"
        "/gamestats day — за 24 часа\n"
        "/gamestats week — за 7 дней\n"
        "/gamestats month — за 30 дней\n"
        "/gamestats all — за всё время"
    )
