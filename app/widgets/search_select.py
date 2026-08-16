from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.search import matches
from app.i18n import t
from app.theme import CONTROL, CONTROL_HOVER, FONT, RADIUS, RING, SELECTED, TEXT, TEXT_MUTED
from app.widgets.select import affix_chip, chevron_image


class SearchSelect(ctk.CTkFrame):
    """Селект с поиском: иконки, теги prefix/suffix, ровная обводка."""

    def __init__(
        self,
        master,
        items: list[tuple[str, str]],
        on_select: Callable[[str], None] | None = None,
        placeholder: str | None = None,
        selected: str | None = None,
        width: int = 360,
        list_height: int = 180,
        image_for=None,
        badge_for=None,
        height: int = 34,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._items = items
        self._on_select = on_select
        self._selected = selected
        self._open = False
        self._placeholder = placeholder or t("search.placeholder")
        self._width = width
        self._list_height = list_height
        self._image_for = image_for
        self._badge_for = badge_for
        self._image = None
        self._row_images: list = []

        self._trigger = ctk.CTkFrame(
            self,
            fg_color=CONTROL,
            border_color=RING,
            border_width=2,
            corner_radius=RADIUS,
            height=height,
            cursor="hand2",
        )
        self._trigger.pack(fill="x")
        self._trigger.pack_propagate(False)
        inner = ctk.CTkFrame(self._trigger, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=3, pady=3)
        self._icon_label = ctk.CTkLabel(inner, text="", width=22)
        self._icon_label.pack(side="left", padx=(6, 0))
        self._badge_host = ctk.CTkFrame(inner, fg_color="transparent")
        self._label = ctk.CTkLabel(
            inner,
            text=self._label_for(selected) or self._placeholder,
            anchor="w",
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=TEXT if selected else TEXT_MUTED,
        )
        self._label.pack(side="left", fill="x", expand=True, padx=8)
        self._chevron = ctk.CTkLabel(inner, text="", image=chevron_image(False), width=18)
        self._chevron.pack(side="right", padx=(0, 6))
        self._sync_trigger()
        for widget in (self._trigger, inner, self._icon_label, self._label, self._chevron):
            widget.bind("<Button-1>", lambda _e: self.toggle(), add="+")
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")

        self._panel = ctk.CTkFrame(
            self,
            fg_color=CONTROL,
            border_color=RING,
            border_width=2,
            corner_radius=RADIUS,
        )
        self._search = ctk.CTkEntry(
            self._panel,
            placeholder_text=self._placeholder,
            fg_color="#111113",
            border_color=RING,
            text_color=TEXT,
            height=32,
            corner_radius=RADIUS,
        )
        self._search.pack(fill="x", padx=8, pady=(8, 4))
        self._search.bind("<KeyRelease>", self._on_filter)

        self._list = ctk.CTkScrollableFrame(
            self._panel,
            fg_color=CONTROL,
            height=list_height,
            corner_radius=RADIUS,
        )
        self._list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def toggle(self) -> None:
        if self._open:
            self.close()
        else:
            self.open()

    def open(self) -> None:
        if self._open:
            return
        self._open = True
        self._search.delete(0, "end")
        self._render(self._items)
        self._panel.pack(fill="x", pady=(6, 0))
        self._chevron.configure(image=chevron_image(True))
        self._search.focus_set()

    def close(self) -> None:
        if not self._open:
            return
        self._open = False
        self._panel.pack_forget()
        self._chevron.configure(image=chevron_image(False))
        self._trigger.configure(fg_color=CONTROL)

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = items
        if self._open:
            self._render(items)

    def set_value(self, item_id: str | None) -> None:
        self._selected = item_id
        self._sync_trigger()

    @property
    def selected(self) -> str | None:
        return self._selected

    def _sync_trigger(self) -> None:
        label = self._label_for(self._selected) or self._placeholder
        self._label.configure(text=label, text_color=TEXT if self._selected else TEXT_MUTED)
        icon = self._icon_for(self._selected)
        self._image = icon
        if icon is not None:
            self._icon_label.configure(image=icon)
            self._icon_label.pack(side="left", padx=(6, 0), before=self._label)
        else:
            self._icon_label.configure(image=None)
            self._icon_label.pack_forget()
        for child in self._badge_host.winfo_children():
            child.destroy()
        generation = self._badge_for(self._selected) if self._badge_for and self._selected else None
        if generation:
            chip = affix_chip(self._badge_host, generation)
            chip.pack()
            self._badge_host.pack(side="left", padx=(6, 0), before=self._label)
            for widget in (self._badge_host, chip, *chip.winfo_children()):
                widget.bind("<Button-1>", lambda _e: self.toggle(), add="+")
        else:
            self._badge_host.pack_forget()

    def _on_enter(self, _event=None) -> None:
        if not self._open:
            self._trigger.configure(fg_color=CONTROL_HOVER)

    def _on_leave(self, _event=None) -> None:
        if not self._open:
            self._trigger.configure(fg_color=CONTROL)

    def _icon_for(self, item_id: str | None):
        if not self._image_for or not item_id:
            return None
        return self._image_for(item_id)

    def _label_for(self, item_id: str | None) -> str:
        if not item_id:
            return ""
        for key, label in self._items:
            if key == item_id:
                return label
        return item_id

    def _on_filter(self, _event=None) -> None:
        query = self._search.get().strip().lower()
        if not query:
            self._render(self._items)
            return
        self._render([item for item in self._items if matches(query, item[0], item[1])])

    def _render(self, items: list[tuple[str, str]]) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        self._row_images = []
        if not items:
            ctk.CTkLabel(
                self._list,
                text=t("search.empty"),
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT, size=12),
            ).pack(anchor="w", padx=6, pady=6)
            return
        for item_id, label in items:
            self._add_row(item_id, label)

    def _add_row(self, item_id: str, label: str) -> None:
        on = item_id == self._selected
        row = ctk.CTkFrame(
            self._list,
            fg_color=SELECTED if on else "transparent",
            corner_radius=6,
            height=32,
            cursor="hand2",
        )
        row.pack(fill="x", pady=1)
        icon = self._icon_for(item_id)
        if icon is not None:
            self._row_images.append(icon)
            ctk.CTkLabel(row, text="", image=icon, width=22).pack(side="left", padx=(8, 4))
        generation = self._badge_for(item_id) if self._badge_for else None
        if generation:
            affix_chip(row, generation).pack(side="left", padx=(6, 8), pady=6)
        ctk.CTkLabel(
            row,
            text=label,
            anchor="w",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold" if on else "normal"),
        ).pack(side="left", fill="x", expand=True, padx=(8 if not generation and icon is None else 0, 8), pady=4)
        if on:
            ctk.CTkLabel(row, text="✓", width=18, text_color=TEXT).pack(side="right", padx=(0, 8))
        for widget in (row, *row.winfo_children()):
            widget.bind("<Button-1>", lambda _e, value=item_id: self._choose(value), add="+")
            widget.bind("<Enter>", lambda _e, current=row: current.configure(fg_color=CONTROL_HOVER), add="+")
            widget.bind("<Leave>", lambda _e, current=row, active=on: current.configure(fg_color=SELECTED if active else "transparent"), add="+")

    def _choose(self, item_id: str) -> None:
        self.set_value(item_id)
        self.close()
        if self._on_select:
            self._on_select(item_id)
