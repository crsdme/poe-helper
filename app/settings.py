from __future__ import annotations

import json
from typing import Any

from app.paths import SETTINGS_PATH, ensure_data_dirs


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(data: dict[str, Any]) -> None:
    ensure_data_dirs()
    current = load_settings()
    current.update(data)
    SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
