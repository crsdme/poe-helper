"""Why Grand Heist skipped the top and left job wings.

Fixture: Blueprint #3 from run_20260818_144950 — 9 empty slots
(top clipped by BLUEPRINT header, left next to Fees, right in the open).
"""

from __future__ import annotations

import unittest
from collections import defaultdict
from pathlib import Path

import cv2

from app.heist.engine import (
    ContractHit,
    _pan_needed_px,
    _slot_face_metrics,
    default_config,
    find_contracts,
    slot_looks_assigned,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "heist_bp_top_left.png"


def _cfg(**overrides) -> dict:
    cfg = default_config()
    cfg["inventory_region"] = {"left": 1275, "top": 589, "width": 214, "height": 270}
    cfg["job_inventory_mask_top"] = 640
    cfg["max_job_slot_y"] = 680
    cfg["map_margins"] = {"left": 280, "top": 55, "right": 270, "bottom": 100}
    cfg.update(overrides)
    return cfg


def _wings(hits: list[ContractHit]) -> dict[str, list[ContractHit]]:
    by_y: dict[int, list[ContractHit]] = defaultdict(list)
    for hit in hits:
        key = min((row for row in by_y if abs(row - hit.y) <= 20), default=hit.y)
        by_y[key].append(hit)
    rows = sorted(by_y.items())
    named: dict[str, list[ContractHit]] = {}
    if len(rows) >= 1:
        named["top"] = sorted(rows[0][1], key=lambda h: h.x)
    if len(rows) >= 2:
        named["left"] = sorted(rows[1][1], key=lambda h: h.x)
    if len(rows) >= 3:
        named["right"] = sorted(rows[2][1], key=lambda h: h.x)
    return named


class HeistTopLeftSlotsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE.is_file():
            raise unittest.SkipTest(f"missing fixture {FIXTURE}")
        cls.image = cv2.imread(str(FIXTURE), cv2.IMREAD_COLOR)
        if cls.image is None:
            raise unittest.SkipTest(f"cannot read {FIXTURE}")

    def test_finds_all_nine_empty_slots(self) -> None:
        hits = find_contracts(self.image, cfg=_cfg(), screen_coords=False)
        self.assertEqual(len(hits), 9, [(h.x, h.y, h.group) for h in hits])
        wings = _wings(hits)
        self.assertEqual(len(wings["top"]), 3)
        self.assertEqual(len(wings["left"]), 3)
        self.assertEqual(len(wings["right"]), 3)
        self.assertLess(wings["top"][0].y, 170)
        self.assertLess(wings["left"][0].x, 450)
        self.assertGreater(wings["right"][0].x, 1100)

    def test_top_row_is_clipped_wider_than_tall(self) -> None:
        hits = find_contracts(self.image, cfg=_cfg(), screen_coords=False)
        top = _wings(hits)["top"]
        for hit in top:
            _x, _y, bw, bh = hit.bbox
            self.assertLess(bh / float(bw), 1.15, hit.bbox)
            self.assertGreaterEqual(bh / float(bw), 0.70, hit.bbox)

    def test_old_aspect_filter_dropped_the_top_row(self) -> None:
        cfg = _cfg(clipped_top_min_aspect=1.05, min_aspect=1.05)
        hits = find_contracts(self.image, cfg=cfg, screen_coords=False)
        self.assertFalse(any(h.y < 170 for h in hits), [(h.x, h.y) for h in hits])

    def test_left_perception_icon_is_not_a_rogue_portrait(self) -> None:
        hits = find_contracts(self.image, cfg=_cfg(), screen_coords=False)
        left = _wings(hits)["left"]
        middle = left[1]
        std, parch = _slot_face_metrics(self.image, middle)
        self.assertGreater(std, 50.0, "Perception icon is busy, but not a face")
        self.assertLess(std, 58.0)
        self.assertFalse(slot_looks_assigned(self.image, middle))
        self.assertGreater(parch, 0.55)

    def test_old_face_std_52_broke_the_left_triplet(self) -> None:
        cfg = _cfg(assigned_min_face_std=52.0)
        hits = find_contracts(self.image, cfg=cfg, screen_coords=False)
        leftish = [h for h in hits if 300 < h.x < 650 and 280 < h.y < 400]
        self.assertNotEqual(
            len(leftish),
            3,
            "std=52 treated Perception as assigned and clustering dropped the wing",
        )

    def test_pan_even_when_all_nine_slots_are_visible(self) -> None:
        cfg = _cfg()
        hits = find_contracts(self.image, cfg=cfg, screen_coords=False)
        self.assertEqual(len(hits), 9)
        drag = _pan_needed_px(self.image, hits, cfg)
        self.assertGreater(
            drag,
            0,
            "Fees covers the left wing — must pan right before clicking",
        )


if __name__ == "__main__":
    unittest.main()
