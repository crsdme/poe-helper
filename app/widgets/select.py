from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from app.i18n import t
from app.theme import (
    CONTROL,
    CONTROL_HOVER,
    FONT,
    PREFIX,
    PREFIX_BG,
    RADIUS,
    RING,
    SELECTED,
    SUFFIX,
    SUFFIX_BG,
    TEXT,
    TEXT_MUTED,
)

_OPEN: "Select | None" = None
_CHEVRON: dict[bool, object] = {}


def chevron_image(up: bool = False):
    cached = _CHEVRON.get(up)
    if cached is not None:
        return cached
    from PIL import Image, ImageDraw

    size, scale = 12, 8
    canvas = size * scale
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = canvas / 2
    half_w, half_h = canvas * 0.30, canvas * 0.18
    if up:
        points = [(cx, cy - half_h), (cx + half_w, cy + half_h), (cx - half_w, cy + half_h)]
    else:
        points = [(cx - half_w, cy - half_h), (cx + half_w, cy - half_h), (cx, cy + half_h)]
    draw.polygon(points, fill=(228, 228, 231, 255))
    img = img.resize((size, size), Image.Resampling.LANCZOS)
    image = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _CHEVRON[up] = image
    return image


def affix_chip(master, generation: str) -> ctk.CTkFrame:
    prefix = generation == "prefix"
    chip = ctk.CTkFrame(
        master,
        fg_color=PREFIX_BG if prefix else SUFFIX_BG,
        corner_radius=4,
    )
    ctk.CTkLabel(
        chip,
        text=t("chip.prefix") if prefix else t("chip.suffix"),
        text_color=PREFIX if prefix else SUFFIX,
        font=ctk.CTkFont(family=FONT, size=10, weight="bold"),
    ).pack(padx=6, pady=1)
    return chip


def widget_screen_xy(widget) -> tuple[int, int]:
    """Screen position of a mapped widget (logical pixels Tk already uses)."""
    try:
        widget.update_idletasks()
    except Exception:
        pass
    try:
        if widget.winfo_ismapped():
            return int(widget.winfo_rootx()), int(widget.winfo_rooty())
    except Exception:
        pass
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        hwnd = int(widget.winfo_id())
        if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return int(rect.left), int(rect.top)
    except Exception:
        pass
    try:
        top = widget.winfo_toplevel()
        return int(top.winfo_rootx()) + int(widget.winfo_x()), int(top.winfo_rooty()) + int(widget.winfo_y())
    except Exception:
        return 0, 0


def close_open() -> None:
    if _OPEN is not None:
        try:
            _OPEN.close()
        except Exception:
            pass


class Select(ctk.CTkFrame):
    """Цельный селект с ровной обводкой и чёткой стрелкой."""

    def __init__(
        self,
        master,
        items: list[tuple[str, str]],
        value: str | None = None,
        command: Callable[[str], None] | None = None,
        width: int = 148,
        height: int = 34,
        placeholder: str = "",
        show_code: bool = False,
        menu_width: int | None = None,
        image_for=None,
        badge_for=None,
    ) -> None:
        super().__init__(
            master,
            fg_color=CONTROL,
            border_color=RING,
            border_width=2,
            corner_radius=RADIUS,
            width=width,
            height=height,
            cursor="hand2",
        )
        self.grid_propagate(False)
        self.pack_propagate(False)
        self._items = items
        self._value = value
        self._command = command
        self._placeholder = placeholder
        self._show_code = show_code
        self._menu_width = menu_width or max(width, 168)
        self._image_for = image_for
        self._badge_for = badge_for
        self._popup: ctk.CTkToplevel | None = None
        self._outside_id: str | None = None
        self._outside_widget = None
        self._icon = None
        self._row_images: list = []

        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=3, pady=3)
        inner.grid_columnconfigure(2, weight=1)
        inner.grid_rowconfigure(0, weight=1)
        self._icon_label = ctk.CTkLabel(inner, text="", width=18)
        self._code = ctk.CTkLabel(
            inner,
            text="",
            width=24,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            text_color=TEXT_MUTED,
        )
        self._label = ctk.CTkLabel(
            inner,
            text="",
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=TEXT,
            anchor="w",
        )
        self._chevron = ctk.CTkLabel(inner, text="", image=chevron_image(False), width=18)
        self._icon_label.grid(row=0, column=0, padx=(6, 0))
        if show_code:
            self._code.grid(row=0, column=1, padx=(6, 0))
        self._label.grid(row=0, column=2, sticky="ew", padx=(8, 4))
        self._chevron.grid(row=0, column=3, padx=(0, 6))
        self._sync()
        for widget in (self, inner, self._icon_label, self._code, self._label, self._chevron):
            widget.bind("<Button-1>", self._toggle, add="+")
            widget.bind("<Enter>", self._on_enter, add="+")
            widget.bind("<Leave>", self._on_leave, add="+")

    def get(self) -> str | None:
        return self._value

    def set(self, value: str | None) -> None:
        self._value = value
        self._sync()

    def set_items(self, items: list[tuple[str, str]], value: str | None = None) -> None:
        self._items = items
        if value is not None:
            self._value = value
        elif self._value not in {item[0] for item in items}:
            self._value = items[0][0] if items else None
        self._sync()

    def _text(self) -> str:
        if self._value:
            for item_id, label in self._items:
                if item_id == self._value:
                    return label
            return self._value
        return self._placeholder

    def _sync(self) -> None:
        label = self._text()
        self._label.configure(text=label, text_color=TEXT if self._value else TEXT_MUTED)
        if self._show_code:
            self._code.configure(text=(self._value or "").upper())
        if self._image_for and self._value:
            self._icon = self._image_for(self._value)
            self._icon_label.configure(image=self._icon)
            self._icon_label.grid()
        else:
            self._icon = None
            self._icon_label.configure(image=None)
            if not self._show_code:
                self._icon_label.grid_remove()

    def _on_enter(self, _event=None) -> None:
        if self._popup is None:
            self.configure(fg_color=CONTROL_HOVER)

    def _on_leave(self, _event=None) -> None:
        if self._popup is None:
            self.configure(fg_color=CONTROL, border_color=RING)

    def _toggle(self, _event=None) -> None:
        if self._popup is not None:
            self.close()
        else:
            self.open()

    def open(self) -> None:
        global _OPEN
        if self._popup is not None:
            return
        if _OPEN is not None and _OPEN is not self:
            _OPEN.close()
        _OPEN = self
        self._chevron.configure(image=chevron_image(True))
        self.configure(fg_color=CONTROL_HOVER)

        popup = _Menu(self)
        self._popup = popup
        inner = ctk.CTkFrame(
            popup,
            fg_color=CONTROL,
            corner_radius=RADIUS,
            border_color=RING,
            border_width=2,
        )
        inner.pack(fill="both", expand=True)
        pad = (6, 6)
        host: ctk.CTkFrame = inner
        if len(self._items) > 8:
            host = ctk.CTkScrollableFrame(inner, fg_color=CONTROL, height=220, corner_radius=0)
            host.pack(fill="both", expand=True, padx=4, pady=4)
            pad = (0, 0)
        self._row_images = []
        for item_id, label in self._items:
            self._add_row(host, item_id, label, pad)

        popup.update_idletasks()
        width = max(int(self.winfo_width()), int(self._menu_width))
        height = max(40, int(popup.winfo_reqheight()))
        ax, ay = widget_screen_xy(self)
        widget_h = max(1, int(self.winfo_height()))
        x = ax
        y = ay + widget_h + 4
        screen_w = int(self.winfo_screenwidth())
        screen_h = int(self.winfo_screenheight())
        if x + width > screen_w - 8:
            x = max(8, screen_w - width - 8)
        if y + height > screen_h - 8:
            y = max(8, ay - height - 4)
        popup.geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        popup.deiconify()
        popup.lift()
        popup.bind("<Escape>", lambda _e: self.close())
        popup.bind("<Button-1>", self._on_popup_click, add="+")
        try:
            popup.grab_set()
        except Exception:
            self.after(80, self._listen_outside)

    def _add_row(self, host, item_id: str, label: str, pad: tuple[int, int]) -> None:
        on = item_id == self._value
        row = ctk.CTkFrame(
            host,
            fg_color=SELECTED if on else "transparent",
            corner_radius=6,
            height=32,
            cursor="hand2",
        )
        row.pack(fill="x", padx=pad[0], pady=1)
        row.pack_propagate(False)
        if self._image_for:
            icon = self._image_for(item_id)
            if icon is not None:
                self._row_images.append(icon)
                ctk.CTkLabel(row, text="", image=icon, width=22).pack(side="left", padx=(8, 4))
        generation = self._badge_for(item_id) if self._badge_for else None
        if generation:
            affix_chip(row, generation).pack(side="left", padx=(8, 6))
        ctk.CTkLabel(
            row,
            text=label,
            anchor="w",
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=13, weight="bold" if on else "normal"),
        ).pack(side="left", fill="x", expand=True, padx=(8 if not generation and not self._image_for else 0, 8))
        if on:
            ctk.CTkLabel(row, text="✓", width=18, text_color=TEXT).pack(side="right", padx=(0, 8))
        for widget in (row, *row.winfo_children()):
            widget.bind("<Button-1>", lambda _e, value=item_id: self._pick(value), add="+")

    def close(self) -> None:
        global _OPEN
        self._stop_outside()
        popup = self._popup
        self._popup = None
        if _OPEN is self:
            _OPEN = None
        if popup is not None:
            try:
                popup.grab_release()
            except Exception:
                pass
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except Exception:
                pass
        try:
            if self.winfo_exists():
                self._chevron.configure(image=chevron_image(False))
                self.configure(fg_color=CONTROL, border_color=RING)
        except Exception:
            pass

    def _pick(self, value: str) -> None:
        changed = value != self._value
        self.set(value)
        self.close()
        if changed and self._command:
            self._command(value)

    def _on_popup_click(self, event) -> None:
        popup = self._popup
        if popup is None:
            return
        try:
            if popup.winfo_exists() and popup.winfo_ismapped():
                left = int(popup.winfo_rootx())
                top = int(popup.winfo_rooty())
                if left <= event.x_root <= left + int(popup.winfo_width()) and top <= event.y_root <= top + int(popup.winfo_height()):
                    return
        except Exception:
            pass
        self.close()

    def _listen_outside(self) -> None:
        if self._popup is None:
            return
        try:
            root = self.winfo_toplevel()
            self._outside_widget = root
            self._outside_id = root.bind("<ButtonPress-1>", self._on_outside, add="+")
        except Exception:
            self._outside_id = None
            self._outside_widget = None

    def _stop_outside(self) -> None:
        widget = self._outside_widget
        bind_id = self._outside_id
        self._outside_widget = None
        self._outside_id = None
        if widget is None or not bind_id:
            return
        try:
            if widget.winfo_exists():
                widget.unbind("<ButtonPress-1>", bind_id)
        except Exception:
            pass

    def _on_outside(self, event) -> str | None:
        try:
            if self._inside(event.x_root, event.y_root):
                return None
        except Exception:
            pass
        self.after_idle(self.close)
        return None

    def _inside(self, x: int, y: int) -> bool:
        for widget in (self, self._popup):
            if widget is None:
                continue
            try:
                if not widget.winfo_exists() or not widget.winfo_ismapped():
                    continue
                left = int(widget.winfo_rootx())
                top = int(widget.winfo_rooty())
                if left <= x <= left + int(widget.winfo_width()) and top <= y <= top + int(widget.winfo_height()):
                    return True
            except Exception:
                continue
        return False

    def destroy(self) -> None:
        try:
            self.close()
        except Exception:
            pass
        super().destroy()


class _Menu(tk.Toplevel):
    """Plain Tk popup — CTkToplevel rescales geometry and flashes at 0,0 on Windows."""

    def __init__(self, master) -> None:
        super().__init__(master)
        self.withdraw()
        self.overrideredirect(True)
        self.configure(bg=CONTROL, highlightthickness=0, bd=0)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass
        try:
            self.transient(master.winfo_toplevel())
        except Exception:
            pass
        self.resizable(False, False)
