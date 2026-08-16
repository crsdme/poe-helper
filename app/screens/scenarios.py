from __future__ import annotations

from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from app.data.catalog import delete_scenario, list_scenarios
from app.data.static import item_type_label
from app.i18n import t
from app.theme import BG, BORDER, DANGER, FONT, PRIMARY, PRIMARY_FG, PRIMARY_HOVER, RADIUS, SURFACE, TEXT, TEXT_MUTED
from app.widgets.scroll import enable_mousewheel

if TYPE_CHECKING:
    from app.main_window import MainWindow


class ScenariosScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))

        ctk.CTkButton(
            top,
            text=t("nav.back"),
            width=88,
            fg_color="transparent",
            border_color=BORDER,
            border_width=1,
            text_color=TEXT,
            hover_color=SURFACE,
            corner_radius=RADIUS,
            command=app.show_home,
        ).pack(side="left")

        ctk.CTkLabel(
            top,
            text=t("home.scenarios"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)

        body = ctk.CTkScrollableFrame(self, fg_color=BG)
        body.pack(fill="both", expand=True, padx=32, pady=(8, 20))
        enable_mousewheel(body)

        scenarios = list_scenarios()
        if not scenarios:
            ctk.CTkLabel(
                body,
                text=t("scenarios.empty"),
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT, size=13),
            ).pack(anchor="w", pady=16)
            return

        catalog = app.catalog
        for scenario in scenarios:
            card = ctk.CTkFrame(
                body,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
                corner_radius=RADIUS,
            )
            card.pack(fill="x", pady=6)

            item_name = catalog.item_type_name(scenario.item_type) if catalog else item_type_label(scenario.item_type)
            craft_name = catalog.craft_type_name(scenario.craft_type) if catalog else scenario.craft_type
            ctk.CTkLabel(
                card,
                text=scenario.name,
                font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
                text_color=TEXT,
                anchor="w",
            ).pack(fill="x", padx=16, pady=(12, 0))
            ctk.CTkLabel(
                card,
                text=t("scenarios.meta", item=item_name, craft=craft_name, steps=len(scenario.steps)),
                font=ctk.CTkFont(family=FONT, size=12),
                text_color=TEXT_MUTED,
                anchor="w",
            ).pack(fill="x", padx=16, pady=(4, 0))
            buttons = ctk.CTkFrame(card, fg_color="transparent")
            buttons.pack(fill="x", padx=16, pady=(8, 12))
            ctk.CTkButton(
                buttons,
                text=t("scenarios.edit"),
                width=88,
                height=30,
                fg_color="transparent",
                border_color=BORDER,
                border_width=1,
                text_color=TEXT,
                hover_color=SURFACE,
                corner_radius=RADIUS,
                command=lambda row=scenario: self._edit(row),
            ).pack(side="left")
            ctk.CTkButton(
                buttons,
                text=t("scenarios.delete"),
                width=88,
                height=30,
                fg_color="transparent",
                border_color=DANGER,
                border_width=1,
                text_color=DANGER,
                hover_color="#3f1d1d",
                corner_radius=RADIUS,
                command=lambda row=scenario: self._delete(row),
            ).pack(side="left", padx=8)
            ctk.CTkButton(
                buttons,
                text=t("scenarios.run"),
                width=100,
                height=30,
                fg_color=PRIMARY,
                text_color=PRIMARY_FG,
                hover_color=PRIMARY_HOVER,
                corner_radius=RADIUS,
                command=lambda row=scenario: self._run(row),
            ).pack(side="right")

    def _edit(self, scenario) -> None:
        self._app.open_wizard(scenario)

    def _delete(self, scenario) -> None:
        if not messagebox.askyesno(
            t("home.scenarios"),
            t("scenarios.delete_confirm", name=scenario.name),
        ):
            return
        if not delete_scenario(scenario.id):
            return
        if self._app.selected_scenario_id == scenario.id:
            self._app.selected_scenario_id = None
            from app.settings import save_settings

            save_settings({"last_scenario_id": ""})
        self._app.show_toast(t("scenarios.deleted"), kind="success")
        self._app.open_scenarios()

    def _run(self, scenario) -> None:
        self._app.open_run(scenario, auto_start=True)
