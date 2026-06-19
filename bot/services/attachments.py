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
    if message.sticker:
        return ATTACHMENT_PARODIES["sticker"]
    if message.animation:
        return ATTACHMENT_PARODIES["animation"]
    if message.photo:
        return ATTACHMENT_PARODIES["photo"]
    if message.video:
        return ATTACHMENT_PARODIES["video"]
    if message.voice:
        return ATTACHMENT_PARODIES["voice"]
    if message.location:
        return ATTACHMENT_PARODIES["location"]
    if message.document:
        return ATTACHMENT_PARODIES["document"]
    return None
