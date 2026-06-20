from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.types import Message

from bot.config import DEFAULT_REPLY_COOLDOWN_SECONDS, RANDOM_REPLY_PROBABILITY
from bot.handlers.help_text import build_help_text
from bot.handlers.user_target import TargetUser, resolve_target_user, user_label
from bot.services.settings import (
    RESET_ALIASES,
    add_ignored_user,
    clear_custom_rule,
    clear_reply_cooldown,
    clear_reply_probability,
    clear_user_reply_probability,
    get_effective_reply_probability,
    get_reply_cooldown,
    get_reply_probability,
    list_custom_rules,
    list_ignored_users,
    list_user_reply_probabilities,
    remove_ignored_user,
    set_custom_rule,
    set_reply_cooldown,
    set_reply_probability,
    set_user_reply_probability,
)
from bot.services.stats import build_stats_message, stats_period_help
from bot.services.game_stats import build_game_stats_message, game_stats_period_help
from bot.services.profile import build_profile_message
from bot.services.titles import build_titles_message

logger = logging.getLogger(__name__)

router = Router(name="commands")

CHANCE_PATTERN = re.compile(r"^/chance(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
COOLDOWN_PATTERN = re.compile(r"^/cooldown(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
USER_CHANCE_PATTERN = re.compile(r"^/userchance(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
HELP_PATTERN = re.compile(r"^/help(?:@\w+)?$", re.IGNORECASE)
START_PATTERN = re.compile(r"^/start(?:@\w+)?$", re.IGNORECASE)
IGNORE_PATTERN = re.compile(r"^/ignore(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
UNIGNORE_PATTERN = re.compile(r"^/unignore(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
STATS_PATTERN = re.compile(r"^/stats(?:@\w+)?(?:\s+(\S+))?$", re.IGNORECASE)
GAMESTATS_PATTERN = re.compile(r"^/gamestats(?:@\w+)?(?:\s+(\S+))?$", re.IGNORECASE)
TITLES_PATTERN = re.compile(r"^/titles(?:@\w+)?(?:\s*(.*))?$", re.IGNORECASE)
ME_PATTERN = re.compile(r"^/me(?:@\w+)?$", re.IGNORECASE)
ADDRULE_PATTERN = re.compile(r"^/addrule(?:@\w+)?(?:\s+(.+))?$", re.IGNORECASE)
TRIGGER_WORD_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]+$")
MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_]{4,})")
MAX_CUSTOM_RULE_LENGTH = 500


def _parse_probability(raw: str) -> float:
    value = raw.strip().replace(",", ".")
    probability = float(value)
    if probability > 1:
        probability /= 100
    if not 0 <= probability <= 1:
        raise ValueError("range")
    return probability


def _parse_cooldown(raw: str) -> float:
    value = raw.strip().replace(",", ".")
    cooldown = float(value)
    if cooldown < 0:
        raise ValueError("range")
    return cooldown


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


def _parse_user_chance_args(message: Message, arg: str) -> tuple[str, str | None]:
    parts = arg.strip().split()
    if not parts:
        raise ValueError("empty")

    mention_match = MENTION_PATTERN.search(arg)
    mention_text = f"@{mention_match.group(1)}" if mention_match else None
    tokens = [part for part in parts if not part.startswith("@")]

    if mention_text and not tokens:
        return "show", mention_text
    if mention_text and len(tokens) == 1:
        return tokens[0].lower(), mention_text
    if not mention_text and len(tokens) == 1 and message.reply_to_message:
        return tokens[0].lower(), None
    raise ValueError("format")


def _parse_addrule_args(raw: str) -> tuple[str, str]:
    stripped = raw.strip()
    for separator in ("→", "—", "->", "|"):
        if separator in stripped:
            left, right = stripped.split(separator, 1)
            trigger, response = left.strip(), right.strip()
            if trigger and response:
                return trigger, response
            raise ValueError("format")

    parts = stripped.split(None, 1)
    if len(parts) < 2:
        raise ValueError("format")
    return parts[0], parts[1].strip()


def _validate_rule_trigger(trigger: str) -> None:
    if not TRIGGER_WORD_PATTERN.fullmatch(trigger):
        raise ValueError("trigger")


def _validate_rule_response(response: str) -> None:
    if not response.strip():
        raise ValueError("response")
    if len(response) > MAX_CUSTOM_RULE_LENGTH:
        raise ValueError("length")


@router.message(F.text.regexp(START_PATTERN))
async def handle_start(message: Message) -> None:
    await message.answer(
        "Я передразниваю сообщения в групповых чатах.\n"
        "Добавь меня в группу и отключи Privacy Mode в BotFather.\n"
        "Список команд: /help"
    )


@router.message(F.text.regexp(HELP_PATTERN))
async def handle_help(message: Message) -> None:
    await message.answer(build_help_text(message.chat.id))


@router.message(F.text.regexp(CHANCE_PATTERN))
async def handle_chance(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = CHANCE_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = match.group(1)
    chat_id = message.chat.id
    current = get_reply_probability(chat_id)

    if not arg:
        default_note = ""
        if current != RANDOM_REPLY_PROBABILITY:
            default_note = f"\nПо умолчанию в боте: {_format_percent(RANDOM_REPLY_PROBABILITY)}."
        await message.answer(
            f"Шанс случайного ответа в этом чате: {_format_percent(current)}.{default_note}\n"
            "Изменить: /chance 95 или /chance 0.95\n"
            "Сброс: /chance reset\n"
            "Для участника: /userchance @ник 50"
        )
        return

    try:
        if arg.strip().lower() in RESET_ALIASES:
            clear_reply_probability(chat_id)
            await message.answer(
                f"Сброшено. Шанс: {_format_percent(get_reply_probability(chat_id))}."
            )
            return

        probability = _parse_probability(arg)
    except ValueError:
        await message.answer("Укажите число от 0 до 100 (или от 0 до 1).")
        return

    set_reply_probability(chat_id, probability)
    logger.info("Chat %s chance set to %s by %s", chat_id, probability, message.from_user.id)
    await message.answer(f"Готово. Шанс случайного ответа: {_format_percent(probability)}.")


@router.message(F.text.regexp(COOLDOWN_PATTERN))
async def handle_cooldown(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = COOLDOWN_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = match.group(1)
    chat_id = message.chat.id
    current = get_reply_cooldown(chat_id)

    if not arg:
        default_note = ""
        if current != DEFAULT_REPLY_COOLDOWN_SECONDS:
            default_note = f"\nПо умолчанию в боте: {_format_cooldown(DEFAULT_REPLY_COOLDOWN_SECONDS)}."
        await message.answer(
            f"Пауза между ответами в этом чате: {_format_cooldown(current)}.{default_note}\n"
            "Изменить: /cooldown 2\n"
            "Без ограничения: /cooldown 0\n"
            "Сброс: /cooldown reset"
        )
        return

    try:
        if arg.strip().lower() in RESET_ALIASES:
            clear_reply_cooldown(chat_id)
            await message.answer(
                f"Сброшено. Пауза: {_format_cooldown(get_reply_cooldown(chat_id))}."
            )
            return

        cooldown = _parse_cooldown(arg)
    except ValueError:
        await message.answer("Укажите число секунд от 0 и выше.")
        return

    set_reply_cooldown(chat_id, cooldown)
    logger.info("Chat %s cooldown set to %s by %s", chat_id, cooldown, message.from_user.id)
    await message.answer(f"Готово. Пауза между ответами: {_format_cooldown(cooldown)}.")


@router.message(F.text.regexp(USER_CHANCE_PATTERN))
async def handle_user_chance(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = USER_CHANCE_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = match.group(1)
    chat_id = message.chat.id

    if not arg:
        users = list_user_reply_probabilities(chat_id)
        if not users:
            await message.answer(
                "Персональных шансов пока нет.\n"
                "Примеры:\n"
                "/userchance @ник 80\n"
                "/userchance 80 — reply на сообщение участника\n"
                "/userchance @ник reset"
            )
            return

        lines = [
            f"{_format_user_key(key)}: {_format_percent(value)}" for key, value in users
        ]
        await message.answer("Персональные шансы:\n" + "\n".join(lines))
        return

    try:
        action, mention_text = _parse_user_chance_args(message, arg)
    except ValueError:
        await message.answer(
            "Примеры:\n"
            "/userchance @ник 80\n"
            "/userchance 80 — reply на сообщение\n"
            "/userchance @ник reset"
        )
        return

    target = resolve_target_user(message, mention_text)
    if target is None:
        await message.answer("Укажите участника через @ник или reply на его сообщение.")
        return

    if action == "show":
        probability = get_effective_reply_probability(chat_id, target.user_id, target.username)
        await message.answer(
            f"Шанс для {target.label}: {_format_percent(probability)}."
        )
        return

    if action in RESET_ALIASES:
        if clear_user_reply_probability(chat_id, target.user_id, target.username):
            probability = get_effective_reply_probability(chat_id, target.user_id, target.username)
            await message.answer(
                f"Сброшено для {target.label}. Шанс: {_format_percent(probability)}."
            )
        else:
            await message.answer(f"Для {target.label} персональный шанс не задан.")
        return

    try:
        probability = _parse_probability(action)
    except ValueError:
        await message.answer("Укажите число от 0 до 100 (или от 0 до 1).")
        return

    set_user_reply_probability(chat_id, target.user_id, target.username, probability)
    logger.info(
        "Chat %s user chance set to %s for %s by %s",
        chat_id,
        probability,
        target.label,
        message.from_user.id,
    )
    await message.answer(
        f"Готово. Шанс для {target.label}: {_format_percent(probability)}."
    )


def _resolve_ignore_target(message: Message, arg: str | None) -> TargetUser | None:
    mention_match = MENTION_PATTERN.search(arg or "")
    mention_text = f"@{mention_match.group(1)}" if mention_match else None
    return resolve_target_user(message, mention_text)


@router.message(F.text.regexp(IGNORE_PATTERN))
async def handle_ignore(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = IGNORE_PATTERN.match(message.text.strip())
    if not match:
        return

    chat_id = message.chat.id
    arg = match.group(1)

    if not arg:
        ignored = list_ignored_users(chat_id)
        if not ignored:
            await message.answer(
                "Игнор-лист пуст.\n"
                "Добавить: /ignore @ник или reply на сообщение + /ignore"
            )
            return
        lines = [_format_user_key(key) for key in ignored]
        await message.answer("Бот не трогает:\n" + "\n".join(lines))
        return

    target = _resolve_ignore_target(message, arg)
    if target is None:
        await message.answer("Укажите участника через @ник или reply на его сообщение.")
        return

    add_ignored_user(chat_id, target.user_id, target.username)
    await message.answer(f"Готово. Бот не будет отвечать {target.label}.")


@router.message(F.text.regexp(UNIGNORE_PATTERN))
async def handle_unignore(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = UNIGNORE_PATTERN.match(message.text.strip())
    if not match:
        return

    chat_id = message.chat.id
    arg = match.group(1)

    if not arg:
        await message.answer(
            "Снять игнор: /unignore @ник или reply на сообщение + /unignore"
        )
        return

    target = _resolve_ignore_target(message, arg)
    if target is None:
        await message.answer("Укажите участника через @ник или reply на его сообщение.")
        return

    if remove_ignored_user(chat_id, target.user_id, target.username):
        await message.answer(f"Готово. {target.label} снова в игре.")
    else:
        await message.answer(f"{target.label} не был в игнор-листе.")


@router.message(F.text.regexp(STATS_PATTERN))
async def handle_stats(message: Message) -> None:
    if not message.text:
        return

    match = STATS_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = (match.group(1) or "").strip().lower()
    if arg in {"", "help", "?"}:
        await message.answer(stats_period_help())
        return

    period = arg or "week"
    await message.answer(build_stats_message(message.chat.id, period))


@router.message(F.text.regexp(GAMESTATS_PATTERN))
async def handle_gamestats(message: Message) -> None:
    if not message.text:
        return

    match = GAMESTATS_PATTERN.match(message.text.strip())
    if not match:
        return

    arg = (match.group(1) or "").strip().lower()
    if arg in {"", "help", "?"}:
        await message.answer(game_stats_period_help())
        return

    period = arg or "week"
    await message.answer(build_game_stats_message(message.chat.id, period))


@router.message(F.text.regexp(TITLES_PATTERN))
async def handle_titles(message: Message) -> None:
    if not message.from_user:
        return

    match = TITLES_PATTERN.match((message.text or "").strip())
    if not match:
        return

    raw_arg = (match.group(1) or "").strip()
    target: TargetUser | None = None
    for part in raw_arg.split():
        if part.startswith("@"):
            target = resolve_target_user(message, part)
            break
    if target is None and message.reply_to_message:
        target = resolve_target_user(message, None)

    if target is not None and target.user_id is not None:
        await message.answer(
            build_titles_message(message.chat.id, target.user_id, target.label)
        )
        return

    await message.answer(
        build_titles_message(
            message.chat.id,
            message.from_user.id,
            user_label(message.from_user),
        )
    )


@router.message(F.text.regexp(ME_PATTERN))
async def handle_me(message: Message) -> None:
    if not message.from_user:
        return

    await message.answer(
        build_profile_message(
            message.chat.id,
            message.from_user.id,
            user_label(message.from_user),
        )
    )


@router.message(F.text.regexp(ADDRULE_PATTERN))
async def handle_addrule(message: Message) -> None:
    if not message.text or not message.from_user:
        return

    match = ADDRULE_PATTERN.match(message.text.strip())
    if not match:
        return

    chat_id = message.chat.id
    arg = match.group(1)

    if not arg:
        rules = list_custom_rules(chat_id)
        if not rules:
            await message.answer(
                "Своих правил пока нет.\n"
                "Примеры:\n"
                "/addrule пиво — пивасик\n"
                "/addrule пиво пивасик\n"
                "/addrule пиво reset — удалить правило"
            )
            return
        lines = [f"• {trigger} → {response}" for trigger, response in rules]
        await message.answer(
            "Правила чата (последнее слово → ответ):\n" + "\n".join(lines)
        )
        return

    parts = arg.strip().split(None, 1)
    trigger = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""

    if not rest or rest.lower() in RESET_ALIASES:
        try:
            _validate_rule_trigger(trigger)
        except ValueError:
            await message.answer("Триггер — одно слово: буквы, цифры, без пробелов.")
            return
        if clear_custom_rule(chat_id, trigger):
            await message.answer(f"Правило для «{trigger.lower()}» удалено.")
        else:
            await message.answer(f"Правила для «{trigger.lower()}» не было.")
        return

    try:
        parsed_trigger, response = _parse_addrule_args(arg)
        _validate_rule_trigger(parsed_trigger)
        _validate_rule_response(response)
    except ValueError as error:
        if str(error) == "length":
            await message.answer(f"Ответ не длиннее {MAX_CUSTOM_RULE_LENGTH} символов.")
        elif str(error) == "trigger":
            await message.answer("Триггер — одно слово: буквы, цифры, без пробелов.")
        else:
            await message.answer(
                "Примеры:\n"
                "/addrule пиво — пивасик\n"
                "/addrule пиво пивасик\n"
                "/addrule пиво reset"
            )
        return

    set_custom_rule(chat_id, parsed_trigger, response)
    logger.info(
        "Chat %s custom rule %r -> %r by %s",
        chat_id,
        parsed_trigger.lower(),
        response,
        message.from_user.id,
    )
    await message.answer(
        f"Готово. Если последнее слово «{parsed_trigger.lower()}» — отвечу: {response}"
    )
