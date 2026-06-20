from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import Message, User


@dataclass(frozen=True)
class TargetUser:
    user_id: int | None
    username: str | None
    label: str


def _user_label(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip()
    return name or str(user.id)


def user_label(user: User) -> str:
    return _user_label(user)


def titled_user_label(user: User, chat_id: int, *, context: str = "both") -> str:
    from bot.services.titles import format_titled_label

    return format_titled_label(
        chat_id,
        user.id,
        _user_label(user),
        context=context,  # type: ignore[arg-type]
    )


def resolve_target_user(message: Message, mention_text: str | None = None) -> TargetUser | None:
    if mention_text and message.entities and message.text:
        for entity in message.entities:
            fragment = message.text[entity.offset : entity.offset + entity.length]
            if fragment.lower() != mention_text.lower():
                continue
            if entity.type == "text_mention" and entity.user:
                return TargetUser(entity.user.id, entity.user.username, _user_label(entity.user))
            if entity.type == "mention":
                username = fragment.lstrip("@")
                return TargetUser(None, username, fragment)

    reply = message.reply_to_message
    if reply and reply.from_user and not reply.from_user.is_bot:
        user = reply.from_user
        return TargetUser(user.id, user.username, _user_label(user))

    return None
