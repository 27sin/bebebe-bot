from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MENU_CALLBACK_PREFIX = "cm"


@dataclass(frozen=True)
class MenuButton:
    label: str
    action: str


@dataclass(frozen=True)
class CommandMenu:
    title: str
    intro: str
    option_lines: tuple[str, ...]
    rows: tuple[tuple[MenuButton, ...], ...]
    footer: str = ""


def menu_callback_data(menu_id: str, action: str) -> str:
    data = f"{MENU_CALLBACK_PREFIX}:{menu_id}:{action}"
    if len(data.encode("utf-8")) > 64:
        raise ValueError(f"callback_data too long: {data!r}")
    return data


def parse_menu_callback(data: str) -> tuple[str, str] | None:
    if not data.startswith(f"{MENU_CALLBACK_PREFIX}:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3:
        return None
    _, menu_id, action = parts
    if not menu_id or not action:
        return None
    return menu_id, action


def build_menu_keyboard(menu_id: str) -> InlineKeyboardMarkup | None:
    menu = COMMAND_MENUS.get(menu_id)
    if menu is None or not menu.rows:
        return None

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for row in menu.rows:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=button.label,
                    callback_data=menu_callback_data(menu_id, button.action),
                )
                for button in row
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


def build_menu_text(menu_id: str, *, extra: str = "") -> str | None:
    menu = COMMAND_MENUS.get(menu_id)
    if menu is None:
        return None

    lines = [menu.title, "", menu.intro, "", "Доступные опции:"]
    lines.extend(f"• {line}" for line in menu.option_lines)
    if menu.footer:
        lines.extend(["", menu.footer])
    if extra:
        lines.extend(["", extra])
    lines.append("")
    lines.append("Или набери вручную, например /guess 5 или /stats week.")
    return "\n".join(lines)


COMMAND_MENUS: dict[str, CommandMenu] = {
    "guess": CommandMenu(
        title="🎮 Угадай пародию",
        intro="Бот показывает пародию — угадай исходное слово. Победитель сессии получает +1 в лидерборд.",
        option_lines=(
            "Старт — 3 раунда по 60 сек",
            "Старт — 5 раундов",
            "Лидерборд побед",
            "Остановить текущую игру",
        ),
        rows=(
            (
                MenuButton("▶️ Старт (3)", "start"),
                MenuButton("▶️ 5 раундов", "start:5"),
            ),
            (
                MenuButton("🏆 Лидерборд", "score"),
                MenuButton("⏹ Стоп", "stop"),
            ),
        ),
    ),
    "guessduel": CommandMenu(
        title="🎮 Дуэль 1×1",
        intro="Вызов соперника: /guessduel @ник. У соперника 30 сек, чтобы принять.",
        option_lines=(
            "Принять вызов",
            "Отменить дуэль / лобби",
        ),
        rows=(
            (
                MenuButton("✅ Принять", "accept"),
                MenuButton("⏹ Стоп", "stop"),
            ),
        ),
        footer="Вызвать: /guessduel @ник или /guessduel @ник 5",
    ),
    "guessparty": CommandMenu(
        title="🎮 Party-режим",
        intro="Лобби с подтверждением участников перед стартом.",
        option_lines=(
            "Открыть лобби",
            "Войти в лобби",
            "Выйти из лобби",
            "Отменить party",
        ),
        rows=(
            (
                MenuButton("🎉 Лобби", "start"),
                MenuButton("➕ Войти", "join"),
            ),
            (
                MenuButton("➖ Выйти", "leave"),
                MenuButton("⏹ Стоп", "stop"),
            ),
        ),
        footer="С числом участников: /guessparty 4 или /guessparty 4 5",
    ),
    "chance": CommandMenu(
        title="⚙️ Шанс случайного ответа",
        intro="Вероятность, с которой бот ответит без reply и @упоминания.",
        option_lines=(
            "Быстрые пресеты: 10%, 30%, 50%, 80%, 95%",
            "Сброс к значению по умолчанию",
        ),
        rows=(
            (
                MenuButton("10%", "set:10"),
                MenuButton("30%", "set:30"),
                MenuButton("50%", "set:50"),
            ),
            (
                MenuButton("80%", "set:80"),
                MenuButton("95%", "set:95"),
                MenuButton("↩️ Сброс", "reset"),
            ),
        ),
        footer="Точное значение: /chance 42. Для участника: /userchance @ник 50",
    ),
    "cooldown": CommandMenu(
        title="⚙️ Пауза между ответами",
        intro="Минимальный интервал между ответами бота в этом чате.",
        option_lines=(
            "Без ограничения, 2 сек, 5 сек",
            "Сброс к значению по умолчанию",
        ),
        rows=(
            (
                MenuButton("♾ Без лимита", "set:0"),
                MenuButton("2 сек", "set:2"),
                MenuButton("5 сек", "set:5"),
            ),
            (MenuButton("↩️ Сброс", "reset"),),
        ),
        footer="Другое значение: /cooldown 3",
    ),
    "stats": CommandMenu(
        title="📊 Статистика ответов бота",
        intro="Кто сколько раз получил пародию от бота в этом чате.",
        option_lines=("За день, неделю, месяц или всё время",),
        rows=(
            (
                MenuButton("День", "period:day"),
                MenuButton("Неделя", "period:week"),
            ),
            (
                MenuButton("Месяц", "period:month"),
                MenuButton("Всё время", "period:all"),
            ),
        ),
    ),
    "gamestats": CommandMenu(
        title="📊 Статистика игр",
        intro="Попытки угадать, победы и сессии «Угадай пародию».",
        option_lines=("За день, неделю, месяц или всё время",),
        rows=(
            (
                MenuButton("День", "period:day"),
                MenuButton("Неделя", "period:week"),
            ),
            (
                MenuButton("Месяц", "period:month"),
                MenuButton("Всё время", "period:all"),
            ),
        ),
    ),
    "userchance": CommandMenu(
        title="⚙️ Персональный шанс",
        intro="Отдельная вероятность ответа для конкретного участника.",
        option_lines=(
            "Задать: /userchance @ник 80",
            "Reply на сообщение + /userchance 80",
            "Сброс: /userchance @ник reset",
        ),
        rows=(),
        footer="Список персональных шансов показывается при /userchance без аргументов.",
    ),
    "ignore": CommandMenu(
        title="⚙️ Игнор-лист",
        intro="Бот не отвечает участникам из списка.",
        option_lines=(
            "Добавить: /ignore @ник или reply + /ignore",
            "Убрать: /unignore @ник",
        ),
        rows=(),
    ),
    "addrule": CommandMenu(
        title="⚙️ Свои правила",
        intro="Уникальный ответ бота, если последнее слово сообщения совпало с триггером.",
        option_lines=(
            "Добавить: /addrule слово — ответ",
            "Удалить: /addrule слово reset",
        ),
        rows=(),
    ),
}
