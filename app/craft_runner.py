from __future__ import annotations

import json
import logging
import time
from collections import Counter
from collections.abc import Callable
from threading import Event, Thread

from app.config import AppConfig, Rect, clamp_speed_ms, load_config
from app.craft_logic import condition_report, matched_mod_names
from app.data.catalog import GameCatalog
from app.data.models import CraftScenario, CraftStep
from app.debug import dbg, dbg_exc
from app.i18n import t
from app.input_win import (
    VK_CONTROL,
    VK_ESCAPE,
    alt_down,
    alt_up,
    click,
    find_game_window,
    focus_game,
    game_is_active,
    get_clipboard,
    key_is_down,
    move_to,
    release_ctrl,
    release_modifiers,
    set_clipboard,
    shift_down,
    shift_up,
    tap_ctrl_c,
)
from app.item_parse import ParsedItem, magic_slot_counts, parse_item

logger = logging.getLogger("poe_helper")

MAX_STEP_ACTIONS = 400
MAX_TOTAL_ACTIONS = 2000

NEED_MAGIC = {"alteration", "augmentation", "regal"}
NEED_RARE = {"chaos", "exalted", "annulment", "scouring"}
NEED_NORMAL = {"transmutation", "alchemy", "chance"}
MUST_CHANGE = {
    "transmutation",
    "augmentation",
    "regal",
    "alchemy",
    "scouring",
    "wisdom",
    "exalted",
    "annulment",
}
SAME_STREAK = 3
_CLIP_MARK = "POE_HELPER_NO_ITEM"


class CraftRunner:
    def __init__(self, catalog: GameCatalog, emit: Callable[[str, str], None]) -> None:
        self.catalog = catalog
        self._emit = emit
        self._stop = Event()
        self._thread: Thread | None = None
        self.running = False
        self.scenario: CraftScenario | None = None
        self.spent: Counter[str] = Counter()
        self.hits = 0
        self.misses = 0
        self._status = "idle"
        self._locked: str | None = None
        self._cursor_orb: str | None = None
        self._locked_point: tuple[int, int] | None = None
        self._prefer_aug_orb = False
        self._leave = "run.stopped"
        self._total = 0
        self._pace = 0
        self._resume = Event()
        self._same_streak = 0
        self._handoff: ParsedItem | None = None
        self._logged_raw: str | None = None
        self.chain_index = 0
        self.chain_total = 0
        self._chaining = False

    def start(self, scenario: CraftScenario, chain: bool = False) -> str | None:
        if self.running:
            return "run.already"
        config = load_config()
        error = validate_ready(scenario, config, chain=chain)
        if error:
            return error
        self.scenario = scenario
        if self.catalog:
            self.catalog.sync_scenario(scenario)
        self.spent = Counter()
        self.hits = 0
        self.misses = 0
        self._status = "running"
        self._locked = None
        self._cursor_orb = None
        self._locked_point = None
        self._prefer_aug_orb = False
        self._leave = "run.stopped"
        self._total = 0
        self._pace = clamp_speed_ms(config.speed_ms)
        self._stop.clear()
        self._resume.clear()
        self._same_streak = 0
        self._handoff = None
        self._logged_raw = None
        self.chain_index = 0
        cells: list[Rect] = []
        if chain and config.chain_grid:
            cells = config.chain_grid.cells()
        self.chain_total = len(cells)
        self._chaining = bool(cells)
        self.running = True
        from app.craft_log import begin_session

        begin_session(scenario.name, scenario.id)
        dbg(
            f"runner.start steps={len(scenario.steps)} action0={scenario.steps[0].action_id if scenario.steps else '-'} "
            f"chain={self.chain_total}"
        )
        self._log(config, "START" + (f" chain {self.chain_total}" if cells else ""))
        self._thread = Thread(target=self._loop, args=(scenario, config, cells), daemon=True)
        self._thread.start()
        dbg(f"runner.thread started alive={self._thread.is_alive()}")
        return None

    @property
    def paused(self) -> bool:
        return self._status == "paused"

    def stop(self) -> None:
        self._stop.set()
        self._resume.set()
        self._release_lock()
        release_modifiers(shift=True)

    def resume(self) -> None:
        if self._status == "paused":
            self._resume.set()

    def _loop(self, scenario: CraftScenario, config: AppConfig, cells: list[Rect] | None = None) -> None:
        dbg("runner.loop enter")
        try:
            self._run(scenario, config, cells or [])
            dbg(f"runner.loop done status={self._status}")
        except Exception:
            dbg_exc("runner.loop crash")
            logger.exception("craft failed")
            self._status = "error"
            self._push_hud("error")
            self._emit("error", "run.crash")
        finally:
            self._release_lock()
            self.running = False
            dbg("runner.loop exit")

    def _run(self, scenario: CraftScenario, config: AppConfig, cells: list[Rect]) -> None:
        self._emit("log", "run.log.start")
        self._push_hud("running")
        if not self._attach_game():
            return
        if cells:
            self._run_chain(scenario, config, cells)
            return
        before = self._spent_total()
        if self._run_scenario(scenario, config):
            self._note_craft(config, before)
            self._finish("done", "run.done")

    def _run_chain(self, scenario: CraftScenario, config: AppConfig, cells: list[Rect]) -> None:
        crafted = 0
        for index, cell in enumerate(cells, start=1):
            if self._stop.is_set():
                self._finish("stopped", self._leave)
                return
            self.chain_index = index
            self._handoff = None
            self._logged_raw = None
            self._same_streak = 0
            self._total = 0
            work = AppConfig.from_dict(config.to_dict())
            work.item = cell
            self._log(work, f"CHAIN item {index}/{len(cells)}")
            self._emit("chain", f"{index}/{len(cells)}")
            parsed = self._peek_item(work)
            if parsed is None:
                if self._stop.is_set():
                    self._finish("stopped", self._leave)
                    return
                self._log(work, f"CHAIN skip empty {index}/{len(cells)}")
                continue
            self._handoff = parsed
            before = self._spent_total()
            if not self._run_scenario(scenario, work):
                return
            if self._note_craft(work, before):
                crafted += 1
        self._finish("done", "run.chain_done" if crafted else "run.chain_empty")

    def _run_scenario(self, scenario: CraftScenario, config: AppConfig) -> bool:
        steps = scenario.steps
        index = 1
        while index <= len(steps):
            if self._stop.is_set():
                self._finish("stopped", self._leave)
                return False
            result = self._run_step(index, steps[index - 1], config)
            if result is False:
                return False
            if type(result) is int:
                index = max(1, min(result, len(steps)))
                continue
            index += 1
        return True

    def _attach_game(self) -> bool:
        hwnd = find_game_window()
        dbg(f"attach_game hwnd={hwnd}")
        if not hwnd:
            self._finish("error", "run.need_game")
            return False
        self._log(load_config(), "FOCUS game")
        ok = focus_game()
        dbg(f"attach_game focus={ok} active={game_is_active()}")
        self._nap()
        return True

    def _run_step(self, index: int, step: CraftStep, config: AppConfig) -> bool | int:
        if not self._game_ok():
            return False
        self._emit("step", f"{index}/{len(self.scenario.steps) if self.scenario else index}|{step.action_id}")
        once_done = False
        actions = 0
        parsed = self._handoff
        self._handoff = None
        known_miss = False
        while not self._stop.is_set():
            if not self._game_ok():
                return False
            if parsed is None:
                parsed = self._await_item(config, tries=2 if self._chaining else 20)
                known_miss = False
            if parsed:
                self._log_item(config, parsed)
            if parsed is None:
                if self._chaining:
                    self._log(config, "CHAIN skip — no item")
                    return True
                if self._stop.is_set():
                    self._finish("stopped", self._leave)
                    return False
                reason = "run.need_game" if not find_game_window() else "run.menu_left"
                self._finish("stopped", reason)
                return False
            prep = self._prepare(parsed, step.action_id, config)
            if isinstance(prep, str):
                self._finish("error", prep)
                return False
            if prep is False:
                parsed = None
                known_miss = False
                continue
            if isinstance(prep, ParsedItem):
                parsed = prep
            if not known_miss and self._condition_met(parsed, step, config, index, actions, once_done):
                self._handoff = parsed
                return True
            if actions >= MAX_STEP_ACTIONS or self._total >= MAX_TOTAL_ACTIONS:
                self._finish("error", "run.limit")
                return False
            action = _currency_for(parsed, step)
            bits: list[str] = []
            if action == "augmentation" and step.fill_affix():
                bits.append(f"empty {step.fill_affix()}")
            if not self._use_currency(parsed, step, config, action):
                if self._status == "running":
                    self._finish("stopped", self._leave)
                return False
            self.spent[action] += 1
            if action == "augmentation" and self._locked == "alteration":
                bits.append("Alt")
            extra = f" ({', '.join(bits)})" if bits else ""
            self._log(config, f"USE   {action}{extra}")
            after = self._read_after(config, parsed)
            if self._use_wasted(parsed, after, action, step, config):
                if self._chaining and after is None:
                    self._log(config, "CHAIN skip — no item")
                    return True
                if not self._pause_empty(action, config):
                    return False
                parsed = None
                known_miss = False
                continue
            if after is None:
                if self._chaining:
                    self._log(config, "CHAIN skip — no item")
                    return True
                parsed = None
                known_miss = False
                continue
            self._total += 1
            once_done = True
            actions += 1
            back = self._rewind_to(after, index, config)
            if back is not None:
                self._handoff = after
                return back
            if self._condition_met(after, step, config, index, actions, once_done):
                self._handoff = after
                return True
            self.misses += 1
            self._log(config, "MISS")
            self._push_hud("running", after)
            parsed = after
            known_miss = True
        self._finish("stopped", self._leave)
        return False

    def _condition_met(
        self,
        item: ParsedItem,
        step: CraftStep,
        config: AppConfig,
        index: int,
        actions: int,
        once_done: bool,
    ) -> bool:
        holds, detail = condition_report(item, step.condition)
        self._log(config, f"CHECK {detail}")
        if step.condition.kind == "once":
            if not once_done:
                return False
            self._log(config, f"STEP {index} done")
            return True
        if holds:
            return False
        if actions:
            self.hits += 1
            names = matched_mod_names(item, step.condition)
            self._log(config, "HIT " + " | ".join(names) if names else "HIT")
        else:
            self._log(config, f"STEP {index} skip — condition already met")
        self._push_hud("running", item)
        return True

    def _rewind_to(self, item: ParsedItem, index: int, config: AppConfig) -> int | None:
        scenario = self.scenario
        if scenario is None or index <= 1:
            return None
        for prior_index, prior in enumerate(scenario.steps[: index - 1], start=1):
            if _step_still_holds(item, prior):
                continue
            self._log(config, t("run.back_step", frm=index, to=prior_index))
            return prior_index
        return None

    def _use_currency(self, item: ParsedItem, step: CraftStep, config: AppConfig, action: str) -> bool:
        self._log_item(config, item, "BEFORE")
        if not self._apply(action, config):
            if self._stop.is_set() or not game_is_active():
                self._leave = "run.game_left" if not game_is_active() else self._leave
                self._finish("stopped", self._leave)
                return False
            self._finish("error", "run.need_augment" if action == "augmentation" else "run.no_point")
            return False
        return self._wait(self._pace)

    def _read_after(
        self,
        config: AppConfig,
        before: ParsedItem | None = None,
        *,
        tries: int = 8,
        wait_ms: int | None = None,
        ready=None,
    ) -> ParsedItem | None:
        last = None
        before_key = _item_key(before)
        gap = max(self._pace, 25) if wait_ms is None else wait_ms
        for attempt in range(max(1, tries)):
            if self._stop.is_set() or self._escape():
                return last
            after = self._read_item(config)
            if after:
                last = after
                if ready is not None:
                    if ready(after):
                        self._log_item(config, after, "AFTER")
                        return after
                elif before_key is None or _item_key(after) != before_key:
                    self._log_item(config, after, "AFTER")
                    return after
                dbg(f"read_after stale attempt={attempt}")
            if not self._wait(gap):
                return last
        if last:
            self._log_item(config, last, "AFTER same", force=True)
            return last
        self._log(config, "AFTER empty")
        return None

    def _use_wasted(
        self,
        before: ParsedItem | None,
        after: ParsedItem | None,
        action: str,
        step: CraftStep | None,
        config: AppConfig,
    ) -> bool:
        if after is None:
            self._log(config, "COPY miss after use")
            return False
        if _item_key(before) != _item_key(after):
            self._same_streak = 0
            if self._aug_did_not_fill(before, after, action, step):
                self._log(config, "AUG   miss — slot still open")
                self._prefer_aug_orb = True
                return False
            self._prefer_aug_orb = False
            return False
        self._same_streak += 1
        self._log(config, f"SAME  {action} ×{self._same_streak}")
        if action == "augmentation":
            self._prefer_aug_orb = True
        need = 2 if action in MUST_CHANGE else SAME_STREAK
        return self._same_streak >= need

    def _aug_did_not_fill(
        self,
        before: ParsedItem | None,
        after: ParsedItem | None,
        action: str,
        step: CraftStep | None,
    ) -> bool:
        if action != "augmentation" or before is None or after is None:
            return False
        if after.rarity != "magic":
            return True
        slot = (step.fill_affix() if step else None) or "any"
        before_p, before_s = magic_slot_counts(before)
        after_p, after_s = magic_slot_counts(after)
        if slot == "prefix":
            return after_p <= before_p
        if slot == "suffix":
            return after_s <= before_s
        return after_p + after_s <= before_p + before_s

    def _pause_empty(self, action: str, config: AppConfig) -> bool:
        alt_up()
        shift_up()
        self._same_streak = 0
        self._status = "paused"
        self._log(config, f"PAUSE empty {action}")
        self._push_hud("paused")
        self._emit("paused", action)
        self._resume.clear()
        while not self._stop.is_set() and not self._escape():
            if self._resume.wait(0.05):
                break
        self._resume.clear()
        if self._stop.is_set() or self._escape():
            self._finish("stopped", self._leave)
            return False
        self._status = "running"
        self._same_streak = 0
        if self._cursor_orb:
            shift_down()
            self._locked = self._cursor_orb
        self._log(config, "RESUME")
        self._emit("resumed", action)
        self._push_hud("running")
        return self._attach_game()

    def _prepare(self, item: ParsedItem, action_id: str, config: AppConfig) -> ParsedItem | str | bool | None:
        if action_id.startswith("harvest_"):
            return None
        current = item
        for _ in range(6):
            if self._stop.is_set() or self._escape():
                return False
            if not current.identified:
                result = self._prep_use(
                    current, config, "wisdom", "run.need_wisdom", "PREP  unidentified → wisdom"
                )
                if not isinstance(result, ParsedItem):
                    return result
                current = result
                continue
            need = _rarity_need(action_id)
            if need is None or current.rarity == need:
                return None if current is item else current
            if need == "magic":
                if current.rarity == "normal":
                    spec = ("transmutation", "run.need_transmute", "PREP  normal → transmutation")
                elif current.rarity == "rare":
                    spec = ("scouring", "run.need_scour", "PREP  rare → scouring")
                else:
                    return None if current is item else current
            elif need == "rare":
                if current.rarity == "normal":
                    spec = ("alchemy", "run.need_alch", "PREP  normal → alchemy")
                elif current.rarity == "magic":
                    spec = ("regal", "run.need_regal", "PREP  magic → regal")
                else:
                    return None if current is item else current
            elif need == "normal":
                return "run.need_normal"
            else:
                return None if current is item else current
            result = self._prep_use(current, config, spec[0], spec[1], spec[2])
            if not isinstance(result, ParsedItem):
                return result
            current = result
        return current

    def _prep_use(
        self,
        before: ParsedItem,
        config: AppConfig,
        action: str,
        missing: str,
        note: str,
    ) -> ParsedItem | str | bool:
        point = config.point_for(action)
        item_pt = config.point_for("item")
        if not point or not item_pt:
            return missing
        self._log(config, note)
        for attempt in range(2):
            if self._stop.is_set() or self._escape():
                return False
            if attempt:
                self._log(config, f"RETRY {action}")
            if not self._apply(action, config, force_hold=bool(attempt)):
                if self._stop.is_set() or not game_is_active():
                    return False
                return "run.no_point"
            if not self._wait(max(self._pace, 70)):
                return False
            after = self._read_after(
                config,
                before,
                tries=12,
                wait_ms=max(self._pace, 40),
                ready=lambda item, kind=action: _prep_done(kind, item),
            )
            if _prep_done(action, after):
                self.spent[action] += 1
                self._log(config, f"USE   {action}")
                self._push_hud("running", after)
                return after
            self._log(config, f"SAME  {action} rarity={after.rarity if after else '-'}")
        if not self._pause_empty(action, config):
            return False
        return False

    def _peek_item(self, config: AppConfig) -> ParsedItem | None:
        for _ in range(2):
            if self._stop.is_set() or self._escape():
                return None
            text = self._copy_item(config, attempts=1, require_item=False)
            parsed = parse_item(text)
            if parsed:
                return parsed
            if text:
                self._log(config, f"COPY parse fail\n{text[:2000]}")
            self._nap()
        return None

    def _await_item(self, config: AppConfig, tries: int = 20) -> ParsedItem | None:
        parsed = self._read_item(config)
        if parsed:
            return parsed
        if tries <= 2:
            return None
        self._emit("log", "run.waiting_item")
        self._log(config, "WAIT item")
        for attempt in range(tries):
            if self._stop.is_set() or self._escape():
                dbg("await_item stopped")
                return None
            parsed = self._read_item(config)
            if parsed:
                dbg(f"await_item ok attempt={attempt} rarity={parsed.rarity} name={parsed.name!r}")
                return parsed
            dbg(f"await_item miss attempt={attempt}")
            self._nap(0.01)
        dbg("await_item timeout")
        return None

    def _read_item(self, config: AppConfig) -> ParsedItem | None:
        text = self._copy_item(config, attempts=2 if self._chaining else 6)
        parsed = parse_item(text)
        if text and parsed is None:
            self._log(config, f"COPY parse fail\n{text[:2000]}")
        return parsed

    def _copy_item(self, config: AppConfig, attempts: int = 6, require_item: bool = True) -> str:
        point = config.point_for("item")
        if not point:
            return ""
        focus_game()
        text = ""
        for _ in range(max(1, attempts)):
            if self._stop.is_set() or self._escape():
                break
            set_clipboard(_CLIP_MARK)
            move_to(*point)
            self._nap()
            tap_ctrl_c()
            if key_is_down(VK_CONTROL):
                dbg("copy_item ctrl still down, releasing")
                release_ctrl()
            if self._locked or self._cursor_orb:
                shift_down()
            self._nap()
            try:
                text = get_clipboard()
            except Exception:
                text = ""
            if text == _CLIP_MARK:
                text = ""
            if _is_item_text(text):
                dbg(f"copy_item ok chars={len(text)}")
                return text
            if not require_item:
                break
            if self._stop.wait(self._pace / 1000 if self._pace else 0):
                break
        if text:
            snippet = text.strip()
            if len(snippet) > 2000:
                snippet = snippet[:2000] + "\n…"
            self._log(config, f"COPY not item ({len(text)} chars)\n{snippet}")
        else:
            self._log(config, "COPY empty")
        return ""

    def _apply(self, action: str, config: AppConfig, *, force_hold: bool = False) -> bool:
        item = config.point_for("item")
        if not item:
            return False
        point = config.point_for(action)
        if not point:
            return False
        harvest = action.startswith("harvest_")
        if harvest:
            self._release_lock()
            self._click(*point, "left")
            if not self._wait(self._pace):
                return False
            apply_at = config.point_for("harvest_apply")
            if apply_at and apply_at != point:
                self._click(*apply_at, "left")
                if not self._wait(self._pace):
                    return False
            self._click(*item, "left")
            return True
        if config.shift_lock:
            if (
                action == "augmentation"
                and not self._prefer_aug_orb
                and not force_hold
                and self._aug_with_alt(item, config)
            ):
                return True
            if force_hold or self._locked != action:
                if not self._hold_currency(action, point, force=force_hold):
                    return False
            shift_down()
            self._click(*item, "left")
            return True
        self._release_lock()
        self._click(*point, "right")
        if not self._wait(self._pace):
            return False
        self._click(*item, "left")
        return True

    def _aug_with_alt(self, item: tuple[int, int], config: AppConfig) -> bool:
        """PoE 3.27: Alteration on cursor + Alt + click item uses Augment from stash."""
        alt_point = config.point_for("alteration")
        if not alt_point:
            return False
        if self._locked != "alteration":
            if not self._hold_currency("alteration", alt_point):
                return False
            if not self._wait(max(self._pace, 60)):
                return False
        shift_down()
        try:
            alt_down()
            self._nap(0.04)
            self._click(*item, "left")
        finally:
            alt_up()
        return True

    def _hold_currency(self, action: str, point: tuple[int, int], *, force: bool = False) -> bool:
        """Pick up `action`. Shift is released only while the cursor is over that stash cell."""
        alt_up()
        if not force and self._cursor_orb == action:
            shift_down()
            self._locked = action
            self._locked_point = point
            return True
        move_to(*point)
        self._nap()
        shift_up()
        self._nap()
        self._click(*point, "right")
        shift_down()
        self._locked = action
        self._cursor_orb = action
        self._locked_point = point
        return self._wait(max(self._pace, 50))

    def _park_orb(self) -> None:
        """Put the cursor orb back. Move to its slot first so Shift is not released over the item."""
        alt_up()
        point = self._locked_point if self._cursor_orb else None
        if point is not None:
            move_to(*point)
            self._nap()
        shift_up()
        if point is not None:
            self._nap()
            self._click(*point, "right")
            self._nap()
        self._locked = None
        self._cursor_orb = None
        self._locked_point = None

    def _release_lock(self, *, put_back: bool = True) -> None:
        if put_back:
            self._park_orb()
            return
        alt_up()
        shift_up()
        self._locked = None
        self._cursor_orb = None
        self._locked_point = None

    def _escape(self) -> bool:
        if not key_is_down(VK_ESCAPE):
            return False
        self._leave = "run.stopped"
        self._stop.set()
        self._release_lock()
        release_modifiers(shift=True)
        return True

    def _click(self, x: int, y: int, button: str = "left") -> None:
        click(x, y, button, pause_ms=self._pace)

    def _nap(self, extra: float = 0) -> None:
        delay = self._pace / 1000 + extra
        if delay > 0:
            time.sleep(delay)

    def _wait(self, ms: int) -> bool:
        wait_s = max(0.0, ms / 1000)
        deadline = time.time() + wait_s
        if wait_s <= 0:
            return not (self._stop.is_set() or self._escape())
        while time.time() < deadline:
            if self._stop.is_set() or self._escape():
                return False
            if not game_is_active():
                focus_game()
                if not find_game_window():
                    self._leave = "run.need_game"
                    self._stop.set()
                    self._release_lock()
                    return False
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.012, remaining))
        return True

    def _game_ok(self) -> bool:
        if self._stop.is_set() or self._escape():
            self._finish("stopped", self._leave)
            return False
        if game_is_active():
            return True
        if focus_game() and game_is_active():
            return True
        if find_game_window():
            return True
        self._leave = "run.need_game"
        self._stop.set()
        self._release_lock()
        self._finish("stopped", self._leave)
        return False

    def _spent_total(self) -> int:
        return int(sum(self.spent.values()))

    def _note_craft(self, config: AppConfig, before: int) -> bool:
        if self._spent_total() > before:
            self._log(config, "CRAFT done")
            return True
        self._log(config, "CRAFT skip")
        return False

    def _spent_line(self) -> str:
        parts = [f"{name}={count}" for name, count in self.spent.items() if count]
        return ("SPENT " + " ".join(parts)) if parts else ""

    def _finish(self, kind: str, payload: str) -> None:
        dbg(f"finish kind={kind} payload={payload}")
        if self._status in {"stopped", "done", "error"} and kind != "error":
            return
        spent_line = self._spent_line()
        if spent_line:
            self._log(load_config(), spent_line)
        self._status = kind
        self._push_hud(kind)
        self._emit(kind, payload)
        from app.craft_log import finish_session

        finish_session(kind)

    def _push_hud(self, status: str, item: ParsedItem | None = None) -> None:
        if self._stop.is_set() and status == "running":
            status = "stopped"
        payload = {
            "status": status,
            "spent": _spent_text(self.spent),
            "hits": self.hits,
            "misses": self.misses,
            "item": item.brief() if item else "",
        }
        self._emit("hud", json.dumps(payload, ensure_ascii=False))

    def snapshot(self, status: str | None = None) -> dict:
        return {
            "status": status or self._status,
            "spent": _spent_text(self.spent),
            "hits": self.hits,
            "misses": self.misses,
            "item": "",
            "chain_index": self.chain_index,
            "chain_total": self.chain_total,
        }

    def _log(self, config: AppConfig, line: str) -> None:
        ui_line = line.split("\n", 1)[0]
        self._emit("log", ui_line)
        from app.craft_log import append_session

        append_session(line)

    def _log_item(self, config: AppConfig, item: ParsedItem, label: str = "ITEM", *, force: bool = False) -> None:
        raw = (item.raw or "").strip()
        if not force and raw and raw == self._logged_raw:
            return
        self._logged_raw = raw
        self._emit("log", f"{label}  {item.brief()}")
        from app.craft_log import append_session

        append_session(f"{label}\n{raw}" if raw else f"{label}  {item.brief()}")
        if item.rarity == "magic":
            prefixes, suffixes = magic_slot_counts(item)
            self._log(config, f"SLOTS prefix={prefixes} suffix={suffixes}")


def _prep_done(action: str, item: ParsedItem | None) -> bool:
    if item is None:
        return False
    if action == "scouring":
        return item.rarity == "normal"
    if action == "transmutation":
        return item.rarity == "magic"
    if action in {"alchemy", "regal"}:
        return item.rarity == "rare"
    if action == "wisdom":
        return item.identified
    return False


def _step_still_holds(item: ParsedItem, step: CraftStep) -> bool:
    """True if an earlier step's stop-condition is still satisfied on this item."""
    kind = step.condition.kind
    if kind == "once":
        return True
    holds, _ = condition_report(item, step.condition)
    if kind == "has_mod":
        return holds
    return not holds


def _is_item_text(text: str) -> bool:
    raw = text or ""
    return "Item Class:" in raw or "Rarity:" in raw or "Класс предмета:" in raw or "Редкость:" in raw


def _item_key(item: ParsedItem | None) -> tuple | None:
    if item is None:
        return None
    return (item.rarity, item.identified, item.name, tuple(item.explicit_lines()))


def _currency_for(item: ParsedItem, step: CraftStep) -> str:
    slot = step.fill_affix()
    if not slot or item.rarity != "magic":
        return step.action_id
    prefixes, suffixes = magic_slot_counts(item)
    open_prefix = prefixes < 1
    open_suffix = suffixes < 1
    dbg(f"slots prefix={prefixes} suffix={suffixes} want={slot}")
    if slot == "any" and (open_prefix or open_suffix):
        return "augmentation"
    if slot == "prefix" and open_prefix:
        return "augmentation"
    if slot == "suffix" and open_suffix:
        return "augmentation"
    return step.action_id


def _rarity_need(action_id: str) -> str | None:
    if action_id in NEED_MAGIC:
        return "magic"
    if action_id in NEED_RARE:
        return "rare"
    if action_id in NEED_NORMAL:
        return "normal"
    return None


def _spent_text(spent: Counter[str]) -> str:
    if not spent:
        return "—"
    return "  ".join(f"{name} ×{count}" for name, count in spent.items())


def validate_ready(scenario: CraftScenario, config: AppConfig, chain: bool = False) -> str | None:
    if not scenario.steps:
        return "validate.steps"
    if chain:
        if not config.chain_grid or not config.chain_grid.cells():
            return "run.need_chain"
    elif not config.point_for("item"):
        return "run.need_item"
    missing = []
    for step in scenario.steps:
        if config.point_for(step.action_id):
            continue
        if step.action_id.startswith("harvest_") and config.point_for("harvest_apply"):
            continue
        missing.append(step.action_id)
    if missing:
        return "run.need_currency"
        if any(step.fill_affix() for step in scenario.steps) and not config.point_for("augmentation"):
            return "run.need_augment"
    return None
