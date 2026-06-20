from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message

from bot.services.llm import parody_with_llm
from bot.services.rare_replies import maybe_rare_reply
from bot.services.reply_context import apply_reply_context
from bot.services.rules import extract_words, is_special_reply, parody_with_rules
from bot.services.streak import peek_streak_reply


@dataclass(frozen=True)
class BuiltReply:
    text: str
    source: str
    trigger_words: tuple[str, ...]


def _trigger_words(text: str) -> tuple[str, ...]:
    words = extract_words(text)
    if len(words) == 2:
        return tuple(words)
    if words:
        return (words[-1],)
    return ()


async def build_text_reply(message: Message) -> BuiltReply | None:
    if not message.text or not message.from_user:
        return None

    text = message.text
    user_id = message.from_user.id

    streak_reply = peek_streak_reply(message.chat.id, user_id)
    if streak_reply:
        reply = apply_reply_context(message, streak_reply)
        if reply:
            return BuiltReply(reply, "streak", _trigger_words(text))

    base = parody_with_rules(text, message.chat.id)
    source = "text"
    if not base:
        base = await parody_with_llm(text)
        if base:
            source = "text"

    if base and not is_special_reply(text, message.chat.id):
        rare = maybe_rare_reply()
        if rare:
            base = rare
            source = "rare"

    reply = apply_reply_context(message, base)
    if not reply:
        return None

    if base is None and message.reply_to_message is not None:
        source = "reply_context"

    return BuiltReply(reply, source, _trigger_words(text))
