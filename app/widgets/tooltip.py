from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from app.theme import FONT, TEXT, TEXT_MUTED


class Tooltip:
    def __init__(self, widget, text: str, delay: int = 350) -> None:
        self._widget = widget
        self._text = text
        self._delay = delay
        self._job: str | None = None
        self._win: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def set_text(self, text: str) -> None:
        self._text = text
        self._hide()

    def _schedule(self, _event=None) -> None:
        self._cancel()
        if not self._text:
            return
        self._job = self._widget.after(self._delay, self._show)

    def _show(self) -> None:
        self._job = None
        if self._win is not None or not self._widget.winfo_exists():
            return
        x = self._widget.winfo_rootx()
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 8
        win = tk.Toplevel(self._widget)
        win.wm_overrideredirect(True)
        win.wm_attributes("-topmost", True)
        frame = tk.Frame(win, bg="#18181b", highlightbackground="#3f3f46", highlightthickness=1)
        frame.pack()
        tk.Label(
            frame,
            text=self._text,
            bg="#18181b",
            fg="#fafafa",
            font=(FONT, 10),
            wraplength=360,
            justify="left",
            padx=10,
            pady=8,
        ).pack()
        win.update_idletasks()
        screen_w = win.winfo_screenwidth()
        width = win.winfo_reqwidth()
        if x + width > screen_w - 12:
            x = max(8, screen_w - width - 12)
        win.geometry(f"+{x}+{y}")
        self._win = win

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self._win is not None:
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


class HelpBadge(ctk.CTkLabel):
    def __init__(self, master, text: str) -> None:
        super().__init__(
            master,
            text="?",
            width=18,
            height=18,
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            cursor="question_arrow",
        )
        self._tip = Tooltip(self, text)


def field_label(master, text: str, help_text: str | None = None, **kwargs) -> ctk.CTkFrame:
    row = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(
        row,
        text=text,
        text_color=kwargs.pop("text_color", TEXT_MUTED),
        font=kwargs.pop("font", ctk.CTkFont(family=FONT, size=12)),
        **kwargs,
    ).pack(side="left")
    if help_text:
        HelpBadge(row, help_text).pack(side="left", padx=(6, 0))
    return row
