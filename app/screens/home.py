from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.config import load_config
from app.data.catalog import list_scenarios
from app.i18n import t
from app.item_icons import HOME_ICON_SIZE, tile_image
from app.theme import BG, FONT, TEXT, TEXT_MUTED
from app.widgets.tile import Tile

if TYPE_CHECKING:
    from app.main_window import MainWindow


class HomeScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        ready = app.catalog is not None
        scenario_count = len(list_scenarios())

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(28, 8))

        ctk.CTkLabel(
            header,
            text=t("home.title"),
            font=ctk.CTkFont(family=FONT, size=24, weight="bold"),
            text_color=TEXT,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=t("home.hint") if ready else t("home.hint_loading"),
            font=ctk.CTkFont(family=FONT, size=13),
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(6, 0))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=32, pady=16)
        grid.grid_columnconfigure((0, 1), weight=1)

        Tile(
            grid,
            title=t("home.create"),
            subtitle=t("home.create_sub"),
            command=app.open_wizard if ready else None,
            enabled=ready,
            image=tile_image("create", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.scenarios"),
            subtitle=t("home.scenarios_count", count=scenario_count) if scenario_count else t("home.scenarios_empty"),
            command=app.open_scenarios,
            image=tile_image("scenarios", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=0, column=1, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.settings"),
            subtitle=t("home.settings_sub"),
            command=app.open_settings,
            image=tile_image("settings", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=1, column=0, padx=6, pady=6, sticky="nsew")

        config = load_config()
        Tile(
            grid,
            title=t("home.run"),
            subtitle=t("home.run_sub", start=config.hotkey_start, stop=config.hotkey_stop),
            command=app.open_run if ready else None,
            enabled=ready,
            image=tile_image("run", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=1, column=1, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.chain"),
            subtitle=t("home.chain_sub", start=config.hotkey_chain, stop=config.hotkey_stop),
            command=(lambda: app.open_run(prefer_chain=True)) if ready else None,
            enabled=ready,
            image=tile_image("chain", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=2, column=0, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.logs"),
            subtitle=t("home.logs_sub"),
            command=app.open_logs,
            image=tile_image("logs", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=2, column=1, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.heist"),
            subtitle=t("home.heist_sub"),
            command=app.open_heist,
            image=tile_image("heist", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=3, column=0, padx=6, pady=6, sticky="nsew")

        Tile(
            grid,
            title=t("home.reveal"),
            subtitle=t("home.reveal_sub"),
            command=app.open_reveal,
            image=tile_image("reveal", folder="home", size=HOME_ICON_SIZE),
            width=360,
            height=120,
        ).grid(row=3, column=1, padx=6, pady=6, sticky="nsew")
