from __future__ import annotations

from app.i18n.strings import LANGUAGES, STRINGS

__all__ = ["LANGUAGES", "STRINGS", "language", "language_label", "set_language", "t"]

_lang = "en"


def set_language(code: str) -> None:
    global _lang
    if code in {item[0] for item in LANGUAGES}:
        _lang = code


def language() -> str:
    return _lang


def language_label(code: str | None = None) -> str:
    current = code or _lang
    for item_code, label in LANGUAGES:
        if item_code == current:
            return label
    return current


def t(message_id: str, default: str | None = None, **kwargs: object) -> str:
    pack = STRINGS.get(message_id, {})
    text = pack.get(_lang) or pack.get("en") or default or message_id
    if kwargs:
        return text.format(**kwargs)
    return text
