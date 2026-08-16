from __future__ import annotations

from typing import TYPE_CHECKING
from tkinter import messagebox
import tkinter as tk

import customtkinter as ctk

from app.config import HUD_HEIGHT, HUD_WIDTH, default_hud_xy, load_config, save_config
from app.craft_runner import validate_ready
from app.data.catalog import delete_scenario, list_scenarios
from app.data.models import CraftScenario
from app.data.static import item_type_label
from app.debug import dbg
from app.i18n import t
from app.overlay import OverlayWindow, _set_size, _unlock_size
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
from app.input_win import (
    focus_game,
    register_overlay,
    show_without_activate,
    start_window_drag,
    style_overlay,
    unregister_overlay,
    widget_hwnd,
)
from app.widgets.scroll import enable_mousewheel

if TYPE_CHECKING:
    from app.main_window import MainWindow


def _outline() -> dict:
    return {
        "fg_color": "transparent",
        "border_color": BORDER,
        "border_width": 1,
        "text_color": TEXT,
        "hover_color": SELECTED,
        "corner_radius": RADIUS,
    }


class RunScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow, prefer_chain: bool = False) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        self._prefer_chain = prefer_chain
        self._selected: CraftScenario | None = None
        if app.selected_scenario_id:
            self._selected = next(
                (row for row in list_scenarios() if row.id == app.selected_scenario_id),
                None,
            )

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(top, text=t("nav.back"), width=88, command=app.show_home, **_outline()).pack(side="left")
        ctk.CTkLabel(
            top,
            text=t("run.title"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)

        config = load_config()
        ctk.CTkLabel(
            self,
            text=t("run.chain_hint", start=config.hotkey_chain, stop=config.hotkey_stop)
            if prefer_chain
            else t("run.hint", start=config.hotkey_start, stop=config.hotkey_stop),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=13),
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=32, pady=(0, 8))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(body, fg_color=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        enable_mousewheel(left)
        self._list = left

        right = ctk.CTkFrame(body, fg_color=SURFACE, border_color=BORDER, border_width=1, corner_radius=RADIUS)
        right.grid(row=0, column=1, sticky="nsew")
        inner = ctk.CTkFrame(right, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=16, pady=16)
        self._ready = ctk.CTkLabel(inner, text="", text_color=TEXT, wraplength=420, justify="left", anchor="w")
        self._ready.pack(fill="x", pady=(0, 10))
        self._status = ctk.CTkLabel(
            inner,
            text=t("run.idle"),
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            text_color=TEXT,
            anchor="w",
        )
        self._status.pack(fill="x", pady=(0, 8))
        buttons = ctk.CTkFrame(inner, fg_color="transparent")
        buttons.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            buttons,
            text=t("run.start"),
            width=140,
            height=34,
            fg_color=PRIMARY,
            text_color=PRIMARY_FG,
            hover_color=PRIMARY_HOVER,
            corner_radius=RADIUS,
            command=self._start,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text=t("run.chain"),
            width=140,
            height=34,
            fg_color=PRIMARY if prefer_chain else "transparent",
            text_color=PRIMARY_FG if prefer_chain else TEXT,
            hover_color=PRIMARY_HOVER if prefer_chain else SELECTED,
            border_color=BORDER,
            border_width=0 if prefer_chain else 1,
            corner_radius=RADIUS,
            command=self._start_chain,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            buttons,
            text=t("scenarios.edit"),
            width=100,
            height=34,
            **_outline(),
            command=self._edit,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            buttons,
            text=t("scenarios.delete"),
            width=100,
            height=34,
            fg_color="transparent",
            border_color=DANGER,
            border_width=1,
            text_color=DANGER,
            hover_color="#3f1d1d",
            corner_radius=RADIUS,
            command=self._delete,
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            buttons,
            text=t("run.stop"),
            width=120,
            height=34,
            fg_color="transparent",
            border_color=DANGER,
            border_width=1,
            text_color=DANGER,
            hover_color="#3f1d1d",
            corner_radius=RADIUS,
            command=app.stop_craft,
        ).pack(side="left", padx=8)
        self._log = ctk.CTkTextbox(
            inner,
            fg_color=BG,
            text_color=TEXT_MUTED,
            border_color=BORDER,
            border_width=1,
            font=ctk.CTkFont(family=FONT, size=12),
            wrap="word",
        )
        self._log.pack(fill="both", expand=True)
        self._log.configure(state="disabled")

        self._cards: dict[str, ctk.CTkFrame] = {}
        self._fill_list()
        self._refresh_ready()
        app.set_run_view(self)

    def _fill_list(self) -> None:
        scenarios = list_scenarios()
        if not scenarios:
            ctk.CTkLabel(self._list, text=t("scenarios.empty"), text_color=TEXT_MUTED).pack(anchor="w")
            return
        catalog = self._app.catalog
        for scenario in scenarios:
            selected = self._selected is not None and self._selected.id == scenario.id
            card = ctk.CTkFrame(
                self._list,
                fg_color=SELECTED if selected else SURFACE,
                border_color=TEXT if selected else BORDER,
                border_width=1,
                corner_radius=RADIUS,
            )
            card.pack(fill="x", pady=4)
            item_name = catalog.item_type_name(scenario.item_type) if catalog else item_type_label(scenario.item_type)
            craft_name = catalog.craft_type_name(scenario.craft_type) if catalog else scenario.craft_type
            ctk.CTkLabel(
                card,
                text=scenario.name,
                font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                text_color=TEXT,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(10, 0))
            ctk.CTkLabel(
                card,
                text=t("scenarios.meta", item=item_name, craft=craft_name, steps=len(scenario.steps)),
                font=ctk.CTkFont(family=FONT, size=12),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x", padx=12, pady=(2, 10))
            for widget in (card, *card.winfo_children()):
                widget.bind("<Button-1>", lambda _e, row=scenario: self._pick(row))
            self._cards[scenario.id] = card

    def _pick(self, scenario: CraftScenario) -> None:
        self._selected = scenario
        self._app.selected_scenario_id = scenario.id
        from app.settings import save_settings

        save_settings({"last_scenario_id": scenario.id})
        for key, card in self._cards.items():
            on = key == scenario.id
            card.configure(fg_color=SELECTED if on else SURFACE, border_color=TEXT if on else BORDER)
        self._refresh_ready()

    def _refresh_ready(self) -> None:
        if not self._selected:
            self._ready.configure(text=t("run.need_scenario"), text_color=TEXT_MUTED)
            return
        error = validate_ready(self._selected, load_config())
        if error:
            self._ready.configure(text=t(error), text_color=DANGER)
            return
        self._ready.configure(text=t("run.ready"), text_color=TEXT)

    def _start(self) -> None:
        dbg(f"run_screen start selected={self._selected.name if self._selected else None}")
        if not self._selected:
            self._app.show_toast(t("run.need_scenario"))
            return
        self._app.start_craft(self._selected)

    def _start_chain(self) -> None:
        if not self._selected:
            self._app.show_toast(t("run.need_scenario"))
            return
        self._app.start_craft(self._selected, chain=True)

    def _edit(self) -> None:
        if not self._selected:
            self._app.show_toast(t("run.need_scenario"))
            return
        self._app.open_wizard(self._selected)

    def _delete(self) -> None:
        if not self._selected:
            self._app.show_toast(t("run.need_scenario"))
            return
        if not messagebox.askyesno(
            t("home.scenarios"),
            t("scenarios.delete_confirm", name=self._selected.name),
        ):
            return
        scenario_id = self._selected.id
        if not delete_scenario(scenario_id):
            return
        self._selected = None
        if self._app.selected_scenario_id == scenario_id:
            self._app.selected_scenario_id = None
            from app.settings import save_settings

            save_settings({"last_scenario_id": ""})
        for child in self._list.winfo_children():
            child.destroy()
        self._cards.clear()
        self._fill_list()
        self._refresh_ready()
        self._app.show_toast(t("scenarios.deleted"), kind="success")

    def set_status(self, text: str) -> None:
        if self.winfo_exists():
            self._status.configure(text=text)

    def append_log(self, line: str) -> None:
        dbg(f"append_log exists={self.winfo_exists()} line={line!r}")
        if not self.winfo_exists():
            return
        box = getattr(self._log, "_textbox", self._log)
        try:
            box.configure(state="normal")
            box.insert("end", line + "\n")
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            pass
        try:
            self._status.configure(text=line)
        except Exception:
            pass


class CraftHud(OverlayWindow):
    _min_w = 180
    _min_h = 110

    def __init__(self, master, stop_key: str, *, mode: str = "craft") -> None:
        super().__init__(master)
        self.configure(fg_color="#09090b")
        self._mode = mode
        config = load_config()
        width = max(self._min_w, int(config.hud_w or HUD_WIDTH))
        height = max(self._min_h, int(config.hud_h or HUD_HEIGHT))
        if config.hud_x is not None and config.hud_y is not None:
            x, y = config.hud_x, config.hud_y
        else:
            x, y = default_hud_xy(self.winfo_screenwidth(), width)
        x = min(max(0, x), max(0, self.winfo_screenwidth() - width))
        y = min(max(0, y), max(0, self.winfo_screenheight() - height))
        _set_size(self, width, height, x, y)
        _unlock_size(self, self._min_w, self._min_h)
        self._hwnds: list[int] = []
        self._final = False
        self._resize = False

        frame = ctk.CTkFrame(self, fg_color="#18181b", border_color=BORDER, border_width=1, corner_radius=RADIUS)
        frame.pack(fill="both", expand=True)
        self._frame = frame
        wrap = max(120, width - 28)
        self._title = ctk.CTkLabel(
            frame,
            text=t("run.running"),
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TEXT,
            anchor="w",
        )
        self._title.pack(fill="x", padx=12, pady=(10, 2))
        self._spent = ctk.CTkLabel(
            frame,
            text="—",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
        )
        self._spent.pack(fill="x", padx=12)
        self._score = ctk.CTkLabel(
            frame,
            text="" if mode != "craft" else t("run.hud_score", hits=0, misses=0),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
        )
        self._score.pack(fill="x", padx=12)
        self._item = ctk.CTkLabel(
            frame,
            text=t("run.log.start"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=11),
            anchor="w",
            wraplength=wrap,
            justify="left",
        )
        self._item.pack(fill="x", padx=12, pady=(4, 0))
        self._hint = ctk.CTkLabel(
            frame,
            text=t("run.hud_stop", key=stop_key),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=10),
            anchor="w",
            wraplength=wrap,
        )
        self._hint.pack(fill="x", padx=12, pady=(2, 10))

        self._grip = tk.Frame(self, bg="#52525b", width=14, height=14, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-3, y=-3, anchor="se")
        self._grip.bind("<ButtonPress-1>", self._start_resize)
        self._grip.bind("<B1-Motion>", self._do_resize)
        self._grip.bind("<ButtonRelease-1>", self._save_pos)

        self.lift()
        self.update_idletasks()
        self._ready()
        self._bind_drag(self)
        self.bind("<Configure>", self._on_configure, add="+")

    def _ready(self) -> None:
        if not self.winfo_exists():
            return
        hwnd = widget_hwnd(self)
        owner = widget_hwnd(self.master)
        if hwnd and hwnd != owner:
            style_overlay(hwnd)
            register_overlay(hwnd)
            self._hwnds.append(hwnd)
            show_without_activate(hwnd)
        self.attributes("-topmost", True)
        self.lift()

    def set_note(self, text: str) -> None:
        if self.winfo_exists() and text:
            self._item.configure(text=text)

    def set_hint(self, text: str) -> None:
        if self.winfo_exists() and text:
            self._hint.configure(text=text)

    def _bind_drag(self, widget) -> None:
        if widget is self._grip:
            return
        widget.bind("<ButtonPress-1>", self._start_move, add="+")
        widget.bind("<B1-Motion>", self._move, add="+")
        widget.bind("<ButtonRelease-1>", self._save_pos, add="+")
        widget.bind("<ButtonPress-3>", self._start_resize, add="+")
        widget.bind("<B3-Motion>", self._do_resize, add="+")
        widget.bind("<ButtonRelease-3>", self._save_pos, add="+")
        for child in widget.winfo_children():
            if child is self._grip:
                continue
            self._bind_drag(child)

    def _on_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        wrap = max(80, self.winfo_width() - 28)
        try:
            self._item.configure(wraplength=wrap)
            self._hint.configure(wraplength=wrap)
        except Exception:
            pass

    def _start_move(self, event) -> None:
        self._resize = False
        self._native_drag = False
        try:
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
        except Exception:
            self._drag_x = 0
            self._drag_y = 0
        hwnd = self._hwnds[0] if self._hwnds else widget_hwnd(self)
        if not hwnd:
            return
        try:
            start_window_drag(hwnd)
            self._native_drag = True
        except Exception:
            self._native_drag = False

    def _move(self, event) -> None:
        if self._resize or getattr(self, "_native_drag", False):
            return
        try:
            tk.Toplevel.geometry(self, f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
        except Exception:
            pass

    def _start_resize(self, event) -> None:
        self._resize = True
        self._drag_x = event.x_root
        self._drag_y = event.y_root
        self._start_w = self.winfo_width()
        self._start_h = self.winfo_height()
        self._start_x = self.winfo_x()
        self._start_y = self.winfo_y()

    def _do_resize(self, event) -> None:
        width = max(self._min_w, self._start_w + (event.x_root - self._drag_x))
        height = max(self._min_h, self._start_h + (event.y_root - self._drag_y))
        _set_size(self, width, height, self._start_x, self._start_y)
        self._on_configure()

    def _save_pos(self, _event=None) -> None:
        if not self.winfo_exists():
            return
        self.update_idletasks()
        config = load_config()
        config.hud_x = int(self.winfo_x())
        config.hud_y = int(self.winfo_y())
        config.hud_w = max(self._min_w, int(self.winfo_width()))
        config.hud_h = max(self._min_h, int(self.winfo_height()))
        save_config(config)

    def destroy(self) -> None:
        for hwnd in self._hwnds:
            unregister_overlay(hwnd)
        self._hwnds.clear()
        super().destroy()

    def set_step(self, text: str) -> None:
        if self.winfo_exists() and not self._final:
            self._title.configure(text=text)

    def set_progress(self, text: str) -> None:
        if self.winfo_exists() and text:
            self._spent.configure(text=text)

    def mark_final(self, data: dict) -> None:
        self._final = True
        if self._mode != "craft":
            status = data.get("status") or "done"
            title = {
                "running": t("run.running"),
                "paused": t("run.paused"),
                "stopped": t("run.stopped"),
                "done": t("run.done"),
                "error": t("run.crash"),
            }.get(status, t("run.done"))
            if self.winfo_exists():
                self._title.configure(text=title)
                progress = data.get("progress") or data.get("spent")
                if progress:
                    self._spent.configure(text=progress)
                item = (data.get("item") or "").strip()
                if item:
                    self._item.configure(text=item)
            return
        self.update_stats(data)

    def update_stats(self, data: dict) -> None:
        if not self.winfo_exists():
            return
        status = data.get("status") or "running"
        if self._final and status == "running":
            status = "stopped"
        if status in {"stopped", "done", "error"}:
            self._final = True
        title = {
            "running": t("run.running"),
            "paused": t("run.paused"),
            "stopped": t("run.stopped"),
            "done": t("run.done"),
            "error": t("run.crash"),
        }.get(status, t("run.stopped") if self._final else t("run.running"))
        self._title.configure(text=title)
        spent = data.get("spent") or data.get("progress")
        if spent:
            self._spent.configure(text=spent)
        if self._mode == "craft":
            self._score.configure(text=t("run.hud_score", hits=data.get("hits", 0), misses=data.get("misses", 0)))
        item = (data.get("item") or "").strip()
        if item:
            self._item.configure(text=item)
