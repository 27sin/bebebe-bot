from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.handlers.command_menus import send_command_menu
from bot.handlers.user_target import resolve_target_user, user_label
from bot.services.guess_duel import (
    accept_duel,
    create_duel,
    is_duel_lobby_active,
    stop_duel,
)
from bot.services.guess_game import DEFAULT_ROUNDS, is_duel_game_active, try_guess

logger = logging.getLogger(__name__)

router = Router(name="guess_duel")

GUESSDUEL_PATTERN = re.compile(r"^/guessduel(?:@\w+)?(?:\s*(.*))?$", re.IGNORECASE)


def _parse_opponent(message: Message, raw_arg: str):
    for part in raw_arg.split():
        if part.startswith("@"):
            return resolve_target_user(message, part)
    return None


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text.regexp(GUESSDUEL_PATTERN),
)
async def handle_guessduel_command(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = GUESSDUEL_PATTERN.match(message.text.strip())
    if not match:
        return

    raw_arg = (match.group(1) or "").strip()
    arg = raw_arg.lower()
    chat_id = message.chat.id
    uid = message.from_user.id
    label = user_label(message.from_user)

    if arg in {"help", "?"}:
        await send_command_menu(message, "guessduel")
        return

    if arg == "stop":
        reply = await stop_duel(chat_id)
        if reply:
            await message.answer(reply)
        return

    if arg == "accept":
        await message.answer(
            await accept_duel(
                chat_id,
                uid,
                label,
                message.from_user.username,
            )
        )
        return

    target = _parse_opponent(message, raw_arg)
    if target is None:
        await send_command_menu(message, "guessduel")
        return

    rounds = DEFAULT_ROUNDS
    for part in raw_arg.split():
        if part.isdigit():
            rounds = int(part)

    text = await create_duel(
        chat_id,
        uid,
        label,
        target.user_id,
        target.username,
        target.label,
        rounds=rounds,
    )
    await message.answer(text)


async def handle_duel_flow(message: Message) -> bool:
    chat_id = message.chat.id

    if is_duel_lobby_active(chat_id):
        return True

    if not is_duel_game_active(chat_id):
        return False

    if message.text and message.from_user and not message.text.startswith("/"):
        await try_guess(
            chat_id,
            message.from_user.id,
            user_label(message.from_user),
            message.text,
        )
    return True
