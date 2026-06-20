from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.types import Message

from bot.config import is_admin_user
from bot.services.analytics import PERIOD_SECONDS, build_admin_stats_message

router = Router(name="admin")

ADMINSTATS_PATTERN = re.compile(r"^/adminstats(?:@\w+)?(?:\s+(\S+))?$", re.IGNORECASE)


@router.message(F.text.regexp(ADMINSTATS_PATTERN))
async def handle_adminstats(message: Message) -> None:
    if not message.from_user or not message.text:
        return
    if not is_admin_user(message.from_user.id):
        return

    match = ADMINSTATS_PATTERN.match(message.text.strip())
    if not match:
        return

    period = (match.group(1) or "week").strip().lower()
    if period not in PERIOD_SECONDS:
        await message.answer(
            "Неизвестный период.\n"
            "Примеры: /adminstats week, /adminstats day, /adminstats month, /adminstats all"
        )
        return

    await message.answer(build_admin_stats_message(period=period, compare_previous=period != "all"))
