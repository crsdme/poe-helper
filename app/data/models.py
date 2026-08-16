from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ModRequirement:
    mod_type_id: str
    generation: str
    name: str
    tier: int | None = None
    value_min: int | None = None
    value_max: int | None = None
    weight: int | None = None
    need: int = 1
    group: str = ""
    count: int = 1

    def need_value(self) -> int:
        return max(1, int(self.need or 1))

    def group_key(self) -> str:
        return str(self.group or "").strip()

    def count_value(self) -> int:
        return max(1, int(self.count or 1))

    def to_dict(self) -> dict[str, Any]:
        data = {
            "mod_type_id": self.mod_type_id,
            "generation": self.generation,
            "name": self.name,
            "tier": self.tier,
            "value_min": self.value_min,
            "value_max": self.value_max,
            "weight": self.weight,
            "need": self.need_value(),
        }
        key = self.group_key()
        if key:
            data["group"] = key
            data["count"] = self.count_value()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModRequirement:
        return cls(
            mod_type_id=data.get("mod_type_id", ""),
            generation=data.get("generation", "prefix"),
            name=data.get("name", ""),
            tier=data.get("tier"),
            value_min=data.get("value_min"),
            value_max=data.get("value_max"),
            weight=data.get("weight"),
            need=max(1, int(data.get("need") or 1)),
            group=str(data.get("group") or "").strip(),
            count=max(1, int(data.get("count") or 1)),
        )


@dataclass
class Condition:
    kind: str = "missing_mod"
    mods: list[ModRequirement] = field(default_factory=list)
    required_weight: int = 1

    def needs_mods(self) -> bool:
        return self.kind in {"missing_mod", "has_mod"}

    def required_total(self) -> int:
        return max(1, int(self.required_weight or 1))

    def matched_need(self, present_ids: set[str]) -> int:
        total = 0
        grouped: dict[str, list[ModRequirement]] = {}
        for row in self.mods:
            key = row.group_key()
            if key:
                grouped.setdefault(key, []).append(row)
            elif row.mod_type_id in present_ids:
                total += row.need_value()
        for rows in grouped.values():
            count = rows[0].count_value()
            hits = [row for row in rows if row.mod_type_id in present_ids]
            total += sum(row.need_value() for row in hits[:count])
        return total

    def need_satisfied(self, present_ids: set[str]) -> bool:
        return self.matched_need(present_ids) >= self.required_total()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mods": [row.to_dict() for row in self.mods],
            "required_weight": self.required_total(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Condition:
        data = data or {}
        mods = [ModRequirement.from_dict(row) for row in data.get("mods") or []]
        if not mods and data.get("mod_type_id"):
            mods = [
                ModRequirement(
                    mod_type_id=data["mod_type_id"],
                    generation=data.get("generation", "any"),
                    name=data.get("name", ""),
                )
            ]
        by_group: dict[str, list[ModRequirement]] = {}
        for row in mods:
            key = row.group_key()
            if key:
                by_group.setdefault(key, []).append(row)
        for rows in by_group.values():
            count = rows[0].count_value()
            for row in rows:
                row.count = count
        return cls(
            kind=data.get("kind", "missing_mod"),
            mods=mods,
            required_weight=max(1, int(data.get("required_weight") or 1)),
        )


@dataclass
class CraftStep:
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    action_id: str = ""
    condition: Condition = field(default_factory=Condition)
    augment_open: str = "off"

    def fill_affix(self) -> str | None:
        if self.action_id == "alteration" and self.augment_open in {"prefix", "suffix", "any"}:
            return self.augment_open
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_id": self.action_id,
            "condition": self.condition.to_dict(),
            "augment_open": self.augment_open if self.augment_open in {"prefix", "suffix", "any"} else "off",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CraftStep:
        augment = data.get("augment_open") or "off"
        if augment not in {"off", "prefix", "suffix", "any"}:
            augment = "off"
        return cls(
            id=data.get("id") or uuid4().hex[:10],
            action_id=data.get("action_id", ""),
            condition=Condition.from_dict(data.get("condition")),
            augment_open=augment,
        )


@dataclass
class CraftScenario:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = "New scenario"
    item_type: str = ""
    craft_type: str = ""
    steps: list[CraftStep] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "item_type": self.item_type,
            "craft_type": self.craft_type,
            "steps": [step.to_dict() for step in self.steps],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CraftScenario:
        return cls(
            id=data.get("id") or uuid4().hex,
            name=data.get("name", "New scenario"),
            item_type=data.get("item_type", ""),
            craft_type=data.get("craft_type", ""),
            steps=[CraftStep.from_dict(step) for step in data.get("steps", [])],
            created_at=data.get("created_at") or _now_iso(),
        )
