from __future__ import annotations

import re

WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+")
HYPHEN_TO_PATTERN = re.compile(
    r"([A-Za-zА-Яа-яЁё0-9]+)[-—](то)\b",
    re.IGNORECASE,
)
SHORT_HYPHEN_TO_LEFT_MAX = 4
MERGED_TO_MIN_STEM = 5
VOWELS = set("аеёиоуыэюя")
YA_PREFIX = "хуя"
YU_PREFIX = "хую"
YI_PREFIX = "хуи"
NO_PREFIX = "хуй"
NO_SUFFIX = "но"
HU_PREFIX = "ху"

_SPECIAL_LAST_WORD_REPLIES: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"макс", "максим", "максон"}), "Макс — красавчик"),
    (frozenset({"женя", "евгений", "женек", "женёк"}), "Женя — пидор❤"),
)

VOWEL_PREFIX = {
    "о": "хуй",
    "и": "хуи",
    "е": "хуе",
    "у": "хую",
    "а": "хуя",
    "я": "хуя",
    "ё": "хуе",
    "ы": "хуи",
    "э": "хуе",
    "ю": "хую",
}

INCLUDE_VOWEL_BEFORE_TO_DA = set("оеёяюа")


def _last_word(text: str) -> str | None:
    words = WORD_PATTERN.findall(text)
    if not words:
        return None
    return words[-1]


def _is_vowel(char: str) -> bool:
    return char.lower() in VOWELS


def _consonants_before(word: str, start: int) -> tuple[list[str], int]:
    consonants: list[str] = []
    index = start
    while index >= 0 and not _is_vowel(word[index]):
        consonants.insert(0, word[index])
        index -= 1
    return consonants, index


def _prefix_from_stem(stem: str) -> str:
    for char in reversed(stem):
        if _is_vowel(char):
            return VOWEL_PREFIX.get(char, HU_PREFIX)
    return HU_PREFIX


def _join_parody(prefix: str, suffix: str) -> str:
    if prefix == YA_PREFIX and suffix.startswith("а"):
        suffix = suffix[1:]
    if prefix == YU_PREFIX and suffix.startswith("у"):
        suffix = suffix[1:]
    return f"{prefix}{suffix}"


def _parody_hyphen_to(text: str) -> str | None:
    match = HYPHEN_TO_PATTERN.search(text)
    if not match:
        return None

    left = match.group(1).lower()
    if len(left) <= SHORT_HYPHEN_TO_LEFT_MAX:
        vowel = left[-1]
        suffix = f"{vowel}то"
        prefix = VOWEL_PREFIX.get(vowel, HU_PREFIX)
        return _join_parody(prefix, suffix)

    prefix = _prefix_from_stem(left)
    return _join_parody(prefix, "то")


def _parody_merged_to(word: str) -> str | None:
    normalized = word.lower()
    if not normalized.endswith("то") or len(normalized) <= MERGED_TO_MIN_STEM + 1:
        return None

    stem = normalized[:-2]
    if len(stem) < MERGED_TO_MIN_STEM or not _is_vowel(stem[-1]):
        return None

    prefix = _prefix_from_stem(stem)
    return _join_parody(prefix, "то")


def _suffix_for_no(word: str) -> tuple[str, str]:
    if not word.endswith(NO_SUFFIX):
        raise ValueError("word must end with -но")

    index = len(word) - len(NO_SUFFIX) - 1
    consonants, vowel_index = _consonants_before(word, index)

    if vowel_index >= 0 and word[vowel_index] == "а":
        return YA_PREFIX, "".join(consonants) + NO_SUFFIX

    if vowel_index >= 0 and word[vowel_index] == "у":
        return YU_PREFIX, "".join(consonants) + NO_SUFFIX

    if vowel_index >= 0 and word[vowel_index] == "и":
        return YI_PREFIX, "".join(consonants) + NO_SUFFIX

    return NO_PREFIX, NO_SUFFIX


def _suffix_for_to_da(word: str) -> str:
    ending = word[-2:]
    before = len(word) - 3

    if len(word) <= 4:
        return ending

    consonants, vowel_index = _consonants_before(word, before)

    if vowel_index < 0:
        return ending if not consonants else "".join(consonants) + ending

    vowel = word[vowel_index]

    if vowel == "а":
        return "".join(consonants) + ending

    if vowel == "у":
        return "".join(consonants) + ending

    if vowel in INCLUDE_VOWEL_BEFORE_TO_DA:
        return word[vowel_index:]

    return "".join(consonants) + ending


def _suffix_general(word: str) -> str:
    length = len(word)
    if length <= 2:
        return word

    last_vowel = _is_vowel(word[-1])
    prelast_vowel = _is_vowel(word[-2])

    if last_vowel and prelast_vowel:
        for index in range(length - 1, -1, -1):
            if not _is_vowel(word[index]):
                for earlier in range(index - 1, -1, -1):
                    if _is_vowel(word[earlier]):
                        return word[earlier:]
                return word[index:]
        return word

    if (not last_vowel) or (not prelast_vowel):
        for index in range(length - 3, -1, -1):
            if _is_vowel(word[index]):
                return word[index:]

    return word[-max(2, length // 3) :]


def _extract_suffix(word: str) -> str:
    normalized = word.lower()

    if normalized.endswith(NO_SUFFIX):
        _, suffix = _suffix_for_no(normalized)
        return suffix

    if normalized.endswith(("то", "да")):
        return _suffix_for_to_da(normalized)

    if normalized.endswith("о") and len(normalized) <= 5:
        return normalized[-2:]

    if len(normalized) >= 8 and normalized.endswith("ие"):
        return normalized[-4:] if len(normalized) >= 9 else normalized[-3:]

    if normalized.endswith("ец"):
        return normalized[-2:]

    if len(normalized) >= 5 and normalized.endswith(("ор", "ер")):
        return normalized[-3:]

    if len(normalized) == 4:
        return normalized[-1:]

    if normalized.endswith("а") and len(normalized) >= 6:
        return normalized[-3:]

    return _suffix_general(normalized)


def _pick_prefix(word: str, suffix: str) -> str:
    normalized = word.lower()

    if normalized.endswith(NO_SUFFIX):
        prefix, _ = _suffix_for_no(normalized)
        return prefix

    if normalized.endswith("ие") or normalized.endswith("ец"):
        return HU_PREFIX

    if suffix.startswith("а"):
        return YA_PREFIX

    if suffix.startswith("у"):
        return YU_PREFIX

    stripped = normalized[: len(normalized) - len(suffix)]
    for char in reversed(stripped):
        if _is_vowel(char):
            return VOWEL_PREFIX.get(char, HU_PREFIX)

    for char in suffix:
        if _is_vowel(char):
            return VOWEL_PREFIX.get(char, HU_PREFIX)

    return HU_PREFIX


def _build_parody_parts(word: str) -> tuple[str, str]:
    normalized = word.lower()
    suffix = _extract_suffix(normalized)
    prefix = _pick_prefix(normalized, suffix)
    return prefix, suffix


def parody_word(word: str) -> str:
    merged = _parody_merged_to(word)
    if merged:
        return merged

    prefix, suffix = _build_parody_parts(word)
    return _join_parody(prefix, suffix)


def _special_last_word_reply(text: str) -> str | None:
    last = _last_word(text)
    if not last:
        return None
    normalized = last.lower()
    for names, reply in _SPECIAL_LAST_WORD_REPLIES:
        if normalized in names:
            return reply
    return None


def parody_with_rules(text: str) -> str | None:
    special = _special_last_word_reply(text)
    if special:
        return special

    hyphen_parody = _parody_hyphen_to(text)
    if hyphen_parody:
        return hyphen_parody

    last = _last_word(text)
    if not last:
        return None

    parody = parody_word(last)
    if not parody or parody.lower() == last.lower():
        return None
    return parody
