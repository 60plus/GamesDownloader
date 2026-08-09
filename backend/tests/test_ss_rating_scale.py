"""ScreenScraper's 0-20 note lands on the entry's 0-5 star, right way up.

The bug: `_apply_ss_entry` divided the score by 4 only when it was above 5, so a
low ScreenScraper note (say 2 out of 20) was written to the star column verbatim
as 2.0 - a 0.1-rated game showing as two-and-a-bit stars. The whole scale is
fixed: the raw note always divides by 4, and the already-normalised 0-1 `rating`
extract_metadata also returns scales up by 5. These pin both paths.
"""
from __future__ import annotations

from handler.library.catalog_meta_handler import _apply_ss_entry
from models.catalog_entry import CatalogEntry


def test_low_ss_score_is_not_inverted():
    """2/20 is 0.5 stars, not the 2.0 the old `val > 5` guard let through."""
    entry = CatalogEntry()
    _apply_ss_entry(entry, {"ss_score": 2})
    assert entry.rating == 0.5


def test_high_ss_score_divides_by_four():
    entry = CatalogEntry()
    _apply_ss_entry(entry, {"ss_score": 16})
    assert entry.rating == 4.0


def test_full_ss_score_caps_at_five_stars():
    entry = CatalogEntry()
    _apply_ss_entry(entry, {"ss_score": 20})
    assert entry.rating == 5.0


def test_normalised_rating_fallback_scales_by_five():
    """No ss_score, but extract_metadata's 0-1 `rating` is present."""
    entry = CatalogEntry()
    _apply_ss_entry(entry, {"rating": 0.8})
    assert entry.rating == 4.0


def test_existing_rating_is_left_alone():
    """A scrape only fills blanks - a rating already set is the better guess."""
    entry = CatalogEntry()
    entry.rating = 4.0
    _apply_ss_entry(entry, {"ss_score": 20})
    assert entry.rating == 4.0
