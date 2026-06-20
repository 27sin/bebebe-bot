#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aiogram import Bot

from bot.config import ADMIN_USER_IDS, BOT_TOKEN
from bot.services.analytics import build_admin_stats_message, init_db, run_pending_rollups


async def main() -> None:
    if not ADMIN_USER_IDS:
        raise SystemExit("ADMIN_USER_IDS is empty in .env")

    init_db()
    run_pending_rollups()

    text = build_admin_stats_message(period="week", compare_previous=True)
    bot = Bot(token=BOT_TOKEN)
    try:
        for admin_id in ADMIN_USER_IDS:
            await bot.send_message(admin_id, text)
            print(f"Sent weekly analytics to {admin_id}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
