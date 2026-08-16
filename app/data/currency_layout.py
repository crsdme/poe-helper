from __future__ import annotations

from dataclasses import dataclass

from app.config import Rect

IMAGE_W = 638
IMAGE_H = 639

_SLOT = 50
_LEFT_X = (18, 76, 134, 192)
_CENTER_X = (266, 324)
_RIGHT_X = (400, 458, 516, 574)
_ROW_Y = (66, 124, 182, 240, 298)
_BOTTOM_X = (123, 181, 239, 297, 355, 413, 471)
_BOTTOM_Y = (466, 524)
_BOTTOM = 46


@dataclass(frozen=True)
class TabSlot:
    key: str
    currency_id: str | None
    x: int
    y: int
    w: int
    h: int
    group: str

    @property
    def norm(self) -> tuple[float, float, float, float]:
        return (self.x / IMAGE_W, self.y / IMAGE_H, self.w / IMAGE_W, self.h / IMAGE_H)

    def to_rect(self, overlay: Rect) -> Rect:
        nx, ny, nw, nh = self.norm
        return Rect(
            x=overlay.x + int(nx * overlay.w),
            y=overlay.y + int(ny * overlay.h),
            w=max(10, int(nw * overlay.w)),
            h=max(10, int(nh * overlay.h)),
        )


# Клики из рабочего конфига другой программы, разложенные по сетке stash.jpg.
# Пустые слоты не заполняем «наугад» — иначе оверлей снова поставит не те сферы.
_LEFT_IDS = (
    (None, "wisdom", None, None),
    ("transmutation", "alteration", "annulment", "chance"),
    (None, None, None, "augmentation"),
    (None, "jeweller", "fusing", "chromatic"),
    (None, "ancient", None, None),
)
_CENTER_IDS = (
    (None, None),
    ("exalted", None),
    (None, None),
)
_RIGHT_IDS = (
    (None, None, None, "gcp"),
    ("regal", "alchemy", "chaos", "blessed"),
    (None, None, None, None),
    ("scouring", None, None, "vaal"),
    (None, None, None, None),
)

# Точные клики (клиентские координаты окна PoE) из того же конфига.
KNOWN_CLICKS: dict[str, tuple[int, int]] = {
    "wisdom": (107, 207),
    "transmutation": (56, 271),
    "alteration": (107, 271),
    "annulment": (165, 265),
    "chance": (229, 271),
    "augmentation": (216, 335),
    "jeweller": (107, 399),
    "fusing": (165, 399),
    "chromatic": (229, 399),
    "ancient": (107, 456),
    "exalted": (299, 271),
    "gcp": (606, 207),
    "regal": (433, 271),
    "alchemy": (491, 271),
    "chaos": (542, 271),
    "blessed": (606, 271),
    "scouring": (433, 399),
    "vaal": (606, 399),
    "harvest_apply": (953, 604),
    "item": (1014, 797),
}


def _slots() -> list[TabSlot]:
    rows: list[TabSlot] = []
    for row, currencies in enumerate(_LEFT_IDS):
        for col, currency_id in enumerate(currencies):
            rows.append(
                TabSlot(
                    key=f"left_{row}_{col}",
                    currency_id=currency_id,
                    x=_LEFT_X[col],
                    y=_ROW_Y[row],
                    w=_SLOT,
                    h=_SLOT,
                    group="left",
                )
            )
    for row, currencies in enumerate(_CENTER_IDS):
        for col, currency_id in enumerate(currencies):
            rows.append(
                TabSlot(
                    key=f"center_{row}_{col}",
                    currency_id=currency_id,
                    x=_CENTER_X[col],
                    y=_ROW_Y[row],
                    w=_SLOT,
                    h=_SLOT,
                    group="center",
                )
            )
    for row, currencies in enumerate(_RIGHT_IDS):
        for col, currency_id in enumerate(currencies):
            rows.append(
                TabSlot(
                    key=f"right_{row}_{col}",
                    currency_id=currency_id,
                    x=_RIGHT_X[col],
                    y=_ROW_Y[row],
                    w=_SLOT,
                    h=_SLOT,
                    group="right",
                )
            )
    rows.append(TabSlot(key="item", currency_id="item", x=276, y=248, w=87, h=178, group="item"))
    for row, y in enumerate(_BOTTOM_Y):
        for col, x in enumerate(_BOTTOM_X):
            rows.append(
                TabSlot(
                    key=f"wildcard_{row}_{col}",
                    currency_id=None,
                    x=x,
                    y=y,
                    w=_BOTTOM,
                    h=_BOTTOM,
                    group="bottom",
                )
            )
    return rows


SLOTS: tuple[TabSlot, ...] = tuple(_slots())
SLOTS_BY_KEY = {slot.key: slot for slot in SLOTS}


def apply_layout(overlay: Rect) -> dict[str, Rect]:
    mapped: dict[str, Rect] = {}
    for slot in SLOTS:
        if not slot.currency_id:
            continue
        mapped[slot.currency_id] = slot.to_rect(overlay)
    return mapped


def rects_from_known_clicks() -> dict[str, Rect]:
    return {key: Rect.from_click(x, y) for key, (x, y) in KNOWN_CLICKS.items()}


def default_slot_assignments() -> dict[str, str]:
    return {slot.key: slot.currency_id for slot in SLOTS if slot.currency_id and slot.currency_id != "item"}
