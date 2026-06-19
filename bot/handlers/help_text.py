from bot.config import DEFAULT_REPLY_COOLDOWN_SECONDS, RANDOM_REPLY_PROBABILITY
from bot.services.settings import get_reply_cooldown, get_reply_probability


def build_help_text(chat_id: int) -> str:
    chance = get_reply_probability(chat_id)
    cooldown = get_reply_cooldown(chat_id)

    return (
        "Бот передразнивает последнее слово в сообщении.\n"
        "На вложения отвечает фиксированными фразами "
        "(картинка, видео, гиф, стикер, голос, документ, гео).\n"
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
        f"Значения по умолчанию бота: шанс {RANDOM_REPLY_PROBABILITY * 100:.0f}%, "
        f"пауза {DEFAULT_REPLY_COOLDOWN_SECONDS:g} сек."
    )
