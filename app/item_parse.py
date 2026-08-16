from __future__ import annotations

import re
from dataclasses import dataclass, field

_SEP = "--------"
_TIER = re.compile(r"\(Tier:\s*(\d+)\)", re.I)
_NUM = re.compile(r"-?\d+(?:\.\d+)?")
_UNID = ("unidentified", "неопознано", "неопознанный", "unidentifiziert", "non identifié", "no identificado")
_RARITY = {
    "normal": "normal",
    "обычный": "normal",
    "magic": "magic",
    "волшебный": "magic",
    "rare": "rare",
    "редкий": "rare",
    "unique": "unique",
    "уникальный": "unique",
}
_SKIP_PREFIXES = (
    "quality:",
    "armour:",
    "armor:",
    "evasion",
    "energy shield:",
    "ward:",
    "physical damage:",
    "elemental damage:",
    "chaos damage:",
    "critical strike",
    "attacks per second:",
    "weapon range:",
    "item class:",
    "rarity:",
    "requirements:",
    "sockets:",
    "item level:",
    "level:",
    "str:",
    "dex:",
    "int:",
    "chance to block",
    "block:",
    "talisman tier:",
    "corrupted",
    "mirrored",
    "split",
    "unidentified",
    "неопознано",
    "неопознанный",
    "note:",
    "flavour",
    "flavor",
)

_MAX = {
    "normal": (0, 0),
    "magic": (1, 1),
    "rare": (3, 3),
    "unique": (0, 0),
}


@dataclass
class ParsedAffix:
    generation: str | None
    tier: int | None
    lines: list[str]
    values: list[int]
    template: str
    crafted: bool = False
    implicit: bool = False


@dataclass
class ParsedItem:
    item_class: str = ""
    rarity: str = ""
    name: str = ""
    identified: bool = True
    item_level: int | None = None
    affixes: list[ParsedAffix] = field(default_factory=list)
    raw: str = ""

    @property
    def prefix_count(self) -> int:
        return sum(1 for row in self.affixes if row.generation == "prefix" and not row.implicit)

    @property
    def suffix_count(self) -> int:
        return sum(1 for row in self.affixes if row.generation == "suffix" and not row.implicit)

    def max_affixes(self) -> tuple[int, int]:
        if self.rarity == "rare" and _is_jewel_class(self.item_class):
            return 2, 2
        return _MAX.get(self.rarity, (3, 3))

    def has_open_prefix(self) -> bool:
        maximum, _ = self.max_affixes()
        return self.prefix_count < maximum

    def has_open_suffix(self) -> bool:
        _, maximum = self.max_affixes()
        return self.suffix_count < maximum

    def explicit_lines(self) -> list[str]:
        lines: list[str] = []
        for row in self.affixes:
            if row.implicit:
                continue
            lines.extend(row.lines or [row.template])
        return lines

    def brief(self) -> str:
        rarity = self.rarity or "?"
        ident = "id" if self.identified else "UNID"
        mods = ", ".join(self.explicit_lines()) or "—"
        return f"{self.name or '?'} | {rarity} | {ident} | {mods}"


def to_template(text: str) -> str:
    return _NUM.sub("#", text).strip()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace(" / ", "/")).strip()


def _is_jewel_class(item_class: str) -> bool:
    lowered = (item_class or "").lower()
    return "jewel" in lowered or "самоцвет" in lowered


def parse_item(text: str) -> ParsedItem | None:
    raw = (text or "").replace("\r\n", "\n").strip()
    if not _looks_like_item(raw):
        return None
    lowered = raw.lower()
    item = ParsedItem(raw=raw, identified=not any(marker in lowered for marker in _UNID))
    lines = [line.strip() for line in raw.split("\n")]
    for line in lines:
        key, value = _meta(line)
        if key == "class":
            item.item_class = value
        elif key == "rarity":
            item.rarity = _RARITY.get(value.lower(), value.lower())
        elif key == "ilvl":
            try:
                item.item_level = int(_NUM.search(value).group())  # type: ignore[union-attr]
            except (AttributeError, ValueError):
                pass
    names = []
    for line in lines[1:]:
        if line == _SEP:
            break
        key, _value = _meta(line)
        if key in {"class", "rarity"}:
            continue
        if line:
            names.append(line)
    item.name = " / ".join(names[:2])

    current: dict | None = None
    body = False
    grouped = False
    for line in lines:
        key, _value = _meta(line)
        if key == "ilvl":
            body = True
            continue
        if not body:
            continue
        if line == _SEP or not line:
            if current:
                item.affixes.append(_finish(current))
                current = None
            continue
        header = _parse_header(line)
        if header:
            grouped = True
            if current:
                item.affixes.append(_finish(current))
            current = header
            continue
        if _should_skip(line):
            continue
        if current is None:
            current = {"generation": None, "tier": None, "lines": [], "crafted": False, "implicit": False}
        elif not grouped and current.get("lines") and _looks_like_mod(line):
            item.affixes.append(_finish(current))
            current = {"generation": None, "tier": None, "lines": [], "crafted": False, "implicit": False}
        current["lines"].append(line)
    if current and current.get("lines"):
        item.affixes.append(_finish(current))

    if not any(row.generation for row in item.affixes):
        _guess_generation(item)
    return item


def _looks_like_item(raw: str) -> bool:
    return any(
        marker in raw
        for marker in ("Item Class:", "Rarity:", "Класс предмета:", "Редкость:")
    )


def _meta(line: str) -> tuple[str | None, str]:
    prefixes = (
        ("class", ("Item Class:", "Класс предмета:")),
        ("rarity", ("Rarity:", "Редкость:")),
        ("ilvl", ("Item Level:", "Уровень предмета:")),
    )
    for key, labels in prefixes:
        for label in labels:
            if line.startswith(label):
                return key, line.split(":", 1)[1].strip()
    return None, ""


def _looks_like_mod(line: str) -> bool:
    return bool(_NUM.search(line) or line[:1] in {"+", "-"})


def _parse_header(line: str) -> dict | None:
    if not line.startswith("{"):
        return None
    lower = line.lower()
    if not any(
        token in lower
        for token in ("modifier", "модификатор", "prefix", "suffix", "префикс", "суффикс")
    ):
        return None
    generation = None
    if "prefix" in lower or "префикс" in lower or "präfix" in lower or "préfixe" in lower:
        generation = "prefix"
    elif "suffix" in lower or "суффикс" in lower or "suffixe" in lower:
        generation = "suffix"
    tier = None
    match = _TIER.search(line)
    if match:
        tier = int(match.group(1))
    return {
        "generation": generation,
        "tier": tier,
        "lines": [],
        "crafted": "crafted" in lower,
        "implicit": "implicit" in lower or "enchant" in lower,
    }


def _finish(current: dict) -> ParsedAffix:
    lines = [line for line in current["lines"] if line]
    values: list[int] = []
    for line in lines:
        for match in _NUM.finditer(line):
            try:
                values.append(int(float(match.group())))
            except ValueError:
                continue
    return ParsedAffix(
        generation=current.get("generation"),
        tier=current.get("tier"),
        lines=lines,
        values=values,
        template=" / ".join(to_template(line) for line in lines),
        crafted=bool(current.get("crafted")),
        implicit=bool(current.get("implicit")),
    )


def _should_skip(line: str) -> bool:
    lower = line.lower()
    return any(lower.startswith(prefix) or lower == prefix.rstrip(":") for prefix in _SKIP_PREFIXES)


def _guess_generation(item: ParsedItem) -> None:
    prefixes, suffixes = magic_slot_counts(item) if item.rarity == "magic" else (0, 0)
    explicits = [row for row in item.affixes if not row.implicit]
    if item.rarity == "magic" and len(explicits) == 1:
        explicits[0].generation = "prefix" if prefixes else "suffix"


def magic_slot_counts(item: ParsedItem) -> tuple[int, int]:
    """How many prefix/suffix slots a magic item is using."""
    explicits = [row for row in item.affixes if not row.implicit]
    tagged_p = sum(1 for row in explicits if row.generation == "prefix")
    tagged_s = sum(1 for row in explicits if row.generation == "suffix")
    if tagged_p or tagged_s:
        return tagged_p, tagged_s
    if item.rarity != "magic":
        return item.prefix_count, item.suffix_count
    if len(explicits) >= 2:
        return 1, 1
    if len(explicits) == 0:
        return 0, 0
    if re.search(r"\sof\s", item.name or "", re.I):
        return 0, 1
    return 1, 0


def has_open_prefix(item: ParsedItem) -> bool:
    maximum, _ = item.max_affixes()
    if item.rarity == "magic":
        prefixes, _ = magic_slot_counts(item)
        return prefixes < maximum
    tagged = any(row.generation for row in item.affixes if not row.implicit)
    if tagged:
        return item.prefix_count < maximum
    explicits = [row for row in item.affixes if not row.implicit]
    return len(explicits) < (maximum + item.max_affixes()[1]) and item.prefix_count < maximum


def has_open_suffix(item: ParsedItem) -> bool:
    _, maximum = item.max_affixes()
    if item.rarity == "magic":
        _, suffixes = magic_slot_counts(item)
        return suffixes < maximum
    tagged = any(row.generation for row in item.affixes if not row.implicit)
    if tagged:
        return item.suffix_count < maximum
    prefix_max, suffix_max = item.max_affixes()
    explicits = [row for row in item.affixes if not row.implicit]
    return len(explicits) < (prefix_max + suffix_max)
