from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.data.static import action_label
from app.i18n import t
from app.item_icons import action_image
from app.theme import BORDER, DANGER, FONT, RADIUS, SELECTED, SURFACE, TEXT, TEXT_MUTED
from app.widgets.mod_table import ModTable
from app.widgets.scroll import keep_yview
from app.widgets.search_select import SearchSelect
from app.widgets.tooltip import Tooltip, field_label

if TYPE_CHECKING:
    from app.data.models import CraftStep
    from app.screens.wizard import WizardScreen

KIND_KEYS = ["missing_mod", "has_mod", "open_prefix", "open_suffix", "once"]


class StepCard(ctk.CTkFrame):
    def __init__(self, master, wizard: WizardScreen, index: int, step: CraftStep) -> None:
        super().__init__(
            master,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        self._wizard = wizard
        self._step = step
        catalog = wizard._app.catalog
        actions = catalog.actions_for(wizard.scenario.craft_type) if catalog else []
        action_items = [(row["id"], action_label(row)) for row in actions]

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 8))

        badge = ctk.CTkFrame(header, fg_color=SELECTED, width=28, height=28, corner_radius=14)
        badge.pack(side="left")
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge,
            text=str(index + 1),
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            text_color=TEXT,
        ).pack(expand=True)
        ctk.CTkLabel(
            header,
            text=t("wizard.step_n", n=index + 1),
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=(10, 0))

        delete = ctk.CTkButton(
            header,
            text="×",
            width=32,
            height=28,
            fg_color="transparent",
            hover_color="#3f1d1d",
            text_color=DANGER,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family=FONT, size=16),
            command=lambda: wizard.remove_step(index),
        )
        delete.pack(side="right")
        Tooltip(delete, t("wizard.delete_step"))

        fields = ctk.CTkFrame(self, fg_color="transparent")
        fields.pack(fill="x", padx=14, pady=(0, 4))
        fields.grid_columnconfigure(0, weight=1)
        fields.grid_columnconfigure(1, weight=1)

        action_col = ctk.CTkFrame(fields, fg_color="transparent")
        action_col.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        field_label(action_col, t("wizard.action")).pack(anchor="w")
        self._action_row = SearchSelect(
            action_col,
            items=action_items,
            selected=step.action_id,
            on_select=self._on_action,
            placeholder=t("search.action"),
            image_for=action_image,
            list_height=180,
        )
        self._action_row.pack(fill="x", pady=(4, 0))

        cond_col = ctk.CTkFrame(fields, fg_color="transparent")
        cond_col.grid(row=0, column=1, sticky="nsew")
        field_label(cond_col, t("wizard.until")).pack(anchor="w")
        SearchSelect(
            cond_col,
            items=[(key, t(f"cond.{key}")) for key in KIND_KEYS],
            selected=step.condition.kind,
            on_select=self._on_kind,
            placeholder=t("wizard.condition"),
            list_height=160,
        ).pack(fill="x", pady=(4, 0))

        self._fields = fields
        self._augment_host = ctk.CTkFrame(self, fg_color="transparent")
        self._need_host = ctk.CTkFrame(self, fg_color="transparent")
        self._need_host.pack(fill="x", padx=14, pady=(8, 0))
        self._table_host = ctk.CTkFrame(self, fg_color="transparent")
        self._table_host.pack(fill="x", padx=14, pady=(8, 14))
        self._sync_augment()
        self._sync_table()

    def _sync_table(self) -> None:
        keep_yview(self)
        for host in (self._need_host, self._table_host):
            for child in host.winfo_children():
                child.destroy()
        if not self._step.condition.needs_mods():
            self._need_host.pack_forget()
            self._table_host.pack_forget()
            return
        catalog = self._wizard._app.catalog
        if catalog is None:
            return
        self._need_host.pack(fill="x", padx=14, pady=(8, 0))
        self._table_host.pack(fill="x", padx=14, pady=(8, 14))
        row = ctk.CTkFrame(self._need_host, fg_color="transparent")
        row.pack(fill="x")
        field_label(row, t("wizard.required_weight"), t("wizard.required_hint")).pack(side="left")
        need_entry = ctk.CTkEntry(
            row,
            width=56,
            height=28,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=RADIUS,
            justify="center",
        )
        need_entry.insert(0, str(self._step.condition.required_total()))
        need_entry.pack(side="left", padx=10)
        need_entry.bind("<FocusOut>", lambda _e, widget=need_entry: self._on_required(widget))
        need_entry.bind("<Return>", lambda _e, widget=need_entry: self._on_required(widget))
        field_label(self._table_host, t("wizard.mods")).pack(anchor="w")
        ModTable(
            self._table_host,
            catalog=catalog,
            item_class=self._wizard.scenario.item_type,
            requirements=self._step.condition.mods,
        ).pack(fill="x", pady=(4, 0))

    def _on_required(self, widget: ctk.CTkEntry) -> None:
        try:
            self._step.condition.required_weight = max(1, int(widget.get().strip() or "1"))
        except ValueError:
            self._step.condition.required_weight = 1
        widget.delete(0, "end")
        widget.insert(0, str(self._step.condition.required_total()))

    def _sync_augment(self) -> None:
        for child in self._augment_host.winfo_children():
            child.destroy()
        if self._step.action_id != "alteration":
            self._augment_host.pack_forget()
            return
        if not self._augment_host.winfo_ismapped():
            self._augment_host.pack(fill="x", padx=14, pady=(8, 0), after=self._fields)
        field_label(self._augment_host, t("wizard.augment"), t("wizard.augment_hint")).pack(anchor="w")
        SearchSelect(
            self._augment_host,
            items=[
                ("off", t("wizard.augment_off")),
                ("any", t("wizard.augment_any")),
                ("prefix", t("wizard.augment_prefix")),
                ("suffix", t("wizard.augment_suffix")),
            ],
            selected=self._step.augment_open if self._step.augment_open in {"prefix", "suffix", "any"} else "off",
            on_select=self._on_augment,
            placeholder=t("wizard.augment"),
            list_height=140,
        ).pack(fill="x", pady=(4, 0))

    def _on_augment(self, value: str) -> None:
        self._step.augment_open = value if value in {"prefix", "suffix", "any"} else "off"

    def _on_action(self, action_id: str) -> None:
        self._step.action_id = action_id
        self._sync_augment()

    def _on_kind(self, kind: str) -> None:
        self._step.condition.kind = kind
        if not self._step.condition.needs_mods():
            self._step.condition.mods = []
        self._sync_table()
