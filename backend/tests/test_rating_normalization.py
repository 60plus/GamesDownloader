"""The 0-5 star invariant on `library_games.rating`.

The column is a 0-5 star, but several writers reach it and not all speak that
scale. The one that bit us is the metadata-search apply: RAWG comes back as
rawg*2 (a 0-10 value), and a copy of that straight into the column left games
sitting at 8.76 "stars", which then rendered as 8.8 out of 5. These pin the
recovery rule - halve a 0-10, divide a 0-100 by 20, pass a real 0-5 through -
and that the model validator applies it on every write.
"""
from __future__ import annotations

import models.library_file  # noqa: F401 - configures the LibraryGame.files mapper
from models.gog_game import GogGame
from models.library_game import LibraryGame
from utils.ratings import normalize_star_5


# ── The recovery rule ────────────────────────────────────────────────────────

def test_a_real_0_to_5_value_passes_through():
    assert normalize_star_5(4.2) == 4.2
    assert normalize_star_5(5.0) == 5.0
    assert normalize_star_5(0.5) == 0.5


def test_a_0_to_10_value_is_halved():
    """The rawg*2 case that produced the bug: 8.76 is 4.38 on the star scale."""
    assert normalize_star_5(8.76) == 4.4
    assert normalize_star_5(9.6) == 4.8
    assert normalize_star_5(10.0) == 5.0


def test_a_0_to_100_value_is_divided_by_twenty():
    """An IGDB total_rating that reached the column instead of meta_ratings."""
    assert normalize_star_5(78) == 3.9
    assert normalize_star_5(100) == 5.0


def test_nothing_and_nonsense_become_none():
    assert normalize_star_5(None) is None
    assert normalize_star_5("abc") is None
    # Unrated is None, never a stored 0, and a negative is corrupt input.
    assert normalize_star_5(0) is None
    assert normalize_star_5(-3) is None


def test_a_numeric_string_is_parsed():
    """The editor and some scrapers hand numbers over as strings."""
    assert normalize_star_5("4.4") == 4.4
    assert normalize_star_5("8.76") == 4.4


# ── The validator applies it on every write ──────────────────────────────────

def test_construction_normalizes():
    """A catalogue push or scrape builds the row with rating=..., and the
    validator fires from the constructor - the 0-10 value never lands verbatim.
    """
    assert LibraryGame(rating=8.76).rating == 4.4


def test_assignment_normalizes():
    """The editor PATCH sets the attribute after the row exists; same guard."""
    g = LibraryGame(rating=4.2)
    assert g.rating == 4.2          # a real 0-5 is untouched
    g.rating = 9.6                  # a 0-10 slips in later
    assert g.rating == 4.8
    g.rating = None                 # the clear path
    assert g.rating is None


def test_gog_game_shares_the_guard():
    """A source=gog library game reads its star from the linked GogGame, so the
    same 0-10 value (Hitman: Blood Money came back as rawg*2 = 8.62) has to be
    caught on that column too.
    """
    assert GogGame(rating=8.62).rating == 4.3
    gg = GogGame(rating=4.3)
    assert gg.rating == 4.3
