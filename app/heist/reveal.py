from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.config import Rect
from app.heist.engine import (
    AssignLogger,
    capture_screen,
    cell_is_empty,
    classify_blueprint_clipboard,
    click_screen,
    copy_item_under_cursor,
    ctrl_click_screen,
    find_blueprint_item,
    inventory_grid,
    logs_dir_from_config,
    sync_inventory_grid,
    _item_class_name,
)

try:
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None
    np = None

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None


def config_path() -> Path:
    from app.paths import DATA_DIR, ensure_data_dirs

    ensure_data_dirs()
    return DATA_DIR / "heist_reveal.json"


def _apply_defaults(data: dict[str, Any]) -> dict[str, Any]:
    data.setdefault("hotkey", "f11")
    data.setdefault("exit_hotkey", "f12")
    data.setdefault("save_logs", True)
    data.setdefault("logs_dir", "heist_logs")
    data.setdefault("click_delay_sec", 0.1)
    data.setdefault("open_settle_sec", 0.35)
    data.setdefault("reveal_settle_sec", 0.28)
    data.setdefault("between_blueprints_sec", 0.15)
    data.setdefault("max_reveals_per_blueprint", 8)
    data.setdefault("min_area_frac", 0.028)
    data.setdefault("min_side_frac", 0.14)
    data.setdefault("min_area_px", 12000)
    data.setdefault("min_side_px", 90)
    data.setdefault("max_area_frac", 0.22)
    data.setdefault("blink_samples", 2)
    data.setdefault("blink_sample_sec", 0.08)
    data.setdefault("eye_match_threshold", 0.58)
    data.setdefault("take_settle_sec", 0.35)
    data.setdefault("ui_points", {})
    data.setdefault(
        "map_region",
        {"x": 300, "y": 70, "w": 1000, "h": 640},
    )
    data.setdefault(
        "inventory_grid",
        {"x": 1290, "y": 575, "w": 590, "h": 340, "cols": 5, "rows": 2},
    )
    sync_inventory_grid(data)
    return data


def default_config() -> dict[str, Any]:
    return _apply_defaults({})


def load_reveal_config(path: Optional[Path] = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else config_path()
    if not cfg_path.is_file():
        data = default_config()
        save_reveal_config(data, cfg_path)
        return data
    with cfg_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
    return _apply_defaults(data)


def save_reveal_config(cfg: dict[str, Any], path: Optional[Path] = None) -> Path:
    cfg_path = Path(path) if path else config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return cfg_path


def map_rect(cfg: dict[str, Any]) -> Rect:
    return Rect.from_dict(cfg.get("map_region"))


def sync_map_rect(cfg: dict[str, Any], rect: Rect | None = None) -> dict[str, Any]:
    current = rect or map_rect(cfg)
    cfg["map_region"] = current.to_dict()
    return cfg


def slot_point(cfg: dict[str, Any]) -> tuple[int, int] | None:
    ui = cfg.get("ui_points") or {}
    pt = ui.get("blueprint_slot")
    if isinstance(pt, (list, tuple)) and len(pt) == 2:
        return int(pt[0]), int(pt[1])
    return None


def shift_click_screen(x: int, y: int, *, delay: float = 0.0) -> None:
    from app.input_win import shift_click

    shift_click(int(x), int(y), pause_ms=25)
    if delay > 0:
        time.sleep(delay)


@dataclass(frozen=True)
class WingHit:
    x: int
    y: int
    bbox: tuple[int, int, int, int]
    area: float


_EYE_SCALES = (0.85, 1.05, 1.3, 1.6, 1.95)
_EYE_TEMPLATE = None
_EYE_TEMPLATE_TRIED = False


def _eye_template():
    global _EYE_TEMPLATE, _EYE_TEMPLATE_TRIED
    if _EYE_TEMPLATE_TRIED:
        return _EYE_TEMPLATE
    _EYE_TEMPLATE_TRIED = True
    from app.heist.engine import templates_dir

    path = templates_dir() / "wing_reveal_eye.png"
    if path.is_file() and cv2 is not None:
        _EYE_TEMPLATE = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return _EYE_TEMPLATE


def _red_excess(image):
    blue, green, red = cv2.split(image)
    return cv2.subtract(red, cv2.max(green, blue))


def _wing_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 80, 40), (14, 255, 220)),
        cv2.inRange(hsv, (168, 80, 40), (180, 255, 220)),
    )
    return cv2.bitwise_and(hue, cv2.inRange(_red_excess(image), 22, 255))


def _nms_hits(hits: list[WingHit], dist: int = 48) -> list[WingHit]:
    ordered = sorted(hits, key=lambda hit: -hit.area)
    kept: list[WingHit] = []
    gap = dist * dist
    for hit in ordered:
        if any((hit.x - other.x) ** 2 + (hit.y - other.y) ** 2 < gap for other in kept):
            continue
        kept.append(hit)
    kept.sort(key=lambda hit: (hit.x, hit.y))
    return kept


def _template_peaks(result, thresh: float, radius: int, limit: int = 6) -> list[tuple[int, int, float]]:
    peaks: list[tuple[int, int, float]] = []
    work = result.copy()
    rad = max(12, int(radius))
    for _ in range(limit):
        _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(work)
        if float(max_v) < thresh:
            break
        x, y = int(max_l[0]), int(max_l[1])
        peaks.append((x, y, float(max_v)))
        cv2.circle(work, (x, y), rad, 0, -1)
    return peaks


def find_reveal_buttons(image, cfg: dict[str, Any], *, offset: tuple[int, int] = (0, 0)) -> list[WingHit]:
    """Gold circular eye buttons at the bottom-right of large wings."""
    if cv2 is None or np is None or image is None or image.size == 0:
        return []
    tpl = _eye_template()
    if tpl is None or tpl.size == 0:
        return []
    h, w = image.shape[:2]
    thresh = float(cfg.get("eye_match_threshold", 0.58))
    ox, oy = offset
    raw: list[WingHit] = []
    for scale in _EYE_SCALES:
        tw = max(12, int(tpl.shape[1] * scale))
        th = max(12, int(tpl.shape[0] * scale))
        if th >= h or tw >= w:
            continue
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC
        scaled = cv2.resize(tpl, (tw, th), interpolation=interp)
        result = cv2.matchTemplate(image, scaled, cv2.TM_CCOEFF_NORMED)
        for x, y, score in _template_peaks(result, thresh, max(tw, th) // 2):
            cx = x + tw // 2
            cy = y + th // 2
            if cy > h * 0.84 or cx < w * 0.12:
                continue
            raw.append(
                WingHit(
                    x=ox + cx,
                    y=oy + cy,
                    bbox=(ox + x, oy + y, tw, th),
                    area=score * 1000.0,
                )
            )
    return _nms_hits(raw, dist=max(36, int(0.04 * min(h, w))))


def _peak_centers(roi, min_sep: int) -> list[tuple[int, int, float]]:
    dist = cv2.distanceTransform(roi, cv2.DIST_L2, 5)
    peak_h = float(dist.max())
    if peak_h < 8:
        return []
    k = int(max(15, min_sep))
    if k % 2 == 0:
        k += 1
    dilated = cv2.dilate(dist, np.ones((k, k), np.uint8))
    peak = (np.abs(dist - dilated) < 0.01) & (dist >= 0.42 * peak_h)
    count, _labels, _stats, cents = cv2.connectedComponentsWithStats(peak.astype(np.uint8))
    rh, rw = roi.shape[:2]
    pts: list[tuple[int, int, float]] = []
    for index in range(1, count):
        x = int(round(cents[index][0]))
        y = int(round(cents[index][1]))
        if x < 8 or y < 8 or x > rw - 9 or y > rh - 9:
            continue
        pts.append((x, y, float(dist[y, x])))
    pts.sort(key=lambda item: -item[2])
    kept: list[tuple[int, int, float]] = []
    gap = min_sep * min_sep
    for x, y, depth in pts:
        if any((x - ox) ** 2 + (y - oy) ** 2 < gap for ox, oy, _ in kept):
            continue
        kept.append((x, y, depth))
    return kept


def _wings_from_mask(mask, cfg: dict[str, Any], offset: tuple[int, int]) -> list[WingHit]:
    h, w = mask.shape[:2]
    opened = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    opened = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    min_area = max(float(cfg.get("min_area_px", 12000)), float(cfg.get("min_area_frac", 0.028)) * h * w)
    max_area = float(cfg.get("max_area_frac", 0.22)) * h * w
    min_side = max(float(cfg.get("min_side_px", 90)), float(cfg.get("min_side_frac", 0.14)) * min(h, w))
    min_sep = max(50, int(0.22 * min(h, w)))
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hits: list[WingHit] = []
    ox, oy = offset
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < min_area or area > max_area * 1.6:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if y > h * 0.72:
            continue
        roi = opened[y : y + bh, x : x + bw]
        peaks = _peak_centers(roi, min_sep)
        if not peaks:
            if min(bw, bh) < min_side:
                continue
            aspect = bw / float(max(1, bh))
            if aspect < 0.5 or aspect > 1.7:
                continue
            peaks = [(bw // 2, bh // 2, area)]
        for px, py, depth in peaks:
            hits.append(
                WingHit(
                    x=ox + x + px,
                    y=oy + y + py,
                    bbox=(ox + x, oy + y, bw, bh),
                    area=float(depth) * 100.0 if depth < area else area,
                )
            )
    return _nms_hits(hits, dist=min_sep)


def find_large_wings(image, cfg: dict[str, Any], *, offset: tuple[int, int] = (0, 0)) -> list[WingHit]:
    """Large wing reveal buttons — not small reward rooms."""
    if cv2 is None or np is None or image is None or image.size == 0:
        return []
    buttons = find_reveal_buttons(image, cfg, offset=offset)
    if buttons:
        return buttons
    return _wings_from_mask(_wing_mask(image), cfg, offset)


def _stopped(stop_event: Optional[threading.Event]) -> bool:
    return stop_event is not None and stop_event.is_set()


def _sleep(seconds: float, stop_event: Optional[threading.Event]) -> bool:
    if seconds <= 0:
        return not _stopped(stop_event)
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if _stopped(stop_event):
            return False
        time.sleep(min(0.05, end - time.monotonic()))
    return not _stopped(stop_event)


def _capture_map(cfg: dict[str, Any], sct):
    region = map_rect(cfg)
    return capture_screen((region.x, region.y, region.w, region.h), sct=sct)


def _find_slot_item(cfg: dict[str, Any], sct) -> tuple[int, int] | None:
    from app.heist.engine import templates_dir

    if cv2 is None:
        return None
    mapped = slot_point(cfg)
    region = map_rect(cfg)
    left = max(0, region.x)
    top = max(0, region.y + region.h - 80)
    width = max(80, region.w)
    height = 360
    if mapped is not None:
        left = max(0, min(left, mapped[0] - 80))
        top = max(0, min(top, mapped[1] - 60))
        right = max(left + width, mapped[0] + 80)
        bottom = max(top + height, mapped[1] + 60)
        width = right - left
        height = bottom - top
    frame, offset = capture_screen((left, top, width, height), sct=sct)
    tpl_path = templates_dir() / "blueprint_item.png"
    if not tpl_path.is_file():
        found = find_blueprint_item(frame, offset=(0, 0))
        if found is None:
            return None
        return found[0] + offset[0], found[1] + offset[1]
    tpl = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
    if tpl is None or tpl.size == 0:
        return None
    th, tw = tpl.shape[:2]
    if th > tw * 1.25:
        tpl = tpl[:tw, :]
        th, tw = tpl.shape[:2]
    if th >= frame.shape[0] or tw >= frame.shape[1]:
        return None
    res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
    _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(res)
    if max_v < 0.58:
        return None
    return offset[0] + max_l[0] + tw // 2, offset[1] + max_l[1] + th // 2


def _take_blueprint_back(cfg: dict[str, Any], sct, logger: AssignLogger, delay: float) -> bool:
    from app.heist.engine import focus_game_window

    focus_game_window()
    mapped = slot_point(cfg)
    slot = mapped or _find_slot_item(cfg, sct)
    if slot is None:
        logger.log("blueprint slot not found — Shift+click skipped")
        return False
    logger.log(f"SHIFT+click blueprint ({slot[0]},{slot[1]})")
    shift_click_screen(slot[0], slot[1], delay=delay)
    settle = min(0.22, float(cfg.get("take_settle_sec", 0.35)))
    if settle > 0:
        time.sleep(settle)
    if mapped is not None:
        return True
    still = _find_slot_item(cfg, sct)
    if still is None:
        return True
    logger.log("slot still occupied — Shift+click retry")
    shift_click_screen(still[0], still[1], delay=delay)
    time.sleep(max(0.15, settle))
    return _find_slot_item(cfg, sct) is None


def _scan_wings(cfg: dict[str, Any], sct) -> list[WingHit]:
    frame, offset = _capture_map(cfg, sct)
    buttons = find_reveal_buttons(frame, cfg, offset=offset)
    if buttons:
        return buttons
    return _wings_from_mask(_wing_mask(frame), cfg, offset)


def reveal_one_blueprint(
    cfg: dict[str, Any],
    *,
    sct,
    logger: AssignLogger,
    stop_event: Optional[threading.Event] = None,
) -> int:
    delay = float(cfg.get("click_delay_sec", 0.1))
    settle = float(cfg.get("reveal_settle_sec", 0.28))
    blink = float(cfg.get("blink_sample_sec", 0.08))
    samples = max(1, int(cfg.get("blink_samples", 2)))
    limit = max(1, int(cfg.get("max_reveals_per_blueprint", 8)))
    done = 0
    for _ in range(limit):
        if _stopped(stop_event):
            break
        wings = _scan_wings(cfg, sct)
        extra = 1
        while not wings and extra < samples:
            if not _sleep(blink, stop_event):
                return done
            wings = _scan_wings(cfg, sct)
            extra += 1
        if not wings:
            break
        wing = wings[0]
        logger.log(f"REVEAL wing ({wing.x},{wing.y}) {wing.bbox[2]}x{wing.bbox[3]}")
        click_screen(wing.x, wing.y, delay=delay)
        done += 1
        if not _sleep(settle, stop_event):
            break
    return done


def _peek_cell(x: int, y: int) -> tuple[str, str]:
    text = copy_item_under_cursor(x, y, hover_sec=0.1, settle_sec=0.1, retries=2)
    kind = classify_blueprint_clipboard(text)
    return kind, _item_class_name(text) or (text.splitlines()[0].strip() if text.strip() else "")


def reveal_blueprints(
    cfg: Optional[dict[str, Any]] = None,
    *,
    stop_event: Optional[threading.Event] = None,
    on_log=None,
    on_hud=None,
) -> int:
    if mss is None or cv2 is None:
        raise ImportError("Install opencv-python, mss and numpy: pip install opencv-python mss numpy")
    if cfg is None:
        cfg = load_reveal_config()
    sync_inventory_grid(cfg)
    grid = inventory_grid(cfg)
    cells = grid.cells()
    delay = float(cfg.get("click_delay_sec", 0.1))
    open_settle = float(cfg.get("open_settle_sec", 0.35))
    between = float(cfg.get("between_blueprints_sec", 0.15))
    logger = AssignLogger(logs_dir_from_config(cfg), enabled=bool(cfg.get("save_logs", True)), on_log=on_log)
    total = 0
    try:
        logger.log("=" * 60)
        logger.log(f"REVEAL START grid={grid.cols}x{grid.rows} cells={len(cells)}")
        if not cells:
            logger.log("Inventory grid is empty — set overlay first")
            return 0
        with mss.mss() as sct:
            for index, cell in enumerate(cells, start=1):
                if _stopped(stop_event):
                    logger.log("STOPPED by user")
                    break
                frame, offset = capture_screen(sct=sct)
                if cell_is_empty(frame, cell, cfg, offset=offset):
                    logger.log(f"skip empty cell {index}/{len(cells)}")
                    later = cells[index:]
                    if not later or all(cell_is_empty(frame, extra, cfg, offset=offset) for extra in later):
                        logger.log("No more blueprints in inventory area")
                        break
                    continue
                x, y = cell.click
                kind, label = _peek_cell(x, y)
                if kind == "fail":
                    logger.log(f"skip cell {index}/{len(cells)} — could not read item")
                    continue
                if kind == "other":
                    logger.log(f"skip cell {index}/{len(cells)} — not a blueprint ({label or '?'})")
                    continue
                if kind == "confirmed":
                    logger.log(f"skip cell {index}/{len(cells)} — all wings already revealed")
                    continue
                if on_hud is not None:
                    try:
                        on_hud(f"{index}/{len(cells)}", f"OPEN {index}/{len(cells)}")
                    except Exception:
                        pass
                logger.log(f"OPEN blueprint {index}/{len(cells)} ({x},{y}) {label}")
                ctrl_click_screen(x, y, delay=delay)
                ready_until = time.monotonic() + max(0.12, open_settle)
                wings: list[WingHit] = []
                while time.monotonic() < ready_until:
                    if _stopped(stop_event):
                        break
                    wings = _scan_wings(cfg, sct)
                    if wings:
                        break
                    if not _sleep(0.05, stop_event):
                        break
                if _stopped(stop_event):
                    break
                revealed = 0
                if wings:
                    wing = wings[0]
                    logger.log(f"REVEAL wing ({wing.x},{wing.y}) {wing.bbox[2]}x{wing.bbox[3]}")
                    click_screen(wing.x, wing.y, delay=delay)
                    revealed = 1
                    if _sleep(float(cfg.get("reveal_settle_sec", 0.28)), stop_event):
                        revealed += reveal_one_blueprint(cfg, sct=sct, logger=logger, stop_event=stop_event)
                else:
                    revealed = reveal_one_blueprint(cfg, sct=sct, logger=logger, stop_event=stop_event)
                logger.log(f"wings revealed={revealed}")
                total += revealed
                taken = _take_blueprint_back(cfg, sct, logger, delay)
                logger.log("blueprint returned to inventory" if taken else "could not return blueprint")
                if not taken:
                    logger.log("Stop: blueprint still in the NPC slot")
                    break
                if not _sleep(between, stop_event):
                    break
        logger.log("=" * 60)
        logger.log(f"REVEAL TOTAL wings={total}")
        return total
    except Exception as exc:  # noqa: BLE001
        import traceback

        logger.log(f"EXCEPTION: {exc}")
        logger.log(traceback.format_exc())
        raise
    finally:
        logger.close()
