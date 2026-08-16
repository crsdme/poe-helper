from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.theme import BORDER, FONT, RADIUS, SELECTED, SURFACE, TEXT, TEXT_MUTED, TILE_HOVER


class Tile(ctk.CTkFrame):
    def __init__(
        self,
        master,
        title: str,
        subtitle: str = "",
        command: Callable[[], None] | None = None,
        selected: bool = False,
        enabled: bool = True,
        width: int = 280,
        height: int = 108,
        image=None,
    ) -> None:
        super().__init__(
            master,
            fg_color=SELECTED if selected else SURFACE,
            border_color=TEXT if selected else BORDER,
            border_width=1,
            corner_radius=RADIUS,
            width=width,
            height=height,
            cursor="hand2" if enabled and command else "arrow",
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._command = command if enabled else None
        self._selected = selected
        self._image = image

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        text_host = inner
        wrap = width - 40
        if image is not None:
            inner.pack_configure(padx=12, pady=10)
            icon = ctk.CTkLabel(inner, text="", image=image)
            icon.pack(side="left", padx=(0, 10))
            text_host = ctk.CTkFrame(inner, fg_color="transparent")
            text_host.pack(side="left", fill="both", expand=True)
            wrap = max(80, width - 88)

        ctk.CTkLabel(
            text_host,
            text=title,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TEXT if enabled else TEXT_MUTED,
            anchor="w",
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w")

        if subtitle:
            ctk.CTkLabel(
                text_host,
                text=subtitle,
                font=ctk.CTkFont(family=FONT, size=12),
                text_color=TEXT_MUTED,
                anchor="w",
                wraplength=wrap,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))

        if self._command:
            for widget in (self, inner, *inner.winfo_children(), *text_host.winfo_children()):
                widget.bind("<Button-1>", self._on_click)
                widget.bind("<Enter>", self._on_enter)
                widget.bind("<Leave>", self._on_leave)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.configure(
            fg_color=SELECTED if selected else SURFACE,
            border_color=TEXT if selected else BORDER,
        )

    def _on_click(self, _event) -> None:
        if self._command:
            self._command()

    def _on_enter(self, _event) -> None:
        if self._command:
            self.configure(fg_color=TILE_HOVER)

    def _on_leave(self, _event) -> None:
        if self._command:
            self.configure(fg_color=SELECTED if self._selected else SURFACE)
