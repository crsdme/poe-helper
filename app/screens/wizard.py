from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.data.catalog import grouped_item_types, save_scenario
from app.data.models import Condition, CraftScenario, CraftStep
from app.data.static import item_type_label
from app.i18n import t
from app.item_icons import tile_image
from app.theme import (
    BG,
    BORDER,
    FONT,
    PRIMARY,
    PRIMARY_FG,
    PRIMARY_HOVER,
    RADIUS,
    SURFACE,
    TEXT,
    TEXT_MUTED,
)
from app.widgets.scroll import clear_children, enable_mousewheel, reveal_bottom
from app.widgets.step_bar import StepBar
from app.widgets.step_card import StepCard
from app.widgets.tile import Tile
from app.widgets.tooltip import HelpBadge

if TYPE_CHECKING:
    from app.main_window import MainWindow


def _outline_btn() -> dict:
    return {
        "fg_color": "transparent",
        "border_color": BORDER,
        "border_width": 1,
        "text_color": TEXT,
        "hover_color": SURFACE,
        "corner_radius": RADIUS,
    }


def _primary_btn() -> dict:
    return {
        "fg_color": PRIMARY,
        "hover_color": PRIMARY_HOVER,
        "text_color": PRIMARY_FG,
        "corner_radius": RADIUS,
        "font": ctk.CTkFont(family=FONT, size=13, weight="bold"),
    }


class WizardScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow, scenario: CraftScenario | None = None) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        self._step = 3 if scenario and scenario.steps else 1
        self.scenario = scenario or CraftScenario(name=t("scenario.default"))
        if scenario and app.catalog:
            app.catalog.sync_scenario(self.scenario)
        self._item_tiles: dict[str, Tile] = {}
        self._craft_tiles: dict[str, Tile] = {}
        self._empty_hint: ctk.CTkLabel | None = None
        self._steps_host = None
        self._step_bar_host = ctk.CTkFrame(self, fg_color="transparent")
        self._step_bar_host.pack(fill="x", padx=32, pady=(16, 0))
        self._body = ctk.CTkFrame(self, fg_color=BG)
        self._body.pack(fill="both", expand=True, padx=32, pady=8)
        self._footer = ctk.CTkFrame(self, fg_color="transparent")
        self._footer.pack(fill="x", padx=32, pady=(0, 16))
        self._show_step()

    def _show_step(self) -> None:
        for host in (self._step_bar_host, self._body, self._footer):
            for child in host.winfo_children():
                child.destroy()
        self._item_tiles.clear()
        self._craft_tiles.clear()

        StepBar(
            self._step_bar_host,
            [t("wizard.step1"), t("wizard.step2"), t("wizard.step3"), t("wizard.step4")],
            self._step,
        ).pack(anchor="w")

        if self._step == 1:
            self._build_step_item_type()
        elif self._step == 2:
            self._build_step_craft_type()
        elif self._step == 3:
            self._build_step_chain()
        else:
            self._build_step_confirm()
        self._build_footer()

    def _render(self) -> None:
        self._show_step()

    def _build_footer(self) -> None:
        ctk.CTkButton(
            self._footer,
            text=t("nav.back") if self._step > 1 else t("nav.home"),
            width=110,
            command=self._back,
            **_outline_btn(),
        ).pack(side="left")

        if self._step < 4:
            ctk.CTkButton(
                self._footer,
                text=t("nav.next"),
                width=120,
                command=self._next,
                **_primary_btn(),
            ).pack(side="right")
        else:
            ctk.CTkButton(
                self._footer,
                text=t("nav.save"),
                width=160,
                command=self._save,
                **_primary_btn(),
            ).pack(side="right")

    def _back(self) -> None:
        if self._step == 1:
            self._app.show_home()
            return
        self._step -= 1
        self._show_step()

    def _next(self) -> None:
        error = self._validate()
        if error:
            self._app.show_toast(error, kind="error")
            return
        self._step += 1
        self._show_step()

    def _validate(self) -> str | None:
        if self._step == 1 and not self.scenario.item_type:
            return t("validate.item")
        if self._step == 2 and not self.scenario.craft_type:
            return t("validate.craft")
        if self._step == 3:
            if not self.scenario.steps:
                return t("validate.steps")
            for index, step in enumerate(self.scenario.steps, start=1):
                if not step.action_id:
                    return t("validate.action", n=index)
                if step.condition.needs_mods() and not step.condition.mods:
                    return t("validate.mods", n=index)
        return None

    def _heading(self, title: str, subtitle: str, help_text: str | None = None) -> None:
        title_row = ctk.CTkFrame(self._body, fg_color="transparent")
        title_row.pack(anchor="w", pady=(10, 4))
        ctk.CTkLabel(
            title_row,
            text=title,
            font=ctk.CTkFont(family=FONT, size=22, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")
        if help_text:
            HelpBadge(title_row, help_text).pack(side="left", padx=(10, 0))
        if subtitle:
            ctk.CTkLabel(
                self._body,
                text=subtitle,
                font=ctk.CTkFont(family=FONT, size=13),
                text_color=TEXT_MUTED,
                wraplength=980,
                justify="left",
            ).pack(anchor="w", pady=(0, 12))

    def _build_step_item_type(self) -> None:
        self._heading(t("wizard.s1_title"), t("wizard.s1_sub"))
        scroller = ctk.CTkScrollableFrame(self._body, fg_color=BG)
        scroller.pack(fill="both", expand=True)
        enable_mousewheel(scroller)

        for group_id, rows in grouped_item_types(self._app.catalog):
            ctk.CTkLabel(
                scroller,
                text=t(f"group.{group_id}"),
                font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                text_color=TEXT_MUTED,
            ).pack(anchor="w", pady=(10, 6))
            grid = ctk.CTkFrame(scroller, fg_color="transparent")
            grid.pack(fill="x")
            for index, row in enumerate(rows):
                tile = Tile(
                    grid,
                    title=t(f"item.{row['id']}", default=row["name"]),
                    subtitle=row["name"],
                    selected=self.scenario.item_type == row["id"],
                    command=lambda item_id=row["id"]: self._select_item_type(item_id),
                    image=tile_image(row["id"]),
                    width=198,
                    height=86,
                )
                tile.grid(row=index // 4, column=index % 4, padx=5, pady=5, sticky="nsew")
                self._item_tiles[row["id"]] = tile

    def _select_item_type(self, item_id: str) -> None:
        self.scenario.item_type = item_id
        for key, tile in self._item_tiles.items():
            tile.set_selected(key == item_id)
        self._app.set_status(t("status.item", name=self._app.catalog.item_type_name(item_id)))

    def _build_step_craft_type(self) -> None:
        self._heading(t("wizard.s2_title"), t("wizard.s2_sub"))
        row = ctk.CTkFrame(self._body, fg_color="transparent")
        row.pack(anchor="w")
        for craft in self._app.catalog.craft_types:
            tile = Tile(
                row,
                title=t(f"craft.{craft['id']}"),
                subtitle=t(f"craft.{craft['id']}.desc"),
                selected=self.scenario.craft_type == craft["id"],
                command=lambda craft_id=craft["id"]: self._select_craft_type(craft_id),
                image=tile_image(craft["id"], folder="craft"),
                width=300,
                height=118,
            )
            tile.pack(side="left", padx=6)
            self._craft_tiles[craft["id"]] = tile

    def _select_craft_type(self, craft_id: str) -> None:
        if self.scenario.craft_type != craft_id:
            self.scenario.craft_type = craft_id
            self.scenario.steps = []
        for key, tile in self._craft_tiles.items():
            tile.set_selected(key == craft_id)
        self._app.set_status(t("status.method", name=self._app.catalog.craft_type_name(craft_id)))

    def _build_step_chain(self) -> None:
        self._heading(t("wizard.s3_title"), t("wizard.s3_sub"), t("wizard.s3_help"))
        toolbar = ctk.CTkFrame(self._body, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(
            toolbar,
            text=t("wizard.add_step"),
            width=140,
            command=self._add_step,
            **_primary_btn(),
        ).pack(side="right")
        self._steps_host = ctk.CTkScrollableFrame(self._body, fg_color=BG)
        self._steps_host.pack(fill="both", expand=True)
        enable_mousewheel(self._steps_host)
        self._empty_hint = None
        self._refresh_steps()

    def _refresh_steps(self, scroll_to: str | None = None) -> None:
        host = self._steps_host
        if host is None:
            return
        clear_children(host)
        self._empty_hint = None
        if not self.scenario.steps:
            empty = ctk.CTkFrame(
                host,
                fg_color=SURFACE,
                border_color=BORDER,
                border_width=1,
                corner_radius=RADIUS,
            )
            empty.pack(fill="x", pady=8)
            inner = ctk.CTkFrame(empty, fg_color="transparent")
            inner.pack(anchor="w", padx=22, pady=22)
            self._empty_hint = ctk.CTkLabel(
                inner,
                text=t("wizard.s3_empty"),
                font=ctk.CTkFont(family=FONT, size=16, weight="bold"),
                text_color=TEXT,
            )
            self._empty_hint.pack(anchor="w")
            ctk.CTkLabel(
                inner,
                text=t("wizard.s3_empty_hint"),
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT, size=13),
            ).pack(anchor="w", pady=(6, 12))
            ctk.CTkButton(
                inner,
                text=t("wizard.add_step"),
                width=140,
                command=self._add_step,
                **_primary_btn(),
            ).pack(anchor="w")
            return
        for index, step in enumerate(self.scenario.steps):
            StepCard(host, wizard=self, index=index, step=step).pack(fill="x", pady=6)
        if scroll_to == "end":
            reveal_bottom(host)

    def _add_step(self) -> None:
        catalog = self._app.catalog
        if not catalog:
            self._app.show_toast(t("status.wait"))
            return
        if self._steps_host is None:
            return
        actions = catalog.actions_for(self.scenario.craft_type)
        self.scenario.steps.append(
            CraftStep(
                action_id=actions[0]["id"] if actions else "",
                condition=Condition(kind="missing_mod"),
            )
        )
        self._refresh_steps(scroll_to="end")

    def remove_step(self, index: int) -> None:
        if 0 <= index < len(self.scenario.steps):
            self.scenario.steps.pop(index)
            self._refresh_steps()

    def _build_step_confirm(self) -> None:
        catalog = self._app.catalog
        item_name = catalog.item_type_name(self.scenario.item_type)
        craft_name = catalog.craft_type_name(self.scenario.craft_type)
        if not self.scenario.name or self.scenario.name == t("scenario.default"):
            self.scenario.name = f"{item_type_label(self.scenario.item_type)} · {craft_name}"

        self._heading(t("wizard.s4_title"), "")
        form = ctk.CTkFrame(self._body, fg_color="transparent")
        form.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(form, text=t("wizard.name"), text_color=TEXT_MUTED).pack(anchor="w")
        self._name_entry = ctk.CTkEntry(
            form,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            height=36,
            corner_radius=RADIUS,
        )
        self._name_entry.pack(fill="x", pady=(4, 0))
        self._name_entry.insert(0, self.scenario.name)

        card = ctk.CTkScrollableFrame(
            self._body,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        card.pack(fill="both", expand=True)
        enable_mousewheel(card)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(
            inner,
            text=t("wizard.item", name=item_name),
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            inner,
            text=t("wizard.method", name=craft_name),
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
        ).pack(anchor="w", pady=(4, 12))

        for index, step in enumerate(self.scenario.steps, start=1):
            ctk.CTkLabel(
                inner,
                text=f"{index}. {self._describe_step(step)}",
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT, size=13),
                anchor="w",
                justify="left",
                wraplength=900,
            ).pack(anchor="w", pady=3)

    def _describe_step(self, step: CraftStep) -> str:
        catalog = self._app.catalog
        action = catalog.action_name(step.action_id)
        cond = step.condition
        if cond.kind == "once":
            text = t("desc.once", action=action)
        elif cond.kind == "open_prefix":
            text = t("desc.open_prefix", action=action)
        elif cond.kind == "open_suffix":
            text = t("desc.open_suffix", action=action)
        else:
            parts = []
            for req in cond.mods:
                affix = t("table.prefix_short") if req.generation == "prefix" else t("table.suffix_short")
                tier = f" T{req.tier}" if req.tier else ""
                value = ""
                if req.value_min is not None and req.value_max is not None:
                    value = f" {req.value_min}-{req.value_max}" if req.value_min != req.value_max else f" {req.value_min}"
                need = f" ×{req.need_value()}"
                group = f" [{req.group_key()}×{req.count_value()}]" if req.group_key() else ""
                parts.append(f"[{affix}] {req.name}{tier}{value}{need}{group}")
            mods = ", ".join(parts) or t("desc.mod_none")
            key = "desc.missing_need" if cond.kind == "missing_mod" else "desc.has_need"
            text = t(key, action=action, mods=mods, need=cond.required_total())
        if step.augment_open == "any":
            return f"{text}  ·  {t('desc.augment_any')}"
        if step.augment_open == "prefix":
            return f"{text}  ·  {t('desc.augment_prefix')}"
        if step.augment_open == "suffix":
            return f"{text}  ·  {t('desc.augment_suffix')}"
        return text

    def _save(self) -> None:
        name = self._name_entry.get().strip()
        if not name:
            self._app.show_toast(t("validate.name"), kind="error")
            return
        self.scenario.name = name
        save_scenario(self.scenario)
        self._app.show_toast(t("status.saved", name=name), kind="success")
        self._app.set_status(t("status.saved", name=name))
        self._app.open_scenarios()
