from __future__ import annotations

import time

from bot.services.settings import get_reply_cooldown

_last_reply_at: dict[int, float] = {}


def can_reply_now(chat_id: int) -> bool:
    cooldown = get_reply_cooldown(chat_id)
    if cooldown <= 0:
        return True

    last_reply = _last_reply_at.get(chat_id, 0.0)
    return time.monotonic() - last_reply >= cooldown


def mark_replied(chat_id: int) -> None:
    _last_reply_at[chat_id] = time.monotonic()
