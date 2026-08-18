from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class TkLoop:
    """Hidden Tk root on its own thread — overlays and HUD must live here."""

    def __init__(self) -> None:
        self.root: tk.Tk | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, name="tk-overlays", daemon=True)

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=8):
            raise RuntimeError("Tk overlay loop failed to start")

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        self.root = root
        self._ready.set()
        root.mainloop()

    @property
    def thread(self) -> threading.Thread:
        return self._thread

    def after(self, ms: int, fn: Callable[[], None]) -> None:
        root = self.root
        if root is None:
            return
        root.after(max(0, int(ms)), fn)

    def call(self, fn: Callable[..., T], *args: Any, wait: bool = False, **kwargs: Any) -> T | None:
        if threading.current_thread() is self._thread:
            return fn(*args, **kwargs)
        root = self.root
        if root is None:
            raise RuntimeError("Tk overlay loop is not running")
        box: list[Any] = []
        done = threading.Event()

        def wrap() -> None:
            try:
                box.append(fn(*args, **kwargs))
            except Exception as exc:
                box.append(exc)
            finally:
                done.set()

        root.after(0, wrap)
        if not wait:
            return None
        done.wait()
        result = box[0] if box else None
        if isinstance(result, Exception):
            raise result
        return result

    def stop(self) -> None:
        root = self.root
        if root is None:
            return
        try:
            root.after(0, root.destroy)
        except Exception:
            pass
