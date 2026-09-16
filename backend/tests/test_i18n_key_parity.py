"""Every language carries every key.

English is compiled into the bundle and the other seven are fetched at runtime,
so they are eight separate files that have to be edited together. Nothing was
watching that. The CI step named i18n only parses each file as JSON, which a
file missing half its keys passes without complaint, and a missing key does not
raise: it falls back to English, or to the raw key printed on screen, which is
the sort of thing that reaches a user before it reaches a developer.

The count was even on the day this was written, so this starts as a fence
rather than a repair, and the fence is the point: adding a string is an edit in
eight places and the eighth is the one that gets forgotten.
"""
from __future__ import annotations

import json
import pathlib

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"
ENGLISH = FRONTEND / "src" / "i18n" / "en.json"
TRANSLATIONS = FRONTEND / "public" / "i18n"

# The seven fetched at runtime. Named rather than globbed, so a language file
# that goes missing is a failure instead of a smaller loop.
LANGUAGES = ("de", "es", "fr", "it", "pl", "pt", "ru")


def _load(path: pathlib.Path) -> dict:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return json.loads(path.read_text(encoding="utf-8"))


def _translations(code: str) -> dict:
    return _load(TRANSLATIONS / f"{code}.json")


@pytest.fixture(scope="module")
def english() -> dict:
    keys = _load(ENGLISH)
    assert len(keys) > 2000, f"en.json ma tylko {len(keys)} kluczy, cos jest nie tak"
    return keys


@pytest.mark.parametrize("code", LANGUAGES)
def test_the_language_file_exists(code):
    """An absent tree is an environment without the frontend and is skipped.
    An absent language beside seven present ones is a missing file."""
    if not TRANSLATIONS.is_dir():
        pytest.skip("drzewo frontendu nie jest obecne")
    assert (TRANSLATIONS / f"{code}.json").is_file(), f"brak pliku {code}.json"


@pytest.mark.parametrize("code", LANGUAGES)
def test_nothing_is_missing_from_a_language(english, code):
    """A missing key falls back to English silently, so it ships."""
    missing = sorted(set(english) - set(_translations(code)))
    assert missing == [], (
        f"{code}.json nie ma {len(missing)} kluczy, pierwsze: {missing[:8]}"
    )


@pytest.mark.parametrize("code", LANGUAGES)
def test_nothing_lingers_that_english_has_dropped(english, code):
    """The other direction, which is how a rename leaves seven dead strings
    behind and one live one."""
    extra = sorted(set(_translations(code)) - set(english))
    assert extra == [], (
        f"{code}.json ma {len(extra)} kluczy, ktorych nie ma po angielsku: {extra[:8]}"
    )


@pytest.mark.parametrize("code", LANGUAGES)
def test_nothing_was_left_untranslated_by_copying_the_english(english, code):
    """Not a rule, a smell: a handful of strings are the same word in both
    languages and always will be. A file where hundreds match is one somebody
    populated with a copy and meant to come back to."""
    other = _translations(code)
    shared = [k for k in english if english[k] and other.get(k) == english[k]]
    assert len(shared) < len(english) // 4, (
        f"{code}.json powtarza angielski w {len(shared)} z {len(english)} kluczy"
    )
