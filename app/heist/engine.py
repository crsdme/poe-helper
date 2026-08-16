"""Job-slot search on Blueprint Confirm (groups of 3)."""

from __future__ import annotations

import json
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Tuple, Union

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


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    from app.paths import ROOT

    return ROOT


def resource_dir() -> Path:
    from app.paths import BUNDLE

    return BUNDLE


def templates_dir() -> Path:
    from app.paths import BUNDLE, ROOT

    for root in (BUNDLE, ROOT):
        path = root / "app" / "assets" / "heist"
        if path.is_dir():
            return path
    return ROOT / "app" / "assets" / "heist"


def config_path() -> Path:
    from app.paths import DATA_DIR, ensure_data_dirs

    ensure_data_dirs()
    return DATA_DIR / "heist.json"


BASE_DIR = resource_dir()
CONFIG_PATH = None  # resolved at runtime via config_path()

BBox = Tuple[int, int, int, int]
Point = Tuple[int, int]
ImageLike = Union[np.ndarray, str]
Region = Tuple[int, int, int, int]


@dataclass(frozen=True)
class InventoryBlueprint:
    """Р‘Р»СЋРїСЂРёРЅС‚ РІ РёРЅРІРµРЅС‚Р°СЂРµ."""

    x: int
    y: int
    score: float = 1.0
    bbox: BBox = (0, 0, 0, 0)

    @property
    def center(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class ContractHit:
    """РћРґРЅР° РЅР°Р№РґРµРЅРЅР°СЏ РєР°СЂС‚РѕС‡РєР° РєРѕРЅС‚СЂР°РєС‚Р°."""

    x: int
    y: int
    bbox: BBox
    area: float
    score: float = 1.0
    group: int = -1

    @property
    def center(self) -> Point:
        return (self.x, self.y)


@dataclass(frozen=True)
class RogueHit:
    """РћРґРёРЅ rogue РІ РјРѕРґР°Р»СЊРЅРѕРј РѕРєРЅРµ РІС‹Р±РѕСЂР°."""

    x: int
    y: int
    bbox: BBox
    radius: int = 0

    @property
    def center(self) -> Point:
        return (self.x, self.y)


def _apply_defaults(data: dict[str, Any]) -> dict[str, Any]:
    screen = data.setdefault("screen", {})
    screen.setdefault("left", 0)
    screen.setdefault("top", 0)
    screen.setdefault("width", 1920)
    screen.setdefault("height", 1080)
    data.setdefault("map_margins", {"left": 280, "top": 55, "right": 270, "bottom": 100})
    data.setdefault("hotkey", "f9")
    data.setdefault("exit_hotkey", "f10")
    data.setdefault("scan_interval_ms", 250)
    data.setdefault("print_empty", False)
    data.setdefault("save_logs", True)
    data.setdefault("verbose_logs", False)
    data.setdefault("logs_dir", "heist_logs")
    data.setdefault("skip_assigned_slots", True)
    data.setdefault("assigned_min_face_std", 52.0)
    data.setdefault("assigned_max_parch_frac", 0.70)
    data.setdefault("parchment_lower", [10, 25, 140])
    data.setdefault("parchment_upper", [35, 120, 255])
    data.setdefault("min_area", 200)
    data.setdefault("max_area", 10000)
    data.setdefault("min_width", 18)
    data.setdefault("max_width", 90)
    data.setdefault("min_height", 28)
    data.setdefault("max_height", 120)
    data.setdefault("min_aspect", 1.05)
    data.setdefault("max_aspect", 2.4)
    data.setdefault("modal_timeout_sec", 1.5)
    data.setdefault("modal_close_timeout_sec", 1.0)
    data.setdefault("click_delay_sec", 0.1)
    data.setdefault("between_contracts_sec", 0.1)
    data.setdefault("poll_interval_sec", 0.03)
    data.setdefault("mode", "assign")
    data.setdefault("pan_if_not_multiple_of_3", True)
    data.setdefault("pan_if_left_panel_covers", True)
    data.setdefault("pan_drag_px", 180)
    data.setdefault("pan_drag_duration_sec", 0.2)
    data.setdefault("pan_settle_sec", 0.3)
    data.setdefault("pan_max_attempts", 4)
    data.setdefault("pan_left_clear_pad_px", 36)
    if int(data.get("pan_drag_px", 180) or 180) <= 40:
        data["pan_drag_px"] = 180
    data.setdefault("confirm_plans_after_assign", True)
    data.setdefault("confirm_delay_sec", 0.18)
    data.setdefault("ctrl_click_after_confirm", True)
    data.setdefault("confirm_below_blueprint", 70)
    data.setdefault("confirm_match_threshold", 0.72)
    data.setdefault("frame_min_aspect", 1.15)
    data.setdefault("frame_min_std", 18.0)
    data.setdefault("loop_blueprints", True)
    data.setdefault("max_blueprints", 30)
    data.setdefault("blueprint_open_settle_sec", 0.2)
    data.setdefault("blueprint_ready_timeout_sec", 3.0)
    data.setdefault("max_job_slot_y", 680)
    data.setdefault("inventory_wait_before_i_sec", 0.25)
    data.setdefault("inventory_match_threshold", 0.72)
    data.setdefault("inventory_confirmed_threshold", 0.72)
    data.setdefault("inventory_confirmed_margin", 0.12)
    data.setdefault("inventory_use_clipboard", False)
    data.setdefault("clipboard_hover_sec", 0.28)
    data.setdefault("rogue_click_settle_sec", 0.18)
    data.setdefault("rogue_click_retries", 2)
    data.setdefault("ui_points", {})
    data.setdefault("inventory_region", {"left": 1290, "top": 575, "width": 590, "height": 340})
    inv = data["inventory_region"]
    data.setdefault(
        "inventory_grid",
        {
            "x": int(inv.get("left", 1290)),
            "y": int(inv.get("top", 575)),
            "w": int(inv.get("width", 590)),
            "h": int(inv.get("height", 340)),
            "cols": 5,
            "rows": 2,
        },
    )
    data["skip_assigned_slots"] = True
    data["confirm_plans_after_assign"] = True
    data["loop_blueprints"] = True
    data.setdefault("job_inventory_mask_top", 640)
    data.setdefault("inventory_open_settle_sec", 0.25)
    data.setdefault("blueprint_confirm_only_after_sec", 0.35)
    data.setdefault("inventory_template_scales", [1.0])
    return data


def default_config() -> dict[str, Any]:
    return _apply_defaults({})


def load_config(path: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else config_path()
    if not cfg_path.is_file():
        data = default_config()
        save_config(data, cfg_path)
        return data
    with cfg_path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
    return _apply_defaults(data)


def save_config(cfg: dict[str, Any], path: Optional[Union[str, Path]] = None) -> Path:
    cfg_path = Path(path) if path else config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return cfg_path


load_heist_config = load_config
save_heist_config = save_config


def region_from_config(cfg: dict[str, Any]) -> Region:
    s = cfg["screen"]
    return (int(s["left"]), int(s["top"]), int(s["width"]), int(s["height"]))


def logs_dir_from_config(cfg: dict[str, Any]) -> Path:
    from app.paths import DATA_DIR

    raw = Path(str(cfg.get("logs_dir", "heist_logs")))
    path = raw if raw.is_absolute() else DATA_DIR / raw
    path.mkdir(parents=True, exist_ok=True)
    return path


def inventory_grid(cfg: dict[str, Any]):
    from app.config import ItemGrid

    data = cfg.get("inventory_grid")
    if not isinstance(data, dict):
        inv = cfg.get("inventory_region") or {}
        data = {
            "x": int(inv.get("left", 1290)),
            "y": int(inv.get("top", 575)),
            "w": int(inv.get("width", 590)),
            "h": int(inv.get("height", 340)),
            "cols": 5,
            "rows": 2,
        }
    return ItemGrid.from_dict(data)


def sync_inventory_grid(cfg: dict[str, Any], grid=None) -> dict[str, Any]:
    current = grid or inventory_grid(cfg)
    cfg["inventory_grid"] = current.to_dict()
    cfg["inventory_region"] = {
        "left": current.x,
        "top": current.y,
        "width": current.w,
        "height": current.h,
    }
    cfg["max_blueprints"] = max(1, current.cols * current.rows)
    cfg["loop_blueprints"] = True
    cfg["skip_assigned_slots"] = True
    cfg["confirm_plans_after_assign"] = True
    return cfg


def _load_image(source: ImageLike) -> np.ndarray:
    if isinstance(source, np.ndarray):
        if source.ndim == 2:
            return cv2.cvtColor(source, cv2.COLOR_GRAY2BGR)
        if source.shape[2] == 4:
            return cv2.cvtColor(source, cv2.COLOR_BGRA2BGR)
        return source

    img = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"РќРµ СѓРґР°Р»РѕСЃСЊ РїСЂРѕС‡РёС‚Р°С‚СЊ РёР·РѕР±СЂР°Р¶РµРЅРёРµ: {source}")
    return img


def capture_screen(
    region: Optional[Region] = None,
    *,
    sct: Any = None,
) -> Tuple[np.ndarray, Point]:
    if mss is None:
        raise ImportError("РЈСЃС‚Р°РЅРѕРІРёС‚Рµ Р·Р°РІРёСЃРёРјРѕСЃС‚Рё: pip install -r requirements.txt")

    def _grab(instance: Any) -> Tuple[np.ndarray, Point]:
        if region is None:
            mon = instance.monitors[1]
            grab = instance.grab(mon)
            offset = (int(mon["left"]), int(mon["top"]))
        else:
            left, top, width, height = region
            grab = instance.grab(
                {
                    "left": int(left),
                    "top": int(top),
                    "width": int(width),
                    "height": int(height),
                }
            )
            offset = (int(left), int(top))
        frame = np.asarray(grab, dtype=np.uint8)
        bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return bgr, offset

    if sct is not None:
        return _grab(sct)

    with mss.mss() as owned:
        return _grab(owned)


def _apply_map_margins(mask: np.ndarray, margins: dict[str, Any]) -> np.ndarray:
    h, w = mask.shape[:2]
    left = max(0, int(margins.get("left", 0)))
    top = max(0, int(margins.get("top", 0)))
    right = max(0, int(margins.get("right", 0)))
    bottom = max(0, int(margins.get("bottom", 0)))
    out = mask.copy()
    if top:
        out[:top, :] = 0
    if bottom and bottom < h:
        out[h - bottom :, :] = 0
    if left:
        out[:, :left] = 0
    if right and right < w:
        out[:, w - right :] = 0
    return out


def _job_map_inventory_region(cfg: dict[str, Any]) -> dict[str, int]:
    """
    Р—РѕРЅР° РёРЅРІРµРЅС‚Р°СЂСЏ РґР»СЏ РјР°СЃРєРёСЂРѕРІР°РЅРёСЏ РїСЂРё РїРѕРёСЃРєРµ job-СЃР»РѕС‚РѕРІ.
    top РїРѕРґРЅРёРјР°РµРј (job_inventory_mask_top), С‡С‚РѕР±С‹ РЅРµ СЃСЉРµРґР°С‚СЊ РїСЂР°РІС‹Рµ СЃР»РѕС‚С‹ РєР°СЂС‚С‹.
    РџРѕРёСЃРє Р±Р»СЋРїСЂРёРЅС‚РѕРІ РІ РёРЅРІРµРЅС‚Р°СЂРµ РїРѕ-РїСЂРµР¶РЅРµРјСѓ РёСЃРїРѕР»СЊР·СѓРµС‚ inventory_region С†РµР»РёРєРѕРј.
    """
    inv = cfg.get("inventory_region") or {}
    if not inv:
        return {}
    top_min = int(cfg.get("job_inventory_mask_top", 640))
    left = int(inv.get("left", 0))
    top = max(int(inv.get("top", 0)), top_min)
    width = int(inv.get("width", 0))
    height = int(inv.get("height", 0))
    # РЎРѕС…СЂР°РЅСЏРµРј РЅРёР¶РЅСЋСЋ РіСЂР°РЅРёС†Сѓ РёСЃС…РѕРґРЅРѕР№ РѕР±Р»Р°СЃС‚Рё РёРЅРІРµРЅС‚Р°СЂСЏ.
    bottom = int(inv.get("top", 0)) + height
    height = max(0, bottom - top)
    return {"left": left, "top": top, "width": width, "height": height}


def _blank_inventory_region(
    image_or_mask: np.ndarray,
    cfg: dict[str, Any],
    *,
    fill: int = 0,
    for_job_map: bool = True,
) -> np.ndarray:
    """Р—Р°С‚РёСЂР°РµС‚ Р·РѕРЅСѓ РёРЅРІРµРЅС‚Р°СЂСЏ вЂ” РёРЅР°С‡Рµ РёРєРѕРЅРєРё BP Р»РѕРІСЏС‚СЃСЏ РєР°Рє job-СЃР»РѕС‚С‹."""
    inv = _job_map_inventory_region(cfg) if for_job_map else (cfg.get("inventory_region") or {})
    if not inv:
        return image_or_mask
    h, w = image_or_mask.shape[:2]
    x0 = max(0, int(inv.get("left", 0)))
    y0 = max(0, int(inv.get("top", 0)))
    x1 = min(w, x0 + int(inv.get("width", 0)))
    y1 = min(h, y0 + int(inv.get("height", 0)))
    if x1 <= x0 or y1 <= y0:
        return image_or_mask
    out = image_or_mask.copy()
    if out.ndim == 2:
        out[y0:y1, x0:x1] = fill
    else:
        out[y0:y1, x0:x1] = fill
    return out


def _hit_in_inventory(hit: ContractHit, cfg: dict[str, Any], *, for_job_map: bool = True) -> bool:
    inv = _job_map_inventory_region(cfg) if for_job_map else (cfg.get("inventory_region") or {})
    if not inv:
        return False
    x0 = int(inv.get("left", 0))
    y0 = int(inv.get("top", 0))
    x1 = x0 + int(inv.get("width", 0))
    y1 = y0 + int(inv.get("height", 0))
    return x0 <= hit.x <= x1 and y0 <= hit.y <= y1


def _bbox_gap(a: ContractHit, b: ContractHit) -> int:
    """Р“РѕСЂРёР·РѕРЅС‚Р°Р»СЊРЅС‹Р№ Р·Р°Р·РѕСЂ РјРµР¶РґСѓ bbox a (СЃР»РµРІР°) Рё b (СЃРїСЂР°РІР°)."""
    return b.bbox[0] - (a.bbox[0] + a.bbox[2])


def _valid_wing_run(
    run: Sequence[ContractHit],
    *,
    max_width_delta: int = 12,
    min_gap: int = -2,
    max_gap: int = 30,
) -> bool:
    """РџСЂРѕРІРµСЂСЏРµС‚, С‡С‚Рѕ РєР°СЂС‚РѕС‡РєРё вЂ” СЃРѕСЃРµРґРЅРёРµ СЃР»РѕС‚С‹ РѕРґРЅРѕРіРѕ РєСЂС‹Р»Р°."""
    if len(run) < 2:
        return False
    widths = [t.bbox[2] for t in run]
    if max(widths) - min(widths) > max_width_delta:
        return False
    for i in range(len(run) - 1):
        g = _bbox_gap(run[i], run[i + 1])
        if g < min_gap or g > max_gap:
            return False
    return True


def _cluster_triplets(
    hits: Sequence[ContractHit],
    *,
    y_tol: int = 18,
    require_triplets: bool = True,
    allow_pairs: bool = True,
) -> list[ContractHit]:
    """
    Р“СЂСѓРїРїРёСЂСѓРµС‚ РєР°СЂС‚РѕС‡РєРё РїРѕ СЂСЏРґР°Рј, Р·Р°С‚РµРј СЂРµР¶РµС‚ СЂСЏРґ РЅР° РєСЂС‹Р»СЊСЏ РїРѕ Р±РѕР»СЊС€РѕРјСѓ
    РіРѕСЂРёР·РѕРЅС‚Р°Р»СЊРЅРѕРјСѓ СЂР°Р·СЂС‹РІСѓ. РћСЃС‚Р°РІР»СЏРµС‚ РіСЂСѓРїРїС‹ РїРѕ 3 (Рё РїРѕ 2, РµСЃР»Рё allow_pairs).

    Р’Р°Р¶РЅРѕ: СЃРѕСЃРµРґРЅРёРµ РєСЂС‹Р»СЊСЏ С‡Р°СЃС‚Рѕ РЅР° РїРѕС‡С‚Рё РѕРґРЅРѕР№ Y вЂ” РЅРµР»СЊР·СЏ Р±СЂР°С‚СЊ С‚СЂРѕР№РєРё
    В«СЃР»РµРІР° РЅР°РїСЂР°РІРѕ С€Р°РіРѕРј 3В» РїРѕ РІСЃРµРјСѓ СЂСЏРґСѓ, РёРЅР°С‡Рµ 2+3 СЃРєР»РµРёРІР°СЋС‚СЃСЏ РІ РјСѓСЃРѕСЂ.
    """
    items = sorted(hits, key=lambda h: (h.y, h.x))
    if not items:
        return []

    used = [False] * len(items)
    rows: list[list[ContractHit]] = []

    for i, a in enumerate(items):
        if used[i]:
            continue
        row = [a]
        used[i] = True
        for j, b in enumerate(items):
            if used[j]:
                continue
            if abs(a.y - b.y) <= y_tol:
                used[j] = True
                row.append(b)
        row.sort(key=lambda h: h.x)
        rows.append(row)

    result: list[ContractHit] = []
    gi = 0
    for row in rows:
        if not require_triplets:
            for t in row:
                result.append(
                    ContractHit(
                        x=t.x,
                        y=t.y,
                        bbox=t.bbox,
                        area=t.area,
                        score=t.score,
                        group=gi,
                    )
                )
            gi += 1
            continue

        # Р РµР¶РµРј СЂСЏРґ РЅР° В«РєСЂС‹Р»СЊСЏВ» С‚Р°Рј, РіРґРµ СЃРѕСЃРµРґРЅРёРµ РєР°СЂС‚РѕС‡РєРё РґР°Р»РµРєРѕ РґСЂСѓРі РѕС‚ РґСЂСѓРіР°
        runs: list[list[ContractHit]] = []
        cur: list[ContractHit] = [row[0]]
        for nxt in row[1:]:
            if _bbox_gap(cur[-1], nxt) <= 30:
                cur.append(nxt)
            else:
                runs.append(cur)
                cur = [nxt]
        runs.append(cur)

        for run in runs:
            # Р•СЃР»Рё РІ РѕРґРЅРѕРј РєСЂС‹Р»Рµ >3 (С€СѓРј), РІС‹СЂРµР·Р°РµРј РІР°Р»РёРґРЅС‹Рµ РѕРєРЅР° РїРѕ 3, Р·Р°С‚РµРј РїРѕ 2
            sizes = (3, 2) if allow_pairs else (3,)
            taken = [False] * len(run)
            for size in sizes:
                if len(run) < size:
                    continue
                for start in range(0, len(run) - size + 1):
                    if any(taken[start : start + size]):
                        continue
                    win = run[start : start + size]
                    if not _valid_wing_run(win):
                        continue
                    for t in win:
                        result.append(
                            ContractHit(
                                x=t.x,
                                y=t.y,
                                bbox=t.bbox,
                                area=t.area,
                                score=t.score,
                                group=gi,
                            )
                        )
                    for k in range(start, start + size):
                        taken[k] = True
                    gi += 1

    result.sort(key=lambda h: (h.group, h.x))
    return result


def find_contracts_parchment(
    image: np.ndarray,
    *,
    parchment_lower: Sequence[int],
    parchment_upper: Sequence[int],
    map_margins: Optional[dict[str, Any]] = None,
    min_area: float = 200,
    max_area: float = 4500,
    min_width: int = 18,
    max_width: int = 80,
    min_height: int = 28,
    max_height: int = 120,
    min_aspect: float = 1.05,
    max_aspect: float = 2.4,
    require_triplets: bool = True,
    offset: Point = (0, 0),
    cluster: bool = True,
) -> list[ContractHit]:
    """РС‰РµС‚ СЃРІРµС‚Р»С‹Рµ РїРµСЂРіР°РјРµРЅС‚РЅС‹Рµ РєР°СЂС‚РѕС‡РєРё (+ РѕРїС†РёРѕРЅР°Р»СЊРЅРѕ С„РёР»СЊС‚СЂ РіСЂСѓРїРї)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower = np.asarray(parchment_lower, dtype=np.uint8)
    upper = np.asarray(parchment_upper, dtype=np.uint8)
    mask = cv2.inRange(hsv, lower, upper)

    if map_margins:
        mask = _apply_map_margins(mask, map_margins)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    ox, oy = offset
    hits: list[ContractHit] = []

    for cnt in contours:
        area = float(cv2.contourArea(cnt))
        if area < min_area or area > max_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if w < min_width or w > max_width or h < min_height or h > max_height:
            continue
        aspect = h / float(w) if w else 0.0
        if aspect < min_aspect or aspect > max_aspect:
            continue

        hits.append(
            ContractHit(
                x=ox + x + w // 2,
                y=oy + y + h // 2,
                bbox=(ox + x, oy + y, w, h),
                area=area,
                score=1.0,
            )
        )

    if not cluster:
        return hits
    return _cluster_triplets(hits, require_triplets=require_triplets)


def find_contracts_frames(
    image: np.ndarray,
    *,
    map_margins: Optional[dict[str, Any]] = None,
    min_width: int = 26,
    max_width: int = 85,
    min_height: int = 40,
    max_height: int = 110,
    min_aspect: float = 1.15,
    max_aspect: float = 2.5,
    min_std: float = 18.0,
    min_area: float = 850,
    max_area: float = 10000,
    offset: Point = (0, 0),
) -> list[ContractHit]:
    """
    РС‰РµС‚ РїСЂСЏРјРѕСѓРіРѕР»СЊРЅС‹Рµ СЂР°РјРєРё СЃР»РѕС‚РѕРІ (РІ С‚.С‡. СѓР¶Рµ Р·Р°РїРѕР»РЅРµРЅРЅС‹Рµ РїРѕСЂС‚СЂРµС‚РѕРј).
    РџРµСЂРіР°РјРµРЅС‚РЅС‹Р№ HSV РЅР° С‚С‘РјРЅС‹С… РїРѕСЂС‚СЂРµС‚Р°С… СЂРІС‘С‚СЃСЏ вЂ” СЂР°РјРєРё РїРѕ РєСЂР°СЋ РЅР°РґС‘Р¶РЅРµРµ.

    min_aspect >= 1.15 РѕС‚СЃРµРєР°РµС‚ РїРѕС‡С‚Рё РєРІР°РґСЂР°С‚РЅС‹Рµ РєРѕРјРЅР°С‚С‹ РєР°СЂС‚С‹ СЃРЅРёР·Сѓ.
    min_std РѕС‚СЃРµРєР°РµС‚ РїСѓСЃС‚С‹Рµ РїР»РёС‚РєРё СЃ РЅРёР·РєРѕР№ С‚РµРєСЃС‚СѓСЂРѕР№.
    """
    h, w = image.shape[:2]
    margins = map_margins or {}
    x0 = int(margins.get("left", 0))
    y0 = int(margins.get("top", 0))
    x1 = w - int(margins.get("right", 0))
    y1 = h - int(margins.get("bottom", 0))
    if x1 <= x0 or y1 <= y0:
        return []

    roi = image[y0:y1, x0:x1]
    value = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)[:, :, 2]
    edges = cv2.Canny(value, 25, 80)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    ox, oy = offset
    raw: list[ContractHit] = []
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = float(bw * bh)
        if area < min_area or area > max_area:
            continue
        if bw < min_width or bw > max_width or bh < min_height or bh > max_height:
            continue
        aspect = bh / float(bw) if bw else 0.0
        if aspect < min_aspect or aspect > max_aspect:
            continue
        pad = 3
        if bw <= 2 * pad or bh <= 2 * pad:
            continue
        patch = roi[y + pad : y + bh - pad, x + pad : x + bw - pad]
        if patch.size == 0:
            continue
        std = float(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).std())
        if std < min_std:
            continue
        raw.append(
            ContractHit(
                x=ox + x0 + x + bw // 2,
                y=oy + y0 + y + bh // 2,
                bbox=(ox + x0 + x, oy + y0 + y, bw, bh),
                area=area,
                score=std,
            )
        )

    kept: list[ContractHit] = []
    for hit in sorted(raw, key=lambda t: -t.score):
        if any(abs(hit.x - k.x) < 18 and abs(hit.y - k.y) < 18 for k in kept):
            continue
        kept.append(hit)
    return kept


def _merge_contract_hits(*groups: Sequence[ContractHit], dist: int = 20) -> list[ContractHit]:
    merged: list[ContractHit] = []
    for group in groups:
        for hit in group:
            if any(abs(hit.x - m.x) < dist and abs(hit.y - m.y) < dist for m in merged):
                continue
            merged.append(hit)
    return merged


def _slot_face_metrics(
    image: np.ndarray,
    hit: ContractHit,
    *,
    offset: Point = (0, 0),
) -> tuple[float, float]:
    """std СЏСЂРєРѕСЃС‚Рё Рё РґРѕР»СЏ РїРµСЂРіР°РјРµРЅС‚Р° РІ РІРµСЂС…РЅРµР№ С‡Р°СЃС‚Рё СЃР»РѕС‚Р° (Р·РѕРЅР° В«Р»РёС†Р°В»)."""
    ox, oy = offset
    x, y, w, h = hit.bbox
    x -= ox
    y -= oy
    if w < 8 or h < 8:
        return 0.0, 0.0
    y0 = max(0, y)
    y1 = min(image.shape[0], y + h)
    x0 = max(0, x)
    x1 = min(image.shape[1], x + w)
    patch = image[y0:y1, x0:x1]
    if patch.size < 50:
        return 0.0, 0.0
    ph, pw = patch.shape[:2]
    face = patch[int(ph * 0.08) : int(ph * 0.55), int(pw * 0.12) : int(pw * 0.88)]
    if face.size < 50:
        face = patch
    gray = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(face, cv2.COLOR_BGR2HSV)
    lower = np.asarray([10, 25, 140], dtype=np.uint8)
    upper = np.asarray([35, 120, 255], dtype=np.uint8)
    parch = float(cv2.inRange(hsv, lower, upper).mean() / 255.0)
    return float(gray.std()), parch


def slot_looks_assigned(
    image: np.ndarray,
    hit: ContractHit,
    *,
    offset: Point = (0, 0),
    min_face_std: float = 52.0,
    max_parch_frac: float = 0.70,
) -> bool:
    """
    True = РІ СЃР»РѕС‚Рµ СѓР¶Рµ РїРѕСЂС‚СЂРµС‚ rogue (РЅРµ РєР»РёРєР°РµРј РїРѕРІС‚РѕСЂРЅРѕ).
    РџСѓСЃС‚РѕР№ СЃР»РѕС‚: РЅР°РІС‹Рє РЅР° РїРµСЂРіР°РјРµРЅС‚Рµ в†’ РІС‹СЃРѕРєРёР№ parchment, РЅРёР¶Рµ std В«Р»РёС†Р°В».
    """
    std, parch = _slot_face_metrics(image, hit, offset=offset)
    return std >= min_face_std and parch < max_parch_frac


def filter_empty_job_slots(
    image: np.ndarray,
    hits: Sequence[ContractHit],
    *,
    offset: Point = (0, 0),
    min_face_std: float = 52.0,
    max_parch_frac: float = 0.70,
) -> list[ContractHit]:
    """РћСЃС‚Р°РІР»СЏРµС‚ С‚РѕР»СЊРєРѕ РЅРµР·Р°РїРѕР»РЅРµРЅРЅС‹Рµ СЃР»РѕС‚С‹ (РёРєРѕРЅРєР° РЅР°РІС‹РєР°, Р±РµР· rogue)."""
    return [
        h
        for h in hits
        if not slot_looks_assigned(
            image,
            h,
            offset=offset,
            min_face_std=min_face_std,
            max_parch_frac=max_parch_frac,
        )
    ]


def find_contracts(
    image: Optional[ImageLike] = None,
    *,
    region: Optional[Region] = None,
    cfg: Optional[dict[str, Any]] = None,
    screen_coords: bool = True,
) -> list[ContractHit]:
    """РќР°С…РѕРґРёС‚ РєР°СЂС‚РѕС‡РєРё РєРѕРЅС‚СЂР°РєС‚РѕРІ: РїРѕ СѓРјРѕР»С‡Р°РЅРёСЋ С‚РѕР»СЊРєРѕ РџРЈРЎРўР«Р• СЃР»РѕС‚С‹."""
    if cfg is None:
        cfg = load_config()

    if image is None:
        frame, offset = capture_screen(region or region_from_config(cfg))
        ox, oy = offset if screen_coords else (0, 0)
    else:
        frame = _load_image(image)
        ox, oy = (0, 0)

    margins = cfg.get("map_margins") or {}
    # РРЅРІРµРЅС‚Р°СЂСЊ СЃРїСЂР°РІР° СЃРЅРёР·Сѓ РјР°СЃРєРёСЂСѓРµРј вЂ” РёРЅР°С‡Рµ РёРєРѕРЅРєРё BP = Р»РѕР¶РЅС‹Рµ job-СЃР»РѕС‚С‹
    frame_map = _blank_inventory_region(frame, cfg, fill=0)
    parchment = find_contracts_parchment(
        frame_map,
        parchment_lower=cfg["parchment_lower"],
        parchment_upper=cfg["parchment_upper"],
        map_margins=margins,
        min_area=float(cfg["min_area"]),
        max_area=float(cfg["max_area"]),
        min_width=int(cfg["min_width"]),
        max_width=int(cfg["max_width"]),
        min_height=int(cfg["min_height"]),
        max_height=int(cfg["max_height"]),
        min_aspect=float(cfg["min_aspect"]),
        max_aspect=float(cfg["max_aspect"]),
        require_triplets=bool(cfg.get("require_triplets", True)),
        offset=(ox, oy),
        cluster=False,
    )
    frames = find_contracts_frames(
        frame_map,
        map_margins=margins,
        offset=(ox, oy),
        min_aspect=float(cfg.get("frame_min_aspect", 1.15)),
        min_std=float(cfg.get("frame_min_std", 18.0)),
    )
    merged = _merge_contract_hits(parchment, frames)
    max_job_y = int(cfg.get("max_job_slot_y", 560))
    filtered: list[ContractHit] = []
    for hit in merged:
        _x, _y, bw, bh = hit.bbox
        if bw <= 0:
            continue
        if bh / float(bw) < float(cfg.get("frame_min_aspect", 1.15)):
            continue
        if _hit_in_inventory(hit, cfg):
            continue
        if hit.y > max_job_y:
            continue
        filtered.append(hit)

    # Р”Рѕ РєР»Р°СЃС‚РµСЂРёР·Р°С†РёРё: РѕС‚Р±СЂР°СЃС‹РІР°РµРј СѓР¶Рµ Р·Р°РЅСЏС‚С‹Рµ РїРѕСЂС‚СЂРµС‚Р°РјРё СЃР»РѕС‚С‹
    if bool(cfg.get("skip_assigned_slots", True)):
        filtered = filter_empty_job_slots(
            frame,
            filtered,
            offset=(ox, oy),
            min_face_std=float(cfg.get("assigned_min_face_std", 52.0)),
            max_parch_frac=float(cfg.get("assigned_max_parch_frac", 0.70)),
        )

    return _cluster_triplets(
        filtered,
        require_triplets=bool(cfg.get("require_triplets", True)),
        allow_pairs=bool(cfg.get("allow_pairs", True)),
    )


def find_contracts_from_config(
    cfg: Optional[dict[str, Any]] = None,
    *,
    config_path: Optional[Union[str, Path]] = None,
) -> list[ContractHit]:
    if cfg is None:
        cfg = load_config(config_path)
    return find_contracts(region=region_from_config(cfg), cfg=cfg, screen_coords=True)


def find_rogues(image: np.ndarray, *, offset: Point = (0, 0)) -> list[RogueHit]:
    """
    РС‰РµС‚ РїРѕСЂС‚СЂРµС‚С‹ rogue РІ РјРѕРґР°Р»РєРµ (1вЂ“3 С€С‚.) РїРѕ РїСЂСЏРјРѕСѓРіРѕР»СЊРЅС‹Рј СЂР°РјРєР°Рј.
    Р’РѕР·РІСЂР°С‰Р°РµС‚ СЃРїРёСЃРѕРє СЃР»РµРІР° РЅР°РїСЂР°РІРѕ.

    Р’Р°Р¶РЅРѕ: РѕРґРёРЅРѕС‡РЅР°СЏ СЂР°РјРєР° Сѓ РїСЂР°РІРѕРіРѕ РєСЂР°СЏ РјРѕРґР°Р»РєРё (РґРµСЂРµРІРѕ/РїСѓСЃС‚РѕС‚Р°) вЂ” Р»РѕР¶РЅРѕРµ
    СЃСЂР°Р±Р°С‚С‹РІР°РЅРёРµ; РїСЂРёРЅРёРјР°РµРј С‚РѕР»СЊРєРѕ СЂСЏРґ РёР· 2вЂ“3 РїРѕС‡С‚Рё РѕРґРёРЅР°РєРѕРІС‹С… РїРѕСЂС‚СЂРµС‚РѕРІ
    (РёР»Рё 1, РµСЃР»Рё СЃС‚СЂРѕРіРѕ РїРѕ С†РµРЅС‚СЂСѓ Рё СЃ В«С‚РµРєСЃС‚СѓСЂРѕР№ Р»РёС†Р°В»).
    """
    h, w = image.shape[:2]
    x0, y0 = int(w * 0.32), int(h * 0.34)
    x1, y1 = int(w * 0.68), int(h * 0.54)
    roi = image[y0:y1, x0:x1]
    if roi.size == 0:
        return []

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    ox, oy = offset
    rh, rw = roi.shape[:2]
    raw: list[tuple[int, int, int, int, float, int, int]] = []

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = float(bw * bh)
        # РџРѕСЂС‚СЂРµС‚С‹ РјРѕРґР°Р»РєРё ~100x130; РѕС‚СЃРµРєР°РµРј РјРµР»РєРёР№ РјСѓСЃРѕСЂ Рё РѕРіСЂРѕРјРЅС‹Рµ Р±Р»РѕРєРё
        if area < 7000 or area > 20000:
            continue
        if bw < 85 or bh < 100 or bw > 160 or bh > 170:
            continue
        aspect = bw / float(bh)
        if not (0.72 <= aspect <= 0.95):
            continue
        cx, cy = x + bw // 2, y + bh // 2
        if cy < int(rh * 0.10) or cy > int(rh * 0.65):
            continue
        raw.append((x + x0, y + y0, bw, bh, area, cx + x0, cy + y0))

    if not raw:
        return []

    raw.sort(key=lambda t: -t[4])
    kept: list[tuple[int, int, int, int, float, int, int]] = []
    for fr in raw:
        if any(abs(fr[5] - k[5]) < 50 and abs(fr[6] - k[6]) < 50 for k in kept):
            continue
        kept.append(fr)
    if not kept:
        return []

    screen_cx = ox + w // 2

    def face_texture(fr: tuple[int, int, int, int, float, int, int]) -> float:
        x, y, bw, bh, _a, _cx, _cy = fr
        x0b, y0b = max(0, x + 4), max(0, y + 4)
        x1b, y1b = min(image.shape[1], x + bw - 4), min(image.shape[0], y + bh - 4)
        patch = image[y0b:y1b, x0b:x1b]
        if patch.size < 200:
            return 0.0
        return float(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).std())

    def score_cluster(cluster: list[tuple[int, int, int, int, float, int, int]]) -> float:
        if not cluster:
            return -1e18
        cluster = sorted(cluster, key=lambda t: t[5])
        ys = [c[6] for c in cluster]
        if max(ys) - min(ys) > 22:
            return -1e18
        widths = [c[2] for c in cluster]
        heights = [c[3] for c in cluster]
        if max(widths) - min(widths) > 14 or max(heights) - min(heights) > 14:
            return -1e18

        mid = sum(c[5] for c in cluster) / len(cluster)
        mean_y = sum(ys) / len(ys)
        if abs(mid - screen_cx) > w * 0.12:
            return -1e18
        if mean_y < oy + h * 0.40 or mean_y > oy + h * 0.52:
            return -1e18

        if len(cluster) >= 2:
            gaps = [cluster[i + 1][5] - cluster[i][5] for i in range(len(cluster) - 1)]
            min_gap, max_gap = min(gaps), max(gaps)
            if min_gap < 85 or max_gap > 160:
                return -1e18
            if max_gap / max(min_gap, 1) > 1.35:
                return -1e18

        tex = sum(face_texture(c) for c in cluster) / len(cluster)
        # РџСѓСЃС‚Р°СЏ РґРµСЂРµРІСЏРЅРЅР°СЏ СЂР°РјРєР° СЃРїСЂР°РІР° вЂ” РЅРёР·РєР°СЏ С‚РµРєСЃС‚СѓСЂР°
        if tex < 22.0:
            return -1e18

        return (
            len(cluster) * 100
            + tex
            - abs(mid - screen_cx) * 0.8
            - (max(widths) - min(widths)) * 3
        )

    # РљР»Р°СЃС‚РµСЂС‹ РїРѕ РїРѕС…РѕР¶РµРјСѓ СЂР°Р·РјРµСЂСѓ
    best: list[tuple[int, int, int, int, float, int, int]] = []
    best_score = -1e18
    for seed in kept:
        same = [
            fr
            for fr in kept
            if abs(fr[2] - seed[2]) <= 12 and abs(fr[3] - seed[3]) <= 12
        ]
        same = sorted(same, key=lambda t: t[5])
        # РћРєРЅР° 3 Рё 2
        for size in (3, 2):
            if len(same) < size:
                continue
            for i in range(len(same) - size + 1):
                win = same[i : i + size]
                sc = score_cluster(win)
                if sc > best_score:
                    best_score = sc
                    best = win

    # РћРґРёРЅРѕС‡РЅС‹Р№ РїРѕСЂС‚СЂРµС‚ (СЂРµРґРєРѕ): С‚РѕР»СЊРєРѕ С†РµРЅС‚СЂ + Р±РѕРіР°С‚Р°СЏ С‚РµРєСЃС‚СѓСЂР°
    if not best:
        singles = sorted(kept, key=lambda t: abs(t[5] - screen_cx))
        for fr in singles[:3]:
            if abs(fr[5] - screen_cx) > w * 0.06:
                continue
            if face_texture(fr) < 28.0:
                continue
            if score_cluster([fr]) > -1e17:
                best = [fr]
                break

    hits: list[RogueHit] = []
    for x, y, bw, bh, area, cx, cy in sorted(best, key=lambda t: t[5])[:3]:
        hits.append(
            RogueHit(
                x=ox + cx,
                y=oy + cy,
                bbox=(ox + x, oy + y, bw, bh),
                radius=min(bw, bh) // 2,
            )
        )
    return hits


def pick_leftmost_rogue(rogues: Sequence[RogueHit]) -> Optional[RogueHit]:
    """Р’СЃРµРіРґР° РІС‹Р±РёСЂР°РµС‚ СЃР°РјРѕРіРѕ Р»РµРІРѕРіРѕ rogue."""
    if not rogues:
        return None
    return min(rogues, key=lambda r: r.x)


def click_screen(x: int, y: int, *, delay: float = 0.0) -> None:
    from app.input_win import click

    click(int(x), int(y), pause_ms=25)
    if delay > 0:
        time.sleep(delay)


def ctrl_click_screen(x: int, y: int, *, delay: float = 0.0) -> None:
    from app.input_win import ctrl_click

    ctrl_click(int(x), int(y), pause_ms=25)
    if delay > 0:
        time.sleep(delay)


def _clipboard_get() -> str:
    from app.input_win import get_clipboard

    try:
        return str(get_clipboard() or "")
    except Exception:
        return ""


def _clipboard_set(text: str) -> None:
    from app.input_win import set_clipboard

    try:
        set_clipboard(text)
    except Exception:
        pass


def focus_game_window() -> bool:
    from app.input_win import focus_game

    return bool(focus_game())


def _press_ctrl_c() -> None:
    from app.input_win import tap_ctrl_c

    tap_ctrl_c()


def copy_item_under_cursor(
    x: int,
    y: int,
    *,
    hover_sec: float = 0.25,
    focus_game: bool = True,
) -> str:
    """РќР°РІРѕРґРёС‚ РјС‹С€СЊ Рё Р¶РјС‘С‚ Ctrl+C вЂ” PoE РєРѕРїРёСЂСѓРµС‚ РѕРїРёСЃР°РЅРёРµ РїСЂРµРґРјРµС‚Р° РІ Р±СѓС„РµСЂ."""
    from app.input_win import move_to

    if focus_game:
        focused = focus_game_window()
        if not focused:
            time.sleep(0.25)
            focus_game_window()

    marker = f"__poe_bp_{time.time_ns()}__"
    _clipboard_set(marker)
    move_to(int(x), int(y))
    if hover_sec > 0:
        time.sleep(hover_sec)

    _press_ctrl_c()
    time.sleep(0.18)
    text = _clipboard_get()
    if _clipboard_copy_failed(text, marker):
        focus_game_window()
        time.sleep(0.15)
        _press_ctrl_c()
        time.sleep(0.2)
        text = _clipboard_get()
    if _clipboard_copy_failed(text, marker):
        move_to(int(x) + 2, int(y) + 2)
        time.sleep(max(0.25, hover_sec))
        focus_game_window()
        _press_ctrl_c()
        time.sleep(0.22)
        text = _clipboard_get()
    return text


def _clipboard_copy_failed(text: str, marker: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t == marker or t.startswith("__poe_bp_"):
        return True
    if "Item Class:" not in t:
        return True
    return False


def classify_blueprint_clipboard(text: str) -> str:
    """
    Р’РѕР·РІСЂР°С‰Р°РµС‚: usable | confirmed | fail | other
    Confirmed = Wings Revealed X/X (РІСЃРµ РєСЂС‹Р»СЊСЏ СѓР¶Рµ РѕС‚РєСЂС‹С‚С‹).
    """
    if _clipboard_copy_failed(text, ""):
        return "fail"
    if "Item Class: Blueprints" not in text:
        return "other"
    m = re.search(r"Wings Revealed:\s*(\d+)\s*/\s*(\d+)", text, re.IGNORECASE)
    if m:
        revealed, total = int(m.group(1)), int(m.group(2))
        if total > 0 and revealed >= total:
            return "confirmed"
        return "usable"
    # Blueprint Р±РµР· СЃС‚СЂРѕРєРё Wings вЂ” СЃС‡РёС‚Р°РµРј usable (РЅРµ РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Р№ РїРѕ X/X)
    return "usable"


def is_confirmed_blueprint_clipboard(text: str) -> bool:
    """True С‚РѕР»СЊРєРѕ РµСЃР»Рё СЂРµР°Р»СЊРЅРѕ СЃРєРѕРїРёСЂРѕРІР°РЅ Р±Р»СЋРїСЂРёРЅС‚ СЃ Wings X/X."""
    return classify_blueprint_clipboard(text) == "confirmed"


def is_usable_inventory_blueprint(text: str) -> bool:
    """РњРѕР¶РЅРѕ РѕС‚РєСЂС‹РІР°С‚СЊ РІ РїР»Р°РЅРёСЂРѕРІС‰РёРєРµ."""
    return classify_blueprint_clipboard(text) == "usable"


def find_confirm_plans(
    image: np.ndarray,
    *,
    threshold: float = 0.72,
    offset: Point = (0, 0),
) -> Optional[Point]:
    """РС‰РµС‚ РєРЅРѕРїРєСѓ CONFIRM PLANS (РЅР°РґРїРёСЃСЊ), РЅРµ С‰РµР»СЊ РЅР°Рґ РЅРµР№."""
    h, w = image.shape[:2]
    # РљРЅРѕРїРєР° РІ СЃР°РјРѕРј РЅРёР·Сѓ UI, РЅРёР¶Рµ СЃР»РѕС‚Р° Р±Р»СЋРїСЂРёРЅС‚Р°
    y0, y1 = int(h * 0.88), min(h, int(h * 0.97))
    x0, x1 = int(w * 0.35), int(w * 0.65)
    roi = image[y0:y1, x0:x1]
    if roi.size == 0:
        return None

    ox, oy = offset
    tpl_path = templates_dir() / "confirm_plans.png"
    if tpl_path.is_file():
        tpl = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
        if tpl is not None and tpl.shape[0] < roi.shape[0] and tpl.shape[1] < roi.shape[1]:
            res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
            _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(res)
            if max_v >= threshold:
                th, tw = tpl.shape[:2]
                return (
                    ox + x0 + max_l[0] + tw // 2,
                    oy + y0 + max_l[1] + th // 2,
                )

    # Fallback: Р±РµР»Р°СЏ РЅР°РґРїРёСЃСЊ (РІС‹СЃРѕРєРёР№ V + СЃРёР»СЊРЅС‹Р№ РєРѕРЅС‚СЂР°СЃС‚ РїРѕ СЃС‚СЂРѕРєРµ)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    best_y = -1
    best_score = -1.0
    for dy in range(gray.shape[0]):
        row = gray[dy]
        if float(row.max()) < 200:
            continue
        score = float(row.std()) * (float(row.max()) / 255.0)
        if score > best_score:
            best_score = score
            best_y = dy
    if best_y < 0 or best_score < 40:
        return None
    band = gray[max(0, best_y - 4) : min(gray.shape[0], best_y + 5), :]
    bright = (band >= 180).astype(np.uint8) * 255
    col_sums = bright.sum(axis=0)
    nz = np.where(col_sums > 0)[0]
    if nz.size < 30:
        return None
    cx = int((int(nz[0]) + int(nz[-1])) // 2)
    return (ox + x0 + cx, oy + y0 + best_y)


def find_blueprint_item(
    image: np.ndarray,
    *,
    near_xy: Optional[Point] = None,
    offset: Point = (0, 0),
    threshold: float = 0.72,
) -> Optional[Point]:
    """РРєРѕРЅРєР° Р±Р»СЋРїСЂРёРЅС‚Р° РЅР°Рґ CONFIRM PLANS (РЅРёР¶РЅРёР№ С†РµРЅС‚СЂ). Template + fallback РїРѕ СЂР°РјРєРµ."""
    h, w = image.shape[:2]
    ox, oy = offset

    if near_xy is not None:
        lx, ly = near_xy[0] - ox, near_xy[1] - oy
        y0 = max(0, ly - 120)
        y1 = max(y0 + 10, ly - 20)
        x0 = max(0, lx - 80)
        x1 = min(w, lx + 80)
    else:
        y0, y1 = int(h * 0.78), int(h * 0.92)
        x0, x1 = int(w * 0.42), int(w * 0.58)

    roi = image[y0:y1, x0:x1]
    if roi.size == 0:
        return None

    tpl_path = templates_dir() / "blueprint_item.png"
    if tpl_path.is_file():
        tpl = cv2.imread(str(tpl_path), cv2.IMREAD_COLOR)
        if tpl is not None and tpl.size > 0:
            # РµСЃР»Рё РІ С„Р°Р№Р»Рµ СЃР»СѓС‡Р°Р№РЅРѕ РєРЅРѕРїРєР° СЃРЅРёР·Сѓ вЂ” Р±РµСЂС‘Рј С‚РѕР»СЊРєРѕ РІРµСЂС…РЅРёР№ РєРІР°РґСЂР°С‚
            th, tw = tpl.shape[:2]
            if th > tw * 1.25:
                tpl = tpl[:tw, :]
                th, tw = tpl.shape[:2]
            if th < roi.shape[0] and tw < roi.shape[1]:
                res = cv2.matchTemplate(roi, tpl, cv2.TM_CCOEFF_NORMED)
                _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(res)
                if max_v >= threshold:
                    return (
                        ox + x0 + max_l[0] + tw // 2,
                        oy + y0 + max_l[1] + th // 2,
                    )

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: Optional[tuple[float, int, int]] = None
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if not (28 <= bw <= 70 and 28 <= bh <= 70):
            continue
        aspect = bw / float(bh)
        if aspect < 0.75 or aspect > 1.35:
            continue
        patch = gray[y : y + bh, x : x + bw]
        std = float(patch.std()) if patch.size else 0.0
        if std < 12:
            continue
        px, py = x0 + x + bw // 2, y0 + y + bh // 2
        score = std * 10 + bw * bh - abs(px - w // 2) * 0.5
        if best is None or score > best[0]:
            best = (score, px, py)
    if best is None:
        return None
    return (ox + best[1], oy + best[2])


def confirm_plans_and_take_blueprint(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any = None,
    logger: Optional[AssignLogger] = None,
    click_delay: float = 0.05,
) -> bool:
    """РљР»РёРєР°РµС‚ CONFIRM PLANS, Р·Р°С‚РµРј Ctrl+Р›РљРњ РїРѕ Р±Р»СЋРїСЂРёРЅС‚Сѓ РЅР°Рґ РєРЅРѕРїРєРѕР№."""
    if not bool(cfg.get("confirm_plans_after_assign", True)):
        return False

    threshold = float(cfg.get("confirm_match_threshold", 0.72))
    delay = float(cfg.get("confirm_delay_sec", 0.35))
    below_bp = int(cfg.get("confirm_below_blueprint", 70))
    do_ctrl = bool(cfg.get("ctrl_click_after_confirm", True))

    frame, offset = capture_screen(region, sct=sct)

    # Р СѓС‡РЅС‹Рµ С‚РѕС‡РєРё РёР· РєР°Р»РёР±СЂРѕРІРєРё GUI (РїСЂРёРѕСЂРёС‚РµС‚РЅРµРµ Р°РІС‚Рѕ-РїРѕРёСЃРєР°)
    ui = cfg.get("ui_points") or {}
    confirm = None
    bp = None
    if isinstance(ui.get("confirm"), (list, tuple)) and len(ui["confirm"]) == 2:
        confirm = (int(ui["confirm"][0]) - offset[0], int(ui["confirm"][1]) - offset[1])
    if isinstance(ui.get("blueprint_slot"), (list, tuple)) and len(ui["blueprint_slot"]) == 2:
        bp = (
            int(ui["blueprint_slot"][0]) - offset[0],
            int(ui["blueprint_slot"][1]) - offset[1],
        )

    if bp is None:
        bp = find_blueprint_item(frame, offset=(0, 0))
    if confirm is None:
        confirm = find_confirm_plans(frame, threshold=threshold, offset=(0, 0))

    # Р•СЃР»Рё РєРЅРѕРїРєР° РЅРµ РЅР°Р№РґРµРЅР° РёР»Рё РїРѕРїР°Р»Р° СЃР»РёС€РєРѕРј Р±Р»РёР·РєРѕ Рє Р±Р»СЋРїСЂРёРЅС‚Сѓ вЂ” СЏРєРѕСЂСЊ РѕС‚ Р±Р»СЋРїСЂРёРЅС‚Р°
    if bp is not None:
        if confirm is None or abs(confirm[1] - bp[1]) < 45:
            confirm = (bp[0], bp[1] + below_bp)

    if confirm is None:
        if logger is not None:
            logger.log("CONFIRM PLANS: not found")
            logger.save_image("99_confirm_not_found.png", frame)
        return False

    if bp is None:
        bp = (confirm[0], confirm[1] - below_bp)

    conf_screen = (confirm[0] + offset[0], confirm[1] + offset[1])
    bp_screen = (bp[0] + offset[0], bp[1] + offset[1])

    if logger is not None:
        logger.log(f"CONFIRM PLANS at {conf_screen}, blueprint at {bp_screen}")
        if bool(cfg.get("verbose_logs", False)):
            vis = frame.copy()
            cv2.circle(vis, confirm, 8, (0, 255, 0), 2)
            cv2.circle(vis, bp, 8, (0, 0, 255), 2)
            logger.save_image("99_confirm_targets.png", vis)

    click_screen(conf_screen[0], conf_screen[1], delay=click_delay)
    if delay > 0:
        time.sleep(delay)

    if do_ctrl:
        if logger is not None:
            logger.log(f"Ctrl+click blueprint {bp_screen}")
        ctrl_click_screen(bp_screen[0], bp_screen[1], delay=click_delay)
    return True


def _inventory_roi(
    image: np.ndarray, cfg: dict[str, Any]
) -> tuple[np.ndarray, int, int]:
    """Р’С‹СЂРµР·Р°РµС‚ РѕР±Р»Р°СЃС‚СЊ РёРЅРІРµРЅС‚Р°СЂСЏ; РІРѕР·РІСЂР°С‰Р°РµС‚ (roi, x0, y0)."""
    h, w = image.shape[:2]
    inv = cfg.get("inventory_region") or {}
    if all(k in inv for k in ("left", "top", "width", "height")):
        x0 = int(inv["left"])
        y0 = int(inv["top"])
        x1 = min(w, x0 + int(inv["width"]))
        y1 = min(h, y0 + int(inv["height"]))
    else:
        x0, y0 = int(w * 0.68), int(h * 0.53)
        x1, y1 = int(w * 0.98), int(h * 0.78)
    x0, y0 = max(0, x0), max(0, y0)
    return image[y0:y1, x0:x1], x0, y0


def _load_blueprint_templates(*, confirmed: bool = False) -> list[np.ndarray]:
    """
    confirmed=False в†’ blueprint_inv.png / blueprint_inv_1..N (Р±РµР· confirmed).
    confirmed=True  в†’ blueprint_inv_confirmed*.png (СѓР¶Рµ РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ вЂ” РЅРµ РєР»РёРєР°С‚СЊ).
    """
    templates: list[np.ndarray] = []
    tpl_dir = templates_dir()
    if not tpl_dir.is_dir():
        return templates
    for path in sorted(tpl_dir.glob("blueprint_inv*.png")):
        name = path.name.lower()
        is_confirmed = "confirmed" in name
        if confirmed != is_confirmed:
            continue
        tpl = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if tpl is not None and tpl.size > 0:
            templates.append(tpl)
    return templates


def _best_template_score(
    patch: np.ndarray,
    templates: Sequence[np.ndarray],
    *,
    scales: Sequence[float] = (0.9, 1.0, 1.1),
) -> float:
    """РњР°РєСЃРёРјР°Р»СЊРЅС‹Р№ TM_CCOEFF_NORMED РїРѕ С€Р°Р±Р»РѕРЅР°Рј Рё РјР°СЃС€С‚Р°Р±Р°Рј."""
    if patch.size == 0 or not templates:
        return -1.0
    ph, pw = patch.shape[:2]
    best = -1.0
    for tpl in templates:
        th, tw = tpl.shape[:2]
        for scale in scales:
            sh, sw = max(8, int(th * scale)), max(8, int(tw * scale))
            if sh > ph or sw > pw:
                continue
            scaled = (
                tpl
                if scale == 1.0 and sh == th and sw == tw
                else cv2.resize(tpl, (sw, sh), interpolation=cv2.INTER_AREA)
            )
            res = cv2.matchTemplate(patch, scaled, cv2.TM_CCOEFF_NORMED)
            best = max(best, float(res.max()))
    return best


def _cell_patch(image, cell, offset: Point = (0, 0)):
    x0 = int(cell.x - offset[0])
    y0 = int(cell.y - offset[1])
    x1 = x0 + int(cell.w)
    y1 = y0 + int(cell.h)
    pad = max(2, min(int(cell.w), int(cell.h)) // 10)
    x0, y0 = x0 + pad, y0 + pad
    x1, y1 = x1 - pad, y1 - pad
    h, w = image.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return None
    return image[y0:y1, x0:x1]


def cell_is_empty(image, cell, cfg: Optional[dict[str, Any]] = None, *, offset: Point = (0, 0)) -> bool:
    """True if the inventory cell has no item / no blueprint to open."""
    patch = _cell_patch(image, cell, offset)
    if patch is None or patch.size == 0:
        return True
    cfg = cfg or {}
    templates = list(_load_blueprint_templates(confirmed=False))
    templates.extend(_load_blueprint_templates(confirmed=True))
    score = _best_template_score(patch, templates, scales=(0.8, 0.9, 1.0, 1.1, 1.2))
    if score >= float(cfg.get("cell_blueprint_threshold", 0.52)):
        return False
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    std = float(gray.std())
    mean = float(gray.mean())
    occupied = std >= float(cfg.get("cell_occupied_min_std", 15.0)) and mean >= float(
        cfg.get("cell_occupied_min_mean", 32.0)
    )
    return not occupied


def find_inventory_blueprints(
    image: np.ndarray,
    cfg: Optional[dict[str, Any]] = None,
    *,
    offset: Point = (0, 0),
    threshold: Optional[float] = None,
) -> list[InventoryBlueprint]:
    """
    РС‰РµС‚ РќР•РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ Р±Р»СЋРїСЂРёРЅС‚С‹ РІ РёРЅРІРµРЅС‚Р°СЂРµ.
    РСЃРїРѕР»СЊР·СѓРµС‚ blueprint_inv*.png; СЃР»РѕС‚С‹ РїРѕС…РѕР¶РёРµ РЅР° blueprint_inv_confirmed* РѕС‚Р±СЂР°СЃС‹РІР°РµС‚.
    """
    if cfg is None:
        cfg = load_config()
    if threshold is None:
        threshold = float(cfg.get("inventory_match_threshold", 0.72))
    confirmed_threshold = float(cfg.get("inventory_confirmed_threshold", threshold))

    roi, x0, y0 = _inventory_roi(image, cfg)
    if roi.size == 0:
        return []

    ox, oy = offset
    hits: list[InventoryBlueprint] = []
    templates = _load_blueprint_templates(confirmed=False)
    confirmed_tpls = _load_blueprint_templates(confirmed=True)
    template_hits = 0
    scales_raw = cfg.get("inventory_template_scales", [1.0])
    scales = [float(s) for s in scales_raw] if scales_raw else [1.0]

    for tpl in templates:
        th, tw = tpl.shape[:2]
        if th >= roi.shape[0] or tw >= roi.shape[1]:
            continue
        for scale in scales:
            sw, sh = int(tw * scale), int(th * scale)
            if sw < 20 or sh < 20 or sh >= roi.shape[0] or sw >= roi.shape[1]:
                continue
            scaled = (
                tpl
                if abs(scale - 1.0) < 1e-6
                else cv2.resize(tpl, (sw, sh), interpolation=cv2.INTER_AREA)
            )
            res = cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            for yy, xx in zip(loc[0].tolist(), loc[1].tolist()):
                score = float(res[yy, xx])
                cx = ox + x0 + xx + scaled.shape[1] // 2
                cy = oy + y0 + yy + scaled.shape[0] // 2
                hits.append(
                    InventoryBlueprint(
                        x=cx,
                        y=cy,
                        score=score,
                        bbox=(
                            ox + x0 + xx,
                            oy + y0 + yy,
                            scaled.shape[1],
                            scaled.shape[0],
                        ),
                    )
                )
                template_hits += 1

    # Beige fallback С‚РѕР»СЊРєРѕ РµСЃР»Рё С€Р°Р±Р»РѕРЅС‹ РЅРёС‡РµРіРѕ РЅРµ РЅР°С€Р»Рё
    if template_hits == 0:
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        beige = cv2.inRange(
            hsv, np.array([8, 20, 80], np.uint8), np.array([32, 140, 230], np.uint8)
        )
        beige = cv2.morphologyEx(
            beige, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1
        )
        contours, _ = cv2.findContours(beige, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            area = float(cv2.contourArea(cnt))
            if not (28 <= bw <= 58 and 28 <= bh <= 58):
                continue
            if area < 350:
                continue
            patch = roi[y : y + bh, x : x + bw]
            std = float(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).std())
            if std < 15:
                continue
            cx = ox + x0 + x + bw // 2
            cy = oy + y0 + y + bh // 2
            hits.append(
                InventoryBlueprint(
                    x=cx,
                    y=cy,
                    score=0.5 + min(std, 40) / 100.0,
                    bbox=(ox + x0 + x, oy + y0 + y, bw, bh),
                )
            )

    # Р”РµРґСѓРї: Р»СѓС‡С€РёР№ score РІ СЃР»РѕС‚Рµ
    hits.sort(key=lambda h: -h.score)
    kept: list[InventoryBlueprint] = []
    for hit in hits:
        if any(abs(hit.x - k.x) < 28 and abs(hit.y - k.y) < 28 for k in kept):
            continue
        kept.append(hit)

    # РћС‚Р±СЂР°СЃС‹РІР°РµРј confirmed С‚РѕР»СЊРєРѕ РµСЃР»Рё СЃРѕРІРїР°РґРµРЅРёРµ СЃ confirmed РЇР’РќРћ Р»СѓС‡С€Рµ РѕР±С‹С‡РЅРѕРіРѕ.
    # РРЅР°С‡Рµ rare/СЃРёРЅСЏСЏ РїРѕРґСЃРІРµС‚РєР° РґР°С‘С‚ РїРѕС‡С‚Рё РѕРґРёРЅР°РєРѕРІС‹Р№ score Рё РІСЃС‘ РІС‹РєРёРґС‹РІР°РµС‚СЃСЏ.
    if confirmed_tpls:
        filtered: list[InventoryBlueprint] = []
        margin = float(cfg.get("inventory_confirmed_margin", 0.08))
        for hit in kept:
            x, y, w, h = hit.bbox
            lx = x - ox - x0
            ly = y - oy - y0
            pad = 4
            x0p = max(0, lx - pad)
            y0p = max(0, ly - pad)
            x1p = min(roi.shape[1], lx + w + pad)
            y1p = min(roi.shape[0], ly + h + pad)
            patch = roi[y0p:y1p, x0p:x1p]
            conf_score = _best_template_score(patch, confirmed_tpls)
            ok_score = max(hit.score, _best_template_score(patch, templates))
            if (
                conf_score >= confirmed_threshold
                and conf_score > ok_score + margin
            ):
                continue
            filtered.append(hit)
        kept = filtered

    kept.sort(key=lambda h: (h.y, h.x))
    return kept


def pick_next_inventory_blueprint(
    blueprints: Sequence[InventoryBlueprint],
    *,
    exclude: Optional[Sequence[Point]] = None,
    exclude_dist: int = 36,
) -> Optional[InventoryBlueprint]:
    """Р‘РµСЂС‘С‚ СЃР»РµРґСѓСЋС‰РёР№ Р±Р»СЋРїСЂРёРЅС‚ СЃР»РµРІР°-РЅР°РїСЂР°РІРѕ / СЃРІРµСЂС…Сѓ-РІРЅРёР·, РјРёРЅСѓСЃ exclude."""
    exclude = list(exclude or [])
    for bp in sorted(blueprints, key=lambda h: (h.y, h.x)):
        if any(abs(bp.x - ex) < exclude_dist and abs(bp.y - ey) < exclude_dist for ex, ey in exclude):
            continue
        return bp
    return None


def inventory_blueprint_count(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any = None,
) -> int:
    frame, _ = capture_screen(region, sct=sct)
    return len(find_inventory_blueprints(frame, cfg, offset=(0, 0)))


def ensure_inventory_open(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any = None,
    logger: Optional[AssignLogger] = None,
    retries: int = 3,
) -> bool:
    """
    РРЅРІРµРЅС‚Р°СЂСЊ РґРѕР»Р¶РµРЅ Р±С‹С‚СЊ РѕС‚РєСЂС‹С‚. РЎРЅР°С‡Р°Р»Р° Р¶РґС‘Рј (BP РµС‰С‘ РІРѕР·РІСЂР°С‰Р°РµС‚СЃСЏ РІ СЃСѓРјРєСѓ),
    I Р¶РјС‘Рј С‚РѕР»СЊРєРѕ РµСЃР»Рё РїРѕСЃР»Рµ РїР°СѓР·С‹ РІСЃС‘ РµС‰С‘ 0 вЂ” РёРЅР°С‡Рµ Р»РёС€РЅРёР№ I Р—РђРљР Р«Р’РђР•Рў РёРЅРІРµРЅС‚Р°СЂСЊ.
    """
    settle = float(cfg.get("inventory_open_settle_sec", 0.4))
    wait_first = float(cfg.get("inventory_wait_before_i_sec", 0.55))

    n = inventory_blueprint_count(region, cfg, sct=sct)
    if n > 0:
        return True

    # РџРѕСЃР»Рµ CONFIRM+Ctrl РїСЂРµРґРјРµС‚ РµС‰С‘ РЅРµ СѓСЃРїРµР» РїРѕСЏРІРёС‚СЊСЃСЏ вЂ” РЅРµ С‚СЂРѕРіР°РµРј I
    if logger is not None:
        logger.log(f"inventory 0 вЂ” wait {wait_first:.2f}s before I")
    time.sleep(wait_first)
    n = inventory_blueprint_count(region, cfg, sct=sct)
    if n > 0:
        if logger is not None:
            logger.log(f"inventory open OK (blueprints={n}) after wait")
        return True

    for attempt in range(1, max(1, retries) + 1):
        if logger is not None:
            logger.log(f"inventory still closed вЂ” press I (try {attempt}/{retries})")
        from app.input_win import VK_I, tap_key

        tap_key(VK_I)
        if settle > 0:
            time.sleep(settle)
        n = inventory_blueprint_count(region, cfg, sct=sct)
        if n > 0:
            if logger is not None:
                logger.log(f"inventory open OK (blueprints={n}) after I")
            return True
    if logger is not None:
        logger.log(f"inventory after ensure: blueprints={n}")
    return n > 0


def open_next_inventory_blueprint(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any = None,
    logger: Optional[AssignLogger] = None,
    click_delay: float = 0.05,
    exclude: Optional[Sequence[Point]] = None,
) -> Optional[InventoryBlueprint]:
    """
    Р‘РµСЂС‘С‚ СЃР»РµРґСѓСЋС‰РёР№ Р±Р»СЋРїСЂРёРЅС‚ РІ РёРЅРІРµРЅС‚Р°СЂРµ РїРѕ РїРѕСЂСЏРґРєСѓ (СЃРІРµСЂС…Сѓв†’РІРЅРёР·, СЃР»РµРІР°в†’РїСЂР°РІРѕ).
    РЎР»РѕС‚С‹ РёР· exclude (СѓР¶Рµ РѕС‚РєСЂС‹С‚С‹Рµ РІ СЌС‚РѕРј Р·Р°РїСѓСЃРєРµ) РїСЂРѕРїСѓСЃРєР°СЋС‚СЃСЏ.
    """
    settle = float(cfg.get("blueprint_open_settle_sec", 0.2))
    exclude_dist = int(cfg.get("inventory_exclude_dist", 40))
    verbose = bool(cfg.get("verbose_logs", False))

    # Р›С‘РіРєР°СЏ РїСЂРѕРІРµСЂРєР°: РѕРґРёРЅ Р±С‹СЃС‚СЂС‹Р№ СЃРєР°РЅ; I С‚РѕР»СЊРєРѕ РµСЃР»Рё 0
    frame, offset = capture_screen(region, sct=sct)
    local = find_inventory_blueprints(frame, cfg, offset=(0, 0))
    if not local:
        ensure_inventory_open(region, cfg, sct=sct, logger=logger, retries=2)
        frame, offset = capture_screen(region, sct=sct)
        local = find_inventory_blueprints(frame, cfg, offset=(0, 0))

    screen_bps = [
        InventoryBlueprint(
            x=b.x + offset[0],
            y=b.y + offset[1],
            score=b.score,
            bbox=(b.bbox[0] + offset[0], b.bbox[1] + offset[1], b.bbox[2], b.bbox[3]),
        )
        for b in local
    ]
    chosen = pick_next_inventory_blueprint(
        screen_bps, exclude=exclude, exclude_dist=exclude_dist
    )

    if chosen is None and local:
        # РІСЃРµ РІ exclude вЂ” РЅРёС‡РµРіРѕ РЅРµ РѕС‚РєСЂС‹РІР°С‚СЊ
        pass
    elif chosen is None:
        time.sleep(0.3)
        ensure_inventory_open(region, cfg, sct=sct, logger=logger, retries=1)
        frame, offset = capture_screen(region, sct=sct)
        local = find_inventory_blueprints(frame, cfg, offset=(0, 0))
        screen_bps = [
            InventoryBlueprint(
                x=b.x + offset[0],
                y=b.y + offset[1],
                score=b.score,
                bbox=(b.bbox[0] + offset[0], b.bbox[1] + offset[1], b.bbox[2], b.bbox[3]),
            )
            for b in local
        ]
        chosen = pick_next_inventory_blueprint(
            screen_bps, exclude=exclude, exclude_dist=exclude_dist
        )

    if logger is not None:
        candidates = [
            bp
            for bp in sorted(screen_bps, key=lambda h: (h.y, h.x))
            if not any(
                abs(bp.x - ex) < exclude_dist and abs(bp.y - ey) < exclude_dist
                for ex, ey in (exclude or [])
            )
        ]
        logger.log(
            f"inventory blueprints={len(screen_bps)} "
            f"after_exclude={len(candidates)} "
            f"opened_before={len(exclude or [])}"
        )
        if verbose:
            vis = frame.copy()
            for b in local:
                x, y, w, h = b.bbox
                sx, sy = b.x + offset[0], b.y + offset[1]
                is_excl = any(
                    abs(sx - ex) < exclude_dist and abs(sy - ey) < exclude_dist
                    for ex, ey in (exclude or [])
                )
                color = (80, 80, 80) if is_excl else (0, 200, 255)
                cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
            if chosen is not None:
                cv2.circle(
                    vis,
                    (chosen.x - offset[0], chosen.y - offset[1]),
                    10,
                    (0, 255, 0),
                    2,
                )
            logger.save_image("inventory_blueprints.png", vis)

    if chosen is None:
        if logger is not None:
            logger.log("NO inventory blueprint to open (all opened or empty)")
        return None

    if logger is not None:
        logger.log(
            f"Ctrl+click next blueprint #{len(exclude or []) + 1} "
            f"({chosen.x},{chosen.y}) score={chosen.score:.3f}"
        )
    ctrl_click_screen(chosen.x, chosen.y, delay=click_delay)
    # РљРѕСЂРѕС‚РєР°СЏ РїР°СѓР·Р° вЂ” РіРѕС‚РѕРІРЅРѕСЃС‚СЊ UI Р¶РґС‘С‚ wait_blueprint_ready, РЅРµ sleep 0.9
    if settle > 0:
        time.sleep(settle)
    return chosen


def wait_blueprint_ready(
    region: Region,
    cfg: dict[str, Any],
    *,
    timeout: float = 3.0,
    sct: Any = None,
    stop_event: Optional[threading.Event] = None,
    logger: Optional[AssignLogger] = None,
) -> bool:
    """
    Р–РґС‘С‚ РїСѓСЃС‚С‹Рµ СЃР»РѕС‚С‹ job (РїСЂРµРґРїРѕС‡С‚РёС‚РµР»СЊРЅРѕ) РїРѕСЃР»Рµ РѕС‚РєСЂС‹С‚РёСЏ Р±Р»СЋРїСЂРёРЅС‚Р°.
    РћРґРёРЅ С‚РѕР»СЊРєРѕ CONFIRM Р±РµР· СЃР»РѕС‚РѕРІ вЂ” СЂР°РЅРѕ: UI РµС‰С‘ РіСЂСѓР·РёС‚СЃСЏ / РґСЂСѓРіРѕР№ BP.
    """
    poll = float(cfg.get("poll_interval_sec", 0.03))
    min_confirm_wait = float(cfg.get("blueprint_confirm_only_after_sec", 0.35))
    deadline = time.time() + timeout
    t0 = time.time()
    saw_confirm = False
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return False
        frame, _ = capture_screen(region, sct=sct)
        contracts = find_contracts(frame, cfg=cfg, screen_coords=False)
        if contracts:
            if logger is not None:
                logger.log(f"blueprint ready: empty_slots={len(contracts)}")
            return True
        confirm = find_confirm_plans(frame)
        if confirm is not None:
            saw_confirm = True
            if time.time() - t0 >= min_confirm_wait:
                if logger is not None:
                    logger.log("blueprint ready: CONFIRM only (no empty slots)")
                return True
        time.sleep(max(0.03, poll))
    if logger is not None:
        logger.log(f"blueprint ready: TIMEOUT (confirm_seen={saw_confirm})")
    return saw_confirm


def _contracts_prefer_full_triplets(
    contracts: Sequence[ContractHit],
) -> list[ContractHit]:
    """
    Р•СЃР»Рё С‡РёСЃР»Рѕ РЅРµ РєСЂР°С‚РЅРѕ 3, РЅРѕ РµСЃС‚СЊ РїРѕР»РЅС‹Рµ РіСЂСѓРїРїС‹ РїРѕ 3 вЂ” РѕСЃС‚Р°РІР»СЏРµРј С‚РѕР»СЊРєРѕ РёС….
    РРЅР°С‡Рµ pan СЃСЉРµРґР°РµС‚ РІРµСЂС…РЅРёРµ РєСЂС‹Р»СЊСЏ: 3+3+3+РїР°СЂР° в†’ pan в†’ РІРµСЂС… СѓРµР·Р¶Р°РµС‚.
    """
    items = list(contracts)
    if not items or len(items) % 3 == 0:
        return items
    by_g: dict[int, list[ContractHit]] = {}
    for c in items:
        by_g.setdefault(int(c.group), []).append(c)
    triples: list[ContractHit] = []
    for _g, group in sorted(
        by_g.items(), key=lambda kv: (min(h.y for h in kv[1]), min(h.x for h in kv[1]))
    ):
        if len(group) != 3:
            continue
        triples.extend(sorted(group, key=lambda h: h.x))
    if triples and len(triples) % 3 == 0:
        return triples
    return items


def pan_map_drag_right(
    region: Region,
    *,
    drag_px: int = 220,
    duration: float = 0.25,
) -> None:
    """
    Сдвигает карту влево: зажать ЛКМ и потянуть вправо.
    Открывает слоты, которые были за левым краем / под Fees.
    """
    from app.input_win import drag

    left, top, width, height = region
    # Центр карты, не Fees и не The Crew
    cx = left + width // 2
    cy = top + int(height * 0.42)
    half = max(40, int(drag_px) // 2)
    x0, y0 = cx - half, cy
    x1, y1 = cx + half, cy

    drag(x0, y0, x1, y1, duration=max(0.05, float(duration)))


def left_panel_right_edge(image: np.ndarray) -> int:
    """Right edge of Fees / Whakano — the strip that covers map nodes."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    x1 = max(40, int(w * 0.42))
    y0, y1 = int(h * 0.12), int(h * 0.78)
    if y1 <= y0:
        return int(w * 0.18)
    roi = gray[y0:y1, :x1]
    sobel = cv2.Sobel(roi, cv2.CV_32F, 1, 0, ksize=3)
    col = np.abs(sobel).mean(axis=0)
    kernel = max(5, w // 80)
    smooth = np.convolve(col, np.ones(kernel) / kernel, mode="same")
    lo = int(w * 0.10)
    if lo >= len(smooth):
        return int(w * 0.18)
    return lo + int(np.argmax(smooth[lo:]))


def _rooms_hugging_left_panel(image: np.ndarray, edge: int, pad: int) -> bool:
    h, w = image.shape[:2]
    x0 = max(0, edge - 8)
    x1 = min(w, edge + pad + int(0.04 * w))
    y0 = int(h * 0.12)
    y1 = int(h * 0.78)
    if x1 - x0 < 20 or y1 - y0 < 40:
        return False
    roi = image[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 20, 70)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    min_side = max(18, int(0.025 * min(h, w)))
    max_side = max(70, int(0.09 * min(h, w)))
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if min(bw, bh) < min_side or max(bw, bh) > max_side:
            continue
        aspect = bw / float(max(1, bh))
        if aspect < 0.7 or aspect > 1.4:
            continue
        if (x0 + x) < edge - 8:
            continue
        return True
    return False


def _needs_left_panel_pan(
    frame: np.ndarray,
    contracts: Sequence[ContractHit],
    cfg: dict[str, Any],
) -> bool:
    if not contracts:
        return False
    if bool(cfg.get("pan_if_not_multiple_of_3", True)) and len(contracts) % 3 != 0:
        return True
    if not bool(cfg.get("pan_if_left_panel_covers", True)):
        return False
    w = frame.shape[1]
    edge = left_panel_right_edge(frame)
    pad = max(int(cfg.get("pan_left_clear_pad_px", 36)), int(0.02 * w))
    clear_x = edge + pad
    leftmost = min(hit.bbox[0] for hit in contracts)
    if leftmost < clear_x:
        return True
    return _rooms_hugging_left_panel(frame, edge, pad)


def discover_contracts(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any = None,
    logger: Optional[AssignLogger] = None,
) -> tuple[list[ContractHit], np.ndarray, Point]:
    """
    Ищет контракты. Пан карты влево, если слотов не кратно 3
    или левая панель (Fees / Whakano) перекрывает ноды.
    """
    drag_px = int(cfg.get("pan_drag_px", 180))
    drag_dur = float(cfg.get("pan_drag_duration_sec", 0.2))
    settle = float(cfg.get("pan_settle_sec", 0.3))
    max_attempts = int(cfg.get("pan_max_attempts", 4))

    frame, offset = capture_screen(region, sct=sct)
    local = _contracts_prefer_full_triplets(find_contracts(frame, cfg=cfg, screen_coords=False))
    contracts = _with_screen_offset(local, offset)
    before = len(contracts)
    if logger is not None:
        if before != len(contracts):
            logger.log(
                f"scan0 drop incomplete groups: {before} -> {len(contracts)} "
                f"(keep full triplets to avoid pan losing top wings)"
            )
        logger.log(f"scan0 contracts={len(contracts)} screen={[ (c.x, c.y) for c in contracts ]}")
        if not contracts:
            logger.save_image("00_no_contracts_raw.png", frame)
        else:
            logger.save_image("00_raw.png", frame)
            # annotate with local coords of kept hits
            kept_local = [
                ContractHit(
                    x=c.x - offset[0],
                    y=c.y - offset[1],
                    bbox=(
                        c.bbox[0] - offset[0],
                        c.bbox[1] - offset[1],
                        c.bbox[2],
                        c.bbox[3],
                    ),
                    area=c.area,
                    score=c.score,
                    group=c.group,
                )
                for c in contracts
            ]
            logger.save_image("00_targets.png", logger.annotate_contracts(frame, kept_local))

    attempt = 0
    while _needs_left_panel_pan(frame, local, cfg) and attempt < max_attempts:
        attempt += 1
        if logger is not None:
            logger.log(
                f"left panel covers nodes or count={len(contracts)} "
                f"-> pan map left (drag right {drag_px}px) "
                f"attempt {attempt}/{max_attempts}"
            )
        pan_map_drag_right(region, drag_px=drag_px, duration=drag_dur)
        if settle > 0:
            time.sleep(settle)

        frame, offset = capture_screen(region, sct=sct)
        local = _contracts_prefer_full_triplets(find_contracts(frame, cfg=cfg, screen_coords=False))
        contracts = _with_screen_offset(local, offset)
        before = len(contracts)
        if logger is not None:
            if before != len(contracts):
                logger.log(f"scan{attempt} drop incomplete: {before} -> {len(contracts)}")
            logger.log(
                f"scan{attempt} contracts={len(contracts)} "
                f"screen={[ (c.x, c.y) for c in contracts ]}"
            )
            logger.save_image(f"00_raw_pan{attempt}.png", frame)
            kept_local = [
                ContractHit(
                    x=c.x - offset[0],
                    y=c.y - offset[1],
                    bbox=(
                        c.bbox[0] - offset[0],
                        c.bbox[1] - offset[1],
                        c.bbox[2],
                        c.bbox[3],
                    ),
                    area=c.area,
                    score=c.score,
                    group=c.group,
                )
                for c in contracts
            ]
            logger.save_image(
                f"00_targets_pan{attempt}.png",
                logger.annotate_contracts(frame, kept_local),
            )

    return contracts, frame, offset


def _with_screen_offset(
    hits: Sequence[ContractHit], offset: Point
) -> list[ContractHit]:
    ox, oy = offset
    return [
        ContractHit(
            x=h.x + ox,
            y=h.y + oy,
            bbox=(h.bbox[0] + ox, h.bbox[1] + oy, h.bbox[2], h.bbox[3]),
            area=h.area,
            score=h.score,
            group=h.group,
        )
        for h in hits
    ]


class AssignLogger:
    """РџРёС€РµС‚ С‚РµРєСЃС‚РѕРІС‹Р№ Р»РѕРі + СЃРєСЂРёРЅС‹ С€Р°РіРѕРІ РІ logs/run_*/."""

    def __init__(
        self,
        base_logs: Path,
        enabled: bool = True,
        *,
        on_log: Optional[Any] = None,
    ) -> None:
        self.enabled = enabled
        self.on_log = on_log
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.session_dir = base_logs / f"run_{stamp}"
        if enabled:
            self.session_dir.mkdir(parents=True, exist_ok=True)
            self.log_path = self.session_dir / "run.log"
            self._fp = self.log_path.open("a", encoding="utf-8")
        else:
            self.log_path = base_logs / "disabled.log"
            self._fp = None
        self.step = 0

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def log(self, msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d}] {msg}"
        print(line)
        if self._fp is not None:
            self._fp.write(line + "\n")
            self._fp.flush()
        if self.on_log is not None:
            try:
                self.on_log(line)
            except Exception:  # noqa: BLE001
                pass

    def save_image(self, name: str, image: np.ndarray) -> Optional[Path]:
        if not self.enabled or self._fp is None:
            return None
        path = self.session_dir / name
        cv2.imwrite(str(path), image)
        self.log(f"IMG {name} shape={image.shape[1]}x{image.shape[0]}")
        return path

    def annotate_contracts(
        self, frame: np.ndarray, contracts: Sequence[ContractHit], highlight: int = -1
    ) -> np.ndarray:
        canvas = draw_contracts(frame, contracts)
        if 0 <= highlight < len(contracts):
            h = contracts[highlight]
            cv2.circle(canvas, (h.x, h.y), 14, (0, 0, 255), 3)
            cv2.putText(
                canvas,
                "CLICK",
                (h.x + 16, h.y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
        return canvas

    def annotate_rogues(
        self, frame: np.ndarray, rogues: Sequence[RogueHit], chosen: Optional[RogueHit]
    ) -> np.ndarray:
        canvas = frame.copy()
        for i, r in enumerate(rogues, 1):
            is_chosen = chosen is not None and r.center == chosen.center
            color = (0, 255, 255) if is_chosen else (0, 255, 0)
            cv2.circle(canvas, (r.x, r.y), max(12, r.radius), color, 2)
            cv2.circle(canvas, (r.x, r.y), 4, (0, 0, 255), -1)
            label = f"#{i}"
            if is_chosen:
                label += " LEFT"
            cv2.putText(
                canvas,
                label,
                (r.x - 20, r.y - max(14, r.radius) - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        return canvas


def wait_for_rogues(
    region: Region,
    *,
    timeout: float,
    poll: float = 0.03,
    stop_event: Optional[threading.Event] = None,
    logger: Optional[AssignLogger] = None,
    step_idx: int = 0,
    sct: Any = None,
) -> Tuple[list[RogueHit], Optional[np.ndarray], Point]:
    """Р–РґС‘С‚ РјРѕРґР°Р»РєСѓ. Р’РѕР·РІСЂР°С‰Р°РµС‚ (rogues, last_frame, offset)."""
    deadline = time.time() + timeout
    attempts = 0
    last_frame: Optional[np.ndarray] = None
    last_offset: Point = (0, 0)
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return [], last_frame, last_offset
        frame, offset = capture_screen(region, sct=sct)
        last_frame, last_offset = frame, offset
        rogues = find_rogues(frame, offset=offset)
        attempts += 1
        if rogues:
            if logger is not None:
                logger.log(
                    f"step{step_idx}: modal OK tries={attempts} "
                    f"n={len(rogues)} left={rogues[0].center}"
                )
            return rogues, frame, offset
        if poll > 0:
            time.sleep(poll)

    if logger is not None:
        logger.log(f"step{step_idx}: modal TIMEOUT tries={attempts} ({timeout}s)")
        if last_frame is not None:
            logger.save_image(f"step{step_idx:02d}_fail_no_modal.png", last_frame)
    return [], last_frame, last_offset


def wait_modal_closed(
    region: Region,
    *,
    timeout: float,
    poll: float = 0.03,
    stop_event: Optional[threading.Event] = None,
    logger: Optional[AssignLogger] = None,
    step_idx: int = 0,
    sct: Any = None,
) -> bool:
    """Р–РґС‘С‚ Р·Р°РєСЂС‹С‚РёСЏ РјРѕРґР°Р»РєРё (РЅРµС‚ РїРѕСЂС‚СЂРµС‚РѕРІ rogue)."""
    deadline = time.time() + timeout
    attempts = 0
    while time.time() < deadline:
        if stop_event is not None and stop_event.is_set():
            return False
        frame, _ = capture_screen(region, sct=sct)
        still = find_rogues(frame, offset=(0, 0))
        attempts += 1
        if not still:
            if logger is not None:
                logger.log(f"step{step_idx}: modal closed tries={attempts}")
            return True
        if poll > 0:
            time.sleep(poll)

    if logger is not None:
        logger.log(f"step{step_idx}: modal still open after timeout ({timeout}s)")
        frame, _ = capture_screen(region, sct=sct)
        local = find_rogues(frame, offset=(0, 0))
        logger.save_image(
            f"step{step_idx:02d}_fail_modal_still_open.png",
            logger.annotate_rogues(frame, local, pick_leftmost_rogue(local)),
        )
    return False


def assign_single_blueprint(
    region: Region,
    cfg: dict[str, Any],
    *,
    sct: Any,
    logger: AssignLogger,
    stop_event: Optional[threading.Event] = None,
    blueprint_idx: int = 1,
) -> int:
    """РќР°Р·РЅР°С‡Р°РµС‚ rogue РЅР° РѕРґРёРЅ РѕС‚РєСЂС‹С‚С‹Р№ Р±Р»СЋРїСЂРёРЅС‚ + CONFIRM + Ctrl РїРѕ СЃР»РѕС‚Сѓ."""
    timeout = float(cfg.get("modal_timeout_sec", 1.5))
    close_timeout = float(cfg.get("modal_close_timeout_sec", 1.0))
    click_delay = float(cfg.get("click_delay_sec", 0.05))
    between = float(cfg.get("between_contracts_sec", 0.05))
    poll = float(cfg.get("poll_interval_sec", 0.03))
    if poll >= timeout:
        poll = max(0.02, timeout / 6)
    if poll >= close_timeout:
        poll = max(0.02, close_timeout / 6)
    verbose = bool(cfg.get("verbose_logs", False))

    logger.log("-" * 60)
    logger.log(f"BLUEPRINT #{blueprint_idx} START")

    contracts, frame, offset = discover_contracts(
        region, cfg, sct=sct, logger=logger
    )
    logger.log(f"capture offset={offset} frame={frame.shape[1]}x{frame.shape[0]}")
    logger.log(f"contracts={len(contracts)} screen={[ (c.x, c.y) for c in contracts ]}")

    if not contracts:
        # UI РјРѕРі РЅРµ СѓСЃРїРµС‚СЊ вЂ” РєРѕСЂРѕС‚РєР°СЏ РїР°СѓР·Р° Рё РїРѕРІС‚РѕСЂ
        time.sleep(0.2)
        frame2, offset2 = capture_screen(region, sct=sct)
        local2 = find_contracts(frame2, cfg=cfg, screen_coords=False)
        contracts = _with_screen_offset(local2, offset2)
        contracts = _contracts_prefer_full_triplets(contracts)
        if contracts:
            logger.log(f"rescanned empty slots={len(contracts)}")
            logger.save_image(
                "00_targets_rescan.png",
                logger.annotate_contracts(frame2, local2),
            )
        else:
            logger.log("NO EMPTY job slots (СѓР¶Рµ Р·Р°РЅСЏС‚С‹ РёР»Рё РЅРµ РЅР°Р№РґРµРЅС‹) вЂ” С‚РѕР»СЊРєРѕ CONFIRM")
            ok = confirm_plans_and_take_blueprint(
                region,
                cfg,
                sct=sct,
                logger=logger,
                click_delay=click_delay,
            )
            logger.log(f"CONFIRM+CTRL {'OK' if ok else 'SKIP/FAIL'}")
            return 1 if ok else 0

    logger.log(f"assigning {len(contracts)} EMPTY slots (LEFTMOST rogue)")
    done = 0
    t0 = time.perf_counter()

    for idx, contract in enumerate(contracts, 1):
        if stop_event is not None and stop_event.is_set():
            logger.log("STOPPED by user")
            break

        logger.log(f"STEP {idx}/{len(contracts)} click contract ({contract.x},{contract.y})")
        click_screen(contract.x, contract.y, delay=click_delay)

        rogues, modal_frame, _modal_offset = wait_for_rogues(
            region,
            timeout=timeout,
            poll=poll,
            stop_event=stop_event,
            logger=logger,
            step_idx=idx,
            sct=sct,
        )
        if stop_event is not None and stop_event.is_set():
            logger.log("STOPPED by user")
            break

        chosen = pick_leftmost_rogue(rogues)
        if chosen is None or modal_frame is None:
            logger.log(f"STEP {idx}: FAIL no rogue/modal")
            continue

        if verbose:
            local_rogues = find_rogues(modal_frame, offset=(0, 0))
            logger.save_image(
                f"bp{blueprint_idx:02d}_step{idx:02d}_c_rogues.png",
                logger.annotate_rogues(
                    modal_frame, local_rogues, pick_leftmost_rogue(local_rogues)
                ),
            )

        logger.log(f"STEP {idx}: n={len(rogues)} chosen={chosen.center} -> click")
        settle = float(cfg.get("rogue_click_settle_sec", 0.18))
        retries = max(1, int(cfg.get("rogue_click_retries", 2)))
        if settle > 0:
            time.sleep(settle)

        closed = False
        for attempt in range(1, retries + 1):
            frame_now, off_now = capture_screen(region, sct=sct)
            fresh_local = find_rogues(frame_now, offset=(0, 0))
            fresh_screen = [
                RogueHit(
                    x=r.x + off_now[0],
                    y=r.y + off_now[1],
                    bbox=(
                        r.bbox[0] + off_now[0],
                        r.bbox[1] + off_now[1],
                        r.bbox[2],
                        r.bbox[3],
                    ),
                    radius=r.radius,
                )
                for r in fresh_local
            ]
            target = pick_leftmost_rogue(fresh_screen) or chosen
            logger.log(
                f"STEP {idx}: rogue click try {attempt}/{retries} at {target.center}"
            )
            click_screen(target.x, target.y, delay=click_delay)
            closed = wait_modal_closed(
                region,
                timeout=close_timeout,
                poll=poll,
                stop_event=stop_event,
                logger=logger,
                step_idx=idx,
                sct=sct,
            )
            if closed:
                break
            if stop_event is not None and stop_event.is_set():
                break
            if settle > 0:
                time.sleep(settle)

        if closed:
            done += 1
            logger.log(f"STEP {idx}: OK")
        else:
            logger.log(f"STEP {idx}: FAIL modal did not close")

        if between > 0:
            time.sleep(between)

    elapsed = time.perf_counter() - t0
    logger.log(f"BLUEPRINT #{blueprint_idx} ASSIGN {done}/{len(contracts)} in {elapsed:.2f}s")

    stopped = stop_event is not None and stop_event.is_set()
    if done > 0 and not stopped:
        ok = confirm_plans_and_take_blueprint(
            region,
            cfg,
            sct=sct,
            logger=logger,
            click_delay=click_delay,
        )
        logger.log(f"CONFIRM+CTRL {'OK' if ok else 'SKIP/FAIL'}")
    return done


def assign_contracts(
    cfg: Optional[dict[str, Any]] = None,
    *,
    stop_event: Optional[threading.Event] = None,
    on_log: Optional[Any] = None,
    on_hud: Optional[Any] = None,
) -> int:
    """
    РќР°Р·РЅР°С‡Р°РµС‚ rogue РЅР° РєРѕРЅС‚СЂР°РєС‚С‹. РџСЂРё loop_blueprints=true вЂ” С†РёРєР»:
    assign в†’ CONFIRM в†’ Ctrl СЃР»РѕС‚ в†’ Ctrl СЃР»РµРґСѓСЋС‰РёР№ РІ РёРЅРІРµРЅС‚Р°СЂРµ в†’ СЃРЅРѕРІР°.
    """
    if mss is None or cv2 is None:
        raise ImportError("Install opencv-python, mss and numpy: pip install opencv-python mss numpy")

    if cfg is None:
        cfg = load_config()

    region = region_from_config(cfg)
    click_delay = float(cfg.get("click_delay_sec", 0.05))
    save_logs = bool(cfg.get("save_logs", True))
    logs_dir = logs_dir_from_config(cfg)
    logger = AssignLogger(logs_dir, enabled=save_logs, on_log=on_log)
    sync_inventory_grid(cfg)
    grid = inventory_grid(cfg)
    cells = grid.cells()
    click_delay = float(cfg.get("click_delay_sec", 0.05))

    try:
        logger.log("=" * 60)
        logger.log(f"ASSIGN START grid={grid.cols}x{grid.rows} cells={len(cells)}")
        logger.log(f"session={logger.session_dir if save_logs else 'off'}")

        if not cells:
            logger.log("Inventory grid is empty — set overlay first")
            return 0

        total_done = 0
        opened = 0
        ready_timeout = float(cfg.get("blueprint_ready_timeout_sec", 4.5))
        with mss.mss() as sct:
            for bp_idx, cell in enumerate(cells, start=1):
                if stop_event is not None and stop_event.is_set():
                    logger.log("STOPPED by user")
                    break
                frame, offset = capture_screen(region, sct=sct)
                if cell_is_empty(frame, cell, cfg, offset=offset):
                    logger.log(f"skip empty cell {bp_idx}/{len(cells)}")
                    later = cells[bp_idx:]
                    if not later or all(cell_is_empty(frame, extra, cfg, offset=offset) for extra in later):
                        logger.log("No more blueprints in inventory area")
                        break
                    continue
                x, y = cell.click
                opened += 1
                if on_hud is not None:
                    try:
                        on_hud(f"{bp_idx}/{len(cells)}", f"OPEN {bp_idx}/{len(cells)}")
                    except Exception:
                        pass
                logger.log(f"OPEN inventory cell {bp_idx}/{len(cells)} ({x},{y})")
                ctrl_click_screen(x, y, delay=click_delay)
                ready = wait_blueprint_ready(
                    region,
                    cfg,
                    timeout=ready_timeout,
                    sct=sct,
                    stop_event=stop_event,
                    logger=logger,
                )
                if not ready:
                    logger.log("blueprint UI not ready — retry Ctrl+click same cell")
                    ctrl_click_screen(x, y, delay=click_delay)
                    time.sleep(float(cfg.get("blueprint_open_settle_sec", 0.9)))
                    ready = wait_blueprint_ready(
                        region,
                        cfg,
                        timeout=ready_timeout,
                        sct=sct,
                        stop_event=stop_event,
                        logger=logger,
                    )
                if not ready:
                    logger.log(f"Stop: cell {bp_idx} did not open a blueprint")
                    break

                done = assign_single_blueprint(
                    region,
                    cfg,
                    sct=sct,
                    logger=logger,
                    stop_event=stop_event,
                    blueprint_idx=bp_idx,
                )
                total_done += done
                if stop_event is not None and stop_event.is_set():
                    break
                if done == 0:
                    logger.log("Stop: no contracts on this blueprint")
                    break

            if opened == 0:
                logger.log("No more blueprints in inventory area")
            logger.log("=" * 60)
            logger.log(f"ASSIGN TOTAL contracts={total_done}")
            logger.log(f"See folder: {logger.session_dir}")
            return total_done
    except Exception as exc:  # noqa: BLE001
        import traceback

        logger.log(f"EXCEPTION: {exc}")
        logger.log(traceback.format_exc())
        raise
    finally:
        logger.close()


def draw_contracts(
    image: ImageLike,
    contracts: Sequence[ContractHit],
    *,
    color: Tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    canvas = _load_image(image).copy()
    overlay = canvas.copy()

    for hit in contracts:
        x, y, w, h = hit.bbox
        pad = 3
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = x + w + pad, y + h + pad
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, -1)

    cv2.addWeighted(overlay, 0.28, canvas, 0.72, 0, canvas)

    for idx, hit in enumerate(contracts, 1):
        x, y, w, h = hit.bbox
        pad = 3
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = x + w + pad, y + h + pad
        cv2.rectangle(canvas, (x0, y0), (x1, y1), color, 2)
        cv2.circle(canvas, (hit.x, hit.y), 4, (0, 0, 255), -1)
        label = f"#{idx}"
        if hit.group >= 0:
            label += f" g{hit.group}"
        cv2.putText(
            canvas,
            label,
            (x0, max(16, y0 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    return canvas


def save_detection_log(
    frame: np.ndarray,
    contracts: Sequence[ContractHit],
    logs_dir: Union[str, Path],
    *,
    prefix: str = "detect",
) -> Path:
    out_dir = Path(logs_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"{prefix}_{stamp}_{len(contracts)}.png"
    cv2.imwrite(str(path), draw_contracts(frame, contracts))
    return path


def run_hotkey_loop(cfg: Optional[dict[str, Any]] = None) -> None:
    raise RuntimeError('Heist assign is started from the PoE Helper Blueprint Confirm screen.')


if __name__ == "__main__":
    print('Run PoE Helper and open Blueprint Confirm from the home screen.')

