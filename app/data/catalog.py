from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.data.models import CraftScenario, ModRequirement
from app.data.static import (
    CRAFT_TYPES,
    ITEM_TYPE_GROUPS,
    ITEM_TYPE_NAMES,
    ITEM_TYPE_NAMES_RU,
    actions_for_craft_type,
    item_type_label,
)
from app.paths import CATALOG_PATH, SCENARIOS_DIR, ensure_data_dirs


CATALOG_SCHEMA = 5


@dataclass
class GameCatalog:
    patch: str
    fetched_at: str
    source: str
    item_types: list[dict[str, Any]]
    bases: list[dict[str, Any]]
    mod_types: list[dict[str, Any]]
    actions: dict[str, list[dict[str, Any]]]
    craft_types: list[dict[str, Any]]
    schema: int = CATALOG_SCHEMA

    def item_type(self, item_class: str) -> dict[str, Any] | None:
        return next((row for row in self.item_types if row["id"] == item_class), None)

    def item_type_name(self, item_class: str) -> str:
        row = self.item_type(item_class)
        if row:
            return item_type_label(row["id"])
        return item_type_label(item_class)

    def craft_type(self, craft_type_id: str) -> dict[str, Any] | None:
        return next((row for row in self.craft_types if row["id"] == craft_type_id), None)

    def actions_for(self, craft_type_id: str) -> list[dict[str, Any]]:
        return list(self.actions.get(craft_type_id) or actions_for_craft_type(craft_type_id))

    def action(self, action_id: str) -> dict[str, Any] | None:
        for group in self.actions.values():
            for row in group:
                if row["id"] == action_id:
                    return row
        return None

    def action_name(self, action_id: str) -> str:
        from app.i18n import t

        row = self.action(action_id)
        if not row:
            return t(f"action.{action_id}", default=action_id)
        return t(f"action.{action_id}", default=row.get("name") or action_id)

    def craft_type_name(self, craft_type_id: str) -> str:
        from app.i18n import t

        return t(f"craft.{craft_type_id}", default=craft_type_id)

    def mod_type(self, mod_type_id: str) -> dict[str, Any] | None:
        return next((row for row in self.mod_types if row["id"] == mod_type_id), None)

    def tiers_for(self, mod_type_id: str, item_class: str) -> list[dict[str, Any]]:
        row = self.mod_type(mod_type_id)
        if not row:
            return []
        return class_tiers(row, item_class)

    def mod_tier(
        self,
        mod_type_id: str,
        tier: int | None,
        item_class: str | None = None,
    ) -> dict[str, Any] | None:
        if tier is None:
            return None
        if item_class:
            tiers = self.tiers_for(mod_type_id, item_class)
        else:
            row = self.mod_type(mod_type_id)
            tiers = (row or {}).get("tiers") or []
        return next((item for item in tiers if item.get("tier") == tier), None)

    def mod_types_for(self, item_class: str, generation: str | None = None) -> list[dict[str, Any]]:
        result = []
        for row in self.mod_types:
            if item_class not in row.get("item_classes", []):
                continue
            if generation and generation != "any" and row.get("generation") != generation:
                continue
            tiers = class_tiers(row, item_class)
            if not tiers:
                continue
            result.append({**row, "tiers": tiers})
        result.sort(key=lambda row: row.get("name", ""))
        return result

    def generation_pool_weight(self, item_class: str, generation: str) -> int:
        total = 0
        for row in self.mod_types_for(item_class, generation):
            for tier in row.get("tiers") or []:
                total += int(tier.get("weight") or 0)
        return total

    def requirement_weight(self, req: ModRequirement, item_class: str) -> int:
        if req.tier is None:
            return sum(int(tier.get("weight") or 0) for tier in self.tiers_for(req.mod_type_id, item_class))
        if req.weight is not None:
            return int(req.weight)
        tier = self.mod_tier(req.mod_type_id, req.tier, item_class)
        return int((tier or {}).get("weight") or 0)

    def sync_requirement(self, req: ModRequirement, item_class: str) -> None:
        tiers = self.tiers_for(req.mod_type_id, item_class)
        if not tiers:
            return
        for tier in tiers:
            if tier.get("min") == req.value_min and tier.get("max") == req.value_max:
                req.tier = tier.get("tier")
                req.weight = tier.get("weight")
                return
        if req.tier is None:
            return
        tier = next((row for row in tiers if row.get("tier") == req.tier), None)
        if not tier:
            return
        req.value_min = tier.get("min")
        req.value_max = tier.get("max")
        req.weight = tier.get("weight")

    def sync_scenario(self, scenario: CraftScenario) -> None:
        item_class = scenario.item_type
        if not item_class:
            return
        for step in scenario.steps:
            for req in step.condition.mods:
                self.sync_requirement(req, item_class)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "patch": self.patch,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "item_types": self.item_types,
            "bases": self.bases,
            "mod_types": self.mod_types,
            "actions": self.actions,
            "craft_types": self.craft_types,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameCatalog:
        return cls(
            schema=int(data.get("schema") or 1),
            patch=data.get("patch", "unknown"),
            fetched_at=data.get("fetched_at", ""),
            source=data.get("source", ""),
            item_types=data.get("item_types", []),
            bases=data.get("bases", []),
            mod_types=data.get("mod_types", []),
            actions=data.get("actions")
            or {
                "basic_currency": actions_for_craft_type("basic_currency"),
                "harvest": actions_for_craft_type("harvest"),
            },
            craft_types=data.get("craft_types") or CRAFT_TYPES,
        )


def catalog_is_current(path: Path | None = None) -> bool:
    target = path or CATALOG_PATH
    if not target.is_file():
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    types = data.get("mod_types") or []
    first = types[0] if types else {}
    return data.get("schema") == CATALOG_SCHEMA and bool(types) and "variants" in first


def catalog_exists() -> bool:
    return CATALOG_PATH.is_file()


def load_catalog(path: Path | None = None) -> GameCatalog:
    target = path or CATALOG_PATH
    with target.open(encoding="utf-8") as handle:
        return GameCatalog.from_dict(json.load(handle))


def save_catalog(catalog: GameCatalog, path: Path | None = None) -> Path:
    ensure_data_dirs()
    target = path or CATALOG_PATH
    target.write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def list_scenarios() -> list[CraftScenario]:
    ensure_data_dirs()
    scenarios: list[CraftScenario] = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                scenarios.append(CraftScenario.from_dict(json.load(handle)))
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            continue
    scenarios.sort(key=lambda row: row.created_at, reverse=True)
    return scenarios


def save_scenario(scenario: CraftScenario) -> Path:
    ensure_data_dirs()
    path = SCENARIOS_DIR / f"{scenario.id}.json"
    path.write_text(
        json.dumps(scenario.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def delete_scenario(scenario_id: str) -> bool:
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.is_file():
        return False
    try:
        path.unlink()
    except OSError:
        return False
    return True


def grouped_item_types(catalog: GameCatalog) -> list[tuple[str, list[dict[str, Any]]]]:
    by_id = {row["id"]: row for row in catalog.item_types}
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    for group in ITEM_TYPE_GROUPS:
        rows = [by_id[cls] for cls in group["classes"] if cls in by_id]
        if rows:
            groups.append((group["id"], rows))
    return groups


def fallback_item_types() -> list[dict[str, Any]]:
    rows = []
    for group in ITEM_TYPE_GROUPS:
        for item_class in group["classes"]:
            rows.append(
                {
                    "id": item_class,
                    "name": ITEM_TYPE_NAMES.get(item_class, item_class),
                    "name_ru": ITEM_TYPE_NAMES_RU.get(item_class, item_class),
                    "group": group["id"],
                }
            )
    return rows


def class_tiers(row: dict[str, Any], item_class: str) -> list[dict[str, Any]]:
    """Number T1 as the best roll that can actually spawn on this item class."""
    variants = row.get("variants") or []
    if variants:
        matched = [item for item in variants if item_class in (item.get("spawn") or {})]
        matched.sort(
            key=lambda item: (
                -int(item.get("ilvl") or 0),
                -(item.get("max") if item.get("max") is not None else -10**9),
                -(item.get("min") if item.get("min") is not None else -10**9),
                str(item.get("mod_id") or ""),
            )
        )
        tiers = []
        for index, item in enumerate(matched, start=1):
            spawn = item.get("spawn") or {}
            low, high = item.get("min"), item.get("max")
            tiers.append(
                {
                    "tier": index,
                    "ilvl": item.get("ilvl"),
                    "min": low,
                    "max": high,
                    "value": item.get("value") or _format_range(low, high),
                    "weight": spawn.get(item_class),
                    "mod_id": item.get("mod_id"),
                }
            )
        return tiers
    return list(row.get("tiers") or [])


def _format_range(low: int | None, high: int | None) -> str:
    if low is None and high is None:
        return ""
    if low is None:
        return str(high)
    if high is None or low == high:
        return str(low)
    return f"{low}-{high}"


ProgressCallback = Callable[[str], None]
