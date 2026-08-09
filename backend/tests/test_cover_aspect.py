"""Cover aspect-ratio snapping (handler.metadata.rom_scrape_handler).

The grid draws each tile's box from this value, so a wrong answer crops the
art; the detail page fits with contain, so the same wrong answer shows as bars
down the sides. It shipped wrong once, hence the round-trip test below.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from handler.metadata.rom_scrape_handler import _COVER_RATIOS, _detect_cover_aspect

PIL = pytest.importorskip("PIL.Image", reason="Pillow is needed to write test images")


def _write(tmp_path: Path, w: int, h: int, name: str = "cover.png") -> Path:
    p = tmp_path / name
    PIL.new("RGB", (w, h), (0, 0, 0)).save(p)
    return p


@pytest.mark.parametrize("label,value", _COVER_RATIOS)
def test_every_canonical_ratio_maps_to_itself(tmp_path, label, value):
    """The property the old threshold ladder broke.

    An image built at exactly one of the offered ratios must come back as that
    ratio. Three rungs of the ladder returned a value outside the range that
    selected it, so this is the check that would have caught it.
    """
    height = 600
    width = max(1, round(height * value))
    assert _detect_cover_aspect(_write(tmp_path, width, height)) == label


def test_plain_portrait_box_is_three_quarters(tmp_path):
    # The commonest portrait box there is. The ladder answered "4/5".
    assert _detect_cover_aspect(_write(tmp_path, 600, 800)) == "3/4"


def test_playstation_jewel_case_is_seven_sixths(tmp_path):
    # 792x680 = 1.165. The ladder answered "16/11" (1.455), a quarter too wide.
    assert _detect_cover_aspect(_write(tmp_path, 792, 680)) == "7/6"


def test_unreadable_file_yields_none(tmp_path):
    """A caller keeps the previous value on None, so this must not raise."""
    bad = tmp_path / "not-an-image.png"
    bad.write_bytes(b"certainly not a PNG")
    assert _detect_cover_aspect(bad) is None


def test_missing_file_yields_none(tmp_path):
    assert _detect_cover_aspect(tmp_path / "absent.png") is None
