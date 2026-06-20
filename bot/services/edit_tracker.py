from __future__ import annotations

from collections import OrderedDict

MAX_TRACKED_MESSAGES = 5000

_tracked_messages: OrderedDict[tuple[int, int], int] = OrderedDict()


def register_bot_reply(chat_id: int, message_id: int, user_id: int) -> None:
    key = (chat_id, message_id)
    _tracked_messages[key] = user_id
    _tracked_messages.move_to_end(key)
    while len(_tracked_messages) > MAX_TRACKED_MESSAGES:
        _tracked_messages.popitem(last=False)


def was_bot_reply_target(chat_id: int, message_id: int) -> bool:
    return (chat_id, message_id) in _tracked_messages
