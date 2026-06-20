import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env", override=True)


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


BOT_TOKEN = _require("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
RANDOM_REPLY_PROBABILITY = float(os.getenv("RANDOM_REPLY_PROBABILITY", "0.25"))
DEFAULT_REPLY_COOLDOWN_SECONDS = float(os.getenv("DEFAULT_REPLY_COOLDOWN_SECONDS", "1"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "5"))


def _parse_admin_user_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        piece = part.strip()
        if piece.isdigit():
            ids.add(int(piece))
    return frozenset(ids)


ADMIN_USER_IDS = _parse_admin_user_ids(os.getenv("ADMIN_USER_IDS", ""))


def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS
