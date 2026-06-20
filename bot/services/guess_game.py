from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiogram import Bot

from bot.config import PROJECT_ROOT
from bot.services.game_stats import (
    record_correct_guess,
    record_guess_attempt,
    record_session_end,
    record_session_start,
)
from bot.services.rules import WORD_PATTERN, parody_word

GAME_WORDS_PATH = PROJECT_ROOT / "rules" / "game_words.json"
LEADERBOARD_PATH = PROJECT_ROOT / "data" / "guess_leaderboard.json"

DEFAULT_ROUNDS = 3
MAX_ROUNDS = 10
MIN_ROUNDS = 1
ROUND_SECONDS = 60
LEADERBOARD_LIMIT = 10
FAILED_ROUND_COMMENT = "никто из долбоебов не справился"

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_sessions: dict[int, GameSession] = {}
_timeout_tasks: dict[int, asyncio.Task[None]] = {}
_round_locks: dict[int, asyncio.Lock] = {}
_watchdog_task: asyncio.Task[None] | None = None


@dataclass
class GameSession:
    chat_id: int
    total_rounds: int
    current_round: int
    answer: str
    parody: str
    round_token: int
    expires_at: float
    round_scores: dict[int, int] = field(default_factory=dict)
    round_labels: dict[int, str] = field(default_factory=dict)
    guess_attempts: set[int] = field(default_factory=set)
    round_attempts: set[int] = field(default_factory=set)
    started_by: int = 0
    starter_label: str = ""
    participants: frozenset[int] | None = None
    extra_round: bool = False
    tiebreaker_for: frozenset[int] | None = None
    rounds_started: int = 0


def bind_bot(bot: Bot) -> None:
    global _bot, _watchdog_task
    _bot = bot
    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = asyncio.create_task(
            _session_watchdog(),
            name="guess-session-watchdog",
        )


def is_game_active(chat_id: int) -> bool:
    return chat_id in _sessions


def is_party_game_active(chat_id: int) -> bool:
    session = _sessions.get(chat_id)
    return session is not None and session.participants is not None


def _load_game_words() -> list[str]:
    raw = json.loads(GAME_WORDS_PATH.read_text(encoding="utf-8"))
    return [str(word) for word in raw]


def _pick_challenge() -> tuple[str, str] | None:
    words = _load_game_words()
    random.shuffle(words)
    for word in words:
        parody = parody_word(word)
        if parody and parody.lower() != word.lower():
            return word, parody
    return None


def normalize_guess(text: str) -> str:
    words = WORD_PATTERN.findall(text.strip())
    if not words:
        return ""
    return words[-1].lower().replace("ё", "е")


def _normalize_answer(word: str) -> str:
    return word.lower().replace("ё", "е")


def _cancel_timeout(chat_id: int) -> None:
    task = _timeout_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _chat_lock(chat_id: int) -> asyncio.Lock:
    lock = _round_locks.get(chat_id)
    if lock is None:
        lock = asyncio.Lock()
        _round_locks[chat_id] = lock
    return lock


def _schedule_timeout(chat_id: int, round_token: int, expires_at: float) -> None:
    _cancel_timeout(chat_id)
    _timeout_tasks[chat_id] = asyncio.create_task(
        _round_timeout(chat_id, round_token, expires_at),
        name=f"guess-timeout-{chat_id}-{round_token}",
    )


async def _session_watchdog() -> None:
    while True:
        try:
            await asyncio.sleep(1)
            now = time.time()
            for chat_id in list(_sessions):
                session = _sessions.get(chat_id)
                if session is None or now <= session.expires_at:
                    continue
                await _on_round_timeout(chat_id, round_token=session.round_token)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Guess session watchdog failed")


async def _send(chat_id: int, text: str) -> None:
    if _bot is None:
        logger.warning("Guess message skipped: bot is not bound chat=%s", chat_id)
        return
    try:
        await _bot.send_message(chat_id, text)
    except Exception:
        logger.exception("Failed to send guess message chat=%s", chat_id)


def _session_scoreboard(session: GameSession) -> str:
    if not session.round_scores:
        return "  —"
    ranked = sorted(session.round_scores.items(), key=lambda item: (-item[1], item[0]))
    lines = []
    for index, (user_id, wins) in enumerate(ranked, start=1):
        label = session.round_labels.get(user_id, str(user_id))
        lines.append(f"  {index}. {label} — {wins}")
    return "\n".join(lines)


def _session_winners(session: GameSession) -> list[tuple[int, str]]:
    if not session.round_scores:
        return []
    best = max(session.round_scores.values())
    return [
        (user_id, session.round_labels.get(user_id, str(user_id)))
        for user_id, score in session.round_scores.items()
        if score == best
    ]


def _load_leaderboard() -> dict[str, dict[str, Any]]:
    if not LEADERBOARD_PATH.exists():
        return {}
    raw = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
    return raw.get("chats", raw)


def _save_leaderboard(chats: dict[str, dict[str, Any]]) -> None:
    LEADERBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEADERBOARD_PATH.write_text(
        json.dumps({"chats": chats}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_leaderboard_wins(chat_id: int, winners: list[tuple[int, str]]) -> None:
    if not winners:
        return
    chats = _load_leaderboard()
    chat_key = str(chat_id)
    board = chats.setdefault(chat_key, {})
    for user_id, label in winners:
        key = str(user_id)
        entry = board.setdefault(key, {"label": label, "wins": 0})
        entry["label"] = label
        entry["wins"] = int(entry.get("wins", 0)) + 1
    _save_leaderboard(chats)


def build_leaderboard_message(chat_id: int) -> str:
    board = _load_leaderboard().get(str(chat_id), {})
    if not board:
        return "Лидерборд «Угадай пародию» пуст.\nСтарт: /guess или /guess 5"

    ranked = sorted(
        board.items(),
        key=lambda item: (-int(item[1].get("wins", 0)), item[1].get("label", item[0])),
    )
    lines = []
    for index, (_, entry) in enumerate(ranked[:LEADERBOARD_LIMIT], start=1):
        label = str(entry.get("label", "?"))
        wins = int(entry.get("wins", 0))
        lines.append(f"  {index}. {label} — {wins}")
    return "🏆 Лидерборд «Угадай пародию»:\n" + "\n".join(lines)


async def _start_round(session: GameSession) -> str | None:
    challenge = _pick_challenge()
    if challenge is None:
        return None

    answer, parody = challenge
    session.answer = answer
    session.parody = parody
    session.round_attempts.clear()
    session.round_token += 1
    session.expires_at = time.time() + ROUND_SECONDS
    session.rounds_started += 1
    _schedule_timeout(session.chat_id, session.round_token, session.expires_at)

    if session.extra_round:
        round_line = "⚡ Дополнительный раунд (ничья)"
    else:
        round_line = f"Раунд {session.current_round}/{session.total_rounds}"

    return (
        f"{round_line}\n"
        f"Угадай слово: {parody}\n"
        f"⏱ {ROUND_SECONDS} сек"
    )


def _build_finale_message(session: GameSession, header: str, outcome: str) -> str:
    lines = [header, "", "🏁 Игра окончена!", "", "Итог:", _session_scoreboard(session)]
    winners = _session_winners(session)
    suffix = " (party)" if session.participants is not None else ""

    if outcome == "silent":
        lines.extend(["", "Вы че ебанулись? Больше не буду с вами играть."])
        return "\n".join(lines)

    if outcome == "stopped":
        if len(winners) == 1:
            _, name = winners[0]
            lines.extend(["", f"🏆 Лидирует: {name}"])
        elif winners:
            names = ", ".join(label for _, label in winners)
            lines.extend(["", f"🤝 Ничья: {names}"])
        return "\n".join(lines)

    if outcome == "winner" and len(winners) == 1:
        _, name = winners[0]
        lines.extend(
            [
                "",
                f"🏆 Победитель{suffix}: {name}",
                f"🎉 Поздравляю, {name}! Ты победил в «Угадай пародию»!",
                "+1 в лидерборд",
            ]
        )
        return "\n".join(lines)

    if outcome == "tie_after_breaker" and winners:
        names = ", ".join(label for _, label in winners)
        lines.extend(
            [
                "",
                f"🤝 Ничья{suffix}: {names}",
                "После дополнительного раунда победителя нет — делите победу.",
                "+1 в лидерборд каждому",
            ]
        )
        return "\n".join(lines)

    lines.extend(["", "Победителя нет — никто не угадал ни одного раунда."])
    return "\n".join(lines)


async def _finish_session(chat_id: int, header: str, *, outcome: str) -> None:
    session = _sessions.pop(chat_id, None)
    _cancel_timeout(chat_id)
    _round_locks.pop(chat_id, None)
    if session is None:
        return

    winners = _session_winners(session)
    mode = "party" if session.participants is not None else "solo"
    record_session_end(
        chat_id,
        mode=mode,
        outcome=outcome,
        rounds_played=session.rounds_started,
        winners=winners if outcome in {"winner", "tie_after_breaker", "stopped"} else None,
    )

    if outcome in {"winner", "tie_after_breaker"} and winners:
        record_leaderboard_wins(chat_id, winners)

    await _send(chat_id, _build_finale_message(session, header, outcome))


async def _resolve_session_end(chat_id: int, header: str) -> None:
    session = _sessions.get(chat_id)
    if session is None:
        return

    if not session.guess_attempts:
        await _finish_session(chat_id, header, outcome="silent")
        return

    winners = _session_winners(session)
    if len(winners) > 1:
        names = ", ".join(label for _, label in winners)
        session.extra_round = True
        session.tiebreaker_for = frozenset(user_id for user_id, _ in winners)
        round_text = await _start_round(session)
        if round_text is None:
            await _finish_session(
                chat_id,
                f"{header}\n\nНе удалось начать дополнительный раунд.",
                outcome="tie_after_breaker",
            )
            return

        await _send(
            chat_id,
            f"{header}\n\n🤝 Ничья: {names}\n⚡ Дополнительный раунд!\n\n{round_text}",
        )
        return

    if len(winners) == 1:
        await _finish_session(chat_id, header, outcome="winner")
        return

    await _finish_session(chat_id, header, outcome="no_winner")


async def _round_timeout(chat_id: int, round_token: int, expires_at: float) -> None:
    try:
        delay = expires_at - time.time()
        if delay > 0:
            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return

    await _on_round_timeout(chat_id, round_token=round_token)


async def _on_round_timeout(chat_id: int, *, round_token: int | None = None) -> None:
    async with _chat_lock(chat_id):
        session = _sessions.get(chat_id)
        if session is None:
            return

        token = round_token if round_token is not None else session.round_token
        if session.round_token != token:
            return

        answer = session.answer
        if session.extra_round:
            round_label = "дополнительном раунде"
        else:
            round_label = f"раунде {session.current_round}/{session.total_rounds}"
        header = f"⏱ Время вышло в {round_label}.\nБыло: {answer}"
        await _end_round_without_winner(chat_id, header, round_token=token)


async def _end_round_without_winner(chat_id: int, header: str, *, round_token: int) -> None:
    session = _sessions.get(chat_id)
    if session is None or session.round_token != round_token:
        return

    _cancel_timeout(chat_id)

    if session.extra_round:
        winners = _session_winners(session)
        if len(winners) == 1:
            await _finish_session(chat_id, header, outcome="winner")
        elif len(winners) > 1:
            await _finish_session(chat_id, header, outcome="tie_after_breaker")
        else:
            await _finish_session(chat_id, header, outcome="no_winner")
        return

    full_header = f"{header}\n\n{FAILED_ROUND_COMMENT}"

    if session.current_round >= session.total_rounds:
        if not session.guess_attempts:
            await _finish_session(chat_id, full_header, outcome="silent")
        else:
            await _resolve_session_end(chat_id, full_header)
        return

    session.current_round += 1
    round_text = await _start_round(session)
    if round_text is None:
        await _finish_session(
            chat_id,
            f"{full_header}\n\nНе удалось начать следующий раунд.",
            outcome="no_winner",
        )
        return

    await _send(chat_id, f"{full_header}\n\n{round_text}")


async def _advance_or_finish(chat_id: int, header: str) -> None:
    async with _chat_lock(chat_id):
        session = _sessions.get(chat_id)
        if session is None:
            return

        _cancel_timeout(chat_id)

        if session.extra_round:
            winners = _session_winners(session)
            if len(winners) == 1:
                await _finish_session(chat_id, header, outcome="winner")
            elif len(winners) > 1:
                await _finish_session(chat_id, header, outcome="tie_after_breaker")
            else:
                await _finish_session(chat_id, header, outcome="no_winner")
            return

        if session.current_round >= session.total_rounds:
            await _resolve_session_end(chat_id, header)
            return

        session.current_round += 1
        round_text = await _start_round(session)
        if round_text is None:
            await _finish_session(
                chat_id,
                f"{header}\n\nНе удалось начать следующий раунд.",
                outcome="no_winner",
            )
            return

        await _send(chat_id, f"{header}\n\n{round_text}")


async def start_session(
    chat_id: int,
    rounds: int,
    starter_id: int,
    starter_label: str,
    *,
    participants: frozenset[int] | None = None,
) -> str:
    if is_game_active(chat_id):
        stop_cmd = "/guessparty stop" if participants is not None else "/guess stop"
        return f"Игра уже идёт. Дождись конца или {stop_cmd}"

    rounds = max(MIN_ROUNDS, min(MAX_ROUNDS, rounds))
    session = GameSession(
        chat_id=chat_id,
        total_rounds=rounds,
        current_round=1,
        answer="",
        parody="",
        round_token=0,
        expires_at=0.0,
        started_by=starter_id,
        starter_label=starter_label,
        participants=participants,
    )
    _sessions[chat_id] = session

    round_text = await _start_round(session)
    if round_text is None:
        _sessions.pop(chat_id, None)
        _cancel_timeout(chat_id)
        return "Не получилось подобрать загадку. Попробуй ещё раз."

    mode = "party" if participants is not None else "solo"
    record_session_start(
        chat_id,
        starter_id,
        starter_label,
        mode=mode,
        rounds=rounds,
        party_size=len(participants) if participants is not None else None,
    )

    if participants is not None:
        return (
            f"👥 Party-режим — {len(participants)} участник(ов).\n"
            f"{rounds} раунд(а) по {ROUND_SECONDS} сек.\n"
            f"Ответы засчитываются только участникам.\n\n"
            f"{round_text}"
        )

    return (
        f"🎮 Угадай пародию!\n"
        f"{rounds} раунд(а) по {ROUND_SECONDS} сек.\n"
        f"Ответ — одним словом. Стартовал {starter_label}.\n\n"
        f"{round_text}"
    )


async def stop_session(chat_id: int) -> str | None:
    async with _chat_lock(chat_id):
        if not is_game_active(chat_id):
            return "Сейчас нет активной игры."
        header = (
            "🛑 Party-игра остановлена."
            if is_party_game_active(chat_id)
            else "🛑 Игра остановлена."
        )
        await _finish_session(chat_id, header, outcome="stopped")
    return None


async def try_guess(chat_id: int, user_id: int, label: str, text: str) -> bool:
    session = _sessions.get(chat_id)
    if session is None:
        return False

    if session.participants is not None and user_id not in session.participants:
        return True

    if session.tiebreaker_for is not None and user_id not in session.tiebreaker_for:
        return True

    if time.time() > session.expires_at:
        await _on_round_timeout(chat_id, round_token=session.round_token)
        return True

    guess = normalize_guess(text)
    if not guess:
        return True

    session.guess_attempts.add(user_id)
    session.round_attempts.add(user_id)
    session.round_labels.setdefault(user_id, label)

    if guess != _normalize_answer(session.answer):
        record_guess_attempt(chat_id, user_id, label)
        return True

    session.round_scores[user_id] = session.round_scores.get(user_id, 0) + 1
    session.round_labels[user_id] = label
    record_correct_guess(chat_id, user_id, label)

    header = (
        f"✅ {label} угадал!\n"
        f"Раунд {session.current_round}/{session.total_rounds} — было: {session.answer}"
    )
    await _advance_or_finish(chat_id, header)
    return True


def game_help_text() -> str:
    return (
        "🎮 Угадай пародию\n\n"
        "/guess — старт (3 раунда по 60 сек)\n"
        "/guess 5 — сессия из 5 раундов\n"
        "/guess stop — остановить игру\n"
        "/guess score — лидерборд\n\n"
        "Party:\n"
        "/guessparty — лобби с подтверждением\n"
        "/guessparty join|leave|stop\n\n"
        "/gamestats — статистика игр в чате\n\n"
        "Бот показывает пародию — угадай исходное слово.\n"
        "Победитель сессии получает +1 в лидерборд."
    )
