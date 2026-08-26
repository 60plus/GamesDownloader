"""A rating is a number out of ten, and providers do not all agree.

TheGamesDB's `rating` field is the age rating, so it answers "E - Everyone".
That reached a ROM's page as the literal text "NaN/10" under the plugin's name,
and worse, converting it raised inside the one try that wrapped every provider,
so a library with PPE.pl ratings on every game lost all of them because an
unrelated plugin answered with a word.
"""

from __future__ import annotations

import math

import pytest

from handler.metadata.rom_scrape_handler import _numeric_rating


@pytest.mark.parametrize("raw, expected", [
    (8, 8.0),
    (8.25, 8.2),          # rounded to one place, as stored
    ("7.5", 7.5),         # a plugin sending a numeric string still counts
    (0, 0.0),             # a genuine zero is a rating, not a missing one
])
def test_a_number_out_of_ten_is_kept(raw, expected):
    assert _numeric_rating("ppe", raw) == expected


@pytest.mark.parametrize("raw", [
    "E - Everyone",       # TheGamesDB's age rating, the case that started this
    "T - Teen",
    "Not Rated",
    "",
    "abc",
    None,
    {},
    [],
    object(),
])
def test_anything_that_is_not_a_number_is_refused(raw):
    assert _numeric_rating("thegamesdb", raw) is None


@pytest.mark.parametrize("raw", [float("nan"), float("inf"), float("-inf")])
def test_nan_and_infinity_are_refused(raw):
    """A NaN in the database is worse than a missing rating: it is not valid
    JSON, so it can break the response that carries it rather than just look
    wrong on the page."""
    assert _numeric_rating("thegamesdb", raw) is None


@pytest.mark.parametrize("raw", [True, False])
def test_a_boolean_is_not_a_rating(raw):
    """`float(True)` is 1.0, which would quietly become a one-out-of-ten."""
    assert _numeric_rating("odd", raw) is None


def test_one_provider_answering_with_a_word_does_not_silence_the_others():
    """The failure this really guards. Both providers are read in one pass and
    the bad one used to take the good one with it."""
    ratings = {}
    for provider, raw in (("thegamesdb", "E - Everyone"), ("ppe", 9.1)):
        value = _numeric_rating(provider, raw)
        if value is not None:
            ratings[provider] = value

    assert ratings == {"ppe": 9.1}


# ── rows written before the guard existed ────────────────────────────────────

def test_a_stored_row_loses_only_the_entry_that_is_not_a_number():
    """What the startup pass does to a library scraped before this. The good
    provider stays, the bad one goes, and nothing else about the entry moves."""
    from handler.metadata.rom_scrape_handler import clean_plugin_ratings

    stored = {
        "ppe": {"name": "PPE.pl", "rating": 9.1, "logo_url": "/api/plugins/ppe/logo"},
        "thegamesdb": {"name": "TheGamesDB", "rating": "E - Everyone",
                       "logo_url": "/api/plugins/thegamesdb/logo"},
    }
    assert clean_plugin_ratings(stored) == {
        "ppe": {"name": "PPE.pl", "rating": 9.1, "logo_url": "/api/plugins/ppe/logo"},
    }


def test_a_row_with_nothing_usable_left_goes_back_to_nothing():
    """Rather than an empty object, which would keep the ratings row on the
    page with no ratings in it."""
    from handler.metadata.rom_scrape_handler import clean_plugin_ratings

    assert clean_plugin_ratings({"thegamesdb": {"rating": "Not Rated"}}) is None


def test_a_row_that_was_always_fine_is_returned_unchanged():
    """This is how the startup pass knows which rows to skip: it writes only
    where cleaning actually changed something."""
    from handler.metadata.rom_scrape_handler import clean_plugin_ratings

    stored = {"ppe": {"name": "PPE.pl", "rating": 8.0}}
    assert clean_plugin_ratings(stored) == stored


def test_the_media_route_coerces_a_plugin_rating_before_sending_it():
    """A canary, and worth being honest about what it is.

    The metadata editor formats a detail source's rating with .toFixed(). A
    string has no .toFixed, so it throws while the Details tab renders and Vue
    takes the whole editor down: the panel vanishes mid-edit and will not
    reopen until the page is reloaded.

    The behaviour that stops it is `_numeric_rating`, which is covered properly
    by every other test in this file. What cannot be reached without standing
    up ScreenScraper, IGDB and LaunchBox is the route that calls it, so this
    checks the call is still there rather than what it does. If the field is
    ever built somewhere else, this fails and asks to be rewritten instead of
    passing on a route that no longer coerces anything.
    """
    import inspect

    from endpoints.roms import roms_router

    source = inspect.getsource(roms_router.get_rom_all_media)
    assert '"rating":       _p_rating' in source, (
        "the detail-source rating field moved; this canary needs rewriting"
    )
    assert '_p_rating = _numeric_rating(' in source, (
        "a plugin's rating must be coerced before the editor is asked to "
        "format it"
    )


def test_the_stored_value_is_json_safe():
    """Whatever survives has to serialise, because it goes into a JSON column
    and back out through the API."""
    import json

    for raw in (8, "7.5", 0, 10.04):
        value = _numeric_rating("ppe", raw)
        assert value is not None
        assert not math.isnan(value)
        assert json.loads(json.dumps({"rating": value}))["rating"] == value
