from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.services.analytics import track


class AnalyticsCommandMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text and event.text.startswith("/"):
            command_token = event.text.strip().split()[0]
            command = command_token.split("@", 1)[0][1:].lower()
            if command:
                track(
                    "command",
                    chat_id=event.chat.id,
                    user_id=event.from_user.id if event.from_user else None,
                    command=command,
                    has_args=len(event.text.split()) > 1,
                )
        return await handler(event, data)
