from __future__ import annotations

from collections import Counter

from bot.services.easter_eggs import format_progress_line
from bot.services.game_stats import _filter_events
from bot.services.stats import _filter_records
from bot.services.titles import (
    REPLY_TIERS,
    WIN_TIERS,
    _next_tier,
    get_reply_count,
    get_win_count,
    reply_title,
    win_title,
)

SOURCE_NAMES = {
    "text": "текст",
    "attachment": "вложения",
    "streak": "серии",
    "rare": "редкие",
    "reply_context": "контекст",
    "edit": "редактуры",
}


def _user_reply_rank(chat_id: int, user_id: int, *, period: str = "week") -> tuple[int, int] | None:
    counts: Counter[int] = Counter()
    for record in _filter_records(chat_id, period):
        counts[record.user_id] += 1
    if user_id not in counts:
        return None
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    total = len(ranked)
    for place, (uid, _) in enumerate(ranked, start=1):
        if uid == user_id:
            return place, total
    return None


def _user_week_game_stats(chat_id: int, user_id: int) -> tuple[int, int, int]:
    correct = 0
    attempts = 0
    wins = 0
    for entry in _filter_events(chat_id, "week"):
        event_type = str(entry.get("event", ""))
        entry_user_id = int(entry.get("user_id", 0))
        if event_type == "correct_guess" and entry_user_id == user_id:
            correct += 1
        elif event_type == "guess_attempt" and entry_user_id == user_id:
            attempts += 1
        elif event_type == "session_end":
            for winner in entry.get("winners", []):
                if int(winner.get("user_id", 0)) == user_id:
                    wins += 1
    return correct, attempts + correct, wins


def build_profile_message(chat_id: int, user_id: int, base_label: str) -> str:
    week_records = [r for r in _filter_records(chat_id, "week") if r.user_id == user_id]
    replies_week = len(week_records)
    replies_total = get_reply_count(chat_id, user_id)
    wins_total = get_win_count(chat_id, user_id)
    rt = reply_title(chat_id, user_id)
    wt = win_title(chat_id, user_id)
    rank = _user_reply_rank(chat_id, user_id, period="week")
    correct, guess_attempts, wins_week = _user_week_game_stats(chat_id, user_id)

    by_source: Counter[str] = Counter()
    for record in week_records:
        by_source[record.source] += 1

    lines = [
        f"📋 {base_label}",
        "",
        "За 7 дней:",
        f"  Ответов бота на тебя: {replies_week}",
    ]

    if by_source:
        source_parts = [
            f"{SOURCE_NAMES.get(source, source)} {count}"
            for source, count in by_source.most_common()
        ]
        lines.append(f"  ({', '.join(source_parts)})")

    if guess_attempts or wins_week:
        lines.append(f"  Попыток угадать в играх: {guess_attempts}")
        lines.append(f"  Угадываний: {correct}")
        lines.append(f"  Побед в сессиях: {wins_week}")

    lines.extend(["", "Ранг за ответы (всего):", f"  {rt or 'без ранга'} ({replies_total} ответов)"])
    next_reply = _next_tier(replies_total, REPLY_TIERS)
    if next_reply:
        need, title = next_reply
        lines.append(f"  → ещё {need - replies_total} до «{title}»")

    if rank:
        place, total = rank
        lines.append(f"  Место в чате за неделю: {place} из {total}")
    elif replies_week == 0:
        lines.append("  Место в чате за неделю: — (бот не отвечал)")

    lines.extend(["", "Титул в играх:", f"  {wt or 'без титула'} ({wins_total} побед)"])
    next_win = _next_tier(wins_total, WIN_TIERS)
    if next_win:
        need, title = next_win
        lines.append(f"  → ещё {need - wins_total} до «{title}»")

    lines.extend(["", format_progress_line(chat_id, user_id)])

    return "\n".join(lines)
