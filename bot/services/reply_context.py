from __future__ import annotations

from aiogram.types import Message

REPLY_CONTEXT_BY_ATTACHMENT: dict[str, str] = {
    "photo": "комментируешь хуинку?",
    "video": "видос комментируешь?",
    "animation": "гифку комментируешь?",
    "sticker": "стикер комментируешь?",
    "voice": "хуюшку слушаешь?",
    "document": "файлик комментируешь?",
    "location": "гео комментируешь?",
}


def attachment_type(message: Message) -> str | None:
    if message.sticker:
        return "sticker"
    if message.animation:
        return "animation"
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.voice:
        return "voice"
    if message.location:
        return "location"
    if message.document:
        return "document"
    return None


def apply_reply_context(message: Message, parody: str | None) -> str | None:
    parent = message.reply_to_message
    if parent is None:
        return parody

    atype = attachment_type(parent)
    if atype is None:
        return parody

    context = REPLY_CONTEXT_BY_ATTACHMENT.get(atype)
    if context is None:
        return parody

    if parody:
        return f"{context} {parody}"
    return context
