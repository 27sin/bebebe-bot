from bot.config import DEFAULT_REPLY_COOLDOWN_SECONDS, RANDOM_REPLY_PROBABILITY
from bot.services.settings import get_reply_cooldown, get_reply_probability


def build_help_text(chat_id: int) -> str:
    chance = get_reply_probability(chat_id)
    cooldown = get_reply_cooldown(chat_id)

    return (
        "Бот передразнивает слова в сообщении.\n"
        "Ровно два слова — оба; одно или три и больше — последнее.\n"
        "Отвечает на reply, @упоминание или случайно.\n\n"
        f"Сейчас в чате: шанс {chance * 100:.0f}%, пауза {cooldown:g} сек.\n\n"
        "Команды:\n"
        "/start — кратко о боте\n"
        "/help — эта справка\n\n"
        "/chance — шанс случайного ответа для всего чата\n"
        "/chance 95 — поставить 95%\n"
        "/chance reset — сброс к значению по умолчанию\n\n"
        "/userchance — персональные шансы участников\n"
        "/userchance @ник 80 — 80% для участника\n"
        "/userchance 80 — reply на сообщение + 80%\n"
        "/userchance @ник reset — сброс для участника\n\n"
        "/cooldown — пауза между ответами бота\n"
        "/cooldown 2 — не чаще 1 раза в 2 сек\n"
        "/cooldown 0 — без ограничения\n"
        "/cooldown reset — сброс (по умолчанию "
        f"{DEFAULT_REPLY_COOLDOWN_SECONDS:g} сек)\n\n"
        "/ignore — кого бот не трогает\n"
        "/ignore @ник — добавить в игнор\n"
        "/unignore @ник — убрать из игнора\n\n"
        "/stats — статистика за 7 дней\n"
        "/stats day|week|month|all — за другой период\n\n"
        "/gamestats — статистика игр в чате\n"
        "/gamestats day|week|month|all\n\n"
        "/addrule — свои ответы на последнее слово\n"
        "/addrule слово — ответ\n"
        "/addrule слово reset — удалить правило\n\n"
        "/guess — мини-игра «угадай пародию» (3 раунда)\n"
        "/guess 5 — сессия из 5 раундов\n"
        "/guess score — лидерборд\n"
        "/guess stop — остановить игру\n\n"
        "/guessparty — party-режим с лобби и подтверждением\n"
        "/guessparty join — войти в лобби\n"
        "/guessparty stop — отменить party\n\n"
        f"Значения по умолчанию бота: шанс {RANDOM_REPLY_PROBABILITY * 100:.0f}%, "
        f"пауза {DEFAULT_REPLY_COOLDOWN_SECONDS:g} сек."
    )
