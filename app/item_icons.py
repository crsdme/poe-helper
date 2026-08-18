from __future__ import annotations

from pathlib import Path

from app.paths import BUNDLE, ROOT

ICON_SIZE = 48
HOME_ICON_SIZE = 56
ACTION_ICON_SIZE = 22


def icon_path(name: str, folder: str = "items") -> Path | None:
    filename = name.replace(" ", "_") + ".png"
    for root in (BUNDLE, ROOT):
        path = root / "app" / "assets" / folder / filename
        if path.is_file():
            return path
    return None


def asset_rel(name: str, folder: str = "items") -> str | None:
    path = icon_path(name, folder)
    if path is None:
        return None
    return f"../assets/{folder}/{path.name}"


def action_icon(action_id: str) -> str | None:
    if not action_id:
        return None
    if action_id.startswith("harvest"):
        return asset_rel("harvest", "craft")
    return asset_rel(action_id, "currency")
