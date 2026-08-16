from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.settings import load_settings, save_settings

HUD_WIDTH = 260
HUD_HEIGHT = 148


def default_hud_xy(screen_w: int, width: int = HUD_WIDTH) -> tuple[int, int]:
    return max(16, int(screen_w) - int(width) - 16), 16


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


@dataclass
class Rect:
    x: int = 240
    y: int = 240
    w: int = 72
    h: int = 72

    @property
    def click(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_click(cls, x: int, y: int, w: int = 50, h: int = 50) -> Rect:
        return cls(x=int(x) - w // 2, y=int(y) - h // 2, w=w, h=h)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, default: Rect | None = None) -> Rect:
        base = default or cls()
        data = data or {}
        return cls(
            x=int(data.get("x", base.x)),
            y=int(data.get("y", base.y)),
            w=int(data.get("w", base.w)),
            h=int(data.get("h", base.h)),
        )


@dataclass
class CurrencyTab:
    x: int = 80
    y: int = 120
    w: int = 640
    h: int = 360
    cols: int = 12
    rows: int = 5

    def cell_rect(self, col: int, row: int) -> Rect:
        cell_w = max(1, self.w / self.cols)
        cell_h = max(1, self.h / self.rows)
        return Rect(
            x=int(self.x + col * cell_w),
            y=int(self.y + row * cell_h),
            w=int(cell_w),
            h=int(cell_h),
        )

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "cols": self.cols, "rows": self.rows}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CurrencyTab:
        data = data or {}
        return cls(
            x=int(data.get("x", 80)),
            y=int(data.get("y", 120)),
            w=int(data.get("w", 640)),
            h=int(data.get("h", 360)),
            cols=int(data.get("cols", 12)),
            rows=int(data.get("rows", 5)),
        )


@dataclass
class ItemGrid:
    x: int = 420
    y: int = 420
    w: int = 480
    h: int = 196
    cols: int = 5
    rows: int = 2

    def cell_rect(self, col: int, row: int) -> Rect:
        cell_w = max(1, self.w / max(1, self.cols))
        cell_h = max(1, self.h / max(1, self.rows))
        return Rect(
            x=int(self.x + col * cell_w),
            y=int(self.y + row * cell_h),
            w=int(cell_w),
            h=int(cell_h),
        )

    def cells(self) -> list[Rect]:
        return [self.cell_rect(col, row) for row in range(self.rows) for col in range(self.cols)]

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h, "cols": self.cols, "rows": self.rows}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ItemGrid:
        data = data or {}
        return cls(
            x=int(data.get("x", 420)),
            y=int(data.get("y", 420)),
            w=int(data.get("w", 480)),
            h=int(data.get("h", 196)),
            cols=max(1, min(12, int(data.get("cols", 5)))),
            rows=max(1, min(12, int(data.get("rows", 2)))),
        )


@dataclass
class AppConfig:
    language: str = "ru"
    speed_ms: int = 80
    logs_enabled: bool = True
    shift_lock: bool = True
    hotkey_start: str = "F6"
    hotkey_stop: str = "F7"
    hotkey_chain: str = "F8"
    last_scenario_id: str = ""
    hud_x: int | None = None
    hud_y: int | None = None
    hud_w: int | None = None
    hud_h: int | None = None
    item: Rect | None = None
    chain_grid: ItemGrid | None = None
    currency_tab: CurrencyTab | None = None
    currency_cells: dict[str, list[int]] = field(default_factory=dict)
    currency_slots: dict[str, str] = field(default_factory=dict)
    positions: dict[str, Rect] = field(default_factory=dict)

    def point_for(self, key: str) -> tuple[int, int] | None:
        if key == "item" and self.item:
            return self.item.click
        if key in self.positions:
            return self.positions[key].click
        if self.currency_tab and self.currency_slots:
            from app.data.currency_layout import SLOTS_BY_KEY

            tab = Rect(x=self.currency_tab.x, y=self.currency_tab.y, w=self.currency_tab.w, h=self.currency_tab.h)
            for slot_key, currency_id in self.currency_slots.items():
                if currency_id != key:
                    continue
                slot = SLOTS_BY_KEY.get(slot_key)
                if slot:
                    return slot.to_rect(tab).click
        cell = self.currency_cells.get(key)
        if cell and self.currency_tab and len(cell) == 2:
            return self.currency_tab.cell_rect(cell[0], cell[1]).click
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "speed_ms": self.speed_ms,
            "logs_enabled": self.logs_enabled,
            "shift_lock": self.shift_lock,
            "hotkey_start": self.hotkey_start,
            "hotkey_stop": self.hotkey_stop,
            "hotkey_chain": self.hotkey_chain,
            "hud_x": self.hud_x,
            "hud_y": self.hud_y,
            "hud_w": self.hud_w,
            "hud_h": self.hud_h,
            "item": self.item.to_dict() if self.item else None,
            "chain_grid": self.chain_grid.to_dict() if self.chain_grid else None,
            "currency_tab": self.currency_tab.to_dict() if self.currency_tab else None,
            "currency_cells": self.currency_cells,
            "currency_slots": self.currency_slots,
            "positions": {key: rect.to_dict() for key, rect in self.positions.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        positions = {
            key: Rect.from_dict(value)
            for key, value in (data.get("positions") or {}).items()
            if isinstance(value, dict)
        }
        item_data = data.get("item")
        chain_data = data.get("chain_grid")
        tab_data = data.get("currency_tab")
        return cls(
            language=data.get("language", "ru"),
            speed_ms=max(0, int(data.get("speed_ms", 80))),
            logs_enabled=bool(data.get("logs_enabled", True)),
            shift_lock=bool(data.get("shift_lock", True)),
            hotkey_start=data.get("hotkey_start", "F6"),
            hotkey_stop=data.get("hotkey_stop", "F7"),
            hotkey_chain=data.get("hotkey_chain", "F8"),
            last_scenario_id=str(data.get("last_scenario_id") or ""),
            hud_x=_opt_int(data.get("hud_x")),
            hud_y=_opt_int(data.get("hud_y")),
            hud_w=_opt_int(data.get("hud_w")),
            hud_h=_opt_int(data.get("hud_h")),
            item=Rect.from_dict(item_data) if item_data else None,
            chain_grid=ItemGrid.from_dict(chain_data) if chain_data else None,
            currency_tab=CurrencyTab.from_dict(tab_data) if tab_data else None,
            currency_cells={
                key: [int(value[0]), int(value[1])]
                for key, value in (data.get("currency_cells") or {}).items()
                if isinstance(value, list) and len(value) == 2
            },
            currency_slots={
                key: str(value)
                for key, value in (data.get("currency_slots") or {}).items()
                if isinstance(value, str) and value
            },
            positions=positions,
        )


def load_config() -> AppConfig:
    return AppConfig.from_dict(load_settings())


def save_config(config: AppConfig) -> None:
    save_settings(config.to_dict())
