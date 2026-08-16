from __future__ import annotations

import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config import ItemGrid, Rect
from app.heist.engine import inventory_grid, load_heist_config, save_heist_config, sync_inventory_grid
from app.i18n import t
from app.overlay import GridOverlay, PositionOverlay
from app.theme import (
    BG,
    BORDER,
    DANGER,
    FONT,
    PRIMARY,
    PRIMARY_FG,
    PRIMARY_HOVER,
    RADIUS,
    SELECTED,
    SURFACE,
    TEXT,
    TEXT_MUTED,
)
from app.widgets.scroll import enable_mousewheel
from app.widgets.select import close_open
from app.widgets.tooltip import field_label

if TYPE_CHECKING:
    from app.main_window import MainWindow

SPEED_KEYS = [
    ("click_delay_sec", "heist.click_delay"),
    ("between_contracts_sec", "heist.between"),
    ("poll_interval_sec", "heist.poll"),
    ("modal_timeout_sec", "heist.modal_open"),
    ("modal_close_timeout_sec", "heist.modal_close"),
    ("confirm_delay_sec", "heist.confirm_delay"),
    ("blueprint_open_settle_sec", "heist.bp_settle"),
    ("rogue_click_settle_sec", "heist.rogue_settle"),
]

PRESETS = {
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


def _outline() -> dict:
    return {
        "fg_color": "transparent",
        "border_color": BORDER,
        "border_width": 1,
        "text_color": TEXT,
        "hover_color": SELECTED,
        "corner_radius": RADIUS,
    }


def _primary() -> dict:
    return {
        "fg_color": PRIMARY,
        "hover_color": PRIMARY_HOVER,
        "text_color": PRIMARY_FG,
        "corner_radius": RADIUS,
        "font": ctk.CTkFont(family=FONT, size=13, weight="bold"),
    }


class HeistScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        app.set_heist_view(self)
        self._cfg = load_heist_config()
        self._speed_vars: dict[str, ctk.CTkEntry] = {}
        self._overlay = None
        self._capturing: str | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(top, text=t("nav.back"), width=88, command=self._go_home, **_outline()).pack(side="left")
        ctk.CTkLabel(
            top,
            text=t("heist.title"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)
        self._status = ctk.CTkLabel(top, text=t("heist.ready"), text_color=TEXT_MUTED)
        self._status.pack(side="right")

        ctk.CTkLabel(
            self,
            text=t("heist.hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=13),
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=32, pady=(0, 8))

        body = ctk.CTkScrollableFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=32, pady=(0, 12))
        enable_mousewheel(body)
        self._body = body

        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.pack(fill="x", pady=(0, 10))
        self._start_btn = ctk.CTkButton(bar, text=t("heist.start"), width=120, command=self.start, **_primary())
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = ctk.CTkButton(
            bar,
            text=t("heist.stop"),
            width=100,
            command=self.stop,
            fg_color="transparent",
            border_color=DANGER,
            border_width=1,
            text_color=DANGER,
            hover_color="#3f1d1d",
            corner_radius=RADIUS,
            state="disabled",
        )
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._card(t("heist.points"))
        pts = ctk.CTkFrame(self._last, fg_color="transparent")
        pts.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(
            pts,
            text=t("heist.points_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=12),
            wraplength=860,
            justify="left",
        ).pack(anchor="w")
        confirm_row = ctk.CTkFrame(pts, fg_color="transparent")
        confirm_row.pack(fill="x", pady=(10, 0))
        field_label(confirm_row, t("heist.confirm_point"), t("heist.confirm_point_help")).pack(side="left")
        self._confirm_lbl = ctk.CTkLabel(confirm_row, text=self._fmt_point("confirm"), text_color=TEXT)
        self._confirm_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            confirm_row,
            text=t("settings.set_overlay"),
            width=130,
            command=lambda: self._pick_point("confirm"),
            **_outline(),
        ).pack(side="right")
        bp_row = ctk.CTkFrame(pts, fg_color="transparent")
        bp_row.pack(fill="x", pady=(8, 0))
        field_label(bp_row, t("heist.bp_point"), t("heist.bp_point_help")).pack(side="left")
        self._bp_lbl = ctk.CTkLabel(bp_row, text=self._fmt_point("blueprint_slot"), text_color=TEXT)
        self._bp_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            bp_row,
            text=t("settings.set_overlay"),
            width=130,
            command=lambda: self._pick_point("blueprint_slot"),
            **_outline(),
        ).pack(side="right")
        ctk.CTkButton(pts, text=t("heist.clear_points"), width=160, command=self._clear_points, **_outline()).pack(
            anchor="w", pady=(10, 0)
        )

        self._card(t("heist.inventory_region"))
        inv = ctk.CTkFrame(self._last, fg_color="transparent")
        inv.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(
            inv,
            text=t("heist.inventory_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=12),
            wraplength=860,
            justify="left",
        ).pack(anchor="w")
        inv_row = ctk.CTkFrame(inv, fg_color="transparent")
        inv_row.pack(fill="x", pady=(10, 0))
        self._inv_lbl = ctk.CTkLabel(inv_row, text=self._fmt_inventory(), text_color=TEXT)
        self._inv_lbl.pack(side="left")
        ctk.CTkButton(
            inv_row,
            text=t("settings.set_overlay"),
            width=160,
            command=self._pick_inventory,
            **_primary(),
        ).pack(side="right")

        self._card(t("heist.hotkeys"))
        keys = ctk.CTkFrame(self._last, fg_color="transparent")
        keys.pack(fill="x", padx=16, pady=12)
        self._start_key_btn = self._hotkey_row(keys, t("heist.hotkey_start"), self._cfg.get("hotkey", "f9"), "start")
        self._stop_key_btn = self._hotkey_row(keys, t("heist.hotkey_stop"), self._cfg.get("exit_hotkey", "f10"), "stop")
        ctk.CTkLabel(
            keys,
            text=t("heist.hotkeys_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=11),
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self._card(t("heist.speed"))
        speed = ctk.CTkFrame(self._last, fg_color="transparent")
        speed.pack(fill="x", padx=16, pady=12)
        presets = ctk.CTkFrame(speed, fg_color="transparent")
        presets.pack(fill="x", pady=(0, 8))
        for name, label in (("slow", t("heist.slow")), ("normal", t("heist.normal")), ("fast", t("heist.fast"))):
            ctk.CTkButton(presets, text=label, width=110, command=lambda n=name: self._preset(n), **_outline()).pack(
                side="left", padx=(0, 8)
            )
        grid = ctk.CTkFrame(speed, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)
        for index, (key, label_id) in enumerate(SPEED_KEYS):
            r, c = divmod(index, 2)
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="ew", padx=4, pady=3)
            ctk.CTkLabel(cell, text=t(label_id), text_color=TEXT_MUTED, width=220, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(cell, width=72, height=28, fg_color=SURFACE, border_color=BORDER, text_color=TEXT)
            entry.insert(0, str(self._cfg.get(key, "")))
            entry.pack(side="left")
            entry.bind("<FocusOut>", lambda _e: self._persist())
            entry.bind("<Return>", lambda _e: self._persist())
            self._speed_vars[key] = entry

        self._card(t("heist.log"))
        self._log = ctk.CTkTextbox(
            self._last,
            height=180,
            fg_color="#111113",
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        self._log.pack(fill="both", expand=True, padx=12, pady=12)
        self._log.configure(state="disabled")
        self._sync_running()
        self.append_log(t("heist.ready_log", start=str(self._cfg.get("hotkey", "f9")).upper(), stop=str(self._cfg.get("exit_hotkey", "f10")).upper()))

    def _card(self, title: str) -> None:
        ctk.CTkLabel(
            self._body,
            text=title,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", pady=(14, 6))
        card = ctk.CTkFrame(
            self._body,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        card.pack(fill="x", pady=(0, 4))
        self._last = card

    def _go_home(self) -> None:
        self._persist()
        self._app.show_home()

    def _hotkey_row(self, master, label: str, value: str, kind: str) -> ctk.CTkButton:
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, text_color=TEXT_MUTED, width=180, anchor="w").pack(side="left")
        button = ctk.CTkButton(
            row,
            text=str(value or "").upper(),
            width=120,
            command=lambda: self._capture_hotkey(kind),
            **_outline(),
        )
        button.pack(side="left")
        return button

    def _capture_hotkey(self, kind: str) -> None:
        if self._app.heist_running():
            return
        buttons = {"start": self._start_key_btn, "stop": self._stop_key_btn}
        button = buttons[kind]
        button.configure(text=t("settings.press_key"))
        self._capturing = kind
        self._app._hotkeys.enabled = False
        self._app._hotkeys.stop()
        self._app.focus_set()
        self._app.unbind("<KeyPress>")
        self._app.bind("<KeyPress>", self._on_hotkey)

    def _on_hotkey(self, event) -> str:
        kind = self._capturing
        if not kind:
            return "break"
        key = event.keysym
        if key in {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}:
            return "break"
        if kind == "start":
            self._cfg["hotkey"] = key
            self._start_key_btn.configure(text=key)
        else:
            self._cfg["exit_hotkey"] = key
            self._stop_key_btn.configure(text=key)
        self._capturing = None
        self._app.unbind("<KeyPress>")
        save_heist_config(self._cfg)
        self._app.refresh_hotkeys()
        return "break"

    def _fmt_point(self, key: str) -> str:
        ui = self._cfg.get("ui_points") or {}
        pt = ui.get(key)
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            return f"{pt[0]}, {pt[1]}"
        return t("heist.point_auto")

    def _fmt_inventory(self) -> str:
        grid = inventory_grid(self._cfg)
        return f"{grid.cols}×{grid.rows}  ·  {grid.x}, {grid.y}  ·  {grid.w}×{grid.h}"

    def _point_rect(self, key: str) -> Rect:
        ui = self._cfg.get("ui_points") or {}
        pt = ui.get(key)
        if isinstance(pt, (list, tuple)) and len(pt) == 2:
            return Rect.from_click(int(pt[0]), int(pt[1]), 80, 48)
        return Rect(x=480, y=360, w=80, h=48)

    def _read(self) -> None:
        for key, entry in self._speed_vars.items():
            raw = entry.get().strip().replace(",", ".")
            try:
                self._cfg[key] = float(raw)
            except ValueError:
                pass
        sync_inventory_grid(self._cfg)

    def _persist(self) -> None:
        self._read()
        save_heist_config(self._cfg)

    def _preset(self, name: str) -> None:
        for key, value in PRESETS[name].items():
            entry = self._speed_vars.get(key)
            if entry is not None:
                entry.delete(0, "end")
                entry.insert(0, str(value))
        self._persist()
        self.append_log(t("heist.preset", name=name))

    def _clear_points(self) -> None:
        self._cfg["ui_points"] = {}
        save_heist_config(self._cfg)
        self._confirm_lbl.configure(text=t("heist.point_auto"))
        self._bp_lbl.configure(text=t("heist.point_auto"))
        self.append_log(t("heist.points_cleared"))

    def _pick_point(self, key: str) -> None:
        if self._app.heist_running():
            return
        close_open()
        self._drop_overlay()
        self._app.iconify()
        title = t("heist.confirm_point") if key == "confirm" else t("heist.bp_point")
        hint = t("heist.confirm_point_help") if key == "confirm" else t("heist.bp_point_help")
        self._overlay = PositionOverlay(
            self._app,
            title=title,
            rect=self._point_rect(key),
            on_confirm=lambda rect, item=key: self._finish_point(item, rect),
            on_cancel=self._restore,
            min_size=(48, 32),
            hint=hint,
        )

    def _finish_point(self, key: str, rect: Rect) -> None:
        x, y = rect.click
        ui = self._cfg.setdefault("ui_points", {})
        ui[key] = [int(x), int(y)]
        save_heist_config(self._cfg)
        label = self._confirm_lbl if key == "confirm" else self._bp_lbl
        label.configure(text=f"{x}, {y}")
        self._restore()
        name = t("heist.confirm_point") if key == "confirm" else t("heist.bp_point")
        self.append_log(t("heist.point_set", name=name, x=x, y=y))

    def _pick_inventory(self) -> None:
        if self._app.heist_running():
            return
        close_open()
        self._drop_overlay()
        self._app.iconify()
        self._overlay = GridOverlay(
            self._app,
            grid=inventory_grid(self._cfg),
            on_confirm=self._finish_inventory,
            on_cancel=self._restore,
            title=t("heist.inventory_region"),
        )

    def _finish_inventory(self, grid: ItemGrid) -> None:
        sync_inventory_grid(self._cfg, grid)
        save_heist_config(self._cfg)
        self._inv_lbl.configure(text=self._fmt_inventory())
        self._restore()
        self.append_log(t("heist.inventory_set"))

    def _restore(self) -> None:
        self._overlay = None
        self._app.deiconify()
        self._app.lift()

    def _drop_overlay(self) -> None:
        overlay = self._overlay
        self._overlay = None
        if overlay is None:
            return
        try:
            close = getattr(overlay, "_close", None)
            if callable(close):
                close()
            elif overlay.winfo_exists():
                overlay.destroy()
        except Exception:
            pass

    def start(self) -> None:
        self._persist()
        self._app.start_heist()

    def stop(self) -> None:
        self._app.stop_heist()

    def set_running(self, running: bool) -> None:
        self._start_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if running else "disabled")
        self._status.configure(text=t("heist.running") if running else t("heist.ready"))

    def _sync_running(self) -> None:
        self.set_running(self._app.heist_running())

    def append_log(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"{stamp}  {line.rstrip()}\n")
        self._log.see("end")
        self._log.configure(state="disabled")
