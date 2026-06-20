from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from bot.services.guess_game import (
    DEFAULT_ROUNDS,
    MAX_ROUNDS,
    _send,
    is_game_active,
    start_session,
    stop_session,
)
from bot.services.titles import format_titled_label

ACCEPT_SECONDS = 30

_duel_lobbies: dict[int, DuelLobby] = {}
_accept_tasks: dict[int, asyncio.Task[None]] = {}


@dataclass
class DuelLobby:
    chat_id: int
    host_id: int
    host_label: str
    opponent_id: int | None
    opponent_username: str | None
    opponent_label: str
    rounds: int
    expires_at: float


def is_duel_lobby_active(chat_id: int) -> bool:
    return chat_id in _duel_lobbies


def is_duel_mode_blocking(chat_id: int) -> bool:
    from bot.services.guess_game import is_duel_game_active

    return is_duel_lobby_active(chat_id) or is_duel_game_active(chat_id)


def _cancel_accept_timer(chat_id: int) -> None:
    task = _accept_tasks.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


def _clear_duel(chat_id: int) -> None:
    _duel_lobbies.pop(chat_id, None)
    _cancel_accept_timer(chat_id)


def _is_opponent(lobby: DuelLobby, user_id: int, username: str | None) -> bool:
    if lobby.opponent_id is not None:
        return user_id == lobby.opponent_id
    if lobby.opponent_username and username:
        return username.lower() == lobby.opponent_username.lower()
    return False


async def _launch_duel(chat_id: int) -> None:
    lobby = _duel_lobbies.get(chat_id)
    if lobby is None or lobby.opponent_id is None:
        return

    host_id = lobby.host_id
    opponent_id = lobby.opponent_id
    rounds = lobby.rounds
    host_display = format_titled_label(
        chat_id, host_id, lobby.host_label, context="game"
    )
    opponent_display = format_titled_label(
        chat_id, opponent_id, lobby.opponent_label, context="game"
    )
    _clear_duel(chat_id)

    text = await start_session(
        chat_id,
        rounds=rounds,
        starter_id=host_id,
        starter_label=host_display,
        participants=frozenset({host_id, opponent_id}),
        game_mode="duel",
    )
    await _send(
        chat_id,
        f"⚔️ Дуэль: {host_display} vs {opponent_display}\n\n{text}",
    )


async def _accept_timeout(chat_id: int, lobby_token: float) -> None:
    try:
        await asyncio.sleep(ACCEPT_SECONDS)
    except asyncio.CancelledError:
        return

    lobby = _duel_lobbies.get(chat_id)
    if lobby is None or lobby.expires_at != lobby_token:
        return

    opponent = lobby.opponent_label
    _clear_duel(chat_id)
    await _send(chat_id, f"⚔️ {opponent} — второй участник зассал")


def _schedule_accept_timeout(chat_id: int, lobby: DuelLobby) -> None:
    _cancel_accept_timer(chat_id)
    _accept_tasks[chat_id] = asyncio.create_task(
        _accept_timeout(chat_id, lobby.expires_at),
        name=f"duel-accept-{chat_id}",
    )


async def create_duel(
    chat_id: int,
    host_id: int,
    host_label: str,
    opponent_id: int | None,
    opponent_username: str | None,
    opponent_label: str,
    rounds: int = DEFAULT_ROUNDS,
) -> str:
    if is_game_active(chat_id):
        return "Сейчас уже идёт игра. /guessduel stop"
    if is_duel_lobby_active(chat_id):
        return "Дуэль уже открыта. Жди ответа или /guessduel stop"

    from bot.services.guess_party import is_party_lobby_active, is_party_pending_setup

    if is_party_lobby_active(chat_id) or is_party_pending_setup(chat_id):
        return "Сейчас открыто party-лобби. /guessparty stop"

    if opponent_id is not None and opponent_id == host_id:
        return "С самим собой не подерёшься."

    rounds = max(1, min(MAX_ROUNDS, rounds))
    lobby = DuelLobby(
        chat_id=chat_id,
        host_id=host_id,
        host_label=host_label,
        opponent_id=opponent_id,
        opponent_username=opponent_username,
        opponent_label=opponent_label,
        rounds=rounds,
        expires_at=time.time() + ACCEPT_SECONDS,
    )
    _duel_lobbies[chat_id] = lobby
    _schedule_accept_timeout(chat_id, lobby)

    host_display = format_titled_label(chat_id, host_id, host_label, context="game")
    return (
        f"⚔️ {host_display} вызывает {opponent_label} на дуэль!\n"
        f"Раундов: {rounds}\n"
        f"Подтверди: /guessduel accept ({ACCEPT_SECONDS} сек)"
    )


async def accept_duel(chat_id: int, user_id: int, label: str, username: str | None) -> str:
    lobby = _duel_lobbies.get(chat_id)
    if lobby is None:
        return "Вызова на дуэль нет."

    if user_id == lobby.host_id:
        return "Это твой вызов — жди соперника."

    if not _is_opponent(lobby, user_id, username):
        return f"Этот вызов не для тебя. Ждут: {lobby.opponent_label}"

    lobby.opponent_id = user_id
    lobby.opponent_label = label
    _cancel_accept_timer(chat_id)
    await _launch_duel(chat_id)
    return f"⚔️ Принято, {format_titled_label(chat_id, user_id, label, context='game')}! Поехали."


async def stop_duel(chat_id: int) -> str | None:
    if is_duel_lobby_active(chat_id):
        _clear_duel(chat_id)
        await _send(chat_id, "🛑 Дуэль отменена.")
        return None

    if is_game_active(chat_id):
        from bot.services.guess_game import is_duel_game_active

        if is_duel_game_active(chat_id):
            return await stop_session(chat_id)

    return "Нет активной дуэли или игры."


def duel_help_text() -> str:
    return (
        "⚔️ Дуэль «Угадай пародию»\n\n"
        "/guessduel @ник — вызвать на дуэль (3 раунда)\n"
        "/guessduel @ник 5 — дуэль из 5 раундов\n"
        "/guessduel accept — принять вызов (30 сек)\n"
        "/guessduel stop — отменить дуэль или игру\n\n"
        "Победа засчитывается в титулы и /guess score."
    )
