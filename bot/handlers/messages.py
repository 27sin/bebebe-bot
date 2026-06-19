from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.handlers.user_target import user_label
from bot.services.attachments import parody_for_attachment
from bot.services.rate_limit import can_reply_now, mark_replied
from bot.services.reply_context import apply_reply_context
from bot.services.reply_engine import build_text_reply
from bot.services.settings import get_reply_cooldown
from bot.services.stats import record_reply
from bot.services.streak import record_streak
from bot.services.trigger import should_respond

logger = logging.getLogger(__name__)

router = Router(name="messages")


async def _try_parody_reply(
    message: Message,
    parody: str,
    source: str,
    trigger_words: tuple[str, ...] | None = None,
) -> None:
    if not message.from_user:
        return

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
        record_streak(message.chat.id, message.from_user.id)
        record_reply(
            message.chat.id,
            message.from_user.id,
            user_label(message.from_user),
            source,
            trigger_words,
        )
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

    built = await build_text_reply(message)
    if not built:
        logger.info("No parody for chat=%s message=%r", message.chat.id, message.text[:50])
        return

    await _try_parody_reply(message, built.text, built.source, built.trigger_words)


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

    parody = apply_reply_context(message, parody) or parody
    await _try_parody_reply(message, parody, "attachment")
