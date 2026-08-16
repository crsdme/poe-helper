from __future__ import annotations

import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config import ItemGrid, Rect
from app.heist.engine import inventory_grid, sync_inventory_grid
from app.heist.reveal import (
    load_reveal_config,
    map_rect,
    save_reveal_config,
    slot_point,
    sync_map_rect,
)
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
    ("open_settle_sec", "reveal.open_settle"),
    ("reveal_settle_sec", "reveal.wing_settle"),
    ("between_blueprints_sec", "reveal.between"),
]

PRESETS = {
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


class RevealScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        app.set_reveal_view(self)
        self._cfg = load_reveal_config()
        self._speed_vars: dict[str, ctk.CTkEntry] = {}
        self._overlay = None
        self._capturing: str | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(top, text=t("nav.back"), width=88, command=self._go_home, **_outline()).pack(side="left")
        ctk.CTkLabel(
            top,
            text=t("reveal.title"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)
        self._status = ctk.CTkLabel(top, text=t("heist.ready"), text_color=TEXT_MUTED)
        self._status.pack(side="right")

        ctk.CTkLabel(
            self,
            text=t("reveal.hint"),
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
        self._stop_btn.pack(side="left")

        self._card(t("reveal.map"))
        mapping = ctk.CTkFrame(self._last, fg_color="transparent")
        mapping.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(
            mapping,
            text=t("reveal.map_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=12),
            wraplength=860,
            justify="left",
        ).pack(anchor="w")
        map_row = ctk.CTkFrame(mapping, fg_color="transparent")
        map_row.pack(fill="x", pady=(10, 0))
        field_label(map_row, t("reveal.map"), t("reveal.map_help")).pack(side="left")
        self._map_lbl = ctk.CTkLabel(map_row, text=self._fmt_map(), text_color=TEXT)
        self._map_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            map_row,
            text=t("settings.set_overlay"),
            width=130,
            command=self._pick_map,
            **_outline(),
        ).pack(side="right")
        slot_row = ctk.CTkFrame(mapping, fg_color="transparent")
        slot_row.pack(fill="x", pady=(8, 0))
        field_label(slot_row, t("reveal.slot"), t("reveal.slot_help")).pack(side="left")
        self._slot_lbl = ctk.CTkLabel(slot_row, text=self._fmt_slot(), text_color=TEXT)
        self._slot_lbl.pack(side="left", padx=10)
        ctk.CTkButton(
            slot_row,
            text=t("settings.set_overlay"),
            width=130,
            command=self._pick_slot,
            **_outline(),
        ).pack(side="right")

        self._card(t("heist.inventory_region"))
        inv = ctk.CTkFrame(self._last, fg_color="transparent")
        inv.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(
            inv,
            text=t("reveal.inventory_hint"),
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
        self._start_key_btn = self._hotkey_row(keys, t("heist.hotkey_start"), self._cfg.get("hotkey", "f11"), "start")
        self._stop_key_btn = self._hotkey_row(keys, t("heist.hotkey_stop"), self._cfg.get("exit_hotkey", "f12"), "stop")
        ctk.CTkLabel(
            keys,
            text=t("reveal.hotkeys_hint"),
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
        self.append_log(
            t(
                "reveal.ready_log",
                start=str(self._cfg.get("hotkey", "f11")).upper(),
                stop=str(self._cfg.get("exit_hotkey", "f12")).upper(),
            )
        )

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
        if self._app.reveal_running():
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
        save_reveal_config(self._cfg)
        self._app.refresh_hotkeys()
        return "break"

    def _fmt_map(self) -> str:
        rect = map_rect(self._cfg)
        return f"{rect.x}, {rect.y}  ·  {rect.w}×{rect.h}"

    def _fmt_slot(self) -> str:
        point = slot_point(self._cfg)
        if point is None:
            return t("heist.point_auto")
        return f"{point[0]}, {point[1]}"

    def _fmt_inventory(self) -> str:
        grid = inventory_grid(self._cfg)
        return f"{grid.cols}×{grid.rows}  ·  {grid.x}, {grid.y}  ·  {grid.w}×{grid.h}"

    def _slot_rect(self) -> Rect:
        point = slot_point(self._cfg)
        if point is None:
            return Rect(x=900, y=720, w=56, h=56)
        return Rect.from_click(point[0], point[1], 56, 56)

    def _read(self) -> None:
        for key, entry in self._speed_vars.items():
            raw = entry.get().strip().replace(",", ".")
            try:
                self._cfg[key] = float(raw)
            except ValueError:
                pass
        sync_inventory_grid(self._cfg)
        sync_map_rect(self._cfg)

    def _persist(self) -> None:
        self._read()
        save_reveal_config(self._cfg)

    def _preset(self, name: str) -> None:
        for key, value in PRESETS[name].items():
            entry = self._speed_vars.get(key)
            if entry is not None:
                entry.delete(0, "end")
                entry.insert(0, str(value))
        self._persist()
        self.append_log(t("heist.preset", name=name))

    def _pick_map(self) -> None:
        if self._app.reveal_running():
            return
        close_open()
        self._drop_overlay()
        self._app.iconify()
        self._overlay = PositionOverlay(
            self._app,
            title=t("reveal.map"),
            rect=map_rect(self._cfg),
            on_confirm=self._finish_map,
            on_cancel=self._restore,
            min_size=(240, 180),
            show_dot=False,
            hint=t("reveal.map_help"),
        )

    def _finish_map(self, rect: Rect) -> None:
        sync_map_rect(self._cfg, rect)
        save_reveal_config(self._cfg)
        self._map_lbl.configure(text=self._fmt_map())
        self._restore()
        self.append_log(t("reveal.map_set"))

    def _pick_slot(self) -> None:
        if self._app.reveal_running():
            return
        close_open()
        self._drop_overlay()
        self._app.iconify()
        self._overlay = PositionOverlay(
            self._app,
            title=t("reveal.slot"),
            rect=self._slot_rect(),
            on_confirm=self._finish_slot,
            on_cancel=self._restore,
            min_size=(40, 40),
            hint=t("reveal.slot_help"),
        )

    def _finish_slot(self, rect: Rect) -> None:
        x, y = rect.click
        ui = self._cfg.setdefault("ui_points", {})
        ui["blueprint_slot"] = [int(x), int(y)]
        save_reveal_config(self._cfg)
        self._slot_lbl.configure(text=f"{x}, {y}")
        self._restore()
        self.append_log(t("heist.point_set", name=t("reveal.slot"), x=x, y=y))

    def _pick_inventory(self) -> None:
        if self._app.reveal_running():
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
        save_reveal_config(self._cfg)
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
        self._app.start_reveal()

    def stop(self) -> None:
        self._app.stop_reveal()

    def set_running(self, running: bool) -> None:
        self._start_btn.configure(state="disabled" if running else "normal")
        self._stop_btn.configure(state="normal" if running else "disabled")
        self._status.configure(text=t("heist.running") if running else t("heist.ready"))

    def _sync_running(self) -> None:
        self.set_running(self._app.reveal_running())

    def append_log(self, line: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self._log.configure(state="normal")
        self._log.insert("end", f"{stamp}  {line.rstrip()}\n")
        self._log.see("end")
        self._log.configure(state="disabled")
