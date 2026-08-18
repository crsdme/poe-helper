# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = [
    "webview",
    "bottle",
    "proxy_tools",
    "clr_loader",
    "PIL",
    "PIL._tkinter_finder",
    "cv2",
    "numpy",
    "mss",
]

for package in ("webview", "PIL", "cv2", "numpy", "mss"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

assets = project / "app" / "assets"
if assets.is_dir():
    datas.append((str(assets), "app/assets"))
ui = project / "app" / "ui"
if ui.is_dir():
    datas.append((str(ui), "app/ui"))

icon = project / "app" / "assets" / "system" / "icon.ico"
if not icon.is_file():
    icon = project / "app" / "assets" / "system" / "icon.png"

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["customtkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PoE Helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon) if icon.is_file() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PoE Helper",
)
