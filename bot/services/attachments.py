from __future__ import annotations

from aiogram.types import Message

ATTACHMENT_PARODIES: dict[str, str] = {
    "photo": "картинка — хуинка",
    "video": "видео — хуидео",
    "animation": "гифка — хуифка",
    "sticker": "стикер — хуикер",
    "voice": "голосовушка — хуюшка",
    "document": "вложение — хуение",
    "location": "гео — хуео",
}


def parody_for_attachment(message: Message) -> str | None:
    attachment_type = detect_attachment_type(message)
    if attachment_type is None:
        return None
    return ATTACHMENT_PARODIES.get(attachment_type)


def detect_attachment_type(message: Message) -> str | None:
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
