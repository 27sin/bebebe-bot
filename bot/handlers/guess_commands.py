from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.handlers.command_menus import send_command_menu
from bot.handlers.user_target import user_label
from bot.services.guess_duel import is_duel_lobby_active
from bot.services.guess_party import is_party_lobby_active, is_party_pending_setup
from bot.services.guess_game import (
    DEFAULT_ROUNDS,
    build_leaderboard_message,
    is_game_active,
    is_restricted_game_active,
    start_session,
    stop_session,
    try_guess,
)

logger = logging.getLogger(__name__)

router = Router(name="guess")

GUESS_PATTERN = re.compile(r"^/guess(?:@\w+)?(?:\s*(.*))?$", re.IGNORECASE)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.regexp(GUESS_PATTERN),
)
async def handle_guess_command(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = GUESS_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = (match.group(1) or "").strip().lower()
    chat_id = message.chat.id

    if is_party_lobby_active(chat_id) or is_party_pending_setup(chat_id):
        await message.answer("Сейчас открыто party-лобби. /guessparty join или /guessparty stop")
        return

    if is_duel_lobby_active(chat_id):
        await message.answer("Сейчас открыта дуэль. /guessduel accept или /guessduel stop")
        return

    if arg in {"", "help", "?"}:
        await send_command_menu(message, "guess")
        return

    if arg == "start":
        text = await start_session(
            chat_id,
            rounds=DEFAULT_ROUNDS,
            starter_id=message.from_user.id,
            starter_label=user_label(message.from_user),
        )
        await message.answer(text)
        return

    if arg == "stop":
        reply = await stop_session(chat_id)
        if reply:
            await message.answer(reply)
        return

    if arg in {"score", "board", "top"}:
        await message.answer(build_leaderboard_message(chat_id))
        return

    if arg.isdigit():
        rounds = int(arg)
        text = await start_session(
            chat_id,
            rounds=rounds,
            starter_id=message.from_user.id,
            starter_label=user_label(message.from_user),
        )
        await message.answer(text)
        return

    await send_command_menu(message, "guess")


async def handle_guess_attempt(message: Message) -> bool:
    if not message.text or not message.from_user:
        return is_game_active(message.chat.id) and not is_restricted_game_active(message.chat.id)

    if not is_game_active(message.chat.id) or is_restricted_game_active(message.chat.id):
        return False

    await try_guess(
        message.chat.id,
        message.from_user.id,
        user_label(message.from_user),
        message.text,
    )
    return True
