import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import BOT_TOKEN
from bot.handlers.admin_commands import router as admin_router
from bot.handlers.command_menus import router as command_menus_router
from bot.handlers.commands import router as commands_router
from bot.handlers.guess_commands import handle_guess_attempt, router as guess_router
from bot.handlers.guess_duel_commands import router as guess_duel_router
from bot.handlers.guess_party_commands import router as guess_party_router
from bot.handlers.messages import router as messages_router
from bot.logging_setup import setup_logging
from bot.middleware.analytics import AnalyticsCommandMiddleware
from bot.services.analytics import init_db, run_pending_rollups
from bot.services.bot_commands import sync_bot_commands
from bot.services.guess_game import bind_bot
from bot.services.trigger import set_bot_id

setup_logging()


async def main() -> None:
    init_db()
    run_pending_rollups()

    bot = Bot(token=BOT_TOKEN)
    bind_bot(bot)
    dispatcher = Dispatcher()
    dispatcher.message.middleware(AnalyticsCommandMiddleware())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(commands_router)
    dispatcher.include_router(command_menus_router)
    dispatcher.include_router(guess_router)
    dispatcher.include_router(guess_duel_router)
    dispatcher.include_router(guess_party_router)
    dispatcher.include_router(messages_router)

    me = await bot.get_me()
    set_bot_id(me.id, me.username)
    await sync_bot_commands(bot)
    logging.info("Bot started as @%s", me.username)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
