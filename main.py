import logging
import traceback

from app.paths import DATA_DIR, ensure_data_dirs


def _log_crash(exc: BaseException) -> None:
    ensure_data_dirs()
    path = DATA_DIR / "app.log"
    path.write_text(
        traceback.format_exc(),
        encoding="utf-8",
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            f"{exc}\n\nПодробности в data\\app.log",
            "PoE Helper",
            0x10,
        )
    except Exception:
        pass


def _windows_app_id() -> None:
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("poe.helper.app")
    except Exception:
        pass


def main() -> None:
    from app.i18n import set_language
    from app.main_window import MainWindow
    from app.settings import load_settings
    from app.theme import BG
    import customtkinter as ctk

    _windows_app_id()
    ensure_data_dirs()
    logging.basicConfig(
        filename=DATA_DIR / "app.log",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    set_language(settings.get("language", "ru"))
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = MainWindow()
    app.configure(fg_color=BG)
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log_crash(exc)
        raise
