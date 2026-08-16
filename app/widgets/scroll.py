from __future__ import annotations

import customtkinter as ctk

_active: list[ctk.CTkScrollableFrame] = []
_bound = False
DEFAULT_PIXELS = 220


def enable_mousewheel(scrollable: ctk.CTkScrollableFrame, step: int = DEFAULT_PIXELS) -> None:
    """Колёсико работает над любым виджетом внутри CTkScrollableFrame (Windows)."""
    canvas = getattr(scrollable, "_parent_canvas", None)
    if canvas is None:
        return
    canvas.configure(yscrollincrement=1)
    scrollable._wheel_step = step  # type: ignore[attr-defined]
    if scrollable not in _active:
        _active.append(scrollable)
    scrollable.bind("<Destroy>", lambda event, widget=scrollable: _release(widget) if event.widget is widget else None, add="+")
    _ensure_bound(scrollable.winfo_toplevel())


def _release(widget: ctk.CTkScrollableFrame) -> None:
    if widget in _active:
        _active.remove(widget)


def _ensure_bound(root) -> None:
    global _bound
    if _bound:
        return
    _bound = True
    root.bind_all("<MouseWheel>", _on_wheel, add="+")
    root.bind_all("<Button-4>", _on_wheel, add="+")
    root.bind_all("<Button-5>", _on_wheel, add="+")


def _on_wheel(event) -> str | None:
    target = _scrollable_under_pointer()
    if target is None:
        return None
    canvas = getattr(target, "_parent_canvas", None)
    if canvas is None:
        return None
    pixels = int(getattr(target, "_wheel_step", DEFAULT_PIXELS))
    delta = int(getattr(event, "delta", 0) or 0)
    if delta:
        canvas.yview_scroll(int(-delta / 120 * pixels), "units")
    elif getattr(event, "num", None) == 4:
        canvas.yview_scroll(-pixels, "units")
    elif getattr(event, "num", None) == 5:
        canvas.yview_scroll(pixels, "units")
    return "break"


def _scrollable_under_pointer() -> ctk.CTkScrollableFrame | None:
    alive = [widget for widget in _active if widget.winfo_exists()]
    _active[:] = alive
    for widget in reversed(alive):
        try:
            x, y = widget.winfo_pointerxy()
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            if left <= x < left + widget.winfo_width() and top <= y < top + widget.winfo_height():
                return widget
        except Exception:
            continue
    return None


def save_yview(widget) -> tuple[object | None, float | None]:
    current = widget
    while current is not None:
        canvas = getattr(current, "_parent_canvas", None)
        if canvas is not None:
            try:
                return canvas, float(canvas.yview()[0])
            except Exception:
                return canvas, None
        current = getattr(current, "master", None)
    return None, None


def restore_yview(canvas, pos: float | None) -> None:
    if canvas is None or pos is None:
        return
    try:
        canvas.yview_moveto(pos)
    except Exception:
        pass


def keep_yview(widget) -> None:
    try:
        if not widget.winfo_ismapped():
            return
    except Exception:
        return
    canvas, pos = save_yview(widget)
    if canvas is None or pos is None:
        return

    def restore() -> None:
        restore_yview(canvas, pos)

    widget.after_idle(restore)


def clear_children(widget) -> None:
    if widget is None:
        return
    for child in list(widget.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass


def reveal_bottom(widget) -> None:
    canvas = getattr(widget, "_parent_canvas", None)
    if canvas is None:
        return

    def go() -> None:
        try:
            widget.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            canvas.yview_moveto(1.0)
        except Exception:
            pass

    widget.after_idle(go)
