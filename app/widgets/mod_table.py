from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from app.data.models import ModRequirement
from app.i18n import t
from app.theme import BORDER, FONT, RADIUS, SURFACE, TEXT, TEXT_MUTED
from app.widgets.scroll import keep_yview
from app.widgets.search_select import SearchSelect
from app.widgets.select import Select, affix_chip
from app.widgets.tooltip import Tooltip, field_label


class ModTable(ctk.CTkFrame):
    def __init__(
        self,
        master,
        catalog,
        item_class: str,
        requirements: list[ModRequirement],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._catalog = catalog
        self._item_class = item_class
        self._requirements = requirements
        self._on_change = on_change
        self._redrawing = False
        self._rows: dict[int, dict[str, object]] = {}
        for req in self._requirements:
            self._catalog.sync_requirement(req, item_class)

        picker_row = ctk.CTkFrame(self, fg_color="transparent")
        picker_row.pack(fill="x")
        self._picker = SearchSelect(
            picker_row,
            items=self._mod_choices(),
            on_select=self._add_mod,
            placeholder=t("search.mod"),
            list_height=200,
            badge_for=self._badge_for,
        )
        self._picker.pack(fill="x", pady=(0, 8))

        self._table = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        self._table.pack(fill="x")
        self._table.grid_columnconfigure(0, weight=4)
        self._table.grid_columnconfigure(1, weight=2)
        self._table.grid_columnconfigure(2, weight=1)
        self._table.grid_columnconfigure(3, weight=1)
        self._table.grid_columnconfigure(4, weight=1)
        self._table.grid_columnconfigure(5, weight=1)
        self._table.grid_columnconfigure(6, weight=0)

        self._odds = ctk.CTkFrame(
            self,
            fg_color=SURFACE,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
        )
        self._odds.pack(fill="x", pady=(8, 0))
        self._redraw()

    def _mod_choices(self) -> list[tuple[str, str]]:
        chosen = {row.mod_type_id for row in self._requirements}
        items = []
        for row in self._catalog.mod_types_for(self._item_class):
            if row["id"] in chosen:
                continue
            items.append((row["id"], row["name"]))
        return items

    def _badge_for(self, mod_type_id: str) -> str | None:
        row = self._catalog.mod_type(mod_type_id)
        generation = (row or {}).get("generation")
        if generation in {"prefix", "suffix"}:
            return generation
        return None

    def _add_mod(self, mod_type_id: str) -> None:
        row = self._catalog.mod_type(mod_type_id)
        if not row:
            return
        tiers = self._catalog.tiers_for(mod_type_id, self._item_class)
        best = tiers[0] if tiers else {}
        self._requirements.append(
            ModRequirement(
                mod_type_id=mod_type_id,
                generation=row.get("generation", "prefix"),
                name=row.get("name", mod_type_id),
                tier=best.get("tier"),
                value_min=best.get("min"),
                value_max=best.get("max"),
                weight=best.get("weight"),
                need=1,
            )
        )
        self._picker.set_items(self._mod_choices())
        self._picker.set_value(None)
        self._redraw()
        if self._on_change:
            self._on_change()

    def _redraw(self) -> None:
        if self._redrawing:
            return
        self._redrawing = True
        keep_yview(self)
        self._rows.clear()
        try:
            for child in self._table.winfo_children():
                child.destroy()
            headers = [
                (t("table.mod"), None),
                (t("table.value"), None),
                (t("table.tier"), None),
                (t("table.need"), t("table.need_help")),
                (t("table.group"), t("table.group_help")),
                (t("table.count"), t("table.count_help")),
                ("", None),
            ]
            for column, (title, help_text) in enumerate(headers):
                if not title:
                    continue
                field_label(
                    self._table,
                    title,
                    help_text,
                    font=ctk.CTkFont(family=FONT, size=11),
                ).grid(row=0, column=column, sticky="w", padx=8, pady=(8, 4))

            if not self._requirements:
                ctk.CTkLabel(
                    self._table,
                    text=t("table.empty"),
                    text_color=TEXT_MUTED,
                    font=ctk.CTkFont(family=FONT, size=12),
                    anchor="w",
                ).grid(row=1, column=0, columnspan=7, sticky="w", padx=8, pady=(0, 10))
                self._draw_odds()
                return

            for index, req in enumerate(self._requirements, start=1):
                self._draw_row(index, req)
            self._draw_odds()
        finally:
            self._redrawing = False

    def _draw_row(self, index: int, req: ModRequirement) -> None:
        name_cell = ctk.CTkFrame(self._table, fg_color="transparent")
        name_cell.grid(row=index, column=0, sticky="ew", padx=8, pady=4)
        prefix = req.generation == "prefix"
        affix_chip(name_cell, "prefix" if prefix else "suffix").pack(side="left")
        Tooltip(name_cell.winfo_children()[-1], t("wizard.affix"))
        name = ctk.CTkLabel(
            name_cell,
            text=req.name,
            text_color=TEXT,
            font=ctk.CTkFont(family=FONT, size=12),
            anchor="w",
            wraplength=280,
        )
        name.pack(side="left", padx=(8, 0), fill="x", expand=True)

        value = _format_value(req.value_min, req.value_max)
        value_entry = ctk.CTkEntry(
            self._table,
            width=90,
            height=28,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=RADIUS,
        )
        value_entry.insert(0, value)
        value_entry.grid(row=index, column=1, sticky="ew", padx=4, pady=4)
        value_entry.bind("<FocusOut>", lambda _e, row=req, widget=value_entry: self._on_value(row, widget))

        items: list[tuple[str, str]] = [("any", t("table.any_tier"))]
        for tier in self._catalog.tiers_for(req.mod_type_id, self._item_class):
            label = f"T{tier['tier']}"
            items.append((str(tier["tier"]), label))
        current = str(req.tier) if req.tier is not None else "any"
        menu = Select(
            self._table,
            items=items,
            value=current if current in {item[0] for item in items} else "any",
            width=86,
            height=28,
            command=lambda value, row=req: self._on_tier(row, value),
        )
        menu.grid(row=index, column=2, sticky="ew", padx=4, pady=4)

        need_entry = ctk.CTkEntry(
            self._table,
            width=48,
            height=28,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=RADIUS,
            justify="center",
        )
        need_entry.insert(0, str(req.need_value()))
        need_entry.grid(row=index, column=3, padx=4, pady=4)
        need_entry.bind("<FocusOut>", lambda _e, row=req, widget=need_entry: self._on_need(row, widget))
        need_entry.bind("<Return>", lambda _e, row=req, widget=need_entry: self._on_need(row, widget))

        group_entry = ctk.CTkEntry(
            self._table,
            width=48,
            height=28,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=RADIUS,
            justify="center",
        )
        group_entry.insert(0, req.group_key())
        group_entry.grid(row=index, column=4, padx=4, pady=4)
        group_entry.bind("<FocusOut>", lambda _e, row=req, widget=group_entry: self._on_group(row, widget))
        group_entry.bind("<Return>", lambda _e, row=req, widget=group_entry: self._on_group(row, widget))

        count_entry = ctk.CTkEntry(
            self._table,
            width=48,
            height=28,
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            corner_radius=RADIUS,
            justify="center",
        )
        if req.group_key():
            count_entry.insert(0, str(req.count_value()))
        else:
            count_entry.insert(0, "—")
            count_entry.configure(state="disabled")
        count_entry.grid(row=index, column=5, padx=4, pady=4)
        count_entry.bind("<FocusOut>", lambda _e, row=req, widget=count_entry: self._on_count(row, widget))
        count_entry.bind("<Return>", lambda _e, row=req, widget=count_entry: self._on_count(row, widget))

        ctk.CTkButton(
            self._table,
            text="×",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=BORDER,
            text_color=TEXT_MUTED,
            command=lambda row=req: self._remove(row),
        ).grid(row=index, column=6, padx=4, pady=4)

        self._rows[id(req)] = {
            "value": value_entry,
            "count": count_entry,
        }

    def _draw_odds(self) -> None:
        for child in self._odds.winfo_children():
            child.destroy()
        inner = ctk.CTkFrame(self._odds, fg_color="transparent")
        inner.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(
            inner,
            text=t("table.odds"),
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        if not self._requirements:
            ctk.CTkLabel(
                inner,
                text=t("table.odds_empty"),
                text_color=TEXT_MUTED,
                font=ctk.CTkFont(family=FONT, size=12),
                anchor="w",
            ).pack(fill="x")
            return
        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, weight=3)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)
        grid.grid_columnconfigure(3, weight=1)
        headers = (
            (t("table.mod"), None),
            (t("table.weight"), None),
            (t("table.chance"), t("table.chance_help")),
        )
        for column, (title, help_text) in enumerate(headers):
            field_label(
                grid,
                title,
                help_text,
                font=ctk.CTkFont(family=FONT, size=11),
            ).grid(row=0, column=column, sticky="w", padx=4, pady=(0, 4))
        pools = {
            "prefix": self._catalog.generation_pool_weight(self._item_class, "prefix"),
            "suffix": self._catalog.generation_pool_weight(self._item_class, "suffix"),
        }
        for index, req in enumerate(self._requirements, start=1):
            weight = self._catalog.requirement_weight(req, self._item_class)
            pool = pools.get(req.generation) or 0
            chance = (100.0 * weight / pool) if pool and weight else 0.0
            name_cell = ctk.CTkFrame(grid, fg_color="transparent")
            name_cell.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            affix_chip(name_cell, req.generation if req.generation in {"prefix", "suffix"} else "prefix").pack(side="left")
            ctk.CTkLabel(
                name_cell,
                text=req.name,
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT, size=12),
                anchor="w",
            ).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(
                grid,
                text=str(weight) if weight else "—",
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT, size=12),
                anchor="w",
            ).grid(row=index, column=1, sticky="w", padx=4, pady=2)
            ctk.CTkLabel(
                grid,
                text=f"{chance:.1f}%" if chance else "—",
                text_color=TEXT,
                font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
                anchor="w",
            ).grid(row=index, column=2, sticky="w", padx=4, pady=2)

    def _alive(self, widget) -> bool:
        try:
            return bool(widget.winfo_exists())
        except Exception:
            return False

    def _set_entry(self, widget: ctk.CTkEntry, text: str, disabled: bool = False) -> None:
        if not self._alive(widget):
            return
        widget.configure(state="normal")
        if widget.get() != text:
            widget.delete(0, "end")
            widget.insert(0, text)
        widget.configure(state="disabled" if disabled else "normal")

    def _apply_count_widget(self, req: ModRequirement) -> None:
        entry = self._rows.get(id(req), {}).get("count")
        if not isinstance(entry, ctk.CTkEntry):
            return
        if req.group_key():
            self._set_entry(entry, str(req.count_value()), disabled=False)
        else:
            self._set_entry(entry, "—", disabled=True)

    def _sync_group_counts(self, key: str) -> None:
        if not key:
            return
        rows = [row for row in self._requirements if row.group_key() == key]
        if not rows:
            return
        count = rows[0].count_value()
        for row in rows:
            row.count = count
            self._apply_count_widget(row)

    def _on_tier(self, req: ModRequirement, value: str) -> None:
        if self._redrawing:
            return
        if value == "any":
            req.tier = None
            req.value_min = None
            req.value_max = None
            req.weight = None
        else:
            req.tier = int(value)
            tier = self._catalog.mod_tier(req.mod_type_id, req.tier, self._item_class)
            if tier:
                req.value_min = tier.get("min")
                req.value_max = tier.get("max")
                req.weight = tier.get("weight")
        widgets = self._rows.get(id(req), {})
        value_entry = widgets.get("value")
        if isinstance(value_entry, ctk.CTkEntry):
            self._set_entry(value_entry, _format_value(req.value_min, req.value_max))
        self._draw_odds()
        if self._on_change:
            self._on_change()

    def _on_need(self, req: ModRequirement, widget: ctk.CTkEntry) -> None:
        if self._redrawing or not self._alive(widget):
            return
        try:
            req.need = max(1, int(widget.get().strip() or "1"))
        except ValueError:
            req.need = 1
        self._set_entry(widget, str(req.need_value()))
        if self._on_change:
            self._on_change()

    def _on_group(self, req: ModRequirement, widget: ctk.CTkEntry) -> None:
        if self._redrawing or not self._alive(widget):
            return
        old = req.group_key()
        key = widget.get().strip()
        if key == old:
            return
        req.group = key
        if key:
            for other in self._requirements:
                if other is not req and other.group_key() == key:
                    req.count = other.count_value()
                    break
            else:
                req.count = max(1, int(req.count or 1))
        self._set_entry(widget, key)
        self._apply_count_widget(req)
        self._sync_group_counts(key or old)
        if self._on_change:
            self._on_change()

    def _on_count(self, req: ModRequirement, widget: ctk.CTkEntry) -> None:
        if self._redrawing or not self._alive(widget) or not req.group_key():
            return
        try:
            req.count = max(1, int(widget.get().strip() or "1"))
        except ValueError:
            req.count = 1
        self._sync_group_counts(req.group_key())
        if self._on_change:
            self._on_change()

    def _on_value(self, req: ModRequirement, widget: ctk.CTkEntry) -> None:
        if self._redrawing or not self._alive(widget):
            return
        raw = widget.get().strip().replace(" ", "")
        if not raw:
            req.value_min = None
            req.value_max = None
            return
        if "-" in raw:
            left, right = raw.split("-", 1)
            try:
                req.value_min = int(left)
                req.value_max = int(right)
            except ValueError:
                return
        else:
            try:
                number = int(raw)
            except ValueError:
                return
            req.value_min = number
            req.value_max = number
        if self._on_change:
            self._on_change()

    def _remove(self, req: ModRequirement) -> None:
        if req in self._requirements:
            self._requirements.remove(req)
        self._picker.set_items(self._mod_choices())
        self._redraw()
        if self._on_change:
            self._on_change()


def _format_value(low: int | None, high: int | None) -> str:
    if low is None and high is None:
        return ""
    if low is None:
        return str(high)
    if high is None or low == high:
        return str(low)
    return f"{low}-{high}"
