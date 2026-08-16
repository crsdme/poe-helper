from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk
import tkinter as tk

from app.config import ItemGrid, Rect
from app.i18n import t
from app.theme import BORDER, FONT, PRIMARY, PRIMARY_FG, RADIUS, SELECTED, TEXT, TEXT_MUTED


class OverlayWindow(ctk.CTkToplevel):
    """CTkToplevel without Windows titlebar withdraw — that flash hides overrideredirect windows."""

    _deactivate_windows_window_header_manipulation = True

    def __init__(self, master) -> None:
        super().__init__(master)
        self._iconbitmap_method_called = True
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.deiconify()
        except Exception:
            pass

    def iconbitmap(self, *args, **kwargs):
        self._iconbitmap_method_called = True
        return ""

    def wm_iconbitmap(self, *args, **kwargs):
        self._iconbitmap_method_called = True
        return ""


def _unlock_size(window, min_w: int, min_h: int) -> None:
    try:
        window._min_width = min_w
        window._min_height = min_h
        window._max_width = 10_000
        window._max_height = 10_000
    except Exception:
        pass
    tk.Toplevel.resizable(window, True, True)
    tk.Toplevel.minsize(window, min_w, min_h)
    tk.Toplevel.maxsize(window, 10_000, 10_000)


def _set_size(window, width: int, height: int, x: int | None = None, y: int | None = None) -> None:
    if x is None:
        x = window.winfo_x()
    if y is None:
        y = window.winfo_y()
    try:
        window._current_width = width
        window._current_height = height
    except Exception:
        pass
    tk.Toplevel.geometry(window, f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")



class PositionOverlay(OverlayWindow):
    """Окно области без подписей: ЛКМ — двигать, ПКМ — растягивать. Кнопки сбоку."""

    def __init__(
        self,
        master,
        title: str,
        rect: Rect | None,
        on_confirm: Callable[[Rect], None],
        on_cancel: Callable[[], None] | None = None,
        min_size: tuple[int, int] = (80, 80),
        background: Path | str | None = None,
        lock_aspect: bool = False,
        show_dot: bool = True,
        hint: str | None = None,
        alpha: float = 0.82,
    ) -> None:
        super().__init__(master)
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._min_w, self._min_h = min_size
        self._lock_aspect = lock_aspect
        self._src = None
        self._photo = None
        self._resize_job: str | None = None
        start = rect or Rect(x=320, y=180, w=160, h=220)
        self._aspect = start.w / max(1, start.h)
        self.attributes("-alpha", alpha)
        self.configure(fg_color="#111111")
        _set_size(self, start.w, start.h, start.x, start.y)
        _unlock_size(self, self._min_w, self._min_h)

        self._drag_x = 0
        self._drag_y = 0
        self._resize = False
        self._start_w = start.w
        self._start_h = start.h

        self._frame = tk.Frame(self, bg="#161616", highlightbackground="#f87171", highlightthickness=2)
        self._frame.pack(fill="both", expand=True)

        if background:
            path = Path(background)
            if path.is_file():
                from PIL import Image

                self._src = Image.open(path).convert("RGB")
                self._aspect = self._src.width / max(1, self._src.height)
                self._canvas = tk.Canvas(self._frame, highlightthickness=0, bd=0, bg="#111111")
                self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
                self._frame.bind("<Configure>", self._schedule_bg)
                self.after(16, self._redraw_bg)

        if show_dot:
            self._dot = ctk.CTkFrame(self._frame, fg_color="#ef4444", width=12, height=12, corner_radius=6)
            self._dot.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self._dot = None

        self._grip = tk.Frame(self._frame, bg="#f87171", width=16, height=16, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-2, y=-2, anchor="se")

        self._panel = OverlayWindow(master)
        self._panel.configure(fg_color="#09090b")
        self._build_panel(title, hint or t("overlay.hint"))

        bind_targets = [self, self._frame, self._grip]
        if self._dot is not None:
            bind_targets.append(self._dot)
        if hasattr(self, "_canvas"):
            bind_targets.append(self._canvas)
        for widget in bind_targets:
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._move)
            widget.bind("<ButtonPress-3>", self._start_resize)
            widget.bind("<B3-Motion>", self._do_resize)
        self._grip.bind("<ButtonPress-1>", self._start_resize)
        self._grip.bind("<B1-Motion>", self._do_resize)

        for window in (self, self._panel):
            window.bind("<Escape>", lambda _e: self._cancel())
            window.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Configure>", self._place_panel, add="+")
        self.after(16, self._place_panel)
        self.lift()
        self.focus_force()

    def _build_panel(self, title: str, hint: str) -> None:
        body = ctk.CTkFrame(
            self._panel,
            fg_color="#18181b",
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(
            body,
            text=title,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            text_color=TEXT,
            wraplength=220,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            body,
            text=hint,
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=TEXT_MUTED,
            wraplength=220,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(0, 10))
        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            buttons,
            text=t("overlay.confirm"),
            width=110,
            height=32,
            fg_color=PRIMARY,
            text_color=PRIMARY_FG,
            hover_color="#e4e4e7",
            corner_radius=RADIUS,
            command=self._confirm,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text=t("overlay.cancel"),
            width=90,
            height=32,
            fg_color="transparent",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            corner_radius=RADIUS,
            command=self._cancel,
        ).pack(side="left", padx=(8, 0))

    def _place_panel(self, _event=None) -> None:
        try:
            if not self.winfo_exists() or not self._panel.winfo_exists():
                return
            width, height = 248, 196
            x = self.winfo_x() + self.winfo_width() + 10
            y = self.winfo_y()
            if x + width > self.winfo_screenwidth() - 8:
                x = self.winfo_x() - width - 10
            if y + height > self.winfo_screenheight() - 8:
                y = max(8, self.winfo_screenheight() - height - 8)
            tk.Toplevel.geometry(self._panel, f"{width}x{height}+{max(8, x)}+{max(8, y)}")
        except Exception:
            pass

    def _schedule_bg(self, _event=None) -> None:
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(20, self._redraw_bg)

    def _redraw_bg(self) -> None:
        self._resize_job = None
        if self._src is None or not hasattr(self, "_canvas"):
            return
        from PIL import ImageTk

        width = max(1, self._frame.winfo_width())
        height = max(1, self._frame.winfo_height())
        image = self._src.resize((width, height), resample=2)
        self._photo = ImageTk.PhotoImage(image)
        self._canvas.delete("bg")
        self._canvas.create_image(0, 0, image=self._photo, anchor="nw", tags="bg")

    def current_rect(self) -> Rect:
        return Rect(x=self.winfo_x(), y=self.winfo_y(), w=self.winfo_width(), h=self.winfo_height())

    def _start_move(self, event) -> None:
        try:
            self._resize = False
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
        except Exception:
            pass

    def _move(self, event) -> None:
        if self._resize:
            return
        try:
            tk.Toplevel.geometry(self, f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
            self._place_panel()
        except Exception:
            pass

    def _start_resize(self, event) -> None:
        try:
            self._resize = True
            self._drag_x = event.x_root
            self._drag_y = event.y_root
            self._start_w = self.winfo_width()
            self._start_h = self.winfo_height()
            self._start_x = self.winfo_x()
            self._start_y = self.winfo_y()
        except Exception:
            pass

    def _do_resize(self, event) -> None:
        width = max(self._min_w, self._start_w + (event.x_root - self._drag_x))
        if self._lock_aspect:
            height = max(self._min_h, int(width / max(0.2, self._aspect)))
        else:
            height = max(self._min_h, self._start_h + (event.y_root - self._drag_y))
        _set_size(self, width, height, getattr(self, "_start_x", self.winfo_x()), getattr(self, "_start_y", self.winfo_y()))
        self._place_panel()

    def _close(self) -> None:
        if self._panel.winfo_exists():
            self._panel.destroy()
        self.destroy()

    def _confirm(self) -> None:
        rect = self.current_rect()
        callback = self._on_confirm
        self._close()
        callback(rect)

    def _cancel(self) -> None:
        callback = self._on_cancel
        self._close()
        if callback:
            callback()


_DOT = 8


class GridOverlay(OverlayWindow):
    """Сетка предметов без кнопок поверх точек: ЛКМ — двигать, ПКМ — размер. Управление сбоку."""

    def __init__(
        self,
        master,
        grid: ItemGrid | None,
        on_confirm: Callable[[ItemGrid], None],
        on_cancel: Callable[[], None] | None = None,
        title: str | None = None,
    ) -> None:
        super().__init__(master)
        self._on_confirm = on_confirm
        self._on_cancel = on_cancel
        self._title = title or t("settings.chain")
        start = grid or ItemGrid()
        self._cols = max(1, min(12, start.cols))
        self._rows = max(1, min(12, start.rows))
        self.attributes("-alpha", 0.62)
        self.configure(fg_color="#111111")
        self._min_w, self._min_h = 160, 120
        _set_size(self, start.w, start.h, start.x, start.y)
        _unlock_size(self, self._min_w, self._min_h)

        self._drag_x = 0
        self._drag_y = 0
        self._resize = False
        self._start_w = start.w
        self._start_h = start.h

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="#161616", highlightbackground="#f87171")
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._grip = tk.Frame(self, bg="#f87171", width=16, height=16, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-2, y=-2, anchor="se")

        self._panel = OverlayWindow(master)
        self._panel.configure(fg_color="#09090b")
        self._build_panel()

        for widget in (self, self._canvas, self._grip):
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._move)
            widget.bind("<ButtonPress-3>", self._start_resize)
            widget.bind("<B3-Motion>", self._do_resize)
        self._grip.bind("<ButtonPress-1>", self._start_resize)
        self._grip.bind("<B1-Motion>", self._do_resize)
        self._canvas.bind("<Configure>", lambda _e: self._draw_dots())
        for window in (self, self._panel):
            window.bind("<Escape>", lambda _e: self._cancel())
            window.bind("<Return>", lambda _e: self._confirm())
        self.bind("<Configure>", self._place_panel, add="+")
        self.after(16, self._place_panel)
        self.after(16, self._draw_dots)
        self.lift()
        self.focus_force()

    def _build_panel(self) -> None:
        body = ctk.CTkFrame(
            self._panel,
            fg_color="#18181b",
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        body.pack(fill="both", expand=True)
        ctk.CTkLabel(
            body,
            text=self._title,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            text_color=TEXT,
            wraplength=220,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(12, 4))
        ctk.CTkLabel(
            body,
            text=f"{t('overlay.grid_move')}\n{t('overlay.grid_resize')}",
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=TEXT_MUTED,
            wraplength=220,
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        sizes = ctk.CTkFrame(body, fg_color="transparent")
        sizes.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkLabel(sizes, text=t("overlay.width"), text_color=TEXT_MUTED).pack(anchor="w")
        self._width_value = self._stepper(sizes, self._cols, self._nudge_cols)
        ctk.CTkLabel(sizes, text=t("overlay.height"), text_color=TEXT_MUTED).pack(anchor="w", pady=(8, 0))
        self._height_value = self._stepper(sizes, self._rows, self._nudge_rows)

        buttons = ctk.CTkFrame(body, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(14, 12))
        ctk.CTkButton(
            buttons,
            text=t("overlay.ok"),
            width=110,
            height=32,
            fg_color=PRIMARY,
            text_color=PRIMARY_FG,
            hover_color="#e4e4e7",
            corner_radius=RADIUS,
            command=self._confirm,
        ).pack(side="left")
        ctk.CTkButton(
            buttons,
            text=t("overlay.cancel"),
            width=90,
            height=32,
            fg_color="transparent",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            corner_radius=RADIUS,
            command=self._cancel,
        ).pack(side="left", padx=(8, 0))

    def _place_panel(self, _event=None) -> None:
        try:
            if not self.winfo_exists() or not self._panel.winfo_exists():
                return
            width, height = 248, 320
            x = self.winfo_x() + self.winfo_width() + 10
            y = self.winfo_y()
            if x + width > self.winfo_screenwidth() - 8:
                x = self.winfo_x() - width - 10
            if y + height > self.winfo_screenheight() - 8:
                y = max(8, self.winfo_screenheight() - height - 8)
            tk.Toplevel.geometry(self._panel, f"{width}x{height}+{max(8, x)}+{max(8, y)}")
        except Exception:
            pass

    def current_grid(self) -> ItemGrid:
        return ItemGrid(
            x=self.winfo_x(),
            y=self.winfo_y(),
            w=self.winfo_width(),
            h=self.winfo_height(),
            cols=self._cols,
            rows=self._rows,
        )

    def _draw_dots(self) -> None:
        self._canvas.delete("grid")
        width = max(1, self._canvas.winfo_width())
        height = max(1, self._canvas.winfo_height())
        self._canvas.create_rectangle(1, 1, width - 2, height - 2, outline="#f87171", width=2, tags="grid")
        for row in range(self._rows):
            for col in range(self._cols):
                x = (col + 0.5) * width / self._cols
                y = (row + 0.5) * height / self._rows
                self._canvas.create_oval(
                    x - _DOT - 2,
                    y - _DOT - 2,
                    x + _DOT + 2,
                    y + _DOT + 2,
                    fill="#fafafa",
                    outline="",
                    tags="grid",
                )
                self._canvas.create_oval(
                    x - _DOT,
                    y - _DOT,
                    x + _DOT,
                    y + _DOT,
                    fill="#ef4444",
                    outline="",
                    tags="grid",
                )

    def _stepper(self, master, value: int, nudge) -> ctk.CTkLabel:
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(anchor="w", pady=(2, 0))
        outline = {
            "fg_color": "transparent",
            "border_color": BORDER,
            "border_width": 1,
            "text_color": TEXT,
            "hover_color": SELECTED,
            "corner_radius": RADIUS,
            "width": 34,
            "height": 32,
        }
        ctk.CTkButton(row, text="−", command=lambda: nudge(-1), **outline).pack(side="left")
        label = ctk.CTkLabel(
            row,
            text=str(value),
            width=36,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
        )
        label.pack(side="left", padx=8)
        ctk.CTkButton(row, text="+", command=lambda: nudge(1), **outline).pack(side="left")
        return label

    def _nudge_cols(self, delta: int) -> None:
        self._cols = max(1, min(12, self._cols + delta))
        self._width_value.configure(text=str(self._cols))
        self._draw_dots()

    def _nudge_rows(self, delta: int) -> None:
        self._rows = max(1, min(12, self._rows + delta))
        self._height_value.configure(text=str(self._rows))
        self._draw_dots()

    def _start_move(self, event) -> None:
        try:
            from app.widgets.select import close_open

            close_open()
            self._resize = False
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
        except Exception:
            pass

    def _move(self, event) -> None:
        if self._resize:
            return
        try:
            tk.Toplevel.geometry(self, f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
            self._place_panel()
        except Exception:
            pass

    def _start_resize(self, event) -> None:
        try:
            self._resize = True
            self._drag_x = event.x_root
            self._drag_y = event.y_root
            self._start_w = self.winfo_width()
            self._start_h = self.winfo_height()
            self._start_x = self.winfo_x()
            self._start_y = self.winfo_y()
        except Exception:
            pass

    def _do_resize(self, event) -> None:
        width = max(self._min_w, self._start_w + (event.x_root - self._drag_x))
        height = max(self._min_h, self._start_h + (event.y_root - self._drag_y))
        _set_size(self, width, height, self._start_x, self._start_y)
        self._place_panel()

    def _close(self) -> None:
        if self._panel.winfo_exists():
            self._panel.destroy()
        self.destroy()

    def _confirm(self) -> None:
        grid = self.current_grid()
        callback = self._on_confirm
        self._close()
        callback(grid)

    def _cancel(self) -> None:
        callback = self._on_cancel
        self._close()
        if callback:
            callback()


class PointPicker(OverlayWindow):
    """Полноэкранный выбор точки: ЛКМ — взять, Esc — отмена."""

    def __init__(self, master, prompt: str, on_pick, on_cancel=None) -> None:
        super().__init__(master)
        self._on_pick = on_pick
        self._on_cancel = on_cancel
        self.attributes("-fullscreen", True)
        try:
            self.attributes("-alpha", 0.38)
        except Exception:
            pass
        self.configure(fg_color="#0c4a6e")
        label = ctk.CTkLabel(
            self,
            text=prompt,
            font=ctk.CTkFont(family=FONT, size=26, weight="bold"),
            text_color="#ffffff",
            justify="center",
        )
        label.pack(expand=True)
        for widget in (self, label):
            widget.bind("<Button-1>", self._click)
        self.bind("<Escape>", self._esc)
        self.focus_force()

    def _click(self, event) -> None:
        callback = self._on_pick
        self.destroy()
        callback((int(event.x_root), int(event.y_root)))

    def _esc(self, _event=None) -> None:
        callback = self._on_cancel
        self.destroy()
        if callback:
            callback()
