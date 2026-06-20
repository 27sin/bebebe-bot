from __future__ import annotations

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeDefault

GROUP_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="help", description="📖 Справка по командам"),
    BotCommand(command="me", description="👤 Моя карточка в чате"),
    BotCommand(command="titles", description="🏅 Титулы за ответы и победы"),
    BotCommand(command="guess", description="🎮 Игра: угадай пародию"),
    BotCommand(command="guessduel", description="🎮 Игра: дуэль 1×1"),
    BotCommand(command="guessparty", description="🎮 Игра: party-лобби"),
    BotCommand(command="stats", description="📊 Статистика: ответы бота"),
    BotCommand(command="gamestats", description="📊 Статистика: игры"),
    BotCommand(command="chance", description="⚙️ Шанс случайного ответа"),
    BotCommand(command="cooldown", description="⚙️ Пауза между ответами"),
    BotCommand(command="userchance", description="⚙️ Персональный шанс"),
    BotCommand(command="ignore", description="⚙️ Игнор-лист"),
    BotCommand(command="addrule", description="⚙️ Свои правила на слово"),
)

DEFAULT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Кратко о боте"),
    BotCommand(command="help", description="📖 Справка по командам"),
)


async def sync_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(GROUP_COMMANDS), scope=BotCommandScopeAllGroupChats())
    await bot.set_my_commands(list(DEFAULT_COMMANDS), scope=BotCommandScopeDefault())
