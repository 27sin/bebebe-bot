import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import BOT_TOKEN
from bot.handlers.commands import router as commands_router
from bot.handlers.guess_commands import handle_guess_attempt, router as guess_router
from bot.handlers.messages import router as messages_router
from bot.logging_setup import setup_logging
from bot.services.guess_game import bind_bot
from bot.services.trigger import set_bot_id

setup_logging()


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    bind_bot(bot)
    dispatcher = Dispatcher()
    dispatcher.include_router(commands_router)
    dispatcher.include_router(guess_router)
    dispatcher.include_router(messages_router)

    me = await bot.get_me()
    set_bot_id(me.id, me.username)
    logging.info("Bot started as @%s", me.username)

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
