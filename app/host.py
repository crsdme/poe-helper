from __future__ import annotations

import json
import logging
import queue
import threading
import time
from typing import Any

from app import __version__
from app.config import (
    HUD_HEIGHT,
    HUD_WIDTH,
    AppConfig,
    CurrencyTab,
    ItemGrid,
    Rect,
    clamp_speed_ms,
    default_hud_xy,
    load_config,
    save_config,
)
from app.craft_log import delete_session, grouped_sessions, load_session
from app.craft_runner import CraftRunner, validate_ready
from app.data.catalog import GameCatalog, delete_scenario, grouped_item_types, list_scenarios, save_scenario
from app.data.currency_layout import SLOTS, SLOTS_BY_KEY, apply_layout, default_slot_assignments
from app.data.fetcher import ensure_catalog
from app.data.models import Condition, CraftScenario, CraftStep, ModRequirement
from app.data.static import action_label, item_type_label
from app.data.targets import BUTTONS, mappable_currencies
from app.debug import dbg
from app.i18n import LANGUAGES, language, set_language, t
from app.i18n.strings import STRINGS
from app.input_win import HotkeyListener, allow_foreground, focus_game, normalize_hotkey, release_modifiers
from app.item_icons import action_icon, asset_rel
from app.overlay import CraftHud, GridOverlay, PositionOverlay
from app.paths import stash_image_path
from app.settings import save_settings
from app.tk_loop import TkLoop

logger = logging.getLogger("poe_helper")

KIND_KEYS = ["missing_mod", "has_mod", "open_prefix", "open_suffix", "once"]
HEIST_SPEED = [
    ("click_delay_sec", "heist.click_delay"),
    ("between_contracts_sec", "heist.between"),
    ("poll_interval_sec", "heist.poll"),
    ("modal_timeout_sec", "heist.modal_open"),
    ("modal_close_timeout_sec", "heist.modal_close"),
    ("confirm_delay_sec", "heist.confirm_delay"),
    ("blueprint_open_settle_sec", "heist.bp_settle"),
    ("rogue_click_settle_sec", "heist.rogue_settle"),
]
HEIST_PRESETS = {
    "slow": {
        "click_delay_sec": 0.15,
        "between_contracts_sec": 0.2,
        "poll_interval_sec": 0.05,
        "modal_timeout_sec": 2.0,
        "modal_close_timeout_sec": 1.5,
        "confirm_delay_sec": 0.3,
        "blueprint_open_settle_sec": 0.35,
        "rogue_click_settle_sec": 0.25,
    },
    "normal": {
        "click_delay_sec": 0.1,
        "between_contracts_sec": 0.1,
        "poll_interval_sec": 0.03,
        "modal_timeout_sec": 1.5,
        "modal_close_timeout_sec": 1.0,
        "confirm_delay_sec": 0.18,
        "blueprint_open_settle_sec": 0.2,
        "rogue_click_settle_sec": 0.18,
    },
    "fast": {
        "click_delay_sec": 0.05,
        "between_contracts_sec": 0.05,
        "poll_interval_sec": 0.02,
        "modal_timeout_sec": 1.2,
        "modal_close_timeout_sec": 0.8,
        "confirm_delay_sec": 0.12,
        "blueprint_open_settle_sec": 0.12,
        "rogue_click_settle_sec": 0.12,
    },
}
REVEAL_SPEED = [
    ("click_delay_sec", "heist.click_delay"),
    ("open_settle_sec", "reveal.open_settle"),
    ("reveal_settle_sec", "reveal.wing_settle"),
    ("between_blueprints_sec", "reveal.between"),
]
REVEAL_PRESETS = {
    "slow": {
        "click_delay_sec": 0.15,
        "open_settle_sec": 0.5,
        "reveal_settle_sec": 0.4,
        "between_blueprints_sec": 0.25,
    },
    "normal": {
        "click_delay_sec": 0.1,
        "open_settle_sec": 0.35,
        "reveal_settle_sec": 0.28,
        "between_blueprints_sec": 0.15,
    },
    "fast": {
        "click_delay_sec": 0.05,
        "open_settle_sec": 0.22,
        "reveal_settle_sec": 0.18,
        "between_blueprints_sec": 0.08,
    },
}


def _strings() -> dict[str, str]:
    lang = language()
    out: dict[str, str] = {}
    for key, pack in STRINGS.items():
        out[key] = pack.get(lang) or pack.get("en") or key
    return out


def _fmt_rect(rect: Rect | None) -> str:
    if not rect:
        return t("settings.not_set")
    x, y = rect.click
    return f"{x}, {y}  ·  {rect.w}×{rect.h}"


def _fmt_grid(grid: ItemGrid | None) -> str:
    if not grid:
        return t("settings.not_set")
    return f"{grid.cols}×{grid.rows}  ·  {grid.x}, {grid.y}  ·  {grid.w}×{grid.h}"


def _fmt_value(low: int | None, high: int | None) -> str:
    if low is None and high is None:
        return ""
    if low is None:
        return str(high)
    if high is None or low == high:
        return str(low)
    return f"{low}-{high}"


def _hotkey_from_capture(raw: str) -> str | None:
    text = (raw or "").strip()
    if not text:
        return ""
    name = normalize_hotkey(text)
    return name or None


def _saved_hotkey(raw, default: str = "") -> str:
    if raw is None:
        text = default
    else:
        text = str(raw).strip()
    return text.upper() if text else ""


class AppHost:
    def __init__(self, tk_loop: TkLoop) -> None:
        self._tk = tk_loop
        self._window = None
        self.catalog: GameCatalog | None = None
        self._current = "home"
        self._loading = False
        self._status = t("status.loading")
        self.selected_scenario_id: str | None = load_config().last_scenario_id or None
        self._prefer_chain = False
        self._runner: CraftRunner | None = None
        self._hotkeys = HotkeyListener()
        self._hud: CraftHud | None = None
        self._overlay = None
        self._heist_thread: threading.Thread | None = None
        self._heist_stop = threading.Event()
        self._reveal_thread: threading.Thread | None = None
        self._reveal_stop = threading.Event()
        self._craft_lines: list[str] = []
        self._craft_status = t("run.idle")
        self._heist_lines: list[str] = []
        self._reveal_lines: list[str] = []
        self._craft_q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._wizard: CraftScenario | None = None
        self._wizard_step = 1
        self._poll_stop = threading.Event()

    def attach(self, window) -> None:
        self._window = window

    def on_started(self) -> None:
        self.refresh_hotkeys()
        self.reload_catalog(force=False)
        threading.Thread(target=self._poll_craft_loop, name="craft-poll", daemon=True).start()

    def emit(self, kind: str, payload: Any = None) -> None:
        window = self._window
        if window is None:
            return
        blob = json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False)
        try:
            window.evaluate_js(f"window.app && window.app.onEvent({blob})")
        except Exception:
            pass

    def after(self, ms: int, fn) -> None:
        self._tk.after(ms, fn)

    def hide_window(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.minimize()
        except Exception:
            pass

    def show_window(self) -> None:
        window = self._window
        if window is None:
            return
        try:
            window.restore()
            window.show()
        except Exception:
            pass

    def toast(self, message: str, kind: str = "error", ms: int = 4500) -> None:
        self.emit("toast", {"message": message, "kind": kind, "ms": ms})

    def set_status(self, message: str) -> None:
        self._status = message
        self.emit("status", self.shell_payload())

    def shell_payload(self) -> dict[str, Any]:
        catalog = self.catalog
        if catalog:
            meta = catalog.patch
            meta_kind = "ok"
        elif self._loading:
            meta = t("status.loading")
            meta_kind = "load"
        else:
            meta = t("header.error")
            meta_kind = "error"
        return {
            "title": t("app.name"),
            "subtitle": t("app.subtitle"),
            "status": self._status,
            "version": f"v{__version__}",
            "language": language(),
            "languages": [{"id": code, "label": label} for code, label in LANGUAGES],
            "meta": meta,
            "meta_kind": meta_kind,
            "strings": _strings(),
            "icon": "../assets/system/icon.png",
        }

    def screen_payload(self) -> dict[str, Any]:
        builders = {
            "home": self._home,
            "wizard": self._wizard_dto,
            "scenarios": self._scenarios,
            "settings": self._settings,
            "run": self._run,
            "logs": self._logs,
            "stats": self._stats,
            "heist": self._heist,
            "reveal": self._reveal,
        }
        build = builders.get(self._current, self._home)
        data = build()
        data["screen"] = self._current
        data["shell"] = self.shell_payload()
        return data

    def navigate(self, name: str, scenario_id: str | None = None, prefer_chain: bool = False) -> dict[str, Any]:
        if name in {"wizard", "run"} and not self.catalog:
            self.toast(t("status.wait"))
            return self.screen_payload()
        if name != "wizard":
            self._wizard = None
        if name == "run":
            self._prefer_chain = bool(prefer_chain)
            if scenario_id:
                self.selected_scenario_id = scenario_id
                save_settings({"last_scenario_id": scenario_id})
        if name == "wizard":
            self._open_wizard(scenario_id)
        self._current = name
        return self.screen_payload()

    def set_language(self, code: str) -> dict[str, Any]:
        if code == language():
            return self.screen_payload()
        set_language(code)
        save_settings({"language": code})
        if self.catalog:
            self._status = t("status.ready", patch=self.catalog.patch, mods=len(self.catalog.mod_types))
        return self.screen_payload()

    def reload_catalog(self, force: bool = False) -> dict[str, Any]:
        if self._loading:
            return self.screen_payload()
        self._loading = True
        if force:
            self.catalog = None
        self.set_status(t("status.loading"))

        def work() -> None:
            try:
                catalog = ensure_catalog(
                    force=force,
                    progress=lambda key: self.set_status(t(key)),
                )
                self.catalog = catalog
                self._loading = False
                self.set_status(t("status.ready", patch=catalog.patch, mods=len(catalog.mod_types)))
                self.emit("screen", self.screen_payload())
            except Exception as exc:
                logger.exception("catalog load failed")
                self._loading = False
                self.set_status(t("status.error", details=str(exc)))
                self.emit("screen", self.screen_payload())

        threading.Thread(target=work, daemon=True).start()
        return self.screen_payload()

    def _home(self) -> dict[str, Any]:
        config = load_config()
        count = len(list_scenarios())
        ready = self.catalog is not None
        return {
            "ready": ready,
            "loading": self._loading,
            "hint": t("home.hint") if ready else t("home.hint_loading"),
            "scenario_count": count,
            "hotkeys": {
                "start": config.hotkey_start,
                "stop": config.hotkey_stop,
                "chain": config.hotkey_chain,
            },
        }

    def _open_wizard(self, scenario_id: str | None) -> None:
        scenario = None
        if scenario_id:
            scenario = next((row for row in list_scenarios() if row.id == scenario_id), None)
        self._wizard = scenario or CraftScenario(name=t("scenario.default"))
        if scenario and self.catalog:
            self.catalog.sync_scenario(self._wizard)
        self._wizard_step = 3 if scenario and scenario.steps else 1

    def _wizard_dto(self) -> dict[str, Any]:
        scenario = self._wizard or CraftScenario(name=t("scenario.default"))
        catalog = self.catalog
        item_groups = []
        if catalog:
            for group_id, rows in grouped_item_types(catalog):
                item_groups.append(
                    {
                        "id": group_id,
                        "label": t(f"group.{group_id}"),
                        "items": [
                            {
                                "id": row["id"],
                                "name": t(f"item.{row['id']}", default=row["name"]),
                                "sub": row["name"],
                                "icon": asset_rel(row["id"]),
                            }
                            for row in rows
                        ],
                    }
                )
        crafts = []
        if catalog:
            for craft in catalog.craft_types:
                crafts.append(
                    {
                        "id": craft["id"],
                        "name": t(f"craft.{craft['id']}"),
                        "desc": t(f"craft.{craft['id']}.desc"),
                        "icon": asset_rel(craft["id"], "craft"),
                    }
                )
        actions = []
        if catalog and scenario.craft_type:
            for row in catalog.actions_for(scenario.craft_type):
                actions.append({"id": row["id"], "name": action_label(row), "icon": action_icon(row["id"])})
        mods = []
        if catalog and scenario.item_type:
            for row in catalog.mod_types_for(scenario.item_type):
                mods.append({"id": row["id"], "name": row["name"], "generation": row.get("generation") or "prefix"})
        steps = []
        for index, step in enumerate(scenario.steps):
            steps.append(self._step_dto(index, step, scenario.item_type))
        item_name = catalog.item_type_name(scenario.item_type) if catalog else item_type_label(scenario.item_type)
        craft_name = catalog.craft_type_name(scenario.craft_type) if catalog else scenario.craft_type
        name = scenario.name
        if self._wizard_step == 4 and (not name or name == t("scenario.default")):
            name = f"{item_type_label(scenario.item_type)} · {craft_name}"
            scenario.name = name
        return {
            "step": self._wizard_step,
            "labels": [t("wizard.step1"), t("wizard.step2"), t("wizard.step3"), t("wizard.step4")],
            "item_type": scenario.item_type,
            "craft_type": scenario.craft_type,
            "name": name,
            "item_name": item_name,
            "craft_name": craft_name,
            "item_icon": asset_rel(scenario.item_type) if scenario.item_type else None,
            "craft_icon": asset_rel(scenario.craft_type, "craft") if scenario.craft_type else None,
            "groups": item_groups,
            "crafts": crafts,
            "actions": actions,
            "mods": mods,
            "kinds": [{"id": key, "name": t(f"cond.{key}")} for key in KIND_KEYS],
            "augments": [
                {"id": "off", "name": t("wizard.augment_off")},
                {"id": "any", "name": t("wizard.augment_any"), "icon": action_icon("augmentation")},
                {"id": "prefix", "name": t("wizard.augment_prefix"), "icon": action_icon("augmentation")},
                {"id": "suffix", "name": t("wizard.augment_suffix"), "icon": action_icon("augmentation")},
            ],
            "steps": steps,
            "summary": [
                {"text": self._describe_step(step), "icon": action_icon(step.action_id)}
                for step in scenario.steps
            ],
        }

    def _step_dto(self, index: int, step: CraftStep, item_class: str) -> dict[str, Any]:
        catalog = self.catalog
        rows = []
        for req in step.condition.mods:
            tiers = [{"id": "any", "name": t("table.any_tier")}]
            if catalog:
                for tier in catalog.tiers_for(req.mod_type_id, item_class):
                    tiers.append({"id": str(tier["tier"]), "name": f"T{tier['tier']}"})
            rows.append(
                {
                    "mod_type_id": req.mod_type_id,
                    "name": req.name,
                    "generation": req.generation,
                    "tier": "" if req.tier is None else str(req.tier),
                    "value": _fmt_value(req.value_min, req.value_max),
                    "need": req.need_value(),
                    "group": req.group_key(),
                    "count": req.count_value() if req.group_key() else "",
                    "tiers": tiers,
                }
            )
        odds = []
        if catalog and item_class and step.condition.needs_mods():
            pools = {
                "prefix": catalog.generation_pool_weight(item_class, "prefix"),
                "suffix": catalog.generation_pool_weight(item_class, "suffix"),
            }
            for req in step.condition.mods:
                weight = catalog.requirement_weight(req, item_class)
                pool = pools.get(req.generation) or 0
                chance = (100.0 * weight / pool) if pool and weight else 0.0
                odds.append(
                    {
                        "name": req.name,
                        "generation": req.generation,
                        "weight": weight,
                        "chance": chance,
                    }
                )
        return {
            "index": index,
            "action_id": step.action_id,
            "kind": step.condition.kind,
            "needs_mods": step.condition.needs_mods(),
            "required": step.condition.required_total(),
            "augment": step.augment_open if step.augment_open in {"prefix", "suffix", "any"} else "off",
            "show_augment": step.action_id == "alteration",
            "mods": rows,
            "odds": odds,
        }

    def _describe_step(self, step: CraftStep) -> str:
        catalog = self.catalog
        action = catalog.action_name(step.action_id) if catalog else step.action_id
        cond = step.condition
        if cond.kind == "once":
            text = t("desc.once", action=action)
        elif cond.kind == "open_prefix":
            text = t("desc.open_prefix", action=action)
        elif cond.kind == "open_suffix":
            text = t("desc.open_suffix", action=action)
        else:
            parts = []
            for req in cond.mods:
                affix = t("table.prefix_short") if req.generation == "prefix" else t("table.suffix_short")
                tier = f" T{req.tier}" if req.tier else ""
                value = ""
                if req.value_min is not None and req.value_max is not None:
                    value = f" {req.value_min}-{req.value_max}" if req.value_min != req.value_max else f" {req.value_min}"
                need = f" ×{req.need_value()}"
                group = f" [{req.group_key()}×{req.count_value()}]" if req.group_key() else ""
                parts.append(f"[{affix}] {req.name}{tier}{value}{need}{group}")
            mods = ", ".join(parts) or t("desc.mod_none")
            key = "desc.missing_need" if cond.kind == "missing_mod" else "desc.has_need"
            text = t(key, action=action, mods=mods, need=cond.required_total())
        if step.augment_open == "any":
            return f"{text}  ·  {t('desc.augment_any')}"
        if step.augment_open == "prefix":
            return f"{text}  ·  {t('desc.augment_prefix')}"
        if step.augment_open == "suffix":
            return f"{text}  ·  {t('desc.augment_suffix')}"
        return text

    def wizard_goto(self, direction: str) -> dict[str, Any]:
        if direction == "back":
            if self._wizard_step <= 1:
                return self.navigate("home")
            self._wizard_step -= 1
            return self.screen_payload()
        error = self._wizard_validate()
        if error:
            self.toast(error)
            return self.screen_payload()
        self._wizard_step = min(4, self._wizard_step + 1)
        return self.screen_payload()

    def _wizard_validate(self) -> str | None:
        scenario = self._wizard
        if scenario is None:
            return t("validate.item")
        if self._wizard_step == 1 and not scenario.item_type:
            return t("validate.item")
        if self._wizard_step == 2 and not scenario.craft_type:
            return t("validate.craft")
        if self._wizard_step == 3:
            if not scenario.steps:
                return t("validate.steps")
            for index, step in enumerate(scenario.steps, start=1):
                if not step.action_id:
                    return t("validate.action", n=index)
                if step.condition.needs_mods() and not step.condition.mods:
                    return t("validate.mods", n=index)
        return None

    def wizard_select_item(self, item_id: str) -> dict[str, Any]:
        if self._wizard:
            self._wizard.item_type = item_id
            if self.catalog:
                self.set_status(t("status.item", name=self.catalog.item_type_name(item_id)))
            self._wizard_step = 2
        return self.screen_payload()

    def wizard_select_craft(self, craft_id: str) -> dict[str, Any]:
        if self._wizard and self._wizard.craft_type != craft_id:
            self._wizard.craft_type = craft_id
            self._wizard.steps = []
            if self.catalog:
                self.set_status(t("status.method", name=self.catalog.craft_type_name(craft_id)))
        elif self._wizard:
            self._wizard.craft_type = craft_id
        if self._wizard and self._wizard.craft_type:
            self._wizard_step = 3
        return self.screen_payload()

    def wizard_add_step(self) -> dict[str, Any]:
        catalog = self.catalog
        scenario = self._wizard
        if not catalog or not scenario:
            self.toast(t("status.wait"))
            return self.screen_payload()
        actions = catalog.actions_for(scenario.craft_type)
        scenario.steps.append(
            CraftStep(
                action_id=actions[0]["id"] if actions else "",
                condition=Condition(kind="missing_mod"),
            )
        )
        return self.screen_payload()

    def wizard_remove_step(self, index: int) -> dict[str, Any]:
        scenario = self._wizard
        if scenario and 0 <= int(index) < len(scenario.steps):
            scenario.steps.pop(int(index))
        return self.screen_payload()

    def wizard_patch_step(self, index: int, patch: dict) -> dict[str, Any]:
        scenario = self._wizard
        if not scenario or not (0 <= int(index) < len(scenario.steps)):
            return self.screen_payload()
        step = scenario.steps[int(index)]
        if "action_id" in patch:
            step.action_id = str(patch["action_id"] or "")
        if "kind" in patch:
            step.condition.kind = str(patch["kind"] or "missing_mod")
            if not step.condition.needs_mods():
                step.condition.mods = []
        if "required" in patch:
            try:
                step.condition.required_weight = max(1, int(patch["required"] or 1))
            except (TypeError, ValueError):
                step.condition.required_weight = 1
        if "augment" in patch:
            value = str(patch["augment"] or "off")
            step.augment_open = value if value in {"prefix", "suffix", "any"} else "off"
        return self.screen_payload()

    def wizard_add_mod(self, index: int, mod_type_id: str) -> dict[str, Any]:
        catalog = self.catalog
        scenario = self._wizard
        if not catalog or not scenario or not (0 <= int(index) < len(scenario.steps)):
            return self.screen_payload()
        step = scenario.steps[int(index)]
        if any(row.mod_type_id == mod_type_id for row in step.condition.mods):
            return self.screen_payload()
        row = catalog.mod_type(mod_type_id)
        if not row:
            return self.screen_payload()
        tiers = catalog.tiers_for(mod_type_id, scenario.item_type)
        best = tiers[0] if tiers else {}
        step.condition.mods.append(
            ModRequirement(
                mod_type_id=mod_type_id,
                generation=row.get("generation", "prefix"),
                name=row.get("name", mod_type_id),
                tier=best.get("tier"),
                value_min=best.get("min"),
                value_max=best.get("max"),
                weight=best.get("weight"),
                need=1,
            )
        )
        return self.screen_payload()

    def wizard_patch_mod(self, index: int, mod_index: int, patch: dict) -> dict[str, Any]:
        catalog = self.catalog
        scenario = self._wizard
        if not scenario or not (0 <= int(index) < len(scenario.steps)):
            return self.screen_payload()
        mods = scenario.steps[int(index)].condition.mods
        if not (0 <= int(mod_index) < len(mods)):
            return self.screen_payload()
        req = mods[int(mod_index)]
        if "tier" in patch:
            value = str(patch["tier"] or "any")
            if value == "any":
                req.tier = None
                req.value_min = None
                req.value_max = None
                req.weight = None
            else:
                req.tier = int(value)
                if catalog:
                    tier = catalog.mod_tier(req.mod_type_id, req.tier, scenario.item_type)
                    if tier:
                        req.value_min = tier.get("min")
                        req.value_max = tier.get("max")
                        req.weight = tier.get("weight")
        if "value" in patch:
            raw = str(patch["value"] or "").strip().replace(" ", "")
            if not raw:
                req.value_min = None
                req.value_max = None
            elif "-" in raw:
                left, right = raw.split("-", 1)
                try:
                    req.value_min = int(left)
                    req.value_max = int(right)
                except ValueError:
                    pass
            else:
                try:
                    number = int(raw)
                    req.value_min = number
                    req.value_max = number
                except ValueError:
                    pass
        if "need" in patch:
            try:
                req.need = max(1, int(patch["need"] or 1))
            except (TypeError, ValueError):
                req.need = 1
        if "group" in patch:
            old = req.group_key()
            key = str(patch["group"] or "").strip()
            req.group = key
            if key:
                for other in mods:
                    if other is not req and other.group_key() == key:
                        req.count = other.count_value()
                        break
            self._sync_group_counts(mods, key or old)
        if "count" in patch and req.group_key():
            try:
                req.count = max(1, int(patch["count"] or 1))
            except (TypeError, ValueError):
                req.count = 1
            self._sync_group_counts(mods, req.group_key())
        return self.screen_payload()

    def _sync_group_counts(self, mods: list[ModRequirement], key: str) -> None:
        if not key:
            return
        rows = [row for row in mods if row.group_key() == key]
        if not rows:
            return
        count = rows[0].count_value()
        for row in rows:
            row.count = count

    def wizard_remove_mod(self, index: int, mod_index: int) -> dict[str, Any]:
        scenario = self._wizard
        if not scenario or not (0 <= int(index) < len(scenario.steps)):
            return self.screen_payload()
        mods = scenario.steps[int(index)].condition.mods
        if 0 <= int(mod_index) < len(mods):
            mods.pop(int(mod_index))
        return self.screen_payload()

    def wizard_save(self, name: str) -> dict[str, Any]:
        scenario = self._wizard
        if scenario is None:
            return self.navigate("home")
        previous = self._wizard_step
        self._wizard_step = 3
        error = self._wizard_validate()
        self._wizard_step = previous
        if error:
            self.toast(error)
            return self.screen_payload()
        title = (name or "").strip()
        if not title:
            self.toast(t("validate.name"))
            return self.screen_payload()
        scenario.name = title
        save_scenario(scenario)
        self.toast(t("status.saved", name=title), kind="success")
        self.set_status(t("status.saved", name=title))
        return self.navigate("scenarios")

    def _scenarios(self) -> dict[str, Any]:
        catalog = self.catalog
        rows = []
        for scenario in list_scenarios():
            item_name = catalog.item_type_name(scenario.item_type) if catalog else item_type_label(scenario.item_type)
            craft_name = catalog.craft_type_name(scenario.craft_type) if catalog else scenario.craft_type
            rows.append(
                {
                    "id": scenario.id,
                    "name": scenario.name,
                    "meta": t("scenarios.meta", item=item_name, craft=craft_name, steps=len(scenario.steps)),
                }
            )
        return {"items": rows}

    def scenario_delete(self, scenario_id: str) -> dict[str, Any]:
        if not delete_scenario(scenario_id):
            return self.screen_payload()
        if self.selected_scenario_id == scenario_id:
            self.selected_scenario_id = None
            save_settings({"last_scenario_id": ""})
        self.toast(t("scenarios.deleted"), kind="success")
        if self._current == "run":
            return self.screen_payload()
        return self.navigate("scenarios")

    def _run(self) -> dict[str, Any]:
        catalog = self.catalog
        config = load_config()
        selected = None
        items = []
        for scenario in list_scenarios():
            item_name = catalog.item_type_name(scenario.item_type) if catalog else item_type_label(scenario.item_type)
            craft_name = catalog.craft_type_name(scenario.craft_type) if catalog else scenario.craft_type
            row = {
                "id": scenario.id,
                "name": scenario.name,
                "meta": t("scenarios.meta", item=item_name, craft=craft_name, steps=len(scenario.steps)),
            }
            items.append(row)
            if scenario.id == self.selected_scenario_id:
                selected = scenario
        if selected is None and items:
            selected = next((row for row in list_scenarios() if row.id == items[0]["id"]), None)
            if selected:
                self.selected_scenario_id = selected.id
        ready = t("run.need_scenario")
        ready_kind = "muted"
        if selected:
            error = validate_ready(selected, config, chain=self._prefer_chain)
            if error:
                ready = t(error)
                ready_kind = "danger"
            else:
                ready = t("run.ready")
                ready_kind = "ok"
        hint = (
            t("run.chain_hint", start=config.hotkey_chain, stop=config.hotkey_stop)
            if self._prefer_chain
            else t("run.hint", start=config.hotkey_start, stop=config.hotkey_stop)
        )
        return {
            "prefer_chain": self._prefer_chain,
            "hint": hint,
            "items": items,
            "selected_id": self.selected_scenario_id,
            "ready": ready,
            "ready_kind": ready_kind,
            "status": self._craft_status,
            "log": list(self._craft_lines[-200:]),
            "running": bool(self._runner and self._runner.running),
        }

    def run_select(self, scenario_id: str) -> dict[str, Any]:
        self.selected_scenario_id = scenario_id
        save_settings({"last_scenario_id": scenario_id})
        return self.screen_payload()

    def _settings(self) -> dict[str, Any]:
        config = load_config()
        currencies = []
        for row in mappable_currencies():
            currencies.append(
                {
                    "id": row["id"],
                    "name": t(f"action.{row['id']}", default=row["name"]),
                    "status": self._target_status(config, row["id"]),
                    "icon": action_icon(row["id"]),
                }
            )
        buttons = []
        for row in BUTTONS:
            buttons.append(
                {
                    "id": row["id"],
                    "name": t(f"target.{row['id']}"),
                    "status": self._target_status(config, row["id"]),
                }
            )
        groups: dict[str, list[dict[str, Any]]] = {"left": [], "center": [], "right": [], "bottom": []}
        cols = {"left": 4, "center": 2, "right": 4, "bottom": 7}
        for slot in SLOTS:
            if slot.group not in groups:
                continue
            currency_id = config.currency_slots.get(slot.key)
            groups[slot.group].append(
                {
                    "key": slot.key,
                    "id": currency_id or "",
                    "label": (currency_id or "·")[:4],
                    "filled": bool(currency_id),
                }
            )
        from app.heist.engine import load_heist_config
        from app.heist.reveal import load_reveal_config

        heist = load_heist_config()
        reveal = load_reveal_config()
        return {
            "speed_ms": config.speed_ms,
            "logs_enabled": config.logs_enabled,
            "shift_lock": config.shift_lock,
            "hotkey_start": config.hotkey_start or "",
            "hotkey_chain": config.hotkey_chain or "",
            "hotkey_stop": config.hotkey_stop or "",
            "heist_hotkey": _saved_hotkey(heist.get("hotkey")),
            "heist_exit_hotkey": _saved_hotkey(heist.get("exit_hotkey")),
            "reveal_hotkey": _saved_hotkey(reveal.get("hotkey")),
            "reveal_exit_hotkey": _saved_hotkey(reveal.get("exit_hotkey")),
            "hud": self._hud_text(config),
            "item": _fmt_rect(config.item),
            "chain": _fmt_grid(config.chain_grid),
            "tab": _fmt_rect(self._tab_as_rect(config)),
            "tab_mapped": t("settings.tab_mapped", count=len(config.currency_slots))
            if config.currency_slots
            else t("settings.tab_empty"),
            "slot_groups": [{"id": key, "cols": cols[key], "slots": groups[key]} for key in ("left", "center", "right", "bottom")],
            "currencies": currencies,
            "assign_items": [{"id": "clear", "name": t("settings.clear_cell")}]
            + [
                {"id": row["id"], "name": t(f"action.{row['id']}", default=row["name"]), "icon": action_icon(row["id"])}
                for row in mappable_currencies()
            ],
            "buttons": buttons,
        }

    def _tab_as_rect(self, config: AppConfig) -> Rect | None:
        tab = config.currency_tab
        if not tab:
            return None
        return Rect(x=tab.x, y=tab.y, w=tab.w, h=tab.h)

    def _hud_size(self, config: AppConfig) -> tuple[int, int]:
        return (max(180, int(config.hud_w or HUD_WIDTH)), max(110, int(config.hud_h or HUD_HEIGHT)))

    def _hud_rect(self, config: AppConfig) -> Rect:
        width, height = self._hud_size(config)
        if config.hud_x is not None and config.hud_y is not None:
            return Rect(x=config.hud_x, y=config.hud_y, w=width, h=height)
        screen = 1920
        try:
            if self._tk.root is not None:
                screen = int(self._tk.root.winfo_screenwidth())
        except Exception:
            pass
        x, y = default_hud_xy(screen, width)
        return Rect(x=x, y=y, w=width, h=height)

    def _hud_text(self, config: AppConfig) -> str:
        if config.hud_x is None or config.hud_y is None:
            return t("settings.hud_default")
        width, height = self._hud_size(config)
        return f"{config.hud_x}, {config.hud_y}  ·  {width}×{height}"

    def _target_status(self, config: AppConfig, key: str) -> str:
        if key in config.positions:
            return _fmt_rect(config.positions[key])
        if key in config.currency_slots.values():
            return t("settings.from_tab")
        if key in config.currency_cells and config.currency_tab:
            col, row = config.currency_cells[key]
            return t("settings.from_grid", col=col + 1, row=row + 1)
        return t("settings.not_set")

    def settings_save(self, patch: dict) -> dict[str, Any]:
        config = load_config()
        if "speed_ms" in patch:
            config.speed_ms = clamp_speed_ms(patch["speed_ms"])
        if "logs_enabled" in patch:
            config.logs_enabled = bool(patch["logs_enabled"])
        if "shift_lock" in patch:
            config.shift_lock = bool(patch["shift_lock"])
        save_config(config)
        self.set_status(t("settings.saved"))
        return self.screen_payload()

    def settings_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        name = _hotkey_from_capture(key)
        if name is None:
            return self.screen_payload()
        if kind in {"heist_start", "heist_stop"}:
            from app.heist.engine import load_heist_config, save_heist_config

            cfg = load_heist_config()
            if kind == "heist_start":
                cfg["hotkey"] = name
            else:
                cfg["exit_hotkey"] = name
            save_heist_config(cfg)
        elif kind in {"reveal_start", "reveal_stop"}:
            from app.heist.reveal import load_reveal_config, save_reveal_config

            cfg = load_reveal_config()
            if kind == "reveal_start":
                cfg["hotkey"] = name
            else:
                cfg["exit_hotkey"] = name
            save_reveal_config(cfg)
        else:
            config = load_config()
            if kind == "start":
                config.hotkey_start = name
            elif kind == "chain":
                config.hotkey_chain = name
            else:
                config.hotkey_stop = name
            save_config(config)
        self.refresh_hotkeys()
        self.set_status(t("settings.saved"))
        return self.screen_payload()

    def settings_reset_hud(self) -> dict[str, Any]:
        config = load_config()
        config.hud_x = None
        config.hud_y = None
        config.hud_w = None
        config.hud_h = None
        save_config(config)
        return self.screen_payload()

    def settings_assign_slot(self, slot_key: str, currency_id: str) -> dict[str, Any]:
        config = load_config()
        slot = SLOTS_BY_KEY.get(slot_key)
        tab = self._tab_as_rect(config)
        if slot is None or tab is None:
            return self.screen_payload()
        previous = config.currency_slots.get(slot.key)
        if previous:
            config.positions.pop(previous, None)
        if currency_id == "clear":
            config.currency_slots.pop(slot.key, None)
        else:
            for key, value in list(config.currency_slots.items()):
                if value == currency_id:
                    config.currency_slots.pop(key, None)
            config.currency_slots[slot.key] = currency_id
            config.positions[currency_id] = slot.to_rect(tab)
        save_config(config)
        return self.screen_payload()

    def settings_map(self, kind: str, target: str = "") -> dict[str, Any]:
        config = load_config()
        if kind == "hud":
            self._open_overlay(
                t("settings.hud"),
                self._hud_rect(config),
                self._on_hud,
                min_size=(180, 110),
                lock_aspect=False,
                show_dot=False,
                hint=t("settings.hud_hint"),
                alpha=0.92,
            )
        elif kind == "item":
            self._open_overlay(
                t("settings.set_item"),
                config.item or Rect(x=480, y=200, w=140, h=200),
                self._on_item,
                min_size=(70, 90),
            )
        elif kind == "tab":
            current = self._tab_as_rect(config) or Rect(x=200, y=60, w=638, h=639)
            self._open_overlay(
                t("settings.map_tab"),
                current,
                self._on_tab,
                min_size=(360, 360),
                background=stash_image_path(),
                lock_aspect=True,
                show_dot=False,
                hint=t("overlay.tab_hint"),
                alpha=0.82,
            )
        elif kind == "chain":
            self._open_grid(config.chain_grid, self._on_chain, t("settings.chain"))
        elif kind == "position" and target:
            self._open_overlay(
                t(f"target.{target}", default=target),
                config.positions.get(target) or Rect(),
                lambda rect, item=target: self._on_position(item, rect),
            )
        return {"ok": True}

    def _on_hud(self, rect: Rect) -> None:
        config = load_config()
        config.hud_x = rect.x
        config.hud_y = rect.y
        config.hud_w = rect.w
        config.hud_h = rect.h
        save_config(config)
        self.emit("screen", self.screen_payload())

    def _on_item(self, rect: Rect) -> None:
        config = load_config()
        config.item = rect
        save_config(config)
        self.emit("screen", self.screen_payload())

    def _on_tab(self, rect: Rect) -> None:
        config = load_config()
        config.currency_tab = CurrencyTab(x=rect.x, y=rect.y, w=rect.w, h=rect.h)
        mapped = apply_layout(rect)
        item_rect = mapped.pop("item", None)
        current = config.item
        inside_tab = bool(
            current
            and rect.x <= current.click[0] <= rect.x + rect.w
            and rect.y <= current.click[1] <= rect.y + rect.h
        )
        if item_rect and (current is None or inside_tab):
            config.item = item_rect
        config.currency_slots = default_slot_assignments()
        for key, slot_rect in mapped.items():
            config.positions[key] = slot_rect
        save_config(config)
        self.emit("screen", self.screen_payload())

    def _on_chain(self, grid: ItemGrid) -> None:
        config = load_config()
        config.chain_grid = grid
        save_config(config)
        self.emit("screen", self.screen_payload())

    def _on_position(self, key: str, rect: Rect) -> None:
        config = load_config()
        config.positions[key] = rect
        save_config(config)
        self.emit("screen", self.screen_payload())

    def _logs(self) -> dict[str, Any]:
        return self.logs_query("")

    def _stats(self) -> dict[str, Any]:
        from app.stats import stats_payload

        return stats_payload()

    def logs_query(self, query: str = "") -> dict[str, Any]:
        groups = []
        for name, rows in grouped_sessions(query):
            groups.append(
                {
                    "name": name,
                    "items": [
                        {
                            "id": session.id,
                            "label": t(
                                "logs.session",
                                when=session.when(),
                                status=t(f"logs.status_{session.status}", default=session.status),
                                n=len(session.lines),
                            ),
                        }
                        for session in rows
                    ],
                }
            )
        return {"query": query, "groups": groups, "empty": t("logs.no_results") if query else t("logs.empty")}

    def logs_open(self, session_id: str, query: str = "") -> dict[str, Any]:
        session = load_session(session_id)
        if session is None:
            return {"missing": True}
        status = t(f"logs.status_{session.status}", default=session.status)
        return {
            "id": session.id,
            "heading": f"{session.name}  ·  {session.when()}  ·  {status}",
            "lines": list(session.lines),
            "running": session.status == "running",
        }

    def logs_delete(self, session_id: str) -> dict[str, Any]:
        delete_session(session_id)
        return self.logs_query("")

    def _heist(self) -> dict[str, Any]:
        from app.heist.engine import inventory_grid, load_heist_config

        cfg = load_heist_config()
        return {
            "running": self.heist_running(),
            "status": t("heist.running") if self.heist_running() else t("heist.ready"),
            "confirm": self._fmt_point(cfg, "confirm"),
            "blueprint": self._fmt_point(cfg, "blueprint_slot"),
            "inventory": _fmt_grid(inventory_grid(cfg)),
            "hotkey": _saved_hotkey(cfg.get("hotkey")),
            "exit_hotkey": _saved_hotkey(cfg.get("exit_hotkey")),
            "speeds": [{"key": key, "label": t(label), "value": cfg.get(key, "")} for key, label in HEIST_SPEED],
            "log": list(self._heist_lines[-300:]),
        }

    def _reveal(self) -> dict[str, Any]:
        from app.heist.engine import inventory_grid
        from app.heist.reveal import load_reveal_config, map_rect, slot_point

        cfg = load_reveal_config()
        point = slot_point(cfg)
        rect = map_rect(cfg)
        return {
            "running": self.reveal_running(),
            "status": t("heist.running") if self.reveal_running() else t("heist.ready"),
            "map": f"{rect.x}, {rect.y}  ·  {rect.w}×{rect.h}",
            "slot": f"{point[0]}, {point[1]}" if point else t("heist.point_auto"),
            "inventory": _fmt_grid(inventory_grid(cfg)),
            "hotkey": _saved_hotkey(cfg.get("hotkey")),
            "exit_hotkey": _saved_hotkey(cfg.get("exit_hotkey")),
            "speeds": [{"key": key, "label": t(label), "value": cfg.get(key, "")} for key, label in REVEAL_SPEED],
            "log": list(self._reveal_lines[-300:]),
        }

    def _fmt_point(self, cfg: dict, key: str) -> str:
        ui = cfg.get("ui_points") or {}
        pt = ui.get(key)
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            return f"{pt[0]}, {pt[1]}"
        return t("heist.point_auto")

    def heist_save(self, patch: dict) -> dict[str, Any]:
        from app.heist.engine import load_heist_config, save_heist_config, sync_inventory_grid

        cfg = load_heist_config()
        for key, _label in HEIST_SPEED:
            if key not in patch:
                continue
            raw = str(patch[key]).strip().replace(",", ".")
            try:
                cfg[key] = float(raw)
            except ValueError:
                pass
        sync_inventory_grid(cfg)
        save_heist_config(cfg)
        return self.screen_payload()

    def heist_preset(self, name: str) -> dict[str, Any]:
        from app.heist.engine import load_heist_config, save_heist_config

        cfg = load_heist_config()
        cfg.update(HEIST_PRESETS.get(name) or {})
        save_heist_config(cfg)
        self._heist_log(t("heist.preset", name=name))
        return self.screen_payload()

    def heist_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        from app.heist.engine import load_heist_config, save_heist_config

        name = _hotkey_from_capture(key)
        if name is None:
            return self.screen_payload()
        cfg = load_heist_config()
        if kind == "start":
            cfg["hotkey"] = name
        else:
            cfg["exit_hotkey"] = name
        save_heist_config(cfg)
        self.refresh_hotkeys()
        return self.screen_payload()

    def heist_clear_points(self) -> dict[str, Any]:
        from app.heist.engine import load_heist_config, save_heist_config

        cfg = load_heist_config()
        cfg["ui_points"] = {}
        save_heist_config(cfg)
        self._heist_log(t("heist.points_cleared"))
        return self.screen_payload()

    def heist_map(self, kind: str) -> dict[str, Any]:
        from app.heist.engine import inventory_grid, load_heist_config

        if self.heist_running():
            return {"ok": False}
        cfg = load_heist_config()
        if kind == "inventory":
            self._open_grid(inventory_grid(cfg), self._on_heist_inventory, t("heist.inventory_region"))
            return {"ok": True}
        title = t("heist.confirm_point") if kind == "confirm" else t("heist.bp_point")
        hint = t("heist.confirm_point_help") if kind == "confirm" else t("heist.bp_point_help")
        ui = cfg.get("ui_points") or {}
        pt = ui.get(kind if kind != "blueprint" else "blueprint_slot")
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            rect = Rect.from_click(int(pt[0]), int(pt[1]), 80, 48)
        else:
            rect = Rect(x=480, y=360, w=80, h=48)
        key = "confirm" if kind == "confirm" else "blueprint_slot"
        self._open_overlay(title, rect, lambda value, item=key: self._on_heist_point(item, value), min_size=(48, 32), hint=hint)
        return {"ok": True}

    def _on_heist_point(self, key: str, rect: Rect) -> None:
        from app.heist.engine import load_heist_config, save_heist_config

        x, y = rect.click
        cfg = load_heist_config()
        ui = cfg.setdefault("ui_points", {})
        ui[key] = [int(x), int(y)]
        save_heist_config(cfg)
        name = t("heist.confirm_point") if key == "confirm" else t("heist.bp_point")
        self._heist_log(t("heist.point_set", name=name, x=x, y=y))
        self.emit("screen", self.screen_payload())

    def _on_heist_inventory(self, grid: ItemGrid) -> None:
        from app.heist.engine import load_heist_config, save_heist_config, sync_inventory_grid

        cfg = load_heist_config()
        sync_inventory_grid(cfg, grid)
        save_heist_config(cfg)
        self._heist_log(t("heist.inventory_set"))
        self.emit("screen", self.screen_payload())

    def reveal_save(self, patch: dict) -> dict[str, Any]:
        from app.heist.engine import sync_inventory_grid
        from app.heist.reveal import load_reveal_config, save_reveal_config, sync_map_rect

        cfg = load_reveal_config()
        for key, _label in REVEAL_SPEED:
            if key not in patch:
                continue
            raw = str(patch[key]).strip().replace(",", ".")
            try:
                cfg[key] = float(raw)
            except ValueError:
                pass
        sync_inventory_grid(cfg)
        sync_map_rect(cfg)
        save_reveal_config(cfg)
        return self.screen_payload()

    def reveal_preset(self, name: str) -> dict[str, Any]:
        from app.heist.reveal import load_reveal_config, save_reveal_config

        cfg = load_reveal_config()
        cfg.update(REVEAL_PRESETS.get(name) or {})
        save_reveal_config(cfg)
        self._reveal_log(t("heist.preset", name=name))
        return self.screen_payload()

    def reveal_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        from app.heist.reveal import load_reveal_config, save_reveal_config

        name = _hotkey_from_capture(key)
        if name is None:
            return self.screen_payload()
        cfg = load_reveal_config()
        if kind == "start":
            cfg["hotkey"] = name
        else:
            cfg["exit_hotkey"] = name
        save_reveal_config(cfg)
        self.refresh_hotkeys()
        return self.screen_payload()

    def reveal_map(self, kind: str) -> dict[str, Any]:
        from app.heist.engine import inventory_grid
        from app.heist.reveal import load_reveal_config, map_rect, slot_point

        if self.reveal_running():
            return {"ok": False}
        cfg = load_reveal_config()
        if kind == "inventory":
            self._open_grid(inventory_grid(cfg), self._on_reveal_inventory, t("heist.inventory_region"))
        elif kind == "map":
            self._open_overlay(
                t("reveal.map"),
                map_rect(cfg),
                self._on_reveal_map,
                min_size=(240, 180),
                show_dot=False,
                hint=t("reveal.map_help"),
            )
        else:
            point = slot_point(cfg)
            rect = Rect.from_click(point[0], point[1], 56, 56) if point else Rect(x=900, y=720, w=56, h=56)
            self._open_overlay(t("reveal.slot"), rect, self._on_reveal_slot, min_size=(40, 40), hint=t("reveal.slot_help"))
        return {"ok": True}

    def _on_reveal_map(self, rect: Rect) -> None:
        from app.heist.reveal import load_reveal_config, save_reveal_config, sync_map_rect

        cfg = load_reveal_config()
        sync_map_rect(cfg, rect)
        save_reveal_config(cfg)
        self._reveal_log(t("reveal.map_set"))
        self.emit("screen", self.screen_payload())

    def _on_reveal_slot(self, rect: Rect) -> None:
        from app.heist.reveal import load_reveal_config, save_reveal_config

        x, y = rect.click
        cfg = load_reveal_config()
        ui = cfg.setdefault("ui_points", {})
        ui["blueprint_slot"] = [int(x), int(y)]
        save_reveal_config(cfg)
        self._reveal_log(t("heist.point_set", name=t("reveal.slot"), x=x, y=y))
        self.emit("screen", self.screen_payload())

    def _on_reveal_inventory(self, grid: ItemGrid) -> None:
        from app.heist.engine import sync_inventory_grid
        from app.heist.reveal import load_reveal_config, save_reveal_config

        cfg = load_reveal_config()
        sync_inventory_grid(cfg, grid)
        save_reveal_config(cfg)
        self._reveal_log(t("heist.inventory_set"))
        self.emit("screen", self.screen_payload())

    def _open_overlay(self, title: str, rect: Rect, callback, **kwargs) -> None:
        self._drop_overlay()
        self.hide_window()

        def make() -> None:
            self._overlay = PositionOverlay(
                self._tk.root,
                title=title,
                rect=rect,
                on_confirm=lambda value: self._finish_overlay(callback, value),
                on_cancel=self._restore_app,
                **kwargs,
            )

        self._tk.call(make)

    def _open_grid(self, grid: ItemGrid | None, callback, title: str | None = None) -> None:
        self._drop_overlay()
        self.hide_window()

        def make() -> None:
            self._overlay = GridOverlay(
                self._tk.root,
                grid=grid,
                on_confirm=lambda value: self._finish_overlay(callback, value),
                on_cancel=self._restore_app,
                title=title,
            )

        self._tk.call(make)

    def _finish_overlay(self, callback, value) -> None:
        self._restore_app()
        callback(value)

    def _restore_app(self) -> None:
        self._overlay = None
        self.show_window()

    def _drop_overlay(self) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is None:
            return

        def close() -> None:
            try:
                fn = getattr(overlay, "_close", None)
                if callable(fn):
                    fn()
                elif overlay.winfo_exists():
                    overlay.destroy()
            except Exception:
                pass

        self._tk.call(close)

    def refresh_hotkeys(self) -> None:
        config = load_config()
        binds: dict[str, Any] = {}

        def bind(name: str, callback) -> None:
            key = (name or "").strip()
            if key and key not in binds:
                binds[key] = callback

        bind(config.hotkey_start, self._os_start_hotkey)
        bind(config.hotkey_stop, self._os_stop_hotkey)
        bind(config.hotkey_chain, self._os_chain_hotkey)
        try:
            from app.heist.engine import load_heist_config

            heist = load_heist_config()
            bind(_saved_hotkey(heist.get("hotkey")), self._os_heist_toggle)
            bind(_saved_hotkey(heist.get("exit_hotkey")), self._os_heist_stop)
        except Exception:
            pass
        try:
            from app.heist.reveal import load_reveal_config

            reveal = load_reveal_config()
            bind(_saved_hotkey(reveal.get("hotkey")), self._os_reveal_toggle)
            bind(_saved_hotkey(reveal.get("exit_hotkey")), self._os_reveal_stop)
        except Exception:
            pass
        self._hotkeys.start(binds, poll={"ESCAPE": self._os_stop_hotkey})

    def _os_start_hotkey(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_start)

    def _os_chain_hotkey(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_chain)

    def _os_stop_hotkey(self) -> None:
        self.after(0, self._stop_all)

    def _os_heist_toggle(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_heist_toggle)

    def _os_heist_stop(self) -> None:
        self.after(0, self.stop_heist)

    def _os_reveal_toggle(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_reveal_toggle)

    def _os_reveal_stop(self) -> None:
        self.after(0, self.stop_reveal)

    def _stop_all(self) -> None:
        self.stop_heist()
        self.stop_reveal()
        self.stop_craft()

    def _scenario_for_hotkey(self) -> CraftScenario | None:
        scenarios = list_scenarios()
        if not scenarios:
            return None
        chosen = next((row for row in scenarios if row.id == self.selected_scenario_id), None)
        return chosen or scenarios[0]

    def _hotkey_start(self) -> None:
        if self._runner and self._runner.paused:
            self._runner.resume()
            return
        if self._current == "settings":
            return
        if self._runner and self._runner.running:
            return
        chosen = self._scenario_for_hotkey()
        if not chosen:
            self.toast(t("run.need_scenario"))
            return
        self.start_craft(chosen)

    def _hotkey_chain(self) -> None:
        if self._runner and self._runner.paused:
            self._runner.resume()
            return
        if self._current == "settings":
            return
        if self._runner and self._runner.running:
            return
        chosen = self._scenario_for_hotkey()
        if not chosen:
            self.toast(t("run.need_scenario"))
            return
        self.start_craft(chosen, chain=True)

    def run_start(self, chain: bool = False) -> dict[str, Any]:
        chosen = next((row for row in list_scenarios() if row.id == self.selected_scenario_id), None)
        if not chosen:
            self.toast(t("run.need_scenario"))
            return self.screen_payload()
        self.start_craft(chosen, chain=bool(chain))
        return self.screen_payload()

    def start_craft(self, scenario: CraftScenario, chain: bool = False) -> None:
        dbg(f"start_craft name={scenario.name!r} catalog={self.catalog is not None} chain={chain}")
        if self.heist_running() or self.reveal_running():
            self.toast(t("heist.busy_craft"))
            return
        if not self.catalog:
            self.toast(t("status.wait"))
            return
        if self._runner and self._runner.paused:
            self._runner.resume()
            return
        if self._runner and self._runner.running:
            return
        error = validate_ready(scenario, load_config(), chain=chain)
        if error:
            self.toast(t(error))
            return
        self.selected_scenario_id = scenario.id
        save_settings({"last_scenario_id": scenario.id})
        self._runner = CraftRunner(self.catalog, lambda kind, payload: self._craft_q.put((kind, payload)))
        config = load_config()
        self._close_hud()
        self._tk.call(lambda: self._make_hud(config.hotkey_stop, scenario.name), wait=True)
        self._write_craft_log(t("run.log.start"))
        allow_foreground()
        focused = focus_game()
        dbg(f"start_craft focus_game={focused}")
        error = self._runner.start(scenario, chain=chain)
        if error:
            self._close_hud()
            self.toast(t(error))
            self._write_craft_log(t(error))

    def _make_hud(self, stop_key: str, title: str, mode: str = "craft") -> None:
        self._hud = CraftHud(self._tk.root, stop_key, mode=mode)
        self._hud.set_step(title)
        self._hud.set_note(t("run.log.start") if mode == "craft" else t("heist.ready"))
        if mode != "craft":
            self._hud.set_hint(t("run.hud_stop", key=stop_key))

    def _write_craft_log(self, line: str) -> None:
        if not line:
            return
        self._craft_lines.append(line)
        self._craft_status = line
        hud = self._hud
        if hud is not None:
            self._tk.call(lambda: hud.set_note(line) if hud.winfo_exists() else None)
        self.emit("craft_log", {"line": line, "status": line})

    def stop_craft(self) -> dict[str, Any]:
        running = bool(self._runner and self._runner.running)
        if self._runner:
            self._runner.stop()
        if running:
            release_modifiers(shift=True)
        hud = self._hud
        if hud is not None:
            data = self._runner.snapshot("stopped") if self._runner else {"status": "stopped"}
            self._tk.call(lambda: hud.mark_final(data) if hud.winfo_exists() else None)
        return self.screen_payload() if self._current == "run" else {"ok": True}

    def heist_running(self) -> bool:
        return bool(self._heist_thread and self._heist_thread.is_alive())

    def reveal_running(self) -> bool:
        return bool(self._reveal_thread and self._reveal_thread.is_alive())

    def _keep_job_hud(self) -> None:
        hud = self._hud
        if hud is None:
            return

        def keep() -> None:
            try:
                if not hud.winfo_exists():
                    return
                hud.keep_top()
            except Exception:
                pass

        self._tk.call(keep)

    def _job_hud(self, progress: str, note: str = "") -> None:
        def do() -> None:
            hud = self._hud
            if hud and hud.winfo_exists():
                hud.set_progress(t("heist.hud_cell", n=progress))
                if note:
                    hud.set_note(note)

        self._tk.call(do)

    def _finish_job_hud(self, status: str, note: str = "") -> None:
        hud = self._hud
        if hud is None:
            return

        def mark() -> None:
            if hud.winfo_exists():
                hud.mark_final({"status": status, "item": note})

        self._tk.call(mark)
        self.after(2500, lambda: self._close_hud_if(hud))

    def _hotkey_heist_toggle(self) -> None:
        if self.heist_running():
            self.stop_heist()
            return
        if self._current != "heist":
            self._current = "heist"
            self.emit("screen", self.screen_payload())
        self.start_heist()

    def start_heist(self) -> dict[str, Any]:
        if self._runner and self._runner.running:
            self.toast(t("heist.busy_craft"))
            return self.screen_payload()
        if self.reveal_running():
            self.toast(t("reveal.busy"))
            return self.screen_payload()
        if self.heist_running():
            return self.screen_payload()
        try:
            import cv2  # noqa: F401
            import mss  # noqa: F401
        except ImportError:
            self.toast(t("heist.missing_cv"))
            return self.screen_payload()
        from app.heist.engine import assign_contracts, load_heist_config

        if self._current != "heist":
            self._current = "heist"
        cfg = load_heist_config()
        stop_key = _saved_hotkey(cfg.get("exit_hotkey"))
        self._heist_stop.clear()
        self._heist_log("=== START ===")
        self._drop_overlay()
        self._close_hud()
        self._tk.call(lambda: self._make_hud(stop_key, t("heist.title"), mode="job"), wait=True)
        self.hide_window()
        self.after(80, self._keep_job_hud)
        self.after(250, self._keep_job_hud)

        def worker() -> None:
            try:
                self._heist_stop.wait(0.35)
                focus_game()
                assign_contracts(cfg, stop_event=self._heist_stop, on_log=self._heist_log, on_hud=self._job_hud)
            except Exception as exc:
                self._heist_log(t("heist.error", exc=exc))
            finally:
                self.after(0, self._heist_done)

        self._heist_thread = threading.Thread(target=worker, name="heist-assign", daemon=True)
        self._heist_thread.start()
        self.emit("heist_running", True)
        return self.screen_payload()

    def stop_heist(self) -> dict[str, Any]:
        if not self.heist_running() and not self._heist_stop.is_set():
            return self.screen_payload() if self._current == "heist" else {"ok": True}
        self._heist_stop.set()
        self._heist_log(t("heist.stop"))
        hud = self._hud
        if hud is not None:
            self._tk.call(lambda: hud.mark_final({"status": "stopped"}) if hud.winfo_exists() else None)
        self.show_window()
        return self.screen_payload() if self._current == "heist" else {"ok": True}

    def _heist_log(self, line: str) -> None:
        text = str(line)
        stamp = time.strftime("%H:%M:%S")
        entry = f"{stamp}  {text.rstrip()}"
        self._heist_lines.append(entry)
        hud = self._hud
        if hud is not None:
            self._tk.call(lambda: hud.set_note(text) if hud.winfo_exists() else None)
        self.set_status(text[:120])
        self.emit("job_log", {"job": "heist", "line": entry})

    def _heist_done(self) -> None:
        self._heist_thread = None
        self._heist_log("=== DONE ===")
        status = "stopped" if self._heist_stop.is_set() else "done"
        self._finish_job_hud(status)
        self.show_window()
        self.emit("heist_running", False)
        if self._current == "heist":
            self.emit("screen", self.screen_payload())

    def _hotkey_reveal_toggle(self) -> None:
        if self.reveal_running():
            self.stop_reveal()
            return
        if self._current != "reveal":
            self._current = "reveal"
            self.emit("screen", self.screen_payload())
        self.start_reveal()

    def start_reveal(self) -> dict[str, Any]:
        if self._runner and self._runner.running:
            self.toast(t("reveal.busy"))
            return self.screen_payload()
        if self.heist_running():
            self.toast(t("reveal.busy"))
            return self.screen_payload()
        if self.reveal_running():
            return self.screen_payload()
        try:
            import cv2  # noqa: F401
            import mss  # noqa: F401
        except ImportError:
            self.toast(t("heist.missing_cv"))
            return self.screen_payload()
        from app.heist.reveal import load_reveal_config, reveal_blueprints

        if self._current != "reveal":
            self._current = "reveal"
        cfg = load_reveal_config()
        stop_key = _saved_hotkey(cfg.get("exit_hotkey"))
        self._reveal_stop.clear()
        self._reveal_log("=== START ===")
        self._drop_overlay()
        self._close_hud()
        self._tk.call(lambda: self._make_hud(stop_key, t("reveal.title"), mode="job"), wait=True)
        self.hide_window()
        self.after(80, self._keep_job_hud)
        self.after(250, self._keep_job_hud)

        def worker() -> None:
            try:
                self._reveal_stop.wait(0.35)
                focus_game()
                reveal_blueprints(cfg, stop_event=self._reveal_stop, on_log=self._reveal_log, on_hud=self._job_hud)
            except Exception as exc:
                self._reveal_log(t("reveal.error", exc=exc))
            finally:
                self.after(0, self._reveal_done)

        self._reveal_thread = threading.Thread(target=worker, name="heist-reveal", daemon=True)
        self._reveal_thread.start()
        self.emit("reveal_running", True)
        return self.screen_payload()

    def stop_reveal(self) -> dict[str, Any]:
        if not self.reveal_running() and not self._reveal_stop.is_set():
            return self.screen_payload() if self._current == "reveal" else {"ok": True}
        self._reveal_stop.set()
        self._reveal_log(t("heist.stop"))
        hud = self._hud
        if hud is not None:
            self._tk.call(lambda: hud.mark_final({"status": "stopped"}) if hud.winfo_exists() else None)
        try:
            release_modifiers(shift=True)
        except Exception:
            pass
        self.show_window()
        return self.screen_payload() if self._current == "reveal" else {"ok": True}

    def _reveal_log(self, line: str) -> None:
        text = str(line)
        stamp = time.strftime("%H:%M:%S")
        entry = f"{stamp}  {text.rstrip()}"
        self._reveal_lines.append(entry)
        hud = self._hud
        if hud is not None:
            self._tk.call(lambda: hud.set_note(text) if hud.winfo_exists() else None)
        self.set_status(text[:120])
        self.emit("job_log", {"job": "reveal", "line": entry})

    def _reveal_done(self) -> None:
        self._reveal_thread = None
        self._reveal_log("=== DONE ===")
        status = "stopped" if self._reveal_stop.is_set() else "done"
        self._finish_job_hud(status)
        try:
            release_modifiers(shift=True)
        except Exception:
            pass
        self.show_window()
        self.emit("reveal_running", False)
        if self._current == "reveal":
            self.emit("screen", self.screen_payload())

    def _poll_craft_loop(self) -> None:
        while not self._poll_stop.is_set():
            try:
                kind, payload = self._craft_q.get(timeout=0.08)
            except queue.Empty:
                continue
            try:
                self._on_craft(kind, payload)
            except Exception:
                logger.exception("craft event failed")

    def _on_craft(self, kind: str, payload: str) -> None:
        if kind == "hud":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return
            hud = self._hud
            if hud is None:
                return

            def apply() -> None:
                if not hud.winfo_exists():
                    return
                if data.get("status") in {"stopped", "done", "error"}:
                    hud.mark_final(data)
                else:
                    hud.update_stats(data)

            self._tk.call(apply)
            return
        if kind == "paused":
            config = load_config()
            if payload == "augmentation":
                message = t("run.out_of_augment", start=config.hotkey_start)
            else:
                action = self.catalog.action_name(payload) if self.catalog else payload
                message = t("run.out_of_currency", action=action, start=config.hotkey_start)
            self.toast(message, kind="error", ms=8000)
            hud = self._hud
            runner = self._runner
            if hud is not None and runner:

                def apply() -> None:
                    if hud.winfo_exists():
                        hud.update_stats(runner.snapshot("paused"))
                        hud.set_note(message)
                        hud.set_hint(t("run.hud_paused", start=config.hotkey_start, stop=config.hotkey_stop))

                self._tk.call(apply)
            self._craft_status = message
            self._write_craft_log(message)
            self.set_status(message)
            return
        if kind == "resumed":
            config = load_config()
            message = t("run.resumed")
            hud = self._hud
            runner = self._runner
            if hud is not None and runner:

                def apply() -> None:
                    if hud.winfo_exists():
                        hud.update_stats(runner.snapshot("running"))
                        hud.set_hint(t("run.hud_stop", key=config.hotkey_stop))

                self._tk.call(apply)
            self._write_craft_log(message)
            self._craft_status = t("run.running")
            self.set_status(message)
            return
        if kind == "log":
            line = t(payload) if payload.startswith("run.") else payload
            self._write_craft_log(line)
            return
        if kind == "step":
            index, action_id = (payload.split("|", 1) + [""])[:2]
            name = self.catalog.action_name(action_id) if self.catalog else action_id
            text = t("run.step_status", n=index, action=name)
            if self._runner and self._runner.chain_total:
                text = t(
                    "run.chain_step",
                    item=self._runner.chain_index,
                    total=self._runner.chain_total,
                    step=text,
                )
            hud = self._hud
            if hud is not None:
                self._tk.call(lambda: hud.set_step(text) if hud.winfo_exists() else None)
            self._craft_status = text
            self._write_craft_log(text)
            return
        if kind == "chain":
            message = t("run.chain_item", n=payload)
            self._write_craft_log(message)
            hud = self._hud
            if hud is not None:
                self._tk.call(lambda: hud.set_step(message) if hud.winfo_exists() else None)
            return
        if kind in {"error", "done", "stopped"}:
            key = payload or ("run.stopped" if kind == "stopped" else "run.done")
            message = t(key)
            hud = self._hud
            runner = self._runner
            if hud is not None and runner:
                self._tk.call(lambda: hud.mark_final(runner.snapshot(kind)) if hud.winfo_exists() else None)
            if kind == "error":
                self.toast(message, kind="error")
            elif kind == "done":
                self.toast(message, kind="success")
            self._craft_status = message
            self._write_craft_log(message)
            self.set_status(message)
            current = hud
            self.after(2500, lambda: self._close_hud_if(current))

    def _close_hud_if(self, hud) -> None:
        if self._hud is hud:
            self._close_hud()

    def _close_hud(self) -> None:
        hud = self._hud
        self._hud = None
        if hud is None:
            return

        def close() -> None:
            try:
                if hud.winfo_exists():
                    hud.destroy()
            except Exception:
                pass

        self._tk.call(close)

    def on_close(self) -> None:
        self._poll_stop.set()
        self.stop_heist()
        self.stop_reveal()
        self.stop_craft()
        self._hotkeys.stop()
        self._close_hud()
        self._drop_overlay()
        self._tk.stop()


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


class JsApi:
    def __init__(self, host: AppHost) -> None:
        self._host = host

    def boot(self) -> dict[str, Any]:
        return self._host.screen_payload()

    def set_language(self, code: str) -> dict[str, Any]:
        return self._host.set_language(code)

    def navigate(self, name: str, scenario_id: str = "", prefer_chain: bool = False) -> dict[str, Any]:
        return self._host.navigate(name, scenario_id or None, prefer_chain=prefer_chain)

    def reload_catalog(self, force: bool = False) -> dict[str, Any]:
        return self._host.reload_catalog(force=force)

    def wizard_goto(self, direction: str) -> dict[str, Any]:
        return self._host.wizard_goto(direction)

    def wizard_select_item(self, item_id: str) -> dict[str, Any]:
        return self._host.wizard_select_item(item_id)

    def wizard_select_craft(self, craft_id: str) -> dict[str, Any]:
        return self._host.wizard_select_craft(craft_id)

    def wizard_add_step(self) -> dict[str, Any]:
        return self._host.wizard_add_step()

    def wizard_remove_step(self, index: int) -> dict[str, Any]:
        return self._host.wizard_remove_step(index)

    def wizard_patch_step(self, index: int, patch: dict) -> dict[str, Any]:
        return self._host.wizard_patch_step(index, _as_dict(patch))

    def wizard_add_mod(self, index: int, mod_type_id: str) -> dict[str, Any]:
        return self._host.wizard_add_mod(index, mod_type_id)

    def wizard_patch_mod(self, index: int, mod_index: int, patch: dict) -> dict[str, Any]:
        return self._host.wizard_patch_mod(index, mod_index, _as_dict(patch))

    def wizard_remove_mod(self, index: int, mod_index: int) -> dict[str, Any]:
        return self._host.wizard_remove_mod(index, mod_index)

    def wizard_save(self, name: str) -> dict[str, Any]:
        return self._host.wizard_save(name)

    def scenario_delete(self, scenario_id: str) -> dict[str, Any]:
        return self._host.scenario_delete(scenario_id)

    def run_select(self, scenario_id: str) -> dict[str, Any]:
        return self._host.run_select(scenario_id)

    def run_start(self, chain: bool = False) -> dict[str, Any]:
        return self._host.run_start(chain=chain)

    def run_stop(self) -> dict[str, Any]:
        return self._host.stop_craft()

    def settings_save(self, patch: dict) -> dict[str, Any]:
        return self._host.settings_save(_as_dict(patch))

    def settings_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        return self._host.settings_hotkey(kind, key)

    def settings_reset_hud(self) -> dict[str, Any]:
        return self._host.settings_reset_hud()

    def settings_assign_slot(self, slot_key: str, currency_id: str) -> dict[str, Any]:
        return self._host.settings_assign_slot(slot_key, currency_id)

    def settings_map(self, kind: str, target: str = "") -> dict[str, Any]:
        return self._host.settings_map(kind, target)

    def logs_query(self, query: str = "") -> dict[str, Any]:
        data = self._host.logs_query(query)
        data["screen"] = "logs"
        data["shell"] = self._host.shell_payload()
        return data

    def logs_open(self, session_id: str, query: str = "") -> dict[str, Any]:
        return self._host.logs_open(session_id, query)

    def logs_delete(self, session_id: str) -> dict[str, Any]:
        return self._host.logs_delete(session_id)

    def heist_save(self, patch: dict) -> dict[str, Any]:
        return self._host.heist_save(_as_dict(patch))

    def heist_preset(self, name: str) -> dict[str, Any]:
        return self._host.heist_preset(name)

    def heist_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        return self._host.heist_hotkey(kind, key)

    def heist_clear_points(self) -> dict[str, Any]:
        return self._host.heist_clear_points()

    def heist_map(self, kind: str) -> dict[str, Any]:
        return self._host.heist_map(kind)

    def heist_start(self) -> dict[str, Any]:
        return self._host.start_heist()

    def heist_stop(self) -> dict[str, Any]:
        return self._host.stop_heist()

    def reveal_save(self, patch: dict) -> dict[str, Any]:
        return self._host.reveal_save(_as_dict(patch))

    def reveal_preset(self, name: str) -> dict[str, Any]:
        return self._host.reveal_preset(name)

    def reveal_hotkey(self, kind: str, key: str) -> dict[str, Any]:
        return self._host.reveal_hotkey(kind, key)

    def reveal_map(self, kind: str) -> dict[str, Any]:
        return self._host.reveal_map(kind)

    def reveal_start(self) -> dict[str, Any]:
        return self._host.start_reveal()

    def reveal_stop(self) -> dict[str, Any]:
        return self._host.stop_reveal()
