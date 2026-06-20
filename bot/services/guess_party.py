from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field

from bot.services.guess_game import (
    DEFAULT_ROUNDS,
    MAX_ROUNDS,
    _send,
    is_game_active,
    is_party_game_active,
    start_session,
    stop_session,
)

MIN_PARTY_PLAYERS = 2
MAX_PARTY_PLAYERS = 20
COUNTDOWN_SECONDS = 5

_pending_count_host: dict[int, int] = {}
_lobbies: dict[int, PartyLobby] = {}
_countdown_tasks: dict[int, asyncio.Task[None]] = {}


@dataclass
class PartyLobby:
    chat_id: int
    host_id: int
    host_label: str
    required: int
    rounds: int
    participants: dict[int, str] = field(default_factory=dict)


def is_party_lobby_active(chat_id: int) -> bool:
    return chat_id in _lobbies


def is_party_pending_setup(chat_id: int) -> bool:
    return chat_id in _pending_count_host


def is_party_mode_blocking(chat_id: int) -> bool:
    return is_party_lobby_active(chat_id) or is_party_game_active(chat_id)


def _lobby_status(lobby: PartyLobby) -> str:
    joined = len(lobby.participants)
    lines = [f"Участники: {joined}/{lobby.required}"]
    if lobby.participants:
        names = ", ".join(lobby.participants.values())
        lines.append(names)
    lines.append("Подтвердить: /guessparty join")
    return "\n".join(lines)


def _cancel_countdown(chat_id: int) -> None:
    task = _countdown_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _clear_lobby(chat_id: int) -> None:
    _lobbies.pop(chat_id, None)
    _cancel_countdown(chat_id)


async def _launch_party_game(chat_id: int) -> None:
    lobby = _lobbies.get(chat_id)
    if lobby is None:
        return

    participant_ids = frozenset(lobby.participants.keys())
    host_id = lobby.host_id
    host_label = lobby.host_label
    rounds = lobby.rounds
    _clear_lobby(chat_id)

    text = await start_session(
        chat_id,
        rounds=rounds,
        starter_id=host_id,
        starter_label=host_label,
        participants=participant_ids,
    )
    await _send(chat_id, text)


async def _countdown_to_start(chat_id: int, lobby_token: int) -> None:
    try:
        await asyncio.sleep(COUNTDOWN_SECONDS)
    except asyncio.CancelledError:
        return

    lobby = _lobbies.get(chat_id)
    if lobby is None or len(lobby.participants) != lobby_token:
        return

    await _launch_party_game(chat_id)


async def _maybe_start_countdown(chat_id: int) -> None:
    lobby = _lobbies.get(chat_id)
    if lobby is None:
        return
    if len(lobby.participants) < lobby.required:
        return

    _cancel_countdown(chat_id)
    names = ", ".join(lobby.participants.values())
    await _send(
        chat_id,
        f"✅ Набралось {lobby.required} участник(ов)!\n{names}\n\n"
        f"Игра начнётся через {COUNTDOWN_SECONDS} секунд…",
    )
    token = len(lobby.participants)
    _countdown_tasks[chat_id] = asyncio.create_task(_countdown_to_start(chat_id, token))


def _parse_party_size(raw: str) -> int | None:
    match = re.fullmatch(r"\d+", raw.strip())
    if not match:
        return None
    size = int(match.group(0))
    if not MIN_PARTY_PLAYERS <= size <= MAX_PARTY_PLAYERS:
        return None
    return size


async def begin_party_setup(chat_id: int, host_id: int, host_label: str) -> str:
    if is_game_active(chat_id):
        return "Сейчас уже идёт игра. Дождись конца или /guessparty stop"
    if is_party_lobby_active(chat_id):
        return "Лобби уже открыто. Жди участников или /guessparty stop"
    if is_party_pending_setup(chat_id):
        return "Уже жду число участников. Организатор — ответь числом или /guessparty stop"

    _pending_count_host[chat_id] = host_id
    return (
        "👥 Party «Угадай пародию»\n\n"
        f"Сколько человек должны подтвердить участие? ({MIN_PARTY_PLAYERS}–{MAX_PARTY_PLAYERS})\n"
        "Ответь числом в чат."
    )


async def create_party_lobby(
    chat_id: int,
    host_id: int,
    host_label: str,
    required: int,
    rounds: int = DEFAULT_ROUNDS,
) -> str:
    if is_game_active(chat_id):
        return "Сейчас уже идёт игра. /guessparty stop"
    if is_party_lobby_active(chat_id):
        return "Лобби уже открыто."

    _pending_count_host.pop(chat_id, None)
    rounds = max(1, min(MAX_ROUNDS, rounds))

    lobby = PartyLobby(
        chat_id=chat_id,
        host_id=host_id,
        host_label=host_label,
        required=required,
        rounds=rounds,
    )
    _lobbies[chat_id] = lobby

    return (
        f"👥 Лобби открыто. Нужно {required} подтверждений.\n"
        f"Организатор: {host_label}\n"
        f"Раундов в сессии: {rounds}\n\n"
        f"{_lobby_status(lobby)}"
    )


async def handle_pending_count_message(
    chat_id: int,
    user_id: int,
    text: str,
    user_label: str,
) -> str | None:
    host_id = _pending_count_host.get(chat_id)
    if host_id is None or host_id != user_id:
        return None

    size = _parse_party_size(text)
    if size is None:
        return (
            f"Нужно число от {MIN_PARTY_PLAYERS} до {MAX_PARTY_PLAYERS}. "
            "Например: 4"
        )

    _pending_count_host.pop(chat_id, None)
    return await create_party_lobby(chat_id, host_id, user_label, size)


async def join_party_lobby(chat_id: int, user_id: int, label: str) -> str:
    lobby = _lobbies.get(chat_id)
    if lobby is None:
        return "Лобби не открыто. Старт: /guessparty"

    if user_id in lobby.participants:
        return f"Ты уже в лобби ({len(lobby.participants)}/{lobby.required})."

    lobby.participants[user_id] = label
    await _maybe_start_countdown(chat_id)

    if len(lobby.participants) >= lobby.required:
        return f"Ты в игре, {label}! Старт через {COUNTDOWN_SECONDS} сек…"

    return f"Ты в лобби, {label}!\n\n{_lobby_status(lobby)}"


async def leave_party_lobby(chat_id: int, user_id: int) -> str:
    lobby = _lobbies.get(chat_id)
    if lobby is None:
        return "Лобби не открыто."

    if user_id not in lobby.participants:
        return "Ты не в лобби."

    lobby.participants.pop(user_id, None)
    _cancel_countdown(chat_id)

    if not lobby.participants and user_id == lobby.host_id:
        _clear_lobby(chat_id)
        _pending_count_host.pop(chat_id, None)
        return "Лобби закрыто."

    return f"Ты вышел из лобби.\n\n{_lobby_status(lobby)}"


async def stop_party(chat_id: int) -> str | None:
    _pending_count_host.pop(chat_id, None)

    if is_party_lobby_active(chat_id):
        _clear_lobby(chat_id)
        await _send(chat_id, "🛑 Party-лобби закрыто.")
        return None

    if is_game_active(chat_id):
        return await stop_session(chat_id)

    return "Нет активного party-лобби или игры."


def party_help_text() -> str:
    return (
        "👥 Party «Угадай пародию»\n\n"
        "/guessparty — создать лобби (бот спросит число участников)\n"
        "/guessparty 5 — лобби на 5 человек сразу\n"
        "/guessparty 5 3 — 5 участников, 3 раунда\n"
        "/guessparty join — подтвердить участие\n"
        "/guessparty leave — выйти из лобби\n"
        "/guessparty stop — отменить лобби или игру\n\n"
        "Когда наберётся нужное число — старт через 5 сек.\n"
        "Ответы засчитываются только участникам лобби."
    )
