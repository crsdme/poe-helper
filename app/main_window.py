from __future__ import annotations

import json
import logging
import queue
import threading

import customtkinter as ctk

from app import __version__
from app.config import load_config
from app.craft_runner import CraftRunner, validate_ready
from app.data.catalog import GameCatalog
from app.data.fetcher import ensure_catalog
from app.data.models import CraftScenario
from app.i18n import LANGUAGES, language, set_language, t
from app.input_win import HotkeyListener, allow_foreground, focus_game, release_modifiers
from app.settings import save_settings
from app.screens.home import HomeScreen
from app.screens.heist import HeistScreen
from app.screens.logs import LogsScreen
from app.screens.reveal import RevealScreen
from app.screens.run import CraftHud, RunScreen
from app.screens.scenarios import ScenariosScreen
from app.screens.settings import SettingsScreen
from app.screens.wizard import WizardScreen
from app.debug import dbg
from app.theme import (
    ACCENT,
    BG,
    BORDER,
    DANGER,
    FONT,
    HEADER,
    RADIUS,
    RING,
    SUCCESS,
    TEXT,
    TEXT_MUTED,
)
from app.paths import app_icon_ico, app_icon_png
from app.widgets.select import Select
from app.widgets.toast import ToastHost
from app.widgets.tooltip import Tooltip

WINDOW_SIZE = "1100x740"
WINDOW_MIN_SIZE = (960, 640)
logger = logging.getLogger("poe_helper")


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(t("app.name"))
        self._apply_app_icon()
        self.after(250, self._apply_app_icon)
        self.geometry(WINDOW_SIZE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.configure(fg_color=BG)
        self.catalog: GameCatalog | None = None
        self._current = ""
        self._loading = False
        self.selected_scenario_id: str | None = load_config().last_scenario_id or None
        self._runner: CraftRunner | None = None
        self._hotkeys = HotkeyListener()
        self._hud: CraftHud | None = None
        self._run_view: RunScreen | None = None
        self._heist_view: HeistScreen | None = None
        self._heist_thread: threading.Thread | None = None
        self._heist_stop = threading.Event()
        self._reveal_view: RevealScreen | None = None
        self._reveal_thread: threading.Thread | None = None
        self._reveal_stop = threading.Event()
        self._craft_lines: list[str] = []
        self._craft_q: queue.Queue[tuple[str, str]] = queue.Queue()
        self._center_on_screen()
        self._build_shell()
        self._toasts = ToastHost(self)
        self.show_home()
        self.reload_catalog(force=False)
        self.after(400, self.refresh_hotkeys)
        self.after(40, self._poll_craft)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _center_on_screen(self) -> None:
        width, height = (int(part) for part in WINDOW_SIZE.split("x"))
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _apply_app_icon(self) -> None:
        ico = app_icon_ico()
        if not ico.is_file():
            return
        try:
            self.iconbitmap(str(ico))
        except Exception:
            pass

    def _brand_mark(self, parent):
        png = app_icon_png()
        if png.is_file():
            from PIL import Image

            src = Image.open(png).convert("RGBA")
            self._brand_icon = ctk.CTkImage(light_image=src, dark_image=src, size=(36, 36))
            return ctk.CTkLabel(parent, image=self._brand_icon, text="", width=36, height=36)
        mark = ctk.CTkFrame(
            parent,
            width=36,
            height=36,
            corner_radius=10,
            fg_color=ACCENT,
            border_color=RING,
            border_width=1,
        )
        mark.pack_propagate(False)
        ctk.CTkLabel(
            mark,
            text="H",
            font=ctk.CTkFont(family=FONT, size=16, weight="bold"),
            text_color=TEXT,
        ).place(relx=0.5, rely=0.5, anchor="center")
        return mark

    def _build_shell(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color=HEADER, corner_radius=0, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        header.grid_rowconfigure(0, weight=1)

        brand = ctk.CTkFrame(header, fg_color="transparent", cursor="hand2")
        brand.grid(row=0, column=0, sticky="w", padx=16)
        mark = self._brand_mark(brand)
        mark.pack(side="left")
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left", padx=(10, 0))
        self._title_label = ctk.CTkLabel(
            titles,
            text=t("app.name"),
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=TEXT,
            anchor="w",
        )
        self._title_label.pack(anchor="w")
        self._subtitle_label = ctk.CTkLabel(
            titles,
            text=t("app.subtitle"),
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=TEXT_MUTED,
            anchor="w",
        )
        self._subtitle_label.pack(anchor="w")
        for widget in (brand, mark, titles, self._title_label, self._subtitle_label):
            widget.bind("<Button-1>", lambda _e: self.show_home(), add="+")
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass

        meta = ctk.CTkFrame(
            header,
            fg_color=ACCENT,
            border_color=BORDER,
            border_width=1,
            corner_radius=RADIUS,
            height=28,
        )
        meta.grid(row=0, column=1, sticky="e", padx=(0, 10))
        inner = ctk.CTkFrame(meta, fg_color="transparent")
        inner.pack(padx=10, pady=4)
        self._meta_dot = ctk.CTkLabel(
            inner,
            text="●",
            font=ctk.CTkFont(family=FONT, size=9),
            text_color=TEXT_MUTED,
            width=12,
        )
        self._meta_dot.pack(side="left")
        self._meta_label = ctk.CTkLabel(
            inner,
            text=t("status.loading"),
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=TEXT_MUTED,
        )
        self._meta_label.pack(side="left", padx=(4, 0))

        self._lang_menu = Select(
            header,
            items=list(LANGUAGES),
            value=language(),
            command=self._on_language,
            width=184,
            height=34,
            show_code=True,
            menu_width=200,
        )
        self._lang_menu.grid(row=0, column=2, sticky="e", padx=(0, 16))
        self._lang_tip = Tooltip(self._lang_menu, t("header.language"))

        ctk.CTkFrame(self, fg_color=BORDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew")

        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        bar = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, height=32)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(bar, fg_color=BORDER, height=1, corner_radius=0).place(relx=0, rely=0, relwidth=1)
        self._status = ctk.CTkLabel(
            bar,
            text=t("status.loading"),
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=TEXT_MUTED,
        )
        self._status.grid(row=0, column=0, sticky="w", padx=16, pady=(2, 0))
        ctk.CTkLabel(
            bar,
            text=f"v{__version__}",
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=TEXT_MUTED,
        ).grid(row=0, column=2, sticky="e", padx=16, pady=(2, 0))
        self.title(t("app.name"))

    def _on_language(self, code: str) -> None:
        if code == language():
            return
        set_language(code)
        save_settings({"language": code})
        self._apply_shell_texts()
        if self._current == "wizard":
            for child in self.content.winfo_children():
                if isinstance(child, WizardScreen):
                    child._render()
                    return
        elif self._current == "scenarios":
            self.open_scenarios()
        elif self._current == "settings":
            self.open_settings()
        elif self._current == "run":
            self.open_run()
        else:
            self.show_home()

    def _apply_shell_texts(self) -> None:
        self.title(t("app.name"))
        self._title_label.configure(text=t("app.name"))
        self._subtitle_label.configure(text=t("app.subtitle"))
        self._lang_tip.set_text(t("header.language"))
        self._refresh_header_meta()
        if self.catalog:
            self.set_status(t("status.ready", patch=self.catalog.patch, mods=len(self.catalog.mod_types)))
        else:
            self.set_status(t("status.loading"))

    def set_status(self, message: str) -> None:
        self._status.configure(text=message)
        self._refresh_header_meta()

    def _refresh_header_meta(self) -> None:
        if self.catalog:
            self._meta_dot.configure(text_color=SUCCESS)
            self._meta_label.configure(text=self.catalog.patch)
            return
        if self._loading:
            self._meta_dot.configure(text_color=TEXT_MUTED)
            self._meta_label.configure(text=t("status.loading"))
            return
        self._meta_dot.configure(text_color=DANGER)
        self._meta_label.configure(text=t("header.error"))

    def show_toast(self, message: str, kind: str = "error", ms: int = 4500) -> None:
        self._toasts.show(message, kind, ms)

    def _set_screen(self, name: str, factory) -> None:
        self._run_view = None
        self._heist_view = None
        self._reveal_view = None
        for child in self.content.winfo_children():
            child.destroy()
        self._current = name
        widget = factory(self.content)
        widget.grid(row=0, column=0, sticky="nsew")

    def show_home(self) -> None:
        self._set_screen("home", lambda parent: HomeScreen(parent, self))

    def open_wizard(self, scenario: CraftScenario | None = None) -> None:
        if not self.catalog:
            self.set_status(t("status.wait"))
            return
        self._set_screen("wizard", lambda parent: WizardScreen(parent, self, scenario))

    def open_scenarios(self) -> None:
        self._set_screen("scenarios", lambda parent: ScenariosScreen(parent, self))

    def open_settings(self) -> None:
        self._set_screen("settings", lambda parent: SettingsScreen(parent, self))

    def open_run(self, scenario: CraftScenario | None = None, auto_start: bool = False, prefer_chain: bool = False) -> None:
        if not self.catalog:
            self.set_status(t("status.wait"))
            return
        if scenario is not None:
            self.selected_scenario_id = scenario.id
            save_settings({"last_scenario_id": scenario.id})
        self._set_screen("run", lambda parent: RunScreen(parent, self, prefer_chain=prefer_chain))
        if auto_start and scenario is not None:
            self.after(50, lambda row=scenario: self.start_craft(row))

    def open_logs(self) -> None:
        self._set_screen("logs", lambda parent: LogsScreen(parent, self))

    def open_heist(self) -> None:
        self._set_screen("heist", lambda parent: HeistScreen(parent, self))

    def open_reveal(self) -> None:
        self._set_screen("reveal", lambda parent: RevealScreen(parent, self))

    def set_run_view(self, view: RunScreen | None) -> None:
        self._run_view = view

    def set_heist_view(self, view: HeistScreen | None) -> None:
        self._heist_view = view

    def set_reveal_view(self, view: RevealScreen | None) -> None:
        self._reveal_view = view

    def refresh_hotkeys(self) -> None:
        config = load_config()
        binds = {
            config.hotkey_start: self._os_start_hotkey,
            config.hotkey_stop: self._os_stop_hotkey,
        }
        chain = (config.hotkey_chain or "").strip()
        if chain and chain not in binds:
            binds[chain] = self._os_chain_hotkey
        try:
            from app.heist.engine import load_heist_config

            heist = load_heist_config()
            start = str(heist.get("hotkey") or "f9").strip().upper()
            stop = str(heist.get("exit_hotkey") or "f10").strip().upper()
            if start and start not in binds:
                binds[start] = self._os_heist_toggle
            if stop and stop not in binds:
                binds[stop] = self._os_heist_stop
        except Exception:
            pass
        try:
            from app.heist.reveal import load_reveal_config

            reveal = load_reveal_config()
            start = str(reveal.get("hotkey") or "f11").strip().upper()
            stop = str(reveal.get("exit_hotkey") or "f12").strip().upper()
            if start and start not in binds:
                binds[start] = self._os_reveal_toggle
            if stop and stop not in binds:
                binds[stop] = self._os_reveal_stop
        except Exception:
            pass
        self._hotkeys.start(binds, poll={"ESCAPE": self._os_stop_hotkey})

    def _os_start_hotkey(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_start)

    def _os_chain_hotkey(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_chain)

    def _os_stop_hotkey(self) -> None:
        self.after(0, self._stop_all)

    def _os_heist_toggle(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_heist_toggle)

    def _os_heist_stop(self) -> None:
        self.after(0, self.stop_heist)

    def _os_reveal_toggle(self) -> None:
        allow_foreground()
        self.after(0, self._hotkey_reveal_toggle)

    def _os_reveal_stop(self) -> None:
        self.after(0, self.stop_reveal)

    def _stop_all(self) -> None:
        self.stop_heist()
        self.stop_reveal()
        self.stop_craft()

    def _scenario_for_hotkey(self) -> CraftScenario | None:
        from app.data.catalog import list_scenarios

        view = self._run_view
        if view and view._selected:
            return view._selected
        scenarios = list_scenarios()
        if not scenarios:
            return None
        chosen = next((row for row in scenarios if row.id == self.selected_scenario_id), None)
        return chosen or scenarios[0]

    def _hotkey_start(self) -> None:
        if self._runner and self._runner.paused:
            self._runner.resume()
            return
        if self._current == "settings":
            return
        if self._runner and self._runner.running:
            return
        chosen = self._scenario_for_hotkey()
        if not chosen:
            self.show_toast(t("run.need_scenario"))
            return
        self.start_craft(chosen)

    def _hotkey_chain(self) -> None:
        if self._runner and self._runner.paused:
            self._runner.resume()
            return
        if self._current == "settings":
            return
        if self._runner and self._runner.running:
            return
        chosen = self._scenario_for_hotkey()
        if not chosen:
            self.show_toast(t("run.need_scenario"))
            return
        self.start_craft(chosen, chain=True)

    def start_craft(self, scenario: CraftScenario, chain: bool = False) -> None:
        dbg(
            f"start_craft name={scenario.name!r} current={self._current} "
            f"view={self._run_view is not None} catalog={self.catalog is not None} chain={chain}"
        )
        if self.heist_running() or self.reveal_running():
            self.show_toast(t("heist.busy_craft"))
            return
        if not self.catalog:
            dbg("start_craft abort: no catalog")
            self.show_toast(t("status.wait"))
            return
        if self._runner and self._runner.paused:
            dbg("start_craft resume paused")
            self._runner.resume()
            return
        if self._runner and self._runner.running:
            dbg("start_craft abort: already running")
            return
        error = validate_ready(scenario, load_config(), chain=chain)
        if error:
            dbg(f"start_craft abort: validate {error}")
            self.show_toast(t(error))
            return
        self.selected_scenario_id = scenario.id
        save_settings({"last_scenario_id": scenario.id})
        self._runner = CraftRunner(self.catalog, lambda kind, payload: self._craft_q.put((kind, payload)))
        config = load_config()
        self._close_hud()
        self._hud = CraftHud(self, config.hotkey_stop)
        dbg(f"start_craft hud exists={bool(self._hud.winfo_exists())}")
        self._hud.set_step(scenario.name)
        self._hud.set_note(t("run.log.start"))
        self._write_craft_log(t("run.log.start"))
        self.update_idletasks()
        allow_foreground()
        focused = focus_game()
        dbg(f"start_craft focus_game={focused}")
        error = self._runner.start(scenario, chain=chain)
        dbg(f"start_craft runner.start error={error!r} running={self._runner.running}")
        if error:
            self._close_hud()
            self.show_toast(t(error))
            self._write_craft_log(t(error))

    def _write_craft_log(self, line: str) -> None:
        dbg(f"ui_log view={self._run_view is not None} line={line!r}")
        if not line:
            return
        self._craft_lines.append(line)
        if self._hud and self._hud.winfo_exists():
            self._hud.set_note(line)
        view = self._run_view
        if view is None:
            dbg("ui_log skip: run_view is None")
            return
        try:
            if view.winfo_exists():
                view.append_log(line)
            else:
                dbg("ui_log skip: run_view destroyed")
        except Exception:
            from app.debug import dbg_exc

            dbg_exc("ui_log append failed")

    def stop_craft(self) -> None:
        running = bool(self._runner and self._runner.running)
        if self._runner:
            self._runner.stop()
        if running:
            release_modifiers(shift=True)
        if self._hud and self._hud.winfo_exists():
            data = self._runner.snapshot("stopped") if self._runner else {"status": "stopped"}
            self._hud.mark_final(data)

    def heist_running(self) -> bool:
        return bool(self._heist_thread and self._heist_thread.is_alive())

    def _open_job_hud(self, title: str, stop_key: str) -> None:
        self._close_hud()
        self._hud = CraftHud(self, stop_key, mode="job")
        self._hud.set_step(title)
        self._hud.set_note(t("heist.ready"))
        self._hud.set_hint(t("run.hud_stop", key=stop_key))

    def _keep_job_hud(self) -> None:
        hud = self._hud
        if hud is None:
            return
        try:
            if not hud.winfo_exists():
                return
            hud.deiconify()
            hud.attributes("-topmost", True)
            hud.lift()
            hud._ready()
        except Exception:
            pass

    def _job_hud(self, progress: str, note: str = "") -> None:
        def _do() -> None:
            hud = self._hud
            if hud and hud.winfo_exists():
                hud.set_progress(t("heist.hud_cell", n=progress))
                if note:
                    hud.set_note(note)

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.after(0, _do)

    def _finish_job_hud(self, status: str, note: str = "") -> None:
        hud = self._hud
        if hud and hud.winfo_exists():
            hud.mark_final({"status": status, "item": note})
            self.after(2500, lambda current=hud: self._close_hud_if(current))

    def _hotkey_heist_toggle(self) -> None:
        if self.heist_running():
            self.stop_heist()
            return
        if self._current != "heist":
            self.open_heist()
        self.start_heist()

    def start_heist(self) -> None:
        if self._runner and self._runner.running:
            self.show_toast(t("heist.busy_craft"))
            return
        if self.reveal_running():
            self.show_toast(t("reveal.busy"))
            return
        if self.heist_running():
            return
        try:
            import cv2  # noqa: F401
            import mss  # noqa: F401
        except ImportError:
            self.show_toast(t("heist.missing_cv"))
            return
        from app.heist.engine import assign_contracts, load_heist_config
        from app.widgets.select import close_open

        if self._current != "heist":
            self.open_heist()
        cfg = load_heist_config()
        stop_key = str(cfg.get("exit_hotkey") or "f10").strip().upper()
        self._heist_stop.clear()
        view = self._heist_view
        if view:
            view.set_running(True)
            view.append_log("=== START ===")
        close_open()
        self._open_job_hud(t("heist.title"), stop_key)
        self.iconify()
        self.after(80, self._keep_job_hud)
        self.after(250, self._keep_job_hud)

        def worker() -> None:
            try:
                self._heist_stop.wait(0.35)
                focus_game()
                assign_contracts(
                    cfg,
                    stop_event=self._heist_stop,
                    on_log=self._heist_log,
                    on_hud=self._job_hud,
                )
            except Exception as exc:
                message = t("heist.error", exc=exc)
                self.after(0, lambda text=message: self._heist_log(text))
            finally:
                self.after(0, self._heist_done)

        self._heist_thread = threading.Thread(target=worker, name="heist-assign", daemon=True)
        self._heist_thread.start()

    def stop_heist(self) -> None:
        if not self.heist_running() and not self._heist_stop.is_set():
            return
        self._heist_stop.set()
        view = self._heist_view
        if view and view.winfo_exists():
            view.append_log(t("heist.stop"))
        if self._hud and self._hud.winfo_exists():
            self._hud.mark_final({"status": "stopped"})
        try:
            self.deiconify()
        except Exception:
            pass

    def _heist_log(self, line: str) -> None:
        def _do() -> None:
            view = self._heist_view
            if view and view.winfo_exists():
                view.append_log(str(line))
            if self._hud and self._hud.winfo_exists():
                self._hud.set_note(str(line))
            self.set_status(str(line)[:120])

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.after(0, _do)

    def _heist_done(self) -> None:
        self._heist_thread = None
        view = self._heist_view
        if view and view.winfo_exists():
            view.set_running(False)
            view.append_log("=== DONE ===")
        status = "stopped" if self._heist_stop.is_set() else "done"
        self._finish_job_hud(status)
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass

    def reveal_running(self) -> bool:
        return bool(self._reveal_thread and self._reveal_thread.is_alive())

    def _hotkey_reveal_toggle(self) -> None:
        if self.reveal_running():
            self.stop_reveal()
            return
        if self._current != "reveal":
            self.open_reveal()
        self.start_reveal()

    def start_reveal(self) -> None:
        if self._runner and self._runner.running:
            self.show_toast(t("reveal.busy"))
            return
        if self.heist_running():
            self.show_toast(t("reveal.busy"))
            return
        if self.reveal_running():
            return
        try:
            import cv2  # noqa: F401
            import mss  # noqa: F401
        except ImportError:
            self.show_toast(t("heist.missing_cv"))
            return
        from app.heist.reveal import load_reveal_config, reveal_blueprints
        from app.widgets.select import close_open

        if self._current != "reveal":
            self.open_reveal()
        cfg = load_reveal_config()
        stop_key = str(cfg.get("exit_hotkey") or "f12").strip().upper()
        self._reveal_stop.clear()
        view = self._reveal_view
        if view:
            view.set_running(True)
            view.append_log("=== START ===")
        close_open()
        self._open_job_hud(t("reveal.title"), stop_key)
        self.iconify()
        self.after(80, self._keep_job_hud)
        self.after(250, self._keep_job_hud)

        def worker() -> None:
            try:
                self._reveal_stop.wait(0.35)
                focus_game()
                reveal_blueprints(
                    cfg,
                    stop_event=self._reveal_stop,
                    on_log=self._reveal_log,
                    on_hud=self._job_hud,
                )
            except Exception as exc:
                message = t("reveal.error", exc=exc)
                self.after(0, lambda text=message: self._reveal_log(text))
            finally:
                self.after(0, self._reveal_done)

        self._reveal_thread = threading.Thread(target=worker, name="heist-reveal", daemon=True)
        self._reveal_thread.start()

    def stop_reveal(self) -> None:
        if not self.reveal_running() and not self._reveal_stop.is_set():
            return
        self._reveal_stop.set()
        view = self._reveal_view
        if view and view.winfo_exists():
            view.append_log(t("heist.stop"))
        if self._hud and self._hud.winfo_exists():
            self._hud.mark_final({"status": "stopped"})
        try:
            from app.input_win import release_modifiers

            release_modifiers(shift=True)
        except Exception:
            pass
        try:
            self.deiconify()
        except Exception:
            pass

    def _reveal_log(self, line: str) -> None:
        def _do() -> None:
            view = self._reveal_view
            if view and view.winfo_exists():
                view.append_log(str(line))
            if self._hud and self._hud.winfo_exists():
                self._hud.set_note(str(line))
            self.set_status(str(line)[:120])

        if threading.current_thread() is threading.main_thread():
            _do()
        else:
            self.after(0, _do)

    def _reveal_done(self) -> None:
        self._reveal_thread = None
        view = self._reveal_view
        if view and view.winfo_exists():
            view.set_running(False)
            view.append_log("=== DONE ===")
        status = "stopped" if self._reveal_stop.is_set() else "done"
        self._finish_job_hud(status)
        try:
            from app.input_win import release_modifiers

            release_modifiers(shift=True)
        except Exception:
            pass
        try:
            self.deiconify()
            self.lift()
        except Exception:
            pass

    def _poll_craft(self) -> None:
        try:
            while True:
                kind, payload = self._craft_q.get_nowait()
                self._on_craft(kind, payload)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(40, self._poll_craft)

    def _on_craft(self, kind: str, payload: str) -> None:
        view = self._run_view if self._run_view and self._run_view.winfo_exists() else None
        if kind == "hud":
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return
            if self._hud and self._hud.winfo_exists():
                if data.get("status") in {"stopped", "done", "error"}:
                    self._hud.mark_final(data)
                else:
                    self._hud.update_stats(data)
            return
        if kind == "paused":
            config = load_config()
            if payload == "augmentation":
                message = t("run.out_of_augment", start=config.hotkey_start)
            else:
                action = self.catalog.action_name(payload) if self.catalog else payload
                message = t("run.out_of_currency", action=action, start=config.hotkey_start)
            self.show_toast(message, kind="error", ms=8000)
            if self._hud and self._hud.winfo_exists() and self._runner:
                self._hud.update_stats(self._runner.snapshot("paused"))
                self._hud.set_note(message)
                self._hud.set_hint(t("run.hud_paused", start=config.hotkey_start, stop=config.hotkey_stop))
            if view:
                view.set_status(message)
                view.append_log(message)
            self.set_status(message)
            return
        if kind == "resumed":
            config = load_config()
            message = t("run.resumed")
            if self._hud and self._hud.winfo_exists() and self._runner:
                self._hud.update_stats(self._runner.snapshot("running"))
                self._hud.set_hint(t("run.hud_stop", key=config.hotkey_stop))
            self._write_craft_log(message)
            if view:
                view.set_status(t("run.running"))
            self.set_status(message)
            return
        if kind == "log":
            line = t(payload) if payload.startswith("run.") else payload
            self._write_craft_log(line)
            return
        if kind == "step":
            index, action_id = (payload.split("|", 1) + [""])[:2]
            name = self.catalog.action_name(action_id) if self.catalog else action_id
            text = t("run.step_status", n=index, action=name)
            if self._runner and self._runner.chain_total:
                text = t(
                    "run.chain_step",
                    item=self._runner.chain_index,
                    total=self._runner.chain_total,
                    step=text,
                )
            if self._hud and self._hud.winfo_exists():
                self._hud.set_step(text)
            if view:
                view.set_status(text)
                view.append_log(text)
            return
        if kind == "chain":
            message = t("run.chain_item", n=payload)
            self._write_craft_log(message)
            if self._hud and self._hud.winfo_exists():
                self._hud.set_step(message)
            return
        if kind in {"error", "done", "stopped"}:
            key = payload or ("run.stopped" if kind == "stopped" else "run.done")
            message = t(key)
            if self._hud and self._hud.winfo_exists() and self._runner:
                self._hud.mark_final(self._runner.snapshot(kind))
            if kind == "error":
                self.show_toast(message, kind="error")
            elif kind == "done":
                self.show_toast(message, kind="success")
            if view:
                view.set_status(message)
                view.append_log(message)
            self.set_status(message)
            hud = self._hud
            self.after(2500, lambda current=hud: self._close_hud_if(current))

    def _close_hud_if(self, hud) -> None:
        if self._hud is hud:
            self._close_hud()

    def _close_hud(self) -> None:
        if self._hud is not None and self._hud.winfo_exists():
            self._hud.destroy()
        self._hud = None

    def _on_close(self) -> None:
        self.stop_heist()
        self.stop_reveal()
        self.stop_craft()
        self._hotkeys.stop()
        self._close_hud()
        self.destroy()

    def reload_catalog(self, force: bool = False) -> None:
        if self._loading:
            return
        self._loading = True
        if force:
            self.catalog = None
            if self._current == "home":
                self.show_home()
        self.set_status(t("status.loading"))

        def work() -> None:
            try:
                catalog = ensure_catalog(
                    force=force,
                    progress=lambda key: self.after(0, lambda k=key: self.set_status(t(k))),
                )
                self.after(0, lambda: self._on_catalog_ready(catalog))
            except Exception as exc:
                logger.exception("catalog load failed")
                details = str(exc)
                self.after(0, lambda: self._on_catalog_error(details))

        threading.Thread(target=work, daemon=True).start()

    def _on_catalog_ready(self, catalog: GameCatalog) -> None:
        self._loading = False
        self.catalog = catalog
        self.set_status(t("status.ready", patch=catalog.patch, mods=len(catalog.mod_types)))
        if self._current == "home":
            self.show_home()

    def _on_catalog_error(self, details: str) -> None:
        self._loading = False
        self.set_status(t("status.error", details=details))
        if self._current == "home":
            self.show_home()
