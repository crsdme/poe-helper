from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from threading import Event, Thread
from collections.abc import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
GA_PARENT = 1
GA_ROOT = 2
GW_OWNER = 4

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.ReleaseCapture.restype = wintypes.BOOL
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
user32.AllowSetForegroundWindow.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
if hasattr(user32, "GetWindowLongPtrW"):
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
else:
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
    user32.SetWindowLongW.restype = ctypes.c_long

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_C = 0x43
VK_I = 0x49
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
CF_UNICODETEXT = 13
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_VK = {f"F{i}": 0x70 + i - 1 for i in range(1, 13)}
_VK.update(
    {
        "ESCAPE": 0x1B,
        "SPACE": 0x20,
        "TAB": 0x09,
        "RETURN": 0x0D,
        "ENTER": 0x0D,
        "BACKSPACE": 0x08,
        "PAUSE": 0x13,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "HOME": 0x24,
        "END": 0x23,
        "PRIOR": 0x21,
        "NEXT": 0x22,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
    }
)
ASFW_ANY = 0xFFFFFFFF
_MOD_ALIASES = {
    "CONTROL": "CTRL",
    "CTRL": "CTRL",
    "ALT": "ALT",
    "MENU": "ALT",
    "SHIFT": "SHIFT",
    "WIN": "WIN",
    "META": "WIN",
    "WINDOWS": "WIN",
}
_MOD_BITS = {"CTRL": MOD_CONTROL, "ALT": MOD_ALT, "SHIFT": MOD_SHIFT, "WIN": MOD_WIN}
_KEY_ALIASES = {"ESC": "ESCAPE", "ENTER": "RETURN", "ARROWUP": "UP", "ARROWDOWN": "DOWN"}


class _POINT(ctypes.Structure):
    _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))


class _MSG(ctypes.Structure):
    _fields_ = (
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", _POINT),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD))


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("union", _INPUTUNION))


user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = wintypes.SHORT


def set_dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def vk_from_name(name: str) -> int | None:
    key = (name or "").strip().upper()
    if not key:
        return None
    if "+" in key or " " in key:
        parsed = parse_hotkey(key)
        return None if parsed is None else parsed[1]
    if key in _VK:
        return _VK[key]
    if len(key) == 1:
        return ord(key)
    return None


def _hotkey_tokens(name: str) -> list[str]:
    raw = (name or "").strip().upper().replace(" ", "+")
    return [part for part in raw.split("+") if part]


def normalize_hotkey(name: str) -> str:
    tokens = _hotkey_tokens(name)
    if not tokens:
        return ""
    mods: set[str] = set()
    key = ""
    for token in tokens:
        alias = _MOD_ALIASES.get(token)
        if alias:
            mods.add(alias)
            continue
        if key:
            return ""
        key = _KEY_ALIASES.get(token, token)
    if not key or key in _MOD_ALIASES:
        return ""
    parts = [label for label in ("CTRL", "ALT", "SHIFT", "WIN") if label in mods]
    parts.append(key)
    return "+".join(parts)


def parse_hotkey(name: str) -> tuple[int, int] | None:
    label = normalize_hotkey(name)
    if not label:
        return None
    parts = label.split("+")
    key = parts[-1]
    mods = 0
    for part in parts[:-1]:
        mods |= _MOD_BITS.get(part, 0)
    vk = _VK.get(key) if key in _VK else (ord(key) if len(key) == 1 else None)
    if vk is None:
        return None
    return mods, vk


def _mods_match(mods: int) -> bool:
    ctrl = key_is_down(VK_CONTROL) or key_is_down(VK_LCONTROL) or key_is_down(VK_RCONTROL)
    shift = key_is_down(VK_SHIFT) or key_is_down(VK_LSHIFT) or key_is_down(VK_RSHIFT)
    alt = key_is_down(VK_MENU) or key_is_down(VK_LMENU) or key_is_down(VK_RMENU)
    want_ctrl = bool(mods & MOD_CONTROL)
    want_shift = bool(mods & MOD_SHIFT)
    want_alt = bool(mods & MOD_ALT)
    return ctrl == want_ctrl and shift == want_shift and alt == want_alt


def move_to(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def _scan(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0) & 0xFF)


def key_is_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _keybd(vk: int, up: bool = False, extended: bool = False) -> None:
    flags = 0
    if up:
        flags |= KEYEVENTF_KEYUP
    if extended or vk in {VK_RCONTROL, VK_RMENU, VK_RSHIFT}:
        flags |= KEYEVENTF_EXTENDEDKEY
    user32.keybd_event(vk, _scan(vk), flags, 0)


def release_ctrl() -> None:
    _keybd(VK_CONTROL, up=True)
    _keybd(VK_LCONTROL, up=True)
    _keybd(VK_RCONTROL, up=True, extended=True)


def release_modifiers(*, shift: bool = False) -> None:
    release_ctrl()
    _keybd(VK_MENU, up=True)
    _keybd(VK_LMENU, up=True)
    _keybd(VK_RMENU, up=True, extended=True)
    if shift:
        _keybd(VK_SHIFT, up=True)
        _keybd(VK_LSHIFT, up=True)
        _keybd(VK_RSHIFT, up=True)


def click(x: int, y: int, button: str = "left", pause_ms: int = 0, keep_ctrl: bool = False) -> None:
    pause = max(0, int(pause_ms)) / 1000
    if not keep_ctrl:
        release_ctrl()
    move_to(x, y)
    if pause:
        time.sleep(pause)
    down, up = (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    if button == "right":
        down, up = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(pause if pause else 0.001)
    user32.mouse_event(up, 0, 0, 0, 0)


def ctrl_click(x: int, y: int, pause_ms: int = 20) -> None:
    pause = max(0, int(pause_ms)) / 1000
    release_ctrl()
    move_to(x, y)
    if pause:
        time.sleep(pause)
    _keybd(VK_CONTROL)
    time.sleep(0.012)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(pause if pause else 0.001)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    release_ctrl()


def shift_click(x: int, y: int, pause_ms: int = 20) -> None:
    pause = max(0.025, int(pause_ms) / 1000)
    release_modifiers(shift=True)
    move_to(x, y)
    time.sleep(pause)
    _keybd(VK_SHIFT)
    _keybd(VK_LSHIFT)
    time.sleep(0.05)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(pause)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.03)
    shift_up()


def mouse_down(button: str = "left") -> None:
    flag = MOUSEEVENTF_RIGHTDOWN if button == "right" else MOUSEEVENTF_LEFTDOWN
    user32.mouse_event(flag, 0, 0, 0, 0)


def mouse_up(button: str = "left") -> None:
    flag = MOUSEEVENTF_RIGHTUP if button == "right" else MOUSEEVENTF_LEFTUP
    user32.mouse_event(flag, 0, 0, 0, 0)


def drag(x0: int, y0: int, x1: int, y1: int, duration: float = 0.15) -> None:
    release_ctrl()
    move_to(x0, y0)
    time.sleep(0.04)
    mouse_down()
    steps = max(6, int(max(0.05, duration) / 0.016))
    for index in range(1, steps + 1):
        t = index / steps
        move_to(int(x0 + (x1 - x0) * t), int(y0 + (y1 - y0) * t))
        time.sleep(max(0.05, duration) / steps)
    mouse_up()


def tap_key(vk: int, hold: float = 0.02) -> None:
    release_ctrl()
    _keybd(vk)
    time.sleep(max(0.01, hold))
    _keybd(vk, up=True)


_overlay_hwnds: set[int] = set()


def register_overlay(hwnd: int) -> None:
    if hwnd:
        _overlay_hwnds.add(int(hwnd))


def unregister_overlay(hwnd: int) -> None:
    _overlay_hwnds.discard(int(hwnd))


def _hwnd_in_overlays(hwnd: int) -> bool:
    if not hwnd or not _overlay_hwnds:
        return False
    current = int(hwnd)
    seen: set[int] = set()
    while current and current not in seen:
        if current in _overlay_hwnds:
            return True
        seen.add(current)
        parent = int(user32.GetAncestor(current, GA_PARENT) or 0)
        if parent == current:
            parent = 0
        if not parent:
            parent = int(user32.GetParent(current) or 0)
        if not parent:
            parent = int(user32.GetWindow(current, GW_OWNER) or 0)
        current = parent
    return False


def widget_hwnd(widget) -> int:
    try:
        widget.update_idletasks()
        hwnd = int(widget.winfo_id() or 0)
        if not hwnd:
            return 0
        return int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)
    except Exception:
        return 0


def style_overlay(hwnd: int) -> None:
    if not hwnd:
        return
    getter = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    setter = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    style = int(getter(hwnd, GWL_EXSTYLE) or 0)
    setter(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def show_without_activate(hwnd: int) -> None:
    if hwnd:
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)


def start_window_drag(hwnd: int) -> None:
    if not hwnd:
        return
    try:
        user32.ReleaseCapture()
        user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception:
        pass


def find_game_window() -> int:
    hwnd = user32.FindWindowW(None, "Path of Exile")
    if hwnd:
        return int(hwnd)
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(handle, _lparam):
        length = user32.GetWindowTextLengthW(handle) + 1
        buf = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(handle, buf, length)
        title = buf.value or ""
        if title == "Path of Exile" or title.startswith("Path of Exile"):
            found.append(int(handle))
            return False
        return True

    user32.EnumWindows(_enum, 0)
    return found[0] if found else 0


def game_window_ready() -> bool:
    hwnd = find_game_window()
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        return False
    return bool(user32.IsWindowVisible(hwnd))


def _foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def game_is_active() -> bool:
    hwnd = find_game_window()
    if not hwnd or not game_window_ready():
        return False
    foreground = _foreground_hwnd()
    if not foreground:
        return False
    if foreground == hwnd:
        return True
    if _hwnd_in_overlays(foreground):
        return True
    root = int(user32.GetAncestor(foreground, GA_ROOT) or 0)
    return root == hwnd


def _thread_id(hwnd: int) -> int:
    dummy = wintypes.DWORD(0)
    return int(user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dummy)) or 0)


def _force_foreground(hwnd: int) -> bool:
    if not hwnd:
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    return _foreground_hwnd() == hwnd


def allow_foreground() -> None:
    try:
        user32.AllowSetForegroundWindow(ASFW_ANY)
    except Exception:
        pass


def focus_game(retries: int = 3) -> bool:
    hwnd = find_game_window()
    if not hwnd:
        return False
    if game_is_active():
        return True
    allow_foreground()
    for _ in range(max(1, retries)):
        if _force_foreground(hwnd):
            return True
        time.sleep(0.05)
    return game_is_active()


def tap_ctrl_c() -> None:
    release_ctrl()
    _keybd(VK_CONTROL)
    time.sleep(0.015)
    _keybd(VK_C)
    time.sleep(0.02)
    _keybd(VK_C, up=True)
    time.sleep(0.01)
    _keybd(VK_CONTROL, up=True)
    release_ctrl()


def shift_down() -> None:
    _keybd(VK_SHIFT)


def shift_up() -> None:
    _keybd(VK_SHIFT, up=True)
    _keybd(VK_LSHIFT, up=True)
    _keybd(VK_RSHIFT, up=True)


def alt_down() -> None:
    _keybd(VK_MENU)


def alt_up() -> None:
    _keybd(VK_MENU, up=True)
    _keybd(VK_LMENU, up=True)
    _keybd(VK_RMENU, up=True, extended=True)


user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
kernel32.GlobalSize.restype = ctypes.c_size_t
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p


def get_clipboard() -> str:
    for _ in range(15):
        if not user32.OpenClipboard(None):
            time.sleep(0.03)
            continue
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                return ""
            try:
                size = int(kernel32.GlobalSize(handle) or 0)
                if size <= 0:
                    return ""
                raw = ctypes.string_at(pointer, size)
                return raw.decode("utf-16-le", errors="ignore").rstrip("\x00")
            finally:
                kernel32.GlobalUnlock(handle)
        except Exception:
            return ""
        finally:
            user32.CloseClipboard()
    return ""


def set_clipboard(text: str) -> None:
    payload = (text or "").encode("utf-16-le") + b"\x00\x00"
    handle = kernel32.GlobalAlloc(0x0002, len(payload))
    if not handle:
        return
    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return
    ctypes.memmove(pointer, payload, len(payload))
    kernel32.GlobalUnlock(handle)
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return
        handle = None
    finally:
        user32.CloseClipboard()


class HotkeyListener:
    def __init__(self) -> None:
        self._stop = Event()
        self._thread: Thread | None = None
        self.enabled = True

    def start(
        self,
        binds: dict[str, Callable[[], None]],
        poll: dict[str, Callable[[], None]] | None = None,
    ) -> None:
        self.stop()
        pairs = [(name, callback) for name, callback in binds.items() if parse_hotkey(name)]
        extra = [(name, callback) for name, callback in (poll or {}).items() if parse_hotkey(name)]
        if not pairs and not extra:
            return
        self.enabled = True
        self._stop.clear()
        self._thread = Thread(target=self._loop, args=(pairs, extra), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive() and thread is not Thread.current_thread():
            thread.join(timeout=1.0)

    def _loop(
        self,
        pairs: list[tuple[str, Callable[[], None]]],
        extra: list[tuple[str, Callable[[], None]]],
    ) -> None:
        mapping: dict[int, Callable[[], None]] = {}
        ids: list[int] = []
        hotkey_id = 1
        for name, callback in pairs:
            parsed = parse_hotkey(name)
            if parsed is None:
                continue
            mods, vk = parsed
            ok = user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk)
            if not ok:
                ok = user32.RegisterHotKey(None, hotkey_id, mods, vk)
            if ok:
                mapping[hotkey_id] = callback
                ids.append(hotkey_id)
                hotkey_id += 1
        poll_targets: list[tuple[int, int, Callable[[], None]]] = []
        seen: set[tuple[int, int]] = set()
        for name, callback in pairs + extra:
            parsed = parse_hotkey(name)
            if parsed is None or parsed in seen:
                continue
            seen.add(parsed)
            poll_targets.append((parsed[0], parsed[1], callback))
        prev = {item[:2]: False for item in poll_targets}
        last_fire: dict[int, float] = {}
        msg = _MSG()
        try:
            while not self._stop.is_set():
                got = user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE)
                if got and msg.message == WM_HOTKEY:
                    self._fire(mapping.get(int(msg.wParam)), last_fire)
                for mods, vk, callback in poll_targets:
                    down = key_is_down(vk) and _mods_match(mods)
                    key = (mods, vk)
                    if down and not prev[key]:
                        self._fire(callback, last_fire)
                    prev[key] = down
                time.sleep(0.03)
        finally:
            for item_id in ids:
                user32.UnregisterHotKey(None, item_id)

    def _fire(self, callback: Callable[[], None] | None, last_fire: dict[int, float]) -> None:
        if not callback or not self.enabled:
            return
        now = time.monotonic()
        stamp = id(callback)
        if now - last_fire.get(stamp, 0) < 0.35:
            return
        last_fire[stamp] = now
        callback()
