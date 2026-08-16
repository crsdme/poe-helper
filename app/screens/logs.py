from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from app.craft_log import (
    CraftSession,
    delete_session,
    grouped_sessions,
    matching_lines,
)
from app.i18n import t
from app.theme import BG, BORDER, DANGER, FONT, RADIUS, SELECTED, SURFACE, TEXT, TEXT_MUTED
from app.widgets.scroll import enable_mousewheel

if TYPE_CHECKING:
    from app.main_window import MainWindow


def _outline() -> dict:
    return {
        "fg_color": "transparent",
        "border_color": BORDER,
        "border_width": 1,
        "text_color": TEXT,
        "hover_color": SELECTED,
        "corner_radius": RADIUS,
    }


class LogsScreen(ctk.CTkFrame):
    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color=BG)
        self._app = app
        self._selected_id: str | None = None
        self._sessions: dict[str, CraftSession] = {}
        self._list_key: tuple | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=32, pady=(24, 8))
        ctk.CTkButton(top, text=t("nav.back"), width=88, command=app.show_home, **_outline()).pack(side="left")
        ctk.CTkLabel(
            top,
            text=t("logs.title"),
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=TEXT,
        ).pack(side="left", padx=14)

        ctk.CTkLabel(
            self,
            text=t("logs.hint"),
            text_color=TEXT_MUTED,
            font=ctk.CTkFont(family=FONT, size=13),
            wraplength=980,
            justify="left",
        ).pack(anchor="w", padx=32, pady=(0, 8))

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", padx=32, pady=(0, 8))
        self._search = ctk.CTkEntry(
            tools,
            placeholder_text=t("logs.search"),
            fg_color=SURFACE,
            border_color=BORDER,
            text_color=TEXT,
            height=34,
            corner_radius=RADIUS,
        )
        self._search.pack(side="left", fill="x", expand=True)
        self._search.bind("<KeyRelease>", lambda _e: self._redraw_list())
        ctk.CTkButton(
            tools,
            text=t("logs.delete"),
            width=120,
            command=self._delete_selected,
            fg_color="transparent",
            border_color=DANGER,
            border_width=1,
            text_color=DANGER,
            hover_color="#3f1d1d",
            corner_radius=RADIUS,
        ).pack(side="right", padx=(10, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self._list = ctk.CTkScrollableFrame(body, fg_color=BG)
        self._list.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        enable_mousewheel(self._list)

        right = ctk.CTkFrame(body, fg_color=SURFACE, border_color=BORDER, border_width=1, corner_radius=RADIUS)
        right.grid(row=0, column=1, sticky="nsew")
        inner = ctk.CTkFrame(right, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=14, pady=14)
        self._heading = ctk.CTkLabel(
            inner,
            text=t("logs.pick"),
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
            text_color=TEXT,
            anchor="w",
            wraplength=520,
            justify="left",
        )
        self._heading.pack(fill="x", pady=(0, 8))
        self._body = ctk.CTkTextbox(
            inner,
            fg_color=BG,
            text_color=TEXT,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
        )
        self._body.pack(fill="both", expand=True)
        self._body.configure(state="disabled")
        self._redraw_list()
        self.after(1500, self._poll)

    def _query(self) -> str:
        return self._search.get().strip()

    def _groups_key(self, groups: list[tuple[str, list[CraftSession]]]) -> tuple:
        return tuple(
            (session.id, session.status, len(session.lines), session.name)
            for _, rows in groups
            for session in rows
        )

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        groups = grouped_sessions(self._query())
        key = self._groups_key(groups)
        if key != self._list_key:
            self._redraw_list(groups)
        self.after(1500, self._poll)

    def _clear_detail(self) -> None:
        self._heading.configure(text=t("logs.pick"))
        self._body.configure(state="normal")
        self._body.delete("1.0", "end")
        self._body.configure(state="disabled")

    def _redraw_list(self, groups: list[tuple[str, list[CraftSession]]] | None = None) -> None:
        for child in self._list.winfo_children():
            child.destroy()
        if groups is None:
            groups = grouped_sessions(self._query())
        self._list_key = self._groups_key(groups)
        self._sessions = {session.id: session for _, rows in groups for session in rows}
        if not groups:
            empty = t("logs.no_results") if self._query() else t("logs.empty")
            ctk.CTkLabel(self._list, text=empty, text_color=TEXT_MUTED).pack(anchor="w", pady=8)
            self._clear_detail()
            return
        for name, rows in groups:
            ctk.CTkLabel(
                self._list,
                text=name,
                font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                text_color=TEXT,
                anchor="w",
            ).pack(fill="x", pady=(10, 4))
            for session in rows:
                selected = session.id == self._selected_id
                button = ctk.CTkButton(
                    self._list,
                    text=t(
                        "logs.session",
                        when=session.when(),
                        status=t(f"logs.status_{session.status}", default=session.status),
                        n=len(session.lines),
                    ),
                    anchor="w",
                    fg_color=SELECTED if selected else SURFACE,
                    hover_color=SELECTED,
                    border_color=BORDER,
                    border_width=1,
                    text_color=TEXT,
                    corner_radius=RADIUS,
                    height=34,
                    command=lambda sid=session.id: self._open(sid),
                )
                button.pack(fill="x", pady=2)
        if self._selected_id and self._selected_id in self._sessions:
            self._show(self._sessions[self._selected_id])
        else:
            self._clear_detail()

    def _open(self, session_id: str) -> None:
        self._selected_id = session_id
        self._redraw_list()

    def _show(self, session: CraftSession) -> None:
        status = t(f"logs.status_{session.status}", default=session.status)
        self._heading.configure(text=f"{session.name}  ·  {session.when()}  ·  {status}")
        lines = matching_lines(session, self._query())
        self._body.configure(state="normal")
        self._body.delete("1.0", "end")
        self._body.insert("end", "\n".join(lines) if lines else t("logs.no_hits"))
        if session.status == "running":
            self._body.see("end")
        self._body.configure(state="disabled")

    def _delete_selected(self) -> None:
        if not self._selected_id:
            return
        delete_session(self._selected_id)
        self._selected_id = None
        self._redraw_list()
