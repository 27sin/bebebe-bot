from __future__ import annotations

import random

from aiogram.types import Message

from bot.services.settings import get_effective_reply_probability

_bot_id: int | None = None
_bot_username: str | None = None


def set_bot_id(bot_id: int, username: str | None = None) -> None:
    global _bot_id, _bot_username
    _bot_id = bot_id
    _bot_username = username.lower().lstrip("@") if username else None


def _is_bot_mentioned(message: Message) -> bool:
    if not _bot_username or not message.text or not message.entities:
        return False

    mention = f"@{_bot_username}"
    for entity in message.entities:
        if entity.type != "mention":
            continue
        fragment = message.text[entity.offset : entity.offset + entity.length]
        if fragment.lower() == mention:
            return True
    return False


def should_respond(message: Message) -> bool:
    if _bot_id is None or not message.from_user:
        return False

    if _is_bot_mentioned(message):
        return True

    reply = message.reply_to_message
    if reply and reply.from_user and reply.from_user.id == _bot_id:
        return True

    user = message.from_user
    probability = get_effective_reply_probability(
        message.chat.id,
        user.id,
        user.username,
    )
    return random.random() < probability
