from __future__ import annotations

import re

from app.data.catalog import GameCatalog
from app.data.models import Condition, ModRequirement
from app.item_parse import ParsedAffix, ParsedItem, has_open_prefix, has_open_suffix, normalize, to_template

_STOP = {
    "to",
    "of",
    "the",
    "a",
    "an",
    "and",
    "with",
    "your",
    "you",
    "is",
    "к",
    "ко",
    "на",
    "от",
    "для",
    "по",
}
_SYN: dict[str, tuple[str, ...]] = {
    "cold": ("cold", "холоду", "холода", "холод", "холодом"),
    "fire": ("fire", "огню", "огня", "огонь", "огнём", "огнем"),
    "lightning": ("lightning", "молнии", "молния", "молнией"),
    "chaos": ("chaos", "хаосу", "хаоса", "хаос"),
    "life": ("life", "жизни", "жизнь"),
    "mana": ("mana", "маны", "мана", "мане"),
    "resistance": ("resistance", "resist", "сопротивлению", "сопротивления", "сопротивление"),
    "maximum": ("maximum", "max", "максимум", "максимальной", "максимальную"),
    "energy": ("energy", "энергии", "энергетического"),
    "shield": ("shield", "щита", "щиту", "щит"),
    "armour": ("armour", "armor", "брони", "броня", "броне"),
    "evasion": ("evasion", "уклонению", "уклонения", "уклонение"),
    "accuracy": ("accuracy", "меткости", "меткость"),
    "strength": ("strength", "силе", "сила"),
    "dexterity": ("dexterity", "ловкости", "ловкость"),
    "intelligence": ("intelligence", "интеллекту", "интеллект"),
    "speed": ("speed", "скорости", "скорость"),
    "damage": ("damage", "урона", "урон", "урону"),
    "attack": ("attack", "атаки", "атака"),
    "cast": ("cast", "сотворения", "каста"),
    "critical": ("critical", "критическому", "критический", "крит"),
    "spell": ("spell", "чары", "чар", "заклинаний"),
}


def affix_matches(req: ModRequirement, affix: ParsedAffix) -> bool:
    if affix.implicit:
        return False
    if req.generation in {"prefix", "suffix"} and affix.generation and affix.generation != req.generation:
        return False
    if not _template_match(req.name, affix.template, affix.lines):
        return False
    if req.tier is not None and affix.tier is not None and affix.tier > req.tier:
        return False
    if req.value_min is not None and affix.values:
        if max(affix.values) < req.value_min:
            return False
    return True


def matched_requirements(item: ParsedItem, condition: Condition) -> set[str]:
    found: set[str] = set()
    for req in condition.mods:
        if any(affix_matches(req, affix) for affix in item.affixes):
            found.add(req.mod_type_id)
    return found


def condition_holds(item: ParsedItem, condition: Condition) -> bool:
    return condition_report(item, condition)[0]


def condition_report(item: ParsedItem, condition: Condition) -> tuple[bool, str]:
    kind = condition.kind
    have = ", ".join(item.explicit_lines()) or "—"
    if kind == "once":
        return True, "once"
    if kind == "open_prefix":
        ok = has_open_prefix(item)
        return ok, "open prefix" if ok else "no open prefix"
    if kind == "open_suffix":
        ok = has_open_suffix(item)
        return ok, "open suffix" if ok else "no open suffix"
    present = matched_requirements(item, condition)
    need_names = [req.name for req in condition.mods]
    want = " | ".join(need_names) or kind
    hit = [req.name for req in condition.mods if req.mod_type_id in present]
    satisfied = condition.need_satisfied(present)
    if kind == "missing_mod":
        if satisfied:
            return False, f"found {', '.join(hit)}  ·  have: {have}"
        return True, f"need {want}  ·  have: {have}"
    if kind == "has_mod":
        if satisfied:
            return True, f"has {', '.join(hit)}  ·  have: {have}"
        return False, f"missing {want}  ·  have: {have}"
    return False, kind


def infer_generation(catalog: GameCatalog, item_class: str, affix: ParsedAffix) -> str | None:
    if affix.generation:
        return affix.generation
    template = normalize(affix.template)
    for row in catalog.mod_types_for(item_class):
        if normalize(row.get("name") or "") == template:
            return row.get("generation")
    return None


def _template_match(required_name: str, affix_template: str, lines: list[str]) -> bool:
    need = normalize(to_template(required_name))
    have = normalize(affix_template)
    blob = have + " " + " ".join(normalize(to_template(line)) for line in lines)
    if not need:
        return False
    if need == have or need in blob:
        return True
    need_parts = [part.strip() for part in need.split("/") if part.strip()]
    if need_parts and all(part in blob for part in need_parts):
        return True
    tokens = _tokens(need)
    if not tokens:
        return False
    hay = blob.lower()
    return all(_token_in(token, hay) for token in tokens)


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-zа-яё]+", text.lower())
    return [word for word in words if word not in _STOP and len(word) > 1]


def _token_in(token: str, hay: str) -> bool:
    variants = _SYN.get(token, (token,))
    return any(variant in hay for variant in variants)
