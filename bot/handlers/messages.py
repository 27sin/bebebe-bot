from __future__ import annotations

import logging
import random

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.handlers.user_target import user_label
from bot.handlers.guess_commands import handle_guess_attempt
from bot.handlers.guess_duel_commands import handle_duel_flow
from bot.handlers.guess_party_commands import handle_party_flow
from bot.services.analytics import track
from bot.services.attachments import detect_attachment_type, parody_for_attachment
from bot.services.easter_eggs import (
    on_attachment_reply,
    on_edit_reaction,
    on_rare_reply,
    on_text_reply,
)
from bot.services.guess_party import is_party_or_duel_blocking
from bot.services.guess_game import is_game_active
from bot.services.edit_tracker import register_bot_reply, was_bot_reply_target
from bot.services.rate_limit import can_reply_now, mark_replied
from bot.services.reply_context import apply_reply_context
from bot.services.reply_engine import build_text_reply
from bot.services.settings import get_reply_cooldown, is_user_ignored
from bot.services.stats import record_reply
from bot.services.streak import record_streak
from bot.services.trigger import should_respond

logger = logging.getLogger(__name__)

router = Router(name="messages")

EDIT_REACTIONS: tuple[str, ...] = (
    "передумал?",
    "а теперь?",
    "рерайт?",
    "версия 2.0",
)


async def _try_parody_reply(
    message: Message,
    parody: str,
    source: str,
    trigger_words: tuple[str, ...] | None = None,
    *,
    track_for_edits: bool = True,
    count_streak: bool = True,
    attachment_type: str | None = None,
) -> None:
    if not message.from_user:
        return

    if not can_reply_now(message.chat.id):
        track(
            "reply_skipped",
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            reason="rate_limit",
        )
        logger.debug(
            "Rate limit chat=%s cooldown=%s",
            message.chat.id,
            get_reply_cooldown(message.chat.id),
        )
        return

    try:
        await message.reply(parody)
        mark_replied(message.chat.id)
        if count_streak:
            record_streak(message.chat.id, message.from_user.id)
        if track_for_edits:
            register_bot_reply(message.chat.id, message.message_id, message.from_user.id)
        record_reply(
            message.chat.id,
            message.from_user.id,
            user_label(message.from_user),
            source,
            trigger_words,
        )
        text = message.text or message.caption or ""
        if source == "rare":
            on_rare_reply(message.chat.id, message.from_user.id, parody)
        elif source == "edit":
            on_edit_reaction(message.chat.id, message.from_user.id)
        elif attachment_type:
            on_attachment_reply(message.chat.id, message.from_user.id, attachment_type)
        elif text:
            on_text_reply(message.chat.id, message.from_user.id, text, parody, source)
        track(
            "reply_sent",
            chat_id=message.chat.id,
            user_id=message.from_user.id,
            source=source,
            attachment_type=attachment_type,
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

    if await handle_duel_flow(message):
        return

    if await handle_party_flow(message):
        return

    if await handle_guess_attempt(message):
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

    if is_party_or_duel_blocking(message.chat.id):
        return

    if is_game_active(message.chat.id):
        return

    if not should_respond(message):
        logger.debug("Skip attachment chat=%s", message.chat.id)
        return

    parody = parody_for_attachment(message)
    if not parody:
        return

    parody = apply_reply_context(message, parody) or parody
    attachment_type = detect_attachment_type(message)
    await _try_parody_reply(
        message,
        parody,
        "attachment",
        attachment_type=attachment_type,
    )


@router.edited_message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_edited_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_bot:
        return

    if not was_bot_reply_target(message.chat.id, message.message_id):
        return

    if is_user_ignored(message.chat.id, message.from_user.id, message.from_user.username):
        return

    text = message.text or message.caption
    if text and text.startswith("/"):
        return

    prefix = random.choice(EDIT_REACTIONS)
    built = await build_text_reply(message, skip_streak=True) if text else None

    if built:
        reply = f"{prefix} {built.text}"
        trigger_words = built.trigger_words
    else:
        reply = prefix
        trigger_words = ()

    await _try_parody_reply(
        message,
        reply,
        "edit",
        trigger_words,
        track_for_edits=False,
        count_streak=False,
    )
