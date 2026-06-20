from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from bot.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DB_PATH = PROJECT_ROOT / "data" / "analytics.db"
MSK = ZoneInfo("Europe/Moscow")

PERIOD_SECONDS: dict[str, int | None] = {
    "day": 24 * 60 * 60,
    "week": 7 * 24 * 60 * 60,
    "month": 30 * 24 * 60 * 60,
    "all": None,
}

PERIOD_LABELS = {
    "day": "за 24 часа",
    "week": "за 7 дней",
    "month": "за 30 дней",
    "all": "за всё время",
}

SOURCE_LABELS = {
    "text": "текст",
    "attachment": "вложения",
    "streak": "серии",
    "rare": "редкие",
    "reply_context": "контекст",
    "edit": "редактуры",
}

GAME_MODE_LABELS = {
    "solo": "solo",
    "party": "party",
    "duel": "duel",
}

OUTCOME_LABELS = {
    "winner": "победа",
    "tie_after_breaker": "ничья",
    "silent": "молчали",
    "stopped": "остановлено",
    "no_winner": "без победителя",
}


@dataclass(frozen=True)
class PeriodWindow:
    start: float
    end: float
    label: str


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                event TEXT NOT NULL,
                chat_id INTEGER,
                user_id INTEGER,
                props TEXT NOT NULL DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
            CREATE INDEX IF NOT EXISTS idx_events_event_ts ON events(event, ts);
            CREATE INDEX IF NOT EXISTS idx_events_chat_ts ON events(chat_id, ts);

            CREATE TABLE IF NOT EXISTS daily_metrics (
                day TEXT NOT NULL PRIMARY KEY,
                replies INTEGER NOT NULL DEFAULT 0,
                active_users INTEGER NOT NULL DEFAULT 0,
                active_chats INTEGER NOT NULL DEFAULT 0,
                commands INTEGER NOT NULL DEFAULT 0,
                game_sessions INTEGER NOT NULL DEFAULT 0,
                llm_calls INTEGER NOT NULL DEFAULT 0,
                llm_errors INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT NOT NULL PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def track(
    event: str,
    *,
    chat_id: int | None = None,
    user_id: int | None = None,
    **props: Any,
) -> None:
    try:
        payload = {key: value for key, value in props.items() if value is not None}
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO events (ts, event, chat_id, user_id, props)
                VALUES (?, ?, ?, ?, ?)
                """,
                (time.time(), event, chat_id, user_id, json.dumps(payload, ensure_ascii=False)),
            )
    except Exception:
        logger.exception("analytics.track failed event=%s", event)


def _meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _day_bounds(day: date) -> tuple[float, float]:
    start = datetime(day.year, day.month, day.day, tzinfo=MSK).timestamp()
    end = start + 24 * 60 * 60
    return start, end


def rollup_day(day: date) -> None:
    start, end = _day_bounds(day)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT event, chat_id, user_id, props
            FROM events
            WHERE ts >= ? AND ts < ?
            """,
            (start, end),
        ).fetchall()

        replies = 0
        users: set[int] = set()
        chats: set[int] = set()
        commands = 0
        game_sessions = 0
        llm_calls = 0
        llm_errors = 0

        for row in rows:
            event = str(row["event"])
            chat_id = row["chat_id"]
            user_id = row["user_id"]
            if chat_id is not None:
                chats.add(int(chat_id))
            if user_id is not None:
                users.add(int(user_id))

            if event == "reply_sent":
                replies += 1
            elif event == "command":
                commands += 1
            elif event == "session_start":
                game_sessions += 1
            elif event == "llm_call":
                llm_calls += 1
                props = json.loads(row["props"] or "{}")
                if not props.get("success", True):
                    llm_errors += 1

        conn.execute(
            """
            INSERT INTO daily_metrics (
                day, replies, active_users, active_chats, commands,
                game_sessions, llm_calls, llm_errors
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day) DO UPDATE SET
                replies = excluded.replies,
                active_users = excluded.active_users,
                active_chats = excluded.active_chats,
                commands = excluded.commands,
                game_sessions = excluded.game_sessions,
                llm_calls = excluded.llm_calls,
                llm_errors = excluded.llm_errors
            """,
            (
                day.isoformat(),
                replies,
                len(users),
                len(chats),
                commands,
                game_sessions,
                llm_calls,
                llm_errors,
            ),
        )


def run_pending_rollups() -> None:
    init_db()
    today = datetime.now(MSK).date()
    with _connect() as conn:
        last_raw = _meta_get(conn, "last_rollup_date")
        if last_raw:
            cursor_day = date.fromisoformat(last_raw) + timedelta(days=1)
        else:
            row = conn.execute("SELECT MIN(ts) AS min_ts FROM events").fetchone()
            if row is None or row["min_ts"] is None:
                _meta_set(conn, "last_rollup_date", (today - timedelta(days=1)).isoformat())
                return
            cursor_day = datetime.fromtimestamp(float(row["min_ts"]), MSK).date()

        while cursor_day < today:
            rollup_day(cursor_day)
            _meta_set(conn, "last_rollup_date", cursor_day.isoformat())
            cursor_day += timedelta(days=1)


def _period_window(period: str) -> PeriodWindow:
    if period not in PERIOD_SECONDS:
        period = "week"
    now = time.time()
    seconds = PERIOD_SECONDS[period]
    if seconds is None:
        return PeriodWindow(0, now, PERIOD_LABELS[period])
    return PeriodWindow(now - seconds, now, PERIOD_LABELS[period])


def _count_events(conn: sqlite3.Connection, event: str, start: float, end: float) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM events
        WHERE event = ? AND ts >= ? AND ts < ?
        """,
        (event, start, end),
    ).fetchone()
    return int(row["cnt"]) if row else 0


def _distinct_count(
    conn: sqlite3.Connection,
    column: str,
    start: float,
    end: float,
    *,
    event: str | None = None,
) -> int:
    if column not in {"chat_id", "user_id"}:
        raise ValueError(column)
    query = f"SELECT COUNT(DISTINCT {column}) AS cnt FROM events WHERE ts >= ? AND ts < ? AND {column} IS NOT NULL"
    params: list[Any] = [start, end]
    if event is not None:
        query += " AND event = ?"
        params.append(event)
    row = conn.execute(query, params).fetchone()
    return int(row["cnt"]) if row else 0


def _json_counter(
    conn: sqlite3.Connection,
    event: str,
    prop: str,
    start: float,
    end: float,
    *,
    limit: int = 8,
) -> list[tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT json_extract(props, ?) AS key, COUNT(*) AS cnt
        FROM events
        WHERE event = ? AND ts >= ? AND ts < ?
          AND json_extract(props, ?) IS NOT NULL
        GROUP BY key
        ORDER BY cnt DESC
        LIMIT ?
        """,
        (f"$.{prop}", event, start, end, f"$.{prop}", limit),
    ).fetchall()
    return [(str(row["key"]), int(row["cnt"])) for row in rows]


def _format_delta(current: int, previous: int) -> str:
    if previous <= 0:
        if current <= 0:
            return "0%"
        return "+∞"
    delta = ((current - previous) / previous) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.0f}%"


def _format_top(items: list[tuple[str, int]], *, empty: str = "  —") -> str:
    if not items:
        return empty
    return "\n".join(f"  {index}. {label} — {count}" for index, (label, count) in enumerate(items, start=1))


def build_admin_stats_message(*, period: str = "week", compare_previous: bool = True) -> str:
    init_db()
    window = _period_window(period)
    prev_start = window.start - (window.end - window.start) if compare_previous and period != "all" else None
    prev_end = window.start if prev_start is not None else None

    with _connect() as conn:
        replies = _count_events(conn, "reply_sent", window.start, window.end)
        commands = _count_events(conn, "command", window.start, window.end)
        menu_actions = _count_events(conn, "menu_action", window.start, window.end)
        llm_calls = _count_events(conn, "llm_call", window.start, window.end)
        llm_error_rows = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM events
            WHERE event = 'llm_call' AND ts >= ? AND ts < ?
              AND json_extract(props, '$.success') = 0
            """,
            (window.start, window.end),
        ).fetchone()
        llm_errors = int(llm_error_rows["cnt"]) if llm_error_rows else 0

        active_chats = _distinct_count(conn, "chat_id", window.start, window.end)
        active_users = _distinct_count(conn, "user_id", window.start, window.end)
        total_chats = _distinct_count(conn, "chat_id", 0, window.end)
        skipped = _count_events(conn, "reply_skipped", window.start, window.end)
        egg_unlocks = _count_events(conn, "easter_egg_unlock", window.start, window.end)

        sessions = _count_events(conn, "session_start", window.start, window.end)
        correct = _count_events(conn, "correct_guess", window.start, window.end)
        attempts = _count_events(conn, "guess_attempt", window.start, window.end)

        by_source = _json_counter(conn, "reply_sent", "source", window.start, window.end)
        by_command = _json_counter(conn, "command", "command", window.start, window.end, limit=10)
        by_mode = _json_counter(conn, "session_start", "mode", window.start, window.end)
        by_outcome = _json_counter(conn, "session_end", "outcome", window.start, window.end)
        by_menu = _json_counter(conn, "menu_action", "menu_id", window.start, window.end, limit=6)
        by_skip = _json_counter(conn, "reply_skipped", "reason", window.start, window.end)

        prev_replies = None
        if prev_start is not None and prev_end is not None:
            prev_replies = _count_events(conn, "reply_sent", prev_start, prev_end)

    lines = [
        f"📈 Аналитика бота {window.label}",
        "",
        f"Чаты: {active_chats} активных / {total_chats} всего",
        f"Пользователи: {active_users} unique",
        f"Ответов бота: {replies}",
    ]

    if prev_replies is not None:
        lines[-1] += f" ({_format_delta(replies, prev_replies)} к прошлому периоду)"

    if by_source:
        source_parts = []
        total_source = sum(count for _, count in by_source)
        for key, count in by_source:
            name = SOURCE_LABELS.get(key, key)
            pct = (count / total_source * 100) if total_source else 0
            source_parts.append(f"{name} {pct:.0f}%")
        lines.extend(["", "По типам ответов:", "  " + " | ".join(source_parts)])

    lines.extend(
        [
            "",
            f"Команды: {commands} (меню-кнопки: {menu_actions})",
            f"Пропусков ответа: {skipped}",
        ]
    )
    if by_skip:
        lines.append("  " + ", ".join(f"{reason}: {count}" for reason, count in by_skip))

    lines.extend(
        [
            "",
            f"Игры: {sessions} сессий",
            f"  угадываний: {correct}, промахов: {attempts}",
        ]
    )
    if by_mode:
        mode_parts = [f"{GAME_MODE_LABELS.get(mode, mode)} {count}" for mode, count in by_mode]
        lines.append("  режимы: " + ", ".join(mode_parts))
    if by_outcome:
        outcome_parts = [
            f"{OUTCOME_LABELS.get(outcome, outcome)} {count}" for outcome, count in by_outcome
        ]
        lines.append("  исходы: " + ", ".join(outcome_parts))

    if llm_calls:
        err_pct = (llm_errors / llm_calls * 100) if llm_calls else 0
        lines.extend(["", f"LLM: {llm_calls} вызовов, ошибок {llm_errors} ({err_pct:.1f}%)"])
    else:
        lines.extend(["", "LLM: вызовов не было"])

    if egg_unlocks:
        lines.append(f"Пасхалки: {egg_unlocks} разблокировок")

    if by_command:
        labeled = [(f"/{cmd}", count) for cmd, count in by_command]
        lines.extend(["", "Топ команд:", _format_top(labeled)])

    if by_menu:
        lines.extend(["", "Меню-кнопки:", _format_top(by_menu)])

    lines.append("")
    lines.append("Периоды: /adminstats day | week | month | all")
    return "\n".join(lines)
