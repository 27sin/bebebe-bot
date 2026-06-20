from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.handlers.command_menus import send_command_menu
from bot.handlers.user_target import user_label
from bot.services.guess_party import (
    MAX_PARTY_PLAYERS,
    MIN_PARTY_PLAYERS,
    begin_party_setup,
    create_party_lobby,
    handle_pending_count_message,
    is_party_lobby_active,
    is_party_pending_setup,
    join_party_lobby,
    leave_party_lobby,
    stop_party,
)
from bot.services.guess_game import DEFAULT_ROUNDS, is_party_game_active, try_guess

logger = logging.getLogger(__name__)

router = Router(name="guess_party")

GUESSPARTY_PATTERN = re.compile(r"^/guessparty(?:@\w+)?(?:\s*(.*))?$", re.IGNORECASE)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.regexp(GUESSPARTY_PATTERN),
)
async def handle_guessparty_command(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = GUESSPARTY_PATTERN.match(message.text.strip())
    if not match:
        return

    raw_arg = (match.group(1) or "").strip()
    arg = raw_arg.lower()
    chat_id = message.chat.id
    uid = message.from_user.id
    label = user_label(message.from_user)

    if arg in {"help", "?"}:
        await send_command_menu(message, "guessparty")
        return

    if arg == "stop":
        reply = await stop_party(chat_id)
        if reply:
            await message.answer(reply)
        return

    if arg == "join":
        await message.answer(await join_party_lobby(chat_id, uid, label))
        return

    if arg == "leave":
        await message.answer(await leave_party_lobby(chat_id, uid))
        return

    parts = raw_arg.split()
    if parts and parts[0].isdigit():
        required = int(parts[0])
        if not MIN_PARTY_PLAYERS <= required <= MAX_PARTY_PLAYERS:
            await message.answer(
                f"Число участников: от {MIN_PARTY_PLAYERS} до {MAX_PARTY_PLAYERS}."
            )
            return
        rounds = DEFAULT_ROUNDS
        if len(parts) >= 2 and parts[1].isdigit():
            rounds = int(parts[1])
        text = await create_party_lobby(chat_id, uid, label, required, rounds)
        await message.answer(text)
        return

    if arg == "start":
        text = await begin_party_setup(chat_id, uid, label)
        await message.answer(text)
        return

    if arg in {"", "help", "?"}:
        await send_command_menu(message, "guessparty")
        return


async def handle_party_setup_message(message: Message) -> bool:
    if not message.text or not message.from_user:
        return False

    if not is_party_pending_setup(message.chat.id):
        return False

    reply = await handle_pending_count_message(
        message.chat.id,
        message.from_user.id,
        message.text.strip(),
        user_label(message.from_user),
    )
    if reply is None:
        return False

    await message.answer(reply)
    return True


async def handle_party_flow(message: Message) -> bool:
    chat_id = message.chat.id

    if is_party_pending_setup(chat_id):
        return await handle_party_setup_message(message)

    if is_party_lobby_active(chat_id):
        return True

    if not is_party_game_active(chat_id):
        return False

    if message.text and message.from_user and not message.text.startswith("/"):
        await try_guess(
            chat_id,
            message.from_user.id,
            user_label(message.from_user),
            message.text,
        )
    return True
