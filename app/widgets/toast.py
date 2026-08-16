from __future__ import annotations

import customtkinter as ctk

from app.theme import BORDER, DANGER, FONT, RADIUS, SUCCESS, TEXT, TEXT_MUTED

_KIND = {
    "error": {"border": DANGER, "mark": "!"},
    "success": {"border": SUCCESS, "mark": "✓"},
    "info": {"border": BORDER, "mark": "i"},
}


class ToastHost:
    def __init__(self, master: ctk.CTk) -> None:
        self._master = master
        self._items: list[ctk.CTkFrame] = []

    def show(self, message: str, kind: str = "error", ms: int = 4500) -> None:
        style = _KIND.get(kind, _KIND["info"])
        card = ctk.CTkFrame(
            self._master,
            fg_color="#18181b",
            border_color=style["border"],
            border_width=1,
            corner_radius=RADIUS,
            width=360,
        )
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        badge = ctk.CTkLabel(
            inner,
            text=style["mark"],
            width=22,
            text_color=style["border"],
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
        )
        badge.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            inner,
            text=message,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=13),
            wraplength=280,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)
        close = ctk.CTkButton(
            inner,
            text="×",
            width=24,
            height=24,
            fg_color="transparent",
            hover_color=BORDER,
            text_color=TEXT_MUTED,
            command=lambda: self._dismiss(card),
        )
        close.pack(side="right", padx=(8, 0))
        card.bind("<Button-1>", lambda _e: self._dismiss(card))
        self._items.append(card)
        card.update_idletasks()
        self._layout()
        card.after(ms, lambda: self._dismiss(card))

    def _dismiss(self, card: ctk.CTkFrame) -> None:
        if card in self._items:
            self._items.remove(card)
        if card.winfo_exists():
            card.destroy()
        self._layout()

    def _layout(self) -> None:
        top = 64
        for card in list(self._items):
            if not card.winfo_exists():
                self._items.remove(card)
                continue
            card.place(relx=1.0, x=-20, y=top, anchor="ne")
            card.lift()
            top += max(56, card.winfo_reqheight()) + 8
