from __future__ import annotations

import json
import re
import ssl
import urllib.request
from datetime import datetime, timezone
from typing import Any

from app.data.catalog import (
    GameCatalog,
    ProgressCallback,
    catalog_is_current,
    fallback_item_types,
    load_catalog,
    save_catalog,
)
from app.data.static import (
    CRAFT_TYPES,
    CRAFTABLE_CLASSES,
    ITEM_TYPE_GROUPS,
    ITEM_TYPE_NAMES,
    ITEM_TYPE_NAMES_RU,
    actions_for_craft_type,
)

REPOE_BASE = "https://repoe-fork.github.io"
COE_URL = "https://beta.craftofexile.com/?game=poe1"
USER_AGENT = "poe-helper/0.2 (local cache builder)"
TIMEOUT = 120

_GROUP_BY_CLASS = {
    item_class: group["id"]
    for group in ITEM_TYPE_GROUPS
    for item_class in group["classes"]
}

_BASE_DOMAINS = {
    "item",
    "misc",
    "abyss_jewel",
    "affliction_jewel",
    "heist_npc",
    "heist_trinket",
    "heist_area",
}
_MOD_DOMAINS_FOR: dict[str, set[str]] = {
    "Jewel": {"misc"},
    "AbyssJewel": {"abyss_jewel"},
    "ClusterJewel": {"affliction_jewel"},
    "HeistEquipmentReward": {"heist_npc"},
    "HeistEquipmentUtility": {"heist_npc"},
    "HeistEquipmentWeapon": {"heist_npc"},
    "HeistEquipmentTool": {"heist_npc"},
    "Trinket": {"heist_trinket"},
    "HeistContract": {"heist_area"},
}


def ensure_catalog(
    force: bool = False,
    progress: ProgressCallback | None = None,
) -> GameCatalog:
    """Вернуть локальный каталог. Сеть нужна только при первом запуске или force=True."""
    if catalog_is_current() and not force:
        _report(progress, "fetch.cache")
        return load_catalog()
    catalog = fetch_and_build(progress=progress)
    save_catalog(catalog)
    return catalog


def fetch_and_build(progress: ProgressCallback | None = None) -> GameCatalog:
    _report(progress, "fetch.patch")
    patch = _fetch_patch()

    _report(progress, "fetch.bases")
    bases_raw = _get_json(f"{REPOE_BASE}/base_items.min.json")

    _report(progress, "fetch.mods")
    mods_raw = _get_json(f"{REPOE_BASE}/mods.min.json")

    _report(progress, "fetch.stats")
    translations_raw = _get_json(f"{REPOE_BASE}/stat_translations.min.json")

    _report(progress, "fetch.build")
    item_types = _build_item_types(bases_raw)
    bases = _build_bases(bases_raw)
    class_tags = _class_tags(bases_raw)
    translations = _index_translations(translations_raw)
    mod_types = _build_mod_types(mods_raw, translations, class_tags)

    return GameCatalog(
        patch=patch,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="RePoE + Craft of Exile patch metadata",
        item_types=item_types,
        bases=bases,
        mod_types=mod_types,
        actions={
            "basic_currency": actions_for_craft_type("basic_currency"),
            "harvest": actions_for_craft_type("harvest"),
        },
        craft_types=CRAFT_TYPES,
    )


def _report(progress: ProgressCallback | None, message: str) -> None:
    if progress:
        progress(message)


def _fetch_patch() -> str:
    try:
        html = _get_text(COE_URL)
        match = re.search(r'"patch"\s*:\s*"([0-9.]+)"', html)
        if match:
            return match.group(1)
    except OSError:
        pass
    return "3.29.3.1.2"


def _get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=context) as response:
        return response.read().decode("utf-8")


def _get_json(url: str) -> Any:
    return json.loads(_get_text(url))


def _is_cluster_base(row: dict[str, Any]) -> bool:
    if row.get("domain") == "affliction_jewel":
        return True
    name = (row.get("name") or "").lower()
    if "cluster jewel" in name:
        return True
    return any(
        str(tag).startswith("expansion_jewel") or "cluster_jewel" in str(tag)
        for tag in (row.get("tags") or [])
    )


def _canonical_item_class(row: dict[str, Any]) -> str | None:
    if _is_cluster_base(row):
        return "ClusterJewel"
    item_class = row.get("item_class")
    if item_class in CRAFTABLE_CLASSES:
        return item_class
    return None


def _usable_base(row: dict[str, Any]) -> bool:
    if row.get("release_state") != "released":
        return False
    if row.get("domain") not in _BASE_DOMAINS:
        return False
    name = (row.get("name") or "").strip()
    if not name or name.startswith("[") or "UNUSED" in name.upper():
        return False
    return True


def _build_item_types(bases_raw: dict[str, Any]) -> list[dict[str, Any]]:
    present = {
        _canonical_item_class(row)
        for row in bases_raw.values()
        if _usable_base(row) and _canonical_item_class(row)
    }
    rows = []
    for item_class in CRAFTABLE_CLASSES:
        if item_class not in present:
            continue
        rows.append(
            {
                "id": item_class,
                "name": ITEM_TYPE_NAMES.get(item_class, item_class),
                "name_ru": ITEM_TYPE_NAMES_RU.get(item_class, item_class),
                "group": _GROUP_BY_CLASS.get(item_class, "other"),
            }
        )
    return rows or fallback_item_types()


def _build_bases(bases_raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for metadata_id, row in bases_raw.items():
        if not _usable_base(row):
            continue
        item_class = _canonical_item_class(row)
        if not item_class:
            continue
        name = (row.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "id": metadata_id,
                "name": name,
                "item_class": item_class,
                "drop_level": row.get("drop_level", 1),
            }
        )
    rows.sort(key=lambda item: (item["item_class"], item["drop_level"], item["name"]))
    return rows


def _class_tags(bases_raw: dict[str, Any]) -> dict[str, set[str]]:
    tags: dict[str, set[str]] = {item_class: set() for item_class in CRAFTABLE_CLASSES}
    for row in bases_raw.values():
        if not _usable_base(row):
            continue
        item_class = _canonical_item_class(row)
        if item_class not in tags:
            continue
        tags[item_class].update(row.get("tags") or [])
    return tags


def _index_translations(translations_raw: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in translations_raw:
        for stat_id in row.get("ids") or []:
            index[stat_id] = row
    return index


def _translate_stat(stat_id: str, translations: dict[str, dict[str, Any]]) -> str:
    row = translations.get(stat_id)
    if not row:
        return stat_id
    for trade in row.get("trade_stats") or []:
        if trade.get("type") == "explicit" and trade.get("text"):
            return trade["text"]
    english = row.get("English") or []
    if english:
        text = english[0].get("string") or stat_id
        return text.replace("{0}", "#").replace("{1}", "#")
    return stat_id


def _spawn_weight(mod: dict[str, Any], class_tags: set[str]) -> int:
    """First matching spawn-weight tag wins, same as in-game."""
    for item in mod.get("spawn_weights") or []:
        tag = item.get("tag")
        if tag in class_tags or tag == "default":
            return int(item.get("weight") or 0)
    return 0


def _mod_domains_for(item_class: str) -> set[str]:
    return _MOD_DOMAINS_FOR.get(item_class, {"item"})


def _spawn_weight_for(mod: dict[str, Any], item_class: str, class_tags: set[str]) -> int:
    if mod.get("domain") not in _mod_domains_for(item_class):
        return 0
    if item_class == "ClusterJewel":
        weights = [int(item.get("weight") or 0) for item in (mod.get("spawn_weights") or [])]
        return max(weights, default=0)
    return _spawn_weight(mod, class_tags)


def _stat_range(stats: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    for stat in stats:
        if "min" in stat or "max" in stat:
            return stat.get("min"), stat.get("max")
    return None, None


def _build_mod_types(
    mods_raw: dict[str, Any],
    translations: dict[str, dict[str, Any]],
    class_tags: dict[str, set[str]],
) -> list[dict[str, Any]]:
    allowed_domains = {domain for domains in _MOD_DOMAINS_FOR.values() for domain in domains}
    allowed_domains.add("item")
    collected: dict[tuple[str, str], dict[str, Any]] = {}
    for mod_id, mod in mods_raw.items():
        if mod.get("domain") not in allowed_domains:
            continue
        generation = mod.get("generation_type")
        if generation not in {"prefix", "suffix"}:
            continue
        if mod.get("is_essence_only"):
            continue
        type_id = mod.get("type")
        if not type_id:
            continue

        spawn = {
            item_class: weight
            for item_class, tags in class_tags.items()
            if (weight := _spawn_weight_for(mod, item_class, tags)) > 0
        }
        if not spawn:
            continue

        key = (type_id, generation)
        stats = mod.get("stats") or []
        names = []
        for stat in stats:
            stat_id = stat.get("id")
            if stat_id:
                names.append(_translate_stat(stat_id, translations))
        display = " / ".join(dict.fromkeys(names)) or type_id
        low, high = _stat_range(stats)

        current = collected.get(key)
        if current is None:
            current = {
                "id": f"{generation}:{type_id}",
                "type": type_id,
                "generation": generation,
                "name": display,
                "item_classes": set(spawn),
                "variants": [],
            }
            collected[key] = current
        else:
            current["item_classes"].update(spawn)
            if display and (not current["name"] or current["name"] == type_id):
                current["name"] = display
        current["variants"].append(
            {
                "mod_id": mod_id,
                "ilvl": int(mod.get("required_level") or 1),
                "min": low,
                "max": high,
                "value": _format_range(low, high),
                "spawn": spawn,
            }
        )

    rows = []
    for row in collected.values():
        rows.append(
            {
                "id": row["id"],
                "type": row["type"],
                "generation": row["generation"],
                "name": row["name"],
                "item_classes": sorted(row["item_classes"]),
                "variants": row["variants"],
            }
        )
    rows.sort(key=lambda item: (item["generation"], item["name"]))
    return rows


def _format_range(low: int | None, high: int | None) -> str:
    if low is None and high is None:
        return ""
    if low is None:
        return str(high)
    if high is None or low == high:
        return str(low)
    return f"{low}-{high}"
