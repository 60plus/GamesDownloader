"""How much room an uploader has left, and what counts against it.

There were two byte limits before this and neither was a quota. The upload size
limit is a ceiling on one file: it counts bytes as they stream past and stops,
remembering nothing, so an account allowed 50 GB per file could add a thousand
of them. The save quota is a real running total, but only for save states and
memory cards. Nothing had ever added up what an uploader's games take.

What counts is what they brought in. A game published from a linked GOG account
is recorded against the account that owns the library entry, and can be tens of
gigabytes nobody uploaded, so it does not count; the admin decides whether those
appear at all. Everything else the account is the owner of does count, which
includes games fetched from a plugin catalogue, since those are stored as custom
just like a hand upload.

That also settles what an admin claiming a game does to the quota: nothing has
to happen. The total is a sum over the games the account owns, so the moment the
owner changes, the space is back. There is no counter to adjust and therefore no
counter to get wrong.

Zero keeps the meaning it already has in this dialog for the per-account field,
"use the global default". For the global field it has to mean no limit, because
there is no sensible number to invent for somebody else's disk, and because a
release that started enforcing a figure nobody chose would lock out uploaders
who are already over it.
"""
from __future__ import annotations

import pytest

import pathlib

from handler.library.quota import fits, narrow, resolve_limit

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Every way bytes can arrive, and what has to be true of each. A check wired
# into one of them is not a quota, it is a suggestion, and the rest are then the
# way around it.
#
# This used to assert that the text "quota." appeared somewhere in three files,
# and it would have stayed green through every hole found on 2026-08-29: a ROM
# download that never mentioned the quota, a storefront download that asked for
# a ceiling it could never reach because the game it created had no owner, and a
# ROM upload excused from the body limit on the strength of a limit it did not
# have. A substring is not a behaviour.
WAYS_IN = {
    "wgranie z przegladarki": (
        BACKEND / "endpoints" / "library" / "upload_router.py", "ceiling_for"),
    "pobranie z adresu": (
        BACKEND / "endpoints" / "library" / "upload_router.py", "ceiling_for"),
    "pobranie ze sklepu wtyczki": (
        BACKEND / "endpoints" / "settings" / "plugins_router.py", "ceiling_for"),
    "wgranie ROM-u": (
        BACKEND / "endpoints" / "roms" / "roms_router.py", "ceiling_for"),
}

# Asking for a ceiling is only half of it. The bytes reach the sum only if the
# row they land on names an account, so each way in has to record one too.
RECORDS_AN_OWNER = {
    "pobranie ze sklepu wtyczki":
        (BACKEND / "handler" / "library" / "catalog_sync_handler.py", "published_by"),
    "pobranie ROM-u ze zrodla":
        (BACKEND / "handler" / "roms" / "rom_source_handler.py", "actor_id"),
    "torrent":
        (BACKEND / "handler" / "torrent" / "seed_monitor.py", "published_by"),
}


# ── Which figure applies ─────────────────────────────────────────────────────

def test_a_per_account_figure_wins():
    assert resolve_limit(per_user=5, global_value=99) == 5


def test_zero_on_the_account_falls_back_to_the_global_one():
    """Same as the two fields beside it: blank or zero means use the default."""
    assert resolve_limit(per_user=0, global_value=99) == 99


def test_nothing_on_the_account_falls_back_too():
    assert resolve_limit(per_user=None, global_value=99) == 99


def test_zero_globally_means_no_limit():
    """Nobody can guess a sane figure for somebody else's disk, and a release
    that invented one would refuse uploaders who are already past it."""
    assert resolve_limit(per_user=None, global_value=0) == 0


def test_rubbish_is_treated_as_unset_rather_than_as_zero():
    """These arrive from a JSON column and a config table, both of which hold
    text, and a stray value must not silently become a limit of nothing."""
    for junk in ("", "abc", None, [], {}):
        assert resolve_limit(per_user=junk, global_value=7) == 7
        assert resolve_limit(per_user=7, global_value=junk) == 7


def test_a_negative_figure_is_not_a_limit_of_less_than_nothing():
    assert resolve_limit(per_user=-1, global_value=99) == 99
    assert resolve_limit(per_user=None, global_value=-1) == 0


# ── Whether the next upload fits ─────────────────────────────────────────────

def test_no_limit_always_fits():
    assert fits(used=10 ** 15, incoming=10 ** 15, limit=0)


def test_room_left_fits():
    assert fits(used=40, incoming=9, limit=50)


def test_exactly_filling_it_fits():
    """A limit is a ceiling to reach, not one to stay under."""
    assert fits(used=40, incoming=10, limit=50)


def test_one_byte_over_does_not():
    assert not fits(used=40, incoming=11, limit=50)


def test_already_over_the_limit_refuses_even_an_empty_file():
    """Lowering somebody's figure below what they already hold must not leave
    them able to add more, however small."""
    assert not fits(used=60, incoming=1, limit=50)


def test_already_over_the_limit_does_not_go_backwards():
    """Nothing is deleted to make room, so this only ever refuses."""
    assert not fits(used=60, incoming=0, limit=50)


@pytest.mark.parametrize("used", [0, 1, 49])
def test_a_first_upload_into_an_empty_account_fits(used):
    assert fits(used=used, incoming=1, limit=50)


# ── The ceiling handed to a download that has not started yet ────────────────

def test_with_no_quota_the_file_ceiling_is_unchanged():
    assert narrow(max_bytes=50, limit=0, used=999) == 50


def test_the_smaller_of_the_two_binds():
    assert narrow(max_bytes=50, limit=100, used=70) == 30
    assert narrow(max_bytes=10, limit=100, used=70) == 10


def test_nothing_spare_narrows_to_nothing_rather_than_below_it():
    """A negative ceiling would read as no limit at the far end and hand the
    account the opposite of what it was owed."""
    assert narrow(max_bytes=50, limit=100, used=100) == 0
    assert narrow(max_bytes=50, limit=100, used=140) == 0


# ── Every way in, not just the obvious one ───────────────────────────────────

@pytest.mark.parametrize("way", sorted(WAYS_IN))
def test_every_way_of_adding_bytes_asks_about_the_quota(way):
    """Bytes arrive three ways: a browser upload, a URL fetched in the
    background, and a download from a plugin catalogue. The last two were the
    easy ones to forget, because neither is called an upload."""
    path, needle = WAYS_IN[way]
    source = path.read_text(encoding="utf-8")
    assert needle in source, f"{way}: nic tu nie pyta o pulap z kwoty"


@pytest.mark.parametrize("way", sorted(RECORDS_AN_OWNER))
def test_every_way_in_records_who_brought_it(way):
    """A ceiling asked for and never reached is the shape the storefront bug
    took: it narrowed against a total that was structurally always zero, because
    the game it made belonged to nobody."""
    path, needle = RECORDS_AN_OWNER[way]
    source = path.read_text(encoding="utf-8")
    assert needle in source, f"{way}: nie zapisuje, kto to przyniosl"


def test_the_sum_covers_both_kinds_of_content():
    """A library game and a ROM are two shapes of one thing to a quota, and
    counting only the first is what made a downloaded ROM invisible to it."""
    source = (BACKEND / "handler" / "library" / "quota.py").read_text(encoding="utf-8")
    assert "LibraryFile.size_bytes" in source
    assert "Rom.fs_size_bytes" in source


def test_the_two_background_paths_narrow_the_ceiling_rather_than_counting_twice():
    """They already count bytes as they arrive, to hold the per-file limit.
    Handing that loop a lower ceiling reuses it; a second counter beside it
    would be a second thing to get wrong."""
    for path in {WAYS_IN[w][0] for w in WAYS_IN}:
        source = path.read_text(encoding="utf-8")
        if "max_bytes=" in source:
            assert "ceiling_for" in source, f"{path.name}: sufit nie jest zawezany"
