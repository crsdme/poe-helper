from __future__ import annotations

from pathlib import Path

from app.paths import BUNDLE, ROOT

ICON_SIZE = 48
HOME_ICON_SIZE = 56
ACTION_ICON_SIZE = 22
_CACHE: dict[str, object] = {}


def icon_path(name: str, folder: str = "items") -> Path | None:
    filename = name.replace(" ", "_") + ".png"
    for root in (BUNDLE, ROOT):
        path = root / "app" / "assets" / folder / filename
        if path.is_file():
            return path
    return None


def _ctk_image(image, size: int):
    import customtkinter as ctk

    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def _fallback_orb(name: str, size: int):
    from PIL import Image, ImageDraw, ImageFont

    canvas = max(size * 4, 64)
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    hue = sum(ord(ch) for ch in name) % 360
    color = _hsl(hue, 0.42, 0.48)
    dark = _hsl(hue, 0.50, 0.22)
    pad = canvas * 0.12
    draw.ellipse((pad, pad, canvas - pad, canvas - pad), fill=dark, outline=color, width=max(2, canvas // 18))
    inner = canvas * 0.22
    draw.ellipse((inner, inner, canvas - inner, canvas - inner), outline=color, width=max(2, canvas // 24))
    letter = (name[:1] or "?").upper()
    try:
        font = ImageFont.truetype("segoeui.ttf", int(canvas * 0.38))
    except OSError:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), letter, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(
        ((canvas - tw) / 2 - box[0], (canvas - th) / 2 - box[1] - canvas * 0.02),
        letter,
        fill=color,
        font=font,
    )
    return img.resize((size, size), Image.Resampling.LANCZOS)


def _hsl(hue: int, sat: float, light: float) -> tuple[int, int, int, int]:
    import colorsys

    r, g, b = colorsys.hls_to_rgb(hue / 360, light, sat)
    return int(r * 255), int(g * 255), int(b * 255), 255


def tile_image(name: str, folder: str = "items", size: int = ICON_SIZE):
    key = f"{folder}/{name}:{size}"
    if key in _CACHE:
        return _CACHE[key]
    path = icon_path(name, folder)
    from PIL import Image

    if path is None:
        if folder != "currency":
            _CACHE[key] = None
            return None
        image = _fallback_orb(name, size)
    else:
        image = Image.open(path).convert("RGBA")
    ctk_image = _ctk_image(image, size)
    _CACHE[key] = ctk_image
    return ctk_image


def action_image(action_id: str, size: int = ACTION_ICON_SIZE):
    if not action_id:
        return None
    if action_id.startswith("harvest"):
        return tile_image("harvest", folder="craft", size=size)
    return tile_image(action_id, folder="currency", size=size)
