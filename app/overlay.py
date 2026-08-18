from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import tkinter as tk

from app.config import HUD_HEIGHT, HUD_WIDTH, ItemGrid, Rect, default_hud_xy, load_config, save_config
from app.i18n import t
from app.input_win import register_overlay, show_without_activate, style_overlay, unregister_overlay, widget_hwnd
from app.theme import BORDER, FONT, PRIMARY, PRIMARY_FG, TEXT, TEXT_MUTED

BG = "#09090b"
PANEL = "#18181b"
DANGER = "#f87171"


class OverlayWindow(tk.Toplevel):
    def __init__(self, master) -> None:
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=BG)
        try:
            self.resizable(False, False)
        except Exception:
            pass


def _set_size(window, width: int, height: int, x: int | None = None, y: int | None = None) -> None:
    if x is None:
        x = window.winfo_x()
    if y is None:
        y = window.winfo_y()
    window.geometry(f"{int(width)}x{int(height)}+{int(x)}+{int(y)}")


def _label(master, text: str, *, size: int = 11, bold: bool = False, fg: str = TEXT, wrap: int = 220) -> tk.Label:
    weight = "bold" if bold else "normal"
    return tk.Label(
        master,
        text=text,
        font=(FONT, size, weight),
        fg=fg,
        bg=PANEL,
        wraplength=wrap,
        justify="left",
        anchor="w",
    )


def _button(master, text: str, command, *, primary: bool = False, width: int = 12) -> tk.Button:
    if primary:
        return tk.Button(
            master,
            text=text,
            command=command,
            width=width,
            font=(FONT, 10, "bold"),
            bg=PRIMARY,
            fg=PRIMARY_FG,
            activebackground="#e4e4e7",
            activeforeground=PRIMARY_FG,
            relief="flat",
            bd=0,
            cursor="hand2",
            highlightthickness=0,
        )
    return tk.Button(
        master,
        text=text,
        command=command,
        width=width,
        font=(FONT, 10),
        bg=PANEL,
        fg=TEXT,
        activebackground="#27272a",
        activeforeground=TEXT,
        relief="solid",
        bd=1,
        highlightbackground=BORDER,
        cursor="hand2",
        highlightthickness=0,
    )


class PositionOverlay(OverlayWindow):
    """Area overlay: LMB move, RMB resize. Side panel with confirm."""

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
        self.configure(bg="#111111")
        _set_size(self, start.w, start.h, start.x, start.y)

        self._drag_x = 0
        self._drag_y = 0
        self._resize = False
        self._start_w = start.w
        self._start_h = start.h

        self._frame = tk.Frame(self, bg="#161616", highlightbackground=DANGER, highlightthickness=2)
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
            self._dot = tk.Frame(self._frame, bg="#ef4444", width=12, height=12)
            self._dot.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self._dot = None

        self._grip = tk.Frame(self._frame, bg=DANGER, width=16, height=16, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-2, y=-2, anchor="se")

        self._panel = OverlayWindow(master)
        self._panel.configure(bg=BG)
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
        body = tk.Frame(self._panel, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True)
        _label(body, title, size=13, bold=True).pack(anchor="w", padx=14, pady=(12, 4))
        _label(body, hint, size=10, fg=TEXT_MUTED).pack(anchor="w", padx=14, pady=(0, 10))
        buttons = tk.Frame(body, bg=PANEL)
        buttons.pack(fill="x", padx=14, pady=(0, 12))
        _button(buttons, t("overlay.confirm"), self._confirm, primary=True).pack(side="left")
        _button(buttons, t("overlay.cancel"), self._cancel, width=10).pack(side="left", padx=(8, 0))

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
            self._panel.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")
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
            self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
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
    """Inventory/chain grid: LMB move, RMB resize. Side panel for cols/rows."""

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
        self.configure(bg="#111111")
        self._min_w, self._min_h = 160, 120
        _set_size(self, start.w, start.h, start.x, start.y)

        self._drag_x = 0
        self._drag_y = 0
        self._resize = False
        self._start_w = start.w
        self._start_h = start.h

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, bg="#161616", highlightbackground=DANGER)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._grip = tk.Frame(self, bg=DANGER, width=16, height=16, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-2, y=-2, anchor="se")

        self._panel = OverlayWindow(master)
        self._panel.configure(bg=BG)
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
        body = tk.Frame(self._panel, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        body.pack(fill="both", expand=True)
        _label(body, self._title, size=13, bold=True).pack(anchor="w", padx=14, pady=(12, 4))
        _label(
            body,
            f"{t('overlay.grid_move')}\n{t('overlay.grid_resize')}",
            size=10,
            fg=TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        sizes = tk.Frame(body, bg=PANEL)
        sizes.pack(fill="x", padx=14, pady=(0, 10))
        _label(sizes, t("overlay.width"), size=10, fg=TEXT_MUTED).pack(anchor="w")
        self._width_value = self._stepper(sizes, self._cols, self._nudge_cols)
        _label(sizes, t("overlay.height"), size=10, fg=TEXT_MUTED).pack(anchor="w", pady=(8, 0))
        self._height_value = self._stepper(sizes, self._rows, self._nudge_rows)

        buttons = tk.Frame(body, bg=PANEL)
        buttons.pack(fill="x", padx=14, pady=(14, 12))
        _button(buttons, t("overlay.ok"), self._confirm, primary=True).pack(side="left")
        _button(buttons, t("overlay.cancel"), self._cancel, width=10).pack(side="left", padx=(8, 0))

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
            self._panel.geometry(f"{width}x{height}+{max(8, x)}+{max(8, y)}")
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
        self._canvas.create_rectangle(1, 1, width - 2, height - 2, outline=DANGER, width=2, tags="grid")
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

    def _stepper(self, master, value: int, nudge) -> tk.Label:
        row = tk.Frame(master, bg=PANEL)
        row.pack(anchor="w", pady=(2, 0))
        _button(row, "−", lambda: nudge(-1), width=3).pack(side="left")
        label = tk.Label(
            row,
            text=str(value),
            width=4,
            fg=TEXT,
            bg=PANEL,
            font=(FONT, 14, "bold"),
        )
        label.pack(side="left", padx=8)
        _button(row, "+", lambda: nudge(1), width=3).pack(side="left")
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
            self._resize = False
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
        except Exception:
            pass

    def _move(self, event) -> None:
        if self._resize:
            return
        try:
            self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
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
    def __init__(self, master, prompt: str, on_pick, on_cancel=None) -> None:
        super().__init__(master)
        self._on_pick = on_pick
        self._on_cancel = on_cancel
        self.attributes("-fullscreen", True)
        try:
            self.attributes("-alpha", 0.38)
        except Exception:
            pass
        self.configure(bg="#0c4a6e")
        label = tk.Label(
            self,
            text=prompt,
            font=(FONT, 26, "bold"),
            fg="#ffffff",
            bg="#0c4a6e",
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


class CraftHud(OverlayWindow):
    _min_w = 200
    _min_h = 120

    def __init__(self, master, stop_key: str, *, mode: str = "craft") -> None:
        super().__init__(master)
        self.configure(bg=BG)
        self._mode = mode
        self._hwnds: list[int] = []
        self._final = False
        self._resize = False
        self._wrap = 0
        self._wrap_job: str | None = None
        self._drag_x = 0
        self._drag_y = 0
        self._start_w = HUD_WIDTH
        self._start_h = HUD_HEIGHT
        self._start_x = 0
        self._start_y = 0

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

        shell = tk.Frame(self, bg=BORDER)
        shell.pack(fill="both", expand=True, padx=1, pady=1)
        frame = tk.Frame(shell, bg=PANEL)
        frame.pack(fill="both", expand=True)
        self._frame = frame

        bar = tk.Frame(frame, bg="#27272a", cursor="fleur", height=28)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._bar = bar
        self._title = tk.Label(
            bar,
            text=t("run.running"),
            font=(FONT, 11, "bold"),
            fg=TEXT,
            bg="#27272a",
            anchor="w",
            cursor="fleur",
        )
        self._title.pack(fill="both", expand=True, padx=10)

        body = tk.Frame(frame, bg=PANEL, cursor="fleur")
        body.pack(fill="both", expand=True)
        self._body = body
        wrap = max(120, width - 28)
        self._spent = tk.Label(body, text="—", font=(FONT, 10), fg=TEXT, bg=PANEL, anchor="w", justify="left", cursor="fleur")
        self._spent.pack(fill="x", padx=12, pady=(8, 0))
        self._score = tk.Label(
            body,
            text="" if mode != "craft" else t("run.hud_score", hits=0, misses=0),
            font=(FONT, 10),
            fg=TEXT_MUTED,
            bg=PANEL,
            anchor="w",
            justify="left",
            cursor="fleur",
        )
        self._score.pack(fill="x", padx=12)
        self._item = tk.Label(
            body,
            text=t("run.log.start"),
            font=(FONT, 9),
            fg=TEXT_MUTED,
            bg=PANEL,
            anchor="w",
            wraplength=wrap,
            justify="left",
            cursor="fleur",
        )
        self._item.pack(fill="x", padx=12, pady=(4, 0))
        self._hint = tk.Label(
            body,
            text=t("run.hud_stop", key=stop_key) if stop_key else t("run.hud_stop_esc"),
            font=(FONT, 8),
            fg=TEXT_MUTED,
            bg=PANEL,
            anchor="w",
            wraplength=wrap,
            justify="left",
            cursor="fleur",
        )
        self._hint.pack(fill="x", padx=12, pady=(2, 10))

        self._grip = tk.Frame(self, bg="#71717a", width=14, height=14, cursor="size_nw_se")
        self._grip.place(relx=1, rely=1, x=-2, y=-2, anchor="se")
        self._grip.bind("<ButtonPress-1>", self._start_resize)
        self._grip.bind("<B1-Motion>", self._do_resize)
        self._grip.bind("<ButtonRelease-1>", self._save_pos)

        for widget in (self, shell, frame, bar, body, self._title, self._spent, self._score, self._item, self._hint):
            widget.bind("<ButtonPress-1>", self._start_move)
            widget.bind("<B1-Motion>", self._move)
            widget.bind("<ButtonRelease-1>", self._save_pos)

        self.lift()
        self.update_idletasks()
        self._ready()
        self.bind("<Configure>", self._on_configure, add="+")

    def _ready(self) -> None:
        if not self._alive():
            return
        hwnd = widget_hwnd(self)
        owner = widget_hwnd(self.master)
        if hwnd and hwnd != owner and hwnd not in self._hwnds:
            style_overlay(hwnd)
            register_overlay(hwnd)
            self._hwnds.append(hwnd)
            show_without_activate(hwnd)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

    def keep_top(self) -> None:
        if not self._alive():
            return
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

    def _alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except Exception:
            return False

    def _safe(self, widget, **kwargs) -> None:
        if not self._alive():
            return
        try:
            widget.configure(**kwargs)
        except Exception:
            pass

    def set_note(self, text: str) -> None:
        if text:
            self._safe(self._item, text=text)

    def set_hint(self, text: str) -> None:
        if text:
            self._safe(self._hint, text=text)

    def set_step(self, text: str) -> None:
        if not self._final:
            self._safe(self._title, text=text)

    def set_progress(self, text: str) -> None:
        if text:
            self._safe(self._spent, text=text)

    def _on_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if not self._alive():
            return
        if self._wrap_job:
            try:
                self.after_cancel(self._wrap_job)
            except Exception:
                pass
        self._wrap_job = self.after(40, self._apply_wrap)

    def _apply_wrap(self) -> None:
        self._wrap_job = None
        if not self._alive():
            return
        wrap = max(80, self.winfo_width() - 28)
        if wrap == self._wrap:
            return
        self._wrap = wrap
        self._safe(self._item, wraplength=wrap)
        self._safe(self._hint, wraplength=wrap)

    def _start_move(self, event) -> str | None:
        if event.widget is self._grip:
            return None
        self._resize = False
        try:
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
        except Exception:
            self._drag_x = 0
            self._drag_y = 0
        return "break"

    def _move(self, event) -> str | None:
        if self._resize or not self._alive():
            return None
        try:
            self.geometry(f"+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}")
        except Exception:
            pass
        return "break"

    def _start_resize(self, event) -> str | None:
        if not self._alive():
            return None
        self._resize = True
        self._drag_x = event.x_root
        self._drag_y = event.y_root
        self._start_w = self.winfo_width()
        self._start_h = self.winfo_height()
        self._start_x = self.winfo_x()
        self._start_y = self.winfo_y()
        return "break"

    def _do_resize(self, event) -> str | None:
        if not self._alive():
            return None
        width = max(self._min_w, self._start_w + (event.x_root - self._drag_x))
        height = max(self._min_h, self._start_h + (event.y_root - self._drag_y))
        _set_size(self, width, height, self._start_x, self._start_y)
        return "break"

    def _save_pos(self, _event=None) -> None:
        if not self._alive():
            return
        try:
            self.update_idletasks()
            config = load_config()
            config.hud_x = int(self.winfo_x())
            config.hud_y = int(self.winfo_y())
            config.hud_w = max(self._min_w, int(self.winfo_width()))
            config.hud_h = max(self._min_h, int(self.winfo_height()))
            save_config(config)
        except Exception:
            pass

    def destroy(self) -> None:
        for hwnd in self._hwnds:
            unregister_overlay(hwnd)
        self._hwnds.clear()
        super().destroy()

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
            self._safe(self._title, text=title)
            progress = data.get("progress") or data.get("spent")
            if progress:
                self._safe(self._spent, text=progress)
            item = (data.get("item") or "").strip()
            if item:
                self._safe(self._item, text=item)
            return
        self.update_stats(data)

    def update_stats(self, data: dict) -> None:
        if not self._alive():
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
        self._safe(self._title, text=title)
        spent = data.get("spent") or data.get("progress")
        if spent:
            self._safe(self._spent, text=spent)
        if self._mode == "craft":
            self._safe(self._score, text=t("run.hud_score", hits=data.get("hits", 0), misses=data.get("misses", 0)))
        item = (data.get("item") or "").strip()
        if item:
            self._safe(self._item, text=item)
