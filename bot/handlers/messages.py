from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.services.attachments import parody_for_attachment
from bot.services.llm import parody_with_llm
from bot.services.rate_limit import can_reply_now, mark_replied
from bot.services.rules import parody_with_rules
from bot.services.settings import get_reply_cooldown
from bot.services.trigger import should_respond

logger = logging.getLogger(__name__)

router = Router(name="messages")


async def _build_text_parody(text: str) -> str | None:
    parody = parody_with_rules(text)
    if parody:
        return parody
    return await parody_with_llm(text)


async def _try_parody_reply(message: Message, parody: str, source: str) -> None:
    if not can_reply_now(message.chat.id):
        logger.debug(
            "Rate limit chat=%s cooldown=%s",
            message.chat.id,
            get_reply_cooldown(message.chat.id),
        )
        return

    try:
        await message.reply(parody)
        mark_replied(message.chat.id)
        logger.info("Replied in chat=%s (%s): %r", message.chat.id, source, parody)
    except Exception:
        logger.exception("Failed to send parody reply in chat=%s", message.chat.id)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text,
    ~F.text.startswith("/"),
)
async def handle_group_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot or not message.text:
        return

    if not should_respond(message):
        logger.debug("Skip chat=%s message=%r", message.chat.id, message.text[:50])
        return

    parody = await _build_text_parody(message.text)
    if not parody:
        logger.info("No parody for chat=%s message=%r", message.chat.id, message.text[:50])
        return

    await _try_parody_reply(message, parody, "text")


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.photo | F.video | F.animation | F.sticker | F.voice | F.document | F.location,
)
async def handle_group_attachment(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return

    if not should_respond(message):
        logger.debug("Skip attachment chat=%s", message.chat.id)
        return

    parody = parody_for_attachment(message)
    if not parody:
        return

    await _try_parody_reply(message, parody, "attachment")
