from __future__ import annotations

import sys
from pathlib import Path


def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


ROOT = _exe_dir()
BUNDLE = _bundle_dir()
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
SCENARIOS_DIR = DATA_DIR / "scenarios"
LOGS_DIR = DATA_DIR / "logs"
CATALOG_PATH = CACHE_DIR / "game_catalog.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
ASSETS_DIR = BUNDLE / "app" / "assets"
SYSTEM_DIR = ASSETS_DIR / "system"


def system_path(*parts: str) -> Path:
    return SYSTEM_DIR.joinpath(*parts)


def app_icon_png() -> Path:
    return SYSTEM_DIR / "icon.png"


def app_icon_ico() -> Path:
    ico = SYSTEM_DIR / "icon.ico"
    if ico.is_file():
        return ico
    return SYSTEM_DIR / "icon.png"


def stash_image_path() -> Path:
    for candidate in (
        SYSTEM_DIR / "stash.jpg",
        ASSETS_DIR / "stash.jpg",
        ROOT / "stash.jpg",
    ):
        if candidate.is_file():
            return candidate
    return SYSTEM_DIR / "stash.jpg"


def ensure_data_dirs() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
