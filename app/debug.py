from __future__ import annotations

import threading
import traceback
from datetime import datetime

from app.paths import DATA_DIR, ensure_data_dirs

_lock = threading.Lock()
_PATH = DATA_DIR / "debug.log"


def dbg(message: str) -> None:
    line = f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} [{threading.current_thread().name}] {message}"
    try:
        ensure_data_dirs()
        with _lock:
            with _PATH.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
    except OSError:
        pass


def dbg_exc(message: str) -> None:
    dbg(message + "\n" + traceback.format_exc())
