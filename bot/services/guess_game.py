from __future__ import annotations

import asyncio
import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiogram import Bot

from bot.config import PROJECT_ROOT
from bot.services.rules import WORD_PATTERN, parody_word

GAME_WORDS_PATH = PROJECT_ROOT / "rules" / "game_words.json"
LEADERBOARD_PATH = PROJECT_ROOT / "data" / "guess_leaderboard.json"

DEFAULT_ROUNDS = 3
MAX_ROUNDS = 10
MIN_ROUNDS = 1
ROUND_SECONDS = 60
LEADERBOARD_LIMIT = 10

_bot: Bot | None = None
_sessions: dict[int, GameSession] = {}
_timeout_tasks: dict[int, asyncio.Task[None]] = {}


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
    started_by: int = 0
    starter_label: str = ""


def bind_bot(bot: Bot) -> None:
    global _bot
    _bot = bot


def is_game_active(chat_id: int) -> bool:
    return chat_id in _sessions


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


def _schedule_timeout(chat_id: int, round_token: int) -> None:
    _cancel_timeout(chat_id)
    _timeout_tasks[chat_id] = asyncio.create_task(_round_timeout(chat_id, round_token))


async def _send(chat_id: int, text: str) -> None:
    if _bot is None:
        return
    await _bot.send_message(chat_id, text)


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
    session.round_token += 1
    session.expires_at = time.time() + ROUND_SECONDS
    _schedule_timeout(session.chat_id, session.round_token)

    return (
        f"Раунд {session.current_round}/{session.total_rounds}\n"
        f"Угадай слово: {parody}\n"
        f"⏱ {ROUND_SECONDS} сек"
    )


async def _finish_session(chat_id: int, header: str) -> None:
    session = _sessions.pop(chat_id, None)
    _cancel_timeout(chat_id)
    if session is None:
        return

    winners = _session_winners(session)
    lines = [header, "", "Итог сессии:", _session_scoreboard(session)]

    if winners:
        names = ", ".join(label for _, label in winners)
        lines.append("")
        lines.append(f"🏆 Победитель сессии: {names}")
        record_leaderboard_wins(chat_id, winners)
        lines.append("+1 в лидерборд")
    else:
        lines.append("")
        lines.append("Победителя нет — никто не угадал ни одного раунда.")

    await _send(chat_id, "\n".join(lines))


async def _round_timeout(chat_id: int, round_token: int) -> None:
    try:
        await asyncio.sleep(ROUND_SECONDS)
    except asyncio.CancelledError:
        return

    session = _sessions.get(chat_id)
    if session is None or session.round_token != round_token:
        return

    await _on_round_timeout(chat_id)


async def _on_round_timeout(chat_id: int) -> None:
    session = _sessions.get(chat_id)
    if session is None:
        return

    answer = session.answer
    header = f"⏱ Время вышло в раунде {session.current_round}/{session.total_rounds}.\nБыло: {answer}"
    await _advance_or_finish(chat_id, header)


async def _advance_or_finish(chat_id: int, header: str) -> None:
    session = _sessions.get(chat_id)
    if session is None:
        return

    _cancel_timeout(chat_id)

    if session.current_round >= session.total_rounds:
        await _finish_session(chat_id, header)
        return

    session.current_round += 1
    round_text = await _start_round(session)
    if round_text is None:
        await _finish_session(chat_id, f"{header}\n\nНе удалось начать следующий раунд.")
        return

    await _send(chat_id, f"{header}\n\n{round_text}")


async def start_session(
    chat_id: int,
    rounds: int,
    starter_id: int,
    starter_label: str,
) -> str:
    if is_game_active(chat_id):
        return "Игра уже идёт. Дождись конца или /guess stop"

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
    )
    _sessions[chat_id] = session

    round_text = await _start_round(session)
    if round_text is None:
        _sessions.pop(chat_id, None)
        _cancel_timeout(chat_id)
        return "Не получилось подобрать загадку. Попробуй ещё раз."

    return (
        f"🎮 Угадай пародию!\n"
        f"{rounds} раунд(а) по {ROUND_SECONDS} сек.\n"
        f"Ответ — одним словом. Стартовал {starter_label}.\n\n"
        f"{round_text}"
    )


async def stop_session(chat_id: int) -> str | None:
    if not is_game_active(chat_id):
        return "Сейчас нет активной игры."
    await _finish_session(chat_id, "🛑 Игра остановлена.")
    return None


async def try_guess(chat_id: int, user_id: int, label: str, text: str) -> bool:
    session = _sessions.get(chat_id)
    if session is None:
        return False

    if time.time() > session.expires_at:
        await _on_round_timeout(chat_id)
        return True

    guess = normalize_guess(text)
    if not guess:
        return True

    if guess != _normalize_answer(session.answer):
        return True

    session.round_scores[user_id] = session.round_scores.get(user_id, 0) + 1
    session.round_labels[user_id] = label

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
        "Бот показывает пародию — угадай исходное слово.\n"
        "Победитель сессии получает +1 в лидерборд."
    )
