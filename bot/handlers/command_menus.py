from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from bot.config import DEFAULT_REPLY_COOLDOWN_SECONDS, RANDOM_REPLY_PROBABILITY
from bot.handlers.user_target import user_label
from bot.services.command_menus import (
    COMMAND_MENUS,
    build_menu_keyboard,
    build_menu_text,
    parse_menu_callback,
)
from bot.services.game_stats import build_game_stats_message
from bot.services.guess_duel import accept_duel, duel_help_text, is_duel_lobby_active, stop_duel
from bot.services.guess_game import (
    DEFAULT_ROUNDS,
    build_leaderboard_message,
    is_game_active,
    start_session,
    stop_session,
)
from bot.services.guess_party import (
    begin_party_setup,
    is_party_lobby_active,
    is_party_pending_setup,
    join_party_lobby,
    leave_party_lobby,
    stop_party,
)
from bot.services.settings import (
    clear_reply_cooldown,
    clear_reply_probability,
    get_reply_cooldown,
    get_reply_probability,
    list_custom_rules,
    list_ignored_users,
    list_user_reply_probabilities,
    set_reply_cooldown,
    set_reply_probability,
)
from bot.services.stats import build_stats_message

logger = logging.getLogger(__name__)

router = Router(name="command_menus")


def _format_percent(probability: float) -> str:
    return f"{probability * 100:.0f}%"


def _format_cooldown(seconds: float) -> str:
    if seconds <= 0:
        return "без ограничения"
    if seconds.is_integer():
        return f"{int(seconds)} сек"
    return f"{seconds:.1f} сек"


def _format_user_key(key: str) -> str:
    if key.startswith("@"):
        return key
    return f"id:{key}"


def _menu_extra(menu_id: str, chat_id: int) -> str:
    if menu_id == "chance":
        current = get_reply_probability(chat_id)
        note = f"Сейчас: {_format_percent(current)}."
        if current != RANDOM_REPLY_PROBABILITY:
            note += f" По умолчанию в боте: {_format_percent(RANDOM_REPLY_PROBABILITY)}."
        return note

    if menu_id == "cooldown":
        current = get_reply_cooldown(chat_id)
        note = f"Сейчас: {_format_cooldown(current)}."
        if current != DEFAULT_REPLY_COOLDOWN_SECONDS:
            note += f" По умолчанию: {_format_cooldown(DEFAULT_REPLY_COOLDOWN_SECONDS)}."
        return note

    if menu_id == "ignore":
        ignored = list_ignored_users(chat_id)
        if not ignored:
            return "Игнор-лист пуст."
        lines = [_format_user_key(key) for key in ignored]
        return "Сейчас в игноре:\n" + "\n".join(lines)

    if menu_id == "addrule":
        rules = list_custom_rules(chat_id)
        if not rules:
            return "Своих правил пока нет."
        lines = [f"• {trigger} → {response}" for trigger, response in rules]
        return "Правила чата:\n" + "\n".join(lines)

    if menu_id == "userchance":
        users = list_user_reply_probabilities(chat_id)
        if not users:
            return "Персональных шансов пока нет."
        lines = [f"{_format_user_key(key)}: {_format_percent(value)}" for key, value in users]
        return "Персональные шансы:\n" + "\n".join(lines)

    if menu_id == "guess" and is_game_active(chat_id):
        return "Сейчас идёт игра в этом чате."

    if menu_id == "guessduel" and is_duel_lobby_active(chat_id):
        return "Сейчас открыта дуэль или её лобби."

    if menu_id in {"guessparty", "guess"} and (
        is_party_lobby_active(chat_id) or is_party_pending_setup(chat_id)
    ):
        return "Сейчас открыто party-лобби."

    return ""


async def send_command_menu(message: Message, menu_id: str) -> None:
    text = build_menu_text(menu_id, extra=_menu_extra(menu_id, message.chat.id))
    if text is None:
        return

    await message.answer(
        text,
        reply_markup=build_menu_keyboard(menu_id),
    )


async def _execute_menu_action(
    callback: CallbackQuery,
    menu_id: str,
    action: str,
) -> str | None:
    if callback.message is None or callback.from_user is None:
        return None

    chat_id = callback.message.chat.id
    user = callback.from_user
    uid = user.id
    label = user_label(user)

    if menu_id == "guess":
        if is_party_lobby_active(chat_id) or is_party_pending_setup(chat_id):
            return "Сейчас открыто party-лобби. /guessparty join или /guessparty stop"
        if is_duel_lobby_active(chat_id):
            return "Сейчас открыта дуэль. /guessduel accept или /guessduel stop"

        if action == "start":
            return await start_session(
                chat_id,
                rounds=DEFAULT_ROUNDS,
                starter_id=uid,
                starter_label=label,
            )
        if action == "start:5":
            return await start_session(
                chat_id,
                rounds=5,
                starter_id=uid,
                starter_label=label,
            )
        if action == "score":
            return build_leaderboard_message(chat_id)
        if action == "stop":
            return await stop_session(chat_id)
        return None

    if menu_id == "guessduel":
        if action == "accept":
            return await accept_duel(chat_id, uid, label, user.username)
        if action == "stop":
            return await stop_duel(chat_id)
        if action == "help":
            return duel_help_text()
        return None

    if menu_id == "guessparty":
        if action == "start":
            return await begin_party_setup(chat_id, uid, label)
        if action == "join":
            return await join_party_lobby(chat_id, uid, label)
        if action == "leave":
            return await leave_party_lobby(chat_id, uid)
        if action == "stop":
            return await stop_party(chat_id)
        return None

    if menu_id == "chance":
        if action == "reset":
            clear_reply_probability(chat_id)
            current = get_reply_probability(chat_id)
            logger.info("Chat %s chance reset by %s (menu)", chat_id, uid)
            return f"Сброшено. Шанс: {_format_percent(current)}."
        if action.startswith("set:"):
            percent = int(action.split(":", 1)[1])
            probability = percent / 100
            set_reply_probability(chat_id, probability)
            logger.info("Chat %s chance set to %s by %s (menu)", chat_id, probability, uid)
            return f"Готово. Шанс случайного ответа: {_format_percent(probability)}."
        return None

    if menu_id == "cooldown":
        if action == "reset":
            clear_reply_cooldown(chat_id)
            current = get_reply_cooldown(chat_id)
            logger.info("Chat %s cooldown reset by %s (menu)", chat_id, uid)
            return f"Сброшено. Пауза: {_format_cooldown(current)}."
        if action.startswith("set:"):
            cooldown = float(action.split(":", 1)[1])
            set_reply_cooldown(chat_id, cooldown)
            logger.info("Chat %s cooldown set to %s by %s (menu)", chat_id, cooldown, uid)
            return f"Готово. Пауза между ответами: {_format_cooldown(cooldown)}."
        return None

    if menu_id == "stats" and action.startswith("period:"):
        period = action.split(":", 1)[1]
        return build_stats_message(chat_id, period)

    if menu_id == "gamestats" and action.startswith("period:"):
        period = action.split(":", 1)[1]
        return build_game_stats_message(chat_id, period)

    return None


@router.callback_query(F.data.startswith("cm:"))
async def handle_command_menu_callback(callback: CallbackQuery) -> None:
    if not callback.data or callback.message is None:
        await callback.answer()
        return

    parsed = parse_menu_callback(callback.data)
    if parsed is None:
        await callback.answer()
        return

    menu_id, action = parsed
    if menu_id not in COMMAND_MENUS:
        await callback.answer("Неизвестная команда.", show_alert=True)
        return

    if callback.message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP} and menu_id in {
        "guess",
        "guessduel",
        "guessparty",
        "gamestats",
    }:
        await callback.answer("Эта опция только для групповых чатов.", show_alert=True)
        return

    try:
        result = await _execute_menu_action(callback, menu_id, action)
    except Exception:
        logger.exception("Menu action failed menu=%s action=%s", menu_id, action)
        await callback.answer("Не получилось выполнить.", show_alert=True)
        return

    if result is None:
        await callback.answer("Неизвестная опция.", show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(result)
