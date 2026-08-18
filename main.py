import logging
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from app.paths import BUNDLE, DATA_DIR, app_icon_ico, ensure_data_dirs, ui_index


def _log_crash(exc: BaseException) -> None:
    ensure_data_dirs()
    path = DATA_DIR / "app.log"
    path.write_text(traceback.format_exc(), encoding="utf-8")
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


def _serve_ui() -> str:
    root = str((BUNDLE / "app").resolve())

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def log_message(self, *_args) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, name="ui-http", daemon=True).start()
    port = httpd.server_address[1]
    return f"http://127.0.0.1:{port}/ui/index.html"


def main() -> None:
    from app.host import AppHost, JsApi
    from app.i18n import set_language, t
    from app.input_win import set_dpi_aware
    from app.settings import load_settings
    from app.tk_loop import TkLoop
    import webview

    set_dpi_aware()
    _windows_app_id()
    ensure_data_dirs()
    logging.basicConfig(
        filename=DATA_DIR / "app.log",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    set_language(settings.get("language", "ru"))

    if not ui_index().is_file():
        raise FileNotFoundError(ui_index())

    tk_loop = TkLoop()
    tk_loop.start()
    host = AppHost(tk_loop)
    api = JsApi(host)
    ico = app_icon_ico()
    window = webview.create_window(
        t("app.name"),
        _serve_ui(),
        js_api=api,
        width=1100,
        height=740,
        min_size=(960, 640),
        background_color="#09090b",
        text_select=True,
        easy_drag=False,
    )
    host.attach(window)

    def on_closing() -> bool:
        host.on_close()
        return True

    window.events.closing += on_closing
    kwargs = {"gui": "edgechromium"}
    if ico.is_file():
        kwargs["icon"] = str(ico)
    webview.start(host.on_started, **kwargs)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log_crash(exc)
        raise
