from __future__ import annotations

import re

_SPLIT = re.compile(r"[^a-z0-9а-яё]+", re.IGNORECASE)

_ABBREV = {
    "max": "maximum",
    "min": "minimum",
    "res": "resistance",
    "resist": "resistance",
    "dmg": "damage",
    "spd": "speed",
    "crit": "critical",
    "phys": "physical",
    "ele": "elemental",
    "light": "lightning",
    "lit": "lightning",
    "arm": "armour",
    "armor": "armour",
    "ev": "evasion",
    "es": "energy shield",
    "acc": "accuracy",
    "regen": "regeneration",
    "pen": "penetration",
    "multi": "multiplier",
    "inc": "increased",
    "red": "reduced",
    "add": "added",
    "as": "attack speed",
    "cs": "cast speed",
    "life": "life",
    "hp": "life",
    "mana": "mana",
    "str": "strength",
    "dex": "dexterity",
    "int": "intelligence",
    "move": "movement",
    "ms": "movement speed",
    "block": "block",
    "spell": "spell",
    "atk": "attack",
    "def": "defence",
    "suffix": "suffix",
    "prefix": "prefix",
}


def tokenize(text: str) -> list[str]:
    return [part for part in _SPLIT.split(text.lower()) if part]


def _expand(token: str) -> list[str]:
    extra = _ABBREV.get(token)
    if not extra:
        return [token]
    return [token, *tokenize(extra)]


def _word_matches(word: str, variant: str) -> bool:
    if word == variant or word.startswith(variant):
        return True
    return len(variant) >= 3 and variant in word


def matches(query: str, *fields: str) -> bool:
    """«to max life» находит «to maximum life» и похожие сокращения."""
    raw = query.strip().lower()
    if not raw:
        return True
    haystack = " ".join(str(field) for field in fields if field).lower()
    if raw in haystack:
        return True
    q_tokens = tokenize(raw)
    if not q_tokens:
        return True
    h_tokens = tokenize(haystack)
    if not h_tokens:
        return False
    compact_h = "".join(h_tokens)
    expanded = [(_expand(token)[-1] if token in _ABBREV else token) for token in q_tokens]
    if "".join(q_tokens) in compact_h or "".join(expanded) in compact_h:
        return True
    remaining = list(h_tokens)
    for token in q_tokens:
        variants = _expand(token)
        index = next(
            (
                i
                for i, word in enumerate(remaining)
                if any(_word_matches(word, variant) for variant in variants)
            ),
            None,
        )
        if index is None:
            return False
        remaining.pop(index)
    return True
