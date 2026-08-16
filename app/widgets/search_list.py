from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.search import matches
from app.i18n import t
from app.theme import BORDER, FONT, RADIUS, SELECTED, SURFACE, TEXT, TEXT_MUTED


class SearchList(ctk.CTkFrame):
    def __init__(
        self,
        master,
        items: list[tuple[str, str]],
        on_select: Callable[[str], None] | None = None,
        height: int = 180,
        placeholder: str | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._items = items
        self._on_select = on_select
        self._selected: str | None = None
        self._buttons: dict[str, ctk.CTkButton] = {}

        self._search = ctk.CTkEntry(
            self,
            placeholder_text=placeholder or t("search.placeholder"),
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            height=34,
            corner_radius=RADIUS,
        )
        self._search.pack(fill="x")
        self._search.bind("<KeyRelease>", self._on_filter)

        self._list = ctk.CTkScrollableFrame(
            self,
            fg_color=SURFACE,
            height=height,
            corner_radius=RADIUS,
            border_color=BORDER,
            border_width=1,
        )
        self._list.pack(fill="both", expand=True, pady=(8, 0))
        self._render(items)

    @property
    def selected(self) -> str | None:
        return self._selected

    def set_items(self, items: list[tuple[str, str]]) -> None:
        self._items = items
        self._selected = None
        self._search.delete(0, "end")
        self._render(items)

    def select(self, item_id: str | None) -> None:
        self._selected = item_id
        self._refresh_highlights()

    def _on_filter(self, _event=None) -> None:
        query = self._search.get().strip().lower()
        if not query:
            self._render(self._items)
            return
        filtered = [item for item in self._items if matches(query, item[0], item[1])]
        self._render(filtered)

    def _render(self, items: list[tuple[str, str]]) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        self._buttons.clear()
        if not items:
            ctk.CTkLabel(
                self._list,
                text=t("search.empty"),
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT, size=12),
            ).pack(anchor="w", padx=8, pady=8)
            return
        for item_id, label in items:
            active = item_id == self._selected
            button = ctk.CTkButton(
                self._list,
                text=label,
                anchor="w",
                fg_color=SELECTED if active else "transparent",
                hover_color=SELECTED,
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT, size=12),
                corner_radius=RADIUS,
                command=lambda value=item_id: self._choose(value),
            )
            button.pack(fill="x", pady=1)
            self._buttons[item_id] = button

    def _choose(self, item_id: str) -> None:
        self._selected = item_id
        self._refresh_highlights()
        if self._on_select:
            self._on_select(item_id)

    def _refresh_highlights(self) -> None:
        for item_id, button in self._buttons.items():
            active = item_id == self._selected
            button.configure(fg_color=SELECTED if active else "transparent")
