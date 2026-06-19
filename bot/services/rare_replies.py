from __future__ import annotations

import random

RARE_REPLY_PROBABILITY = 0.03

RARE_REPLIES: tuple[str, ...] = (
    "я устал",
    "не сегодня",
    "мб потом",
    "...",
    "ой",
    "лол",
    "окак",
    "вы эти все одинаковые",
    "мимо",
    "не надо",
    "потом",
    "ща занят",
)


def maybe_rare_reply() -> str | None:
    if random.random() < RARE_REPLY_PROBABILITY:
        return random.choice(RARE_REPLIES)
    return None
