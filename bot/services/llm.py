from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from bot.config import LLM_TIMEOUT_SECONDS, OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты бот, который передразнивает сообщения в стиле интернет-юмора. "
    "Отвечай коротко, 1-5 слов, на русском. Без кавычек и пояснений."
)


async def parody_with_llm(text: str) -> str | None:
    if not OPENAI_API_KEY:
        return None

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                max_tokens=40,
                temperature=0.9,
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("LLM parody failed")
        return None

    content = (response.choices[0].message.content or "").strip()
    if not content:
        return None

    return content.strip('"').strip("'")
