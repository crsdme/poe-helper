from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config import AppConfig, CurrencyTab, HUD_HEIGHT, HUD_WIDTH, ItemGrid, Rect, default_hud_xy, load_config, save_config
from app.data.currency_layout import (
    SLOTS,
    SLOTS_BY_KEY,
    apply_layout,
    default_slot_assignments,
)
from app.data.targets import BUTTONS, mappable_currencies
from app.i18n import t
from app.overlay import GridOverlay, PositionOverlay
from app.paths import stash_image_path
from app.theme import BG, BORDER, FONT, PRIMARY, PRIMARY_FG, PRIMARY_HOVER, RADIUS, SELECTED, SURFACE, TEXT, TEXT_MUTED
from app.widgets.scroll import enable_mousewheel
from app.item_icons import action_image
from app.widgets.search_select import SearchSelect

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


def _primary() -> dict:
    return {
        "fg_color": PRIMARY,
        "hover_color": PRIMARY_HOVER,
        "text_color": PRIMARY_FG,
        "corner_radius": RADIUS,
        "font": ctk.CTkFont(family=FONT, size=13, weight="bold"),
    }


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        self._config = load_config()
        self._overlay: PositionOverlay | None = None
        self._assign_slot: str | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(top, text=t("nav.back"), width=88, command=app.show_home, **_outline()).pack(side="left")
        ctk.CTkLabel(
            top,
            text=t("settings.title"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)

        body = ctk.CTkScrollableFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=32, pady=(0, 20))
        enable_mousewheel(body)
        self._body = body

        self._section(t("settings.craft"))
        self._build_craft()
        self._section(t("settings.item"))
        self._build_item()
        self._section(t("settings.chain"))
        self._build_chain()
        self._section(t("settings.currency_tab"))
        self._build_currency_tab()
        self._section(t("settings.currencies"))
        self._build_currency_list()
        self._section(t("settings.buttons"))
        self._build_buttons()
        self._section(t("settings.data"))
        self._build_data()

    def _section(self, title: str) -> None:
        ctk.CTkLabel(
            self._body,
            text=title,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w", pady=(18, 8))

    def _card(self) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self._body,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        card.pack(fill="x", pady=(0, 8))
        return card

    def _save(self) -> None:
        save_config(self._config)
        self._app.set_status(t("settings.saved"))

    def _fmt_rect(self, rect: Rect | None) -> str:
        if not rect:
            return t("settings.not_set")
        x, y = rect.click
        return f"{x}, {y}  ·  {rect.w}×{rect.h}"

    def _build_craft(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)

        ctk.CTkLabel(inner, text=t("settings.speed"), text_color=TEXT_MUTED).pack(anchor="w")
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(4, 4))
        self._speed_label = ctk.CTkLabel(row, text=f"{self._config.speed_ms} ms", text_color=TEXT, width=70)
        self._speed_label.pack(side="right")
        self._speed = ctk.CTkSlider(
            row,
            from_=0,
            to=400,
            number_of_steps=400,
            command=self._on_speed,
            progress_color=TEXT,
            button_color=TEXT,
            button_hover_color=PRIMARY_HOVER,
        )
        self._speed.set(self._config.speed_ms)
        self._speed.pack(fill="x", padx=(0, 10))
        ctk.CTkLabel(
            inner,
            text=t("settings.speed_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=11),
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self._logs = ctk.CTkCheckBox(
            inner,
            text=t("settings.logs"),
            command=self._on_logs,
            text_color=TEXT,
            fg_color=TEXT,
            hover_color=PRIMARY_HOVER,
            checkmark_color=PRIMARY_FG,
        )
        if self._config.logs_enabled:
            self._logs.select()
        self._logs.pack(anchor="w", pady=(0, 8))

        self._shift = ctk.CTkCheckBox(
            inner,
            text=t("settings.shift_lock"),
            command=self._on_shift,
            text_color=TEXT,
            fg_color=TEXT,
            hover_color=PRIMARY_HOVER,
            checkmark_color=PRIMARY_FG,
        )
        if self._config.shift_lock:
            self._shift.select()
        self._shift.pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text=t("settings.shift_lock_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=11),
            wraplength=820,
            justify="left",
        ).pack(anchor="w", pady=(4, 12))

        keys = ctk.CTkFrame(inner, fg_color="transparent")
        keys.pack(fill="x")
        self._start_btn = self._hotkey_row(keys, t("settings.hotkey_start"), self._config.hotkey_start, "start")
        self._chain_btn = self._hotkey_row(keys, t("settings.hotkey_chain"), self._config.hotkey_chain, "chain")
        self._stop_btn = self._hotkey_row(keys, t("settings.hotkey_stop"), self._config.hotkey_stop, "stop")

        ctk.CTkLabel(
            inner,
            text=t("settings.hud"),
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
        ).pack(anchor="w", pady=(16, 4))
        ctk.CTkLabel(
            inner,
            text=t("settings.hud_hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=11),
            wraplength=820,
            justify="left",
        ).pack(anchor="w")
        hud_row = ctk.CTkFrame(inner, fg_color="transparent")
        hud_row.pack(fill="x", pady=(8, 0))
        self._hud_pos = ctk.CTkLabel(hud_row, text=self._hud_text(), text_color=TEXT)
        self._hud_pos.pack(side="left")
        ctk.CTkButton(
            hud_row,
            text=t("settings.hud_reset"),
            width=120,
            command=self._reset_hud,
            **_outline(),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            hud_row,
            text=t("settings.set_overlay"),
            width=160,
            command=self._map_hud,
            **_primary(),
        ).pack(side="right")

    def _hotkey_row(self, master, label: str, value: str, kind: str) -> ctk.CTkButton:
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, text_color=TEXT_MUTED, width=180, anchor="w").pack(side="left")
        button = ctk.CTkButton(row, text=value, width=120, command=lambda: self._capture_hotkey(kind), **_outline())
        button.pack(side="left")
        return button

    def _capture_hotkey(self, kind: str) -> None:
        buttons = {"start": self._start_btn, "chain": self._chain_btn, "stop": self._stop_btn}
        button = buttons[kind]
        button.configure(text=t("settings.press_key"))
        self._app._hotkeys.enabled = False
        self._app._hotkeys.stop()
        self._app.focus_set()

        def on_key(event) -> str:
            key = event.keysym
            if key in {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"}:
                return "break"
            if kind == "start":
                self._config.hotkey_start = key
            elif kind == "chain":
                self._config.hotkey_chain = key
            else:
                self._config.hotkey_stop = key
            button.configure(text=key)
            self._save()
            self._app.unbind("<KeyPress>")
            self._app.refresh_hotkeys()
            return "break"

        self._app.bind("<KeyPress>", on_key)

    def _on_speed(self, value: float) -> None:
        self._config.speed_ms = int(value)
        self._speed_label.configure(text=f"{self._config.speed_ms} ms")
        self._save()

    def _on_logs(self) -> None:
        self._config.logs_enabled = bool(self._logs.get())
        self._save()

    def _on_shift(self) -> None:
        self._config.shift_lock = bool(self._shift.get())
        self._save()

    def _hud_size(self) -> tuple[int, int]:
        return (
            max(180, int(self._config.hud_w or HUD_WIDTH)),
            max(110, int(self._config.hud_h or HUD_HEIGHT)),
        )

    def _hud_rect(self) -> Rect:
        width, height = self._hud_size()
        if self._config.hud_x is not None and self._config.hud_y is not None:
            return Rect(x=self._config.hud_x, y=self._config.hud_y, w=width, h=height)
        x, y = default_hud_xy(self.winfo_screenwidth(), width)
        return Rect(x=x, y=y, w=width, h=height)

    def _hud_text(self) -> str:
        if self._config.hud_x is None or self._config.hud_y is None:
            return t("settings.hud_default")
        width, height = self._hud_size()
        return f"{self._config.hud_x}, {self._config.hud_y}  ·  {width}×{height}"

    def _map_hud(self) -> None:
        self._open_overlay(
            t("settings.hud"),
            self._hud_rect(),
            self._on_hud,
            min_size=(180, 110),
            lock_aspect=False,
            show_dot=False,
            hint=t("settings.hud_hint"),
            alpha=0.92,
        )

    def _on_hud(self, rect: Rect) -> None:
        self._config.hud_x = rect.x
        self._config.hud_y = rect.y
        self._config.hud_w = rect.w
        self._config.hud_h = rect.h
        self._hud_pos.configure(text=self._hud_text())
        self._save()

    def _reset_hud(self) -> None:
        self._config.hud_x = None
        self._config.hud_y = None
        self._config.hud_w = None
        self._config.hud_h = None
        self._hud_pos.configure(text=self._hud_text())
        self._save()

    def _build_item(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(inner, text=t("settings.item_hint"), text_color=TEXT_MUTED, wraplength=820, justify="left").pack(
            anchor="w"
        )
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        self._item_pos = ctk.CTkLabel(row, text=self._fmt_rect(self._config.item), text_color=TEXT)
        self._item_pos.pack(side="left")
        ctk.CTkButton(
            row,
            text=t("settings.set_overlay"),
            width=160,
            command=lambda: self._open_overlay(
                t("settings.set_item"),
                self._config.item or Rect(x=480, y=200, w=140, h=200),
                self._on_item,
                min_size=(70, 90),
            ),
            **_primary(),
        ).pack(side="right")

    def _on_item(self, rect: Rect) -> None:
        self._config.item = rect
        self._item_pos.configure(text=self._fmt_rect(rect))
        self._save()

    def _build_currency_tab(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(inner, text=t("settings.tab_hint"), text_color=TEXT_MUTED, wraplength=820, justify="left").pack(
            anchor="w"
        )
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(10, 8))
        self._tab_pos = ctk.CTkLabel(
            row,
            text=self._fmt_rect(self._tab_as_rect()),
            text_color=TEXT,
        )
        self._tab_pos.pack(side="left")
        ctk.CTkButton(
            row,
            text=t("settings.map_tab"),
            width=200,
            command=self._map_tab,
            **_primary(),
        ).pack(side="right")

        self._mapped_label = ctk.CTkLabel(inner, text=self._mapped_text(), text_color=TEXT_MUTED)
        self._mapped_label.pack(anchor="w", pady=(4, 0))
        self._grid_host = ctk.CTkFrame(inner, fg_color="transparent")
        self._grid_host.pack(fill="x", pady=(8, 0))
        self._picker_host = ctk.CTkFrame(inner, fg_color="transparent")
        self._picker_host.pack(fill="x", pady=(8, 0))
        self._redraw_grid()

    def _tab_as_rect(self) -> Rect | None:
        tab = self._config.currency_tab
        if not tab:
            return None
        return Rect(x=tab.x, y=tab.y, w=tab.w, h=tab.h)

    def _mapped_text(self) -> str:
        count = len(self._config.currency_slots)
        if not count:
            return t("settings.tab_empty")
        return t("settings.tab_mapped", count=count)

    def _map_tab(self) -> None:
        current = self._tab_as_rect() or Rect(x=200, y=60, w=638, h=639)
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

    def _on_tab(self, rect: Rect) -> None:
        self._config.currency_tab = CurrencyTab(x=rect.x, y=rect.y, w=rect.w, h=rect.h)
        mapped = apply_layout(rect)
        item_rect = mapped.pop("item", None)
        current = self._config.item
        inside_tab = bool(
            current
            and rect.x <= current.click[0] <= rect.x + rect.w
            and rect.y <= current.click[1] <= rect.y + rect.h
        )
        if item_rect and (current is None or inside_tab):
            self._config.item = item_rect
            self._item_pos.configure(text=self._fmt_rect(item_rect))
        self._config.currency_slots = default_slot_assignments()
        for key, slot_rect in mapped.items():
            self._config.positions[key] = slot_rect
        self._tab_pos.configure(text=self._fmt_rect(rect))
        self._mapped_label.configure(text=self._mapped_text())
        self._save()
        self._redraw_grid()
        self._refresh_currency_status()

    def _slot_currency(self, slot_key: str) -> str | None:
        return self._config.currency_slots.get(slot_key)

    def _redraw_grid(self) -> None:
        for child in self._grid_host.winfo_children():
            child.destroy()
        if not self._config.currency_tab:
            ctk.CTkLabel(self._grid_host, text=t("settings.tab_empty"), text_color=TEXT_MUTED).pack(anchor="w")
            return
        board = ctk.CTkFrame(self._grid_host, fg_color="transparent")
        board.pack(anchor="w")
        left = ctk.CTkFrame(board, fg_color="transparent")
        center = ctk.CTkFrame(board, fg_color="transparent")
        right = ctk.CTkFrame(board, fg_color="transparent")
        left.grid(row=0, column=0, padx=4)
        center.grid(row=0, column=1, padx=10)
        right.grid(row=0, column=2, padx=4)
        self._draw_group(left, "left", 4)
        self._draw_group(center, "center", 2)
        self._draw_group(right, "right", 4)
        bottom = ctk.CTkFrame(self._grid_host, fg_color="transparent")
        bottom.pack(anchor="w", pady=(8, 0))
        self._draw_group(bottom, "bottom", 7)

    def _draw_group(self, master, group: str, cols: int) -> None:
        slots = [slot for slot in SLOTS if slot.group == group]
        for index, slot in enumerate(slots):
            currency_id = self._slot_currency(slot.key)
            label = (currency_id or "·")[:4]
            ctk.CTkButton(
                master,
                text=label,
                width=46,
                height=32,
                fg_color=SELECTED if currency_id else SURFACE,
                border_color=BORDER,
                border_width=1,
                text_color=TEXT if currency_id else TEXT_MUTED,
                corner_radius=4,
                command=lambda key=slot.key: self._pick_slot(key),
            ).grid(row=index // cols, column=index % cols, padx=1, pady=1)

    def _pick_slot(self, slot_key: str) -> None:
        self._assign_slot = slot_key
        for child in self._picker_host.winfo_children():
            child.destroy()
        items = [("clear", t("settings.clear_cell"))]
        items.extend(
            (row["id"], t(f"action.{row['id']}", default=row["name"]))
            for row in mappable_currencies()
        )
        ctk.CTkLabel(
            self._picker_host,
            text=t("settings.assign_slot"),
            text_color=TEXT_MUTED,
        ).pack(anchor="w")
        SearchSelect(
            self._picker_host,
            items=items,
            on_select=self._assign_currency,
            placeholder=t("search.action"),
            width=360,
            list_height=180,
            image_for=lambda currency_id: None if currency_id == "clear" else action_image(currency_id),
        ).pack(anchor="w", pady=(4, 0))

    def _assign_currency(self, currency_id: str) -> None:
        if not self._assign_slot:
            return
        slot = SLOTS_BY_KEY.get(self._assign_slot)
        tab = self._tab_as_rect()
        if slot is None or tab is None:
            return
        previous = self._config.currency_slots.get(slot.key)
        if previous:
            self._config.positions.pop(previous, None)
        if currency_id == "clear":
            self._config.currency_slots.pop(slot.key, None)
        else:
            for key, value in list(self._config.currency_slots.items()):
                if value == currency_id:
                    self._config.currency_slots.pop(key, None)
            self._config.currency_slots[slot.key] = currency_id
            self._config.positions[currency_id] = slot.to_rect(tab)
        self._save()
        self._mapped_label.configure(text=self._mapped_text())
        self._redraw_grid()
        for child in self._picker_host.winfo_children():
            child.destroy()
        self._refresh_currency_status()

    def _build_currency_list(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(inner, text=t("settings.currency_hint"), text_color=TEXT_MUTED, wraplength=820, justify="left").pack(
            anchor="w", pady=(0, 8)
        )
        self._currency_rows: dict[str, ctk.CTkLabel] = {}
        for row in mappable_currencies():
            self._target_row(inner, row["id"], t(f"action.{row['id']}", default=row["name"]), "currency")

    def _build_buttons(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        self._button_rows: dict[str, ctk.CTkLabel] = {}
        for row in BUTTONS:
            self._target_row(inner, row["id"], t(f"target.{row['id']}"), "button")

    def _target_row(self, master, key: str, title: str, kind: str) -> None:
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=3)
        ctk.CTkLabel(row, text=title, text_color=TEXT, width=220, anchor="w").pack(side="left")
        status = ctk.CTkLabel(row, text=self._target_status(key), text_color=TEXT_MUTED, anchor="w")
        status.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(
            row,
            text=t("settings.set_overlay"),
            width=130,
            command=lambda target=key: self._open_overlay(
                title,
                self._config.positions.get(target) or Rect(),
                lambda rect, item=target: self._on_position(item, rect),
            ),
            **_outline(),
        ).pack(side="right")
        if kind == "currency":
            self._currency_rows[key] = status
        else:
            self._button_rows[key] = status

    def _target_status(self, key: str) -> str:
        if key in self._config.positions:
            return self._fmt_rect(self._config.positions[key])
        if key in self._config.currency_slots.values():
            return t("settings.from_tab")
        if key in self._config.currency_cells and self._config.currency_tab:
            col, row = self._config.currency_cells[key]
            return t("settings.from_grid", col=col + 1, row=row + 1)
        return t("settings.not_set")

    def _refresh_currency_status(self) -> None:
        for key, label in self._currency_rows.items():
            label.configure(text=self._target_status(key))

    def _on_position(self, key: str, rect: Rect) -> None:
        self._config.positions[key] = rect
        self._save()
        if key in self._currency_rows:
            self._currency_rows[key].configure(text=self._fmt_rect(rect))
        if key in self._button_rows:
            self._button_rows[key].configure(text=self._fmt_rect(rect))

    def _build_data(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(
            inner,
            text=t("home.refresh"),
            width=200,
            command=lambda: self._app.reload_catalog(force=True),
            **_outline(),
        ).pack(anchor="w")

    def _open_overlay(
        self,
        title: str,
        rect: Rect,
        callback,
        min_size: tuple[int, int] = (240, 200),
        **overlay_kwargs,
    ) -> None:
        from app.widgets.select import close_open

        close_open()
        self._drop_overlay()
        self._app.iconify()
        self._overlay = PositionOverlay(
            self._app,
            title=title,
            rect=rect,
            on_confirm=lambda value: self._finish_overlay(callback, value),
            on_cancel=self._restore_app,
            min_size=min_size,
            **overlay_kwargs,
        )

    def _finish_overlay(self, callback, rect: Rect) -> None:
        self._restore_app()
        callback(rect)

    def _restore_app(self) -> None:
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

    def _build_chain(self) -> None:
        card = self._card()
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(inner, text=t("settings.chain_hint"), text_color=TEXT_MUTED, wraplength=820, justify="left").pack(
            anchor="w"
        )
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(10, 0))
        self._chain_pos = ctk.CTkLabel(row, text=self._fmt_grid(self._config.chain_grid), text_color=TEXT)
        self._chain_pos.pack(side="left")
        ctk.CTkButton(
            row,
            text=t("settings.set_overlay"),
            width=160,
            command=self._map_chain,
            **_primary(),
        ).pack(side="right")

    def _fmt_grid(self, grid: ItemGrid | None) -> str:
        if not grid:
            return t("settings.not_set")
        return f"{grid.cols}×{grid.rows}  ·  {grid.x}, {grid.y}  ·  {grid.w}×{grid.h}"

    def _map_chain(self) -> None:
        from app.widgets.select import close_open

        close_open()
        self._drop_overlay()
        self._app.iconify()
        self._overlay = GridOverlay(
            self._app,
            grid=self._config.chain_grid,
            on_confirm=lambda value: self._finish_grid(value),
            on_cancel=self._restore_app,
        )

    def _finish_grid(self, grid: ItemGrid) -> None:
        self._restore_app()
        self._config.chain_grid = grid
        self._chain_pos.configure(text=self._fmt_grid(grid))
        self._save()
