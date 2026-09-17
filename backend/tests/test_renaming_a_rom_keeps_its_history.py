"""Renaming a ROM on disk keeps the game it was.

Today the scanner looks a row up by filename alone (the get_by_fs_name call in
rom_scanner's per-file loop). Rename a file and the scan sees a stranger: a new
row with no cover, no provider ids, no play history and no saves, while the row
that had all of that is marked missing. Two entries for one game, and the one
somebody had actually played is the one that vanished.

THE OBVIOUS FIX IS NOT SAFE. "Look it up by hash when the name misses" steals
rows: two copies of one file hash identically, so the second adopts the first
one's row mid-loop, and which of them wins depends on the order the directory
listing came back in. So the matching is deferred to the end of the scan, where
the question is answerable rather than guessable.

Even then, SHA-1 equality is not identity in this codebase, and the first draft
of this file was too trusting about that. Three collision classes are real here,
all verified in the scanner rather than imagined:

  * `.cue` and `.gdi` are ROM extensions and become rows of their own. Their
    hash is the hash of a few hundred bytes of text, and tool-generated sheets
    naming generic tracks are byte-identical across different games.
  * Blank and utility disk images - adf, dsk, d64, st are all ROM extensions -
    are byte-identical wherever they appear.
  * An archive's hash is the hash of ONE picked member, not of the archive, so
    two different zips sharing their largest ROM member hash the same.

And the digests are nullable: the handler writes `sha1_hash or None`, so an
unhashed row holds NULL, not "". Grouping by raw value would make every
unhashed file share a key with every other unhashed file - and unhashed is
routine here, by design, for anything over the hashing ceiling.

So a pair has to agree on content AND size AND platform, be the only candidate
on each side, carry a digest at all, and not be a companion file. Anything less
certain is left alone: two entries is a mess a person can fix, and two unrelated
games merged into one is not.

The merge keeps the OLD row and deletes the new one. That direction is not a
detail: saves, play history and collection membership all point at the rom id,
so moving the metadata onto the new row would preserve everything except the
things that actually matter. It is also the first row deletion a scan has ever
performed, which is why `arrived` may only ever contain rows this scan itself
created - never "rows that are not missing", which would put a row somebody has
been playing for months within reach of a delete.
"""
from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SCANNER = BACKEND / "handler" / "filesystem" / "rom_scanner.py"


def _source() -> str:
    return io.open(SCANNER, encoding="utf-8").read()


def _row(rid, sha1="aaa", size=100, platform=1, ext="zip", track_of=None):
    return {"id": rid, "sha1": sha1, "size": size, "platform_id": platform,
            "ext": ext, "track_of": track_of}


# ── The rule itself ──────────────────────────────────────────────────────────

def test_a_rename_is_matched_when_both_sides_are_unambiguous():
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7)], [_row(9)]) == [(7, 9)]


def test_two_files_with_the_same_content_are_left_alone():
    """A library holding `game.zip` and `game (1).zip`. The naive fix adopts a
    row here and the two files then fight over it on every scan."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7)], [_row(9), _row(10)]) == []


def test_two_vanished_rows_with_the_same_content_are_left_alone():
    """The mirror case, and the worse one: picking either would be a coin toss
    over whose play history survives."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7), _row(8)], [_row(9)]) == []


def test_the_same_game_on_two_platforms_is_not_one_game():
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, platform=1)], [_row(9, platform=2)]) == []


# ── The digest has to be a digest ────────────────────────────────────────────

@pytest.mark.parametrize("empty", [None, "", "   "])
def test_an_absent_digest_is_never_a_shared_key(empty):
    """The handler writes `sha1_hash or None`, so an unhashed row holds NULL -
    and unhashed is routine, by design, for anything over the hashing ceiling.
    Grouping by raw value would let every unhashed file match every other one,
    which on a platform where one large image vanished and another arrived is
    exactly two unrelated games merging.

    The first version of this test only tried "", which an implementation
    grouping by raw value would have passed while still merging NULLs.
    """
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, sha1=empty)], [_row(9, sha1=empty)]) == []


def test_a_digest_on_one_side_only_is_not_a_match():
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, sha1="aaa")], [_row(9, sha1=None)]) == []


# ── Content alone is not identity ────────────────────────────────────────────

def test_the_size_has_to_agree_as_well():
    """An archive's hash is the hash of one picked member, not of the archive,
    so two different zips sharing their largest ROM hash the same. The archives
    themselves almost never share a size."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, size=100)], [_row(9, size=101)]) == []


@pytest.mark.parametrize("ext", ["cue", "gdi", "m3u"])
def test_a_companion_file_is_never_adopted(ext):
    """A sheet is a few hundred bytes of text naming its tracks, and generated
    ones are byte-identical across games. It is also not the game: the disc set
    it belongs to is decided separately, from the filenames."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, ext=ext)], [_row(9, ext=ext)]) == []


def test_a_track_belonging_to_a_sheet_is_never_adopted():
    """Same reason from the other direction: a track is part of a disc, and
    discs are grouped by name earlier in the scan."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files(
        [_row(7, track_of="game.cue")], [_row(9, track_of="game.cue")]) == []


def test_a_renamed_and_edited_file_is_a_new_game():
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files([_row(7, sha1="aaa")], [_row(9, sha1="bbb")]) == []


def test_several_independent_renames_in_one_scan_all_land():
    from handler.filesystem.rom_scanner import adopt_renamed_files

    gone = [_row(1, sha1="aaa"), _row(2, sha1="bbb", size=200)]
    arrived = [_row(11, sha1="bbb", size=200), _row(12, sha1="aaa")]
    assert sorted(adopt_renamed_files(gone, arrived)) == [(1, 12), (2, 11)]


def test_one_ambiguous_pair_does_not_spoil_the_unambiguous_ones():
    """A library is allowed to contain both a duplicate and a rename."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    gone = [_row(1, sha1="dup"), _row(2, sha1="uniq", size=200)]
    arrived = [_row(11, sha1="dup"), _row(12, sha1="dup"),
               _row(13, sha1="uniq", size=200)]
    assert adopt_renamed_files(gone, arrived) == [(2, 13)]


# ── What the scan is allowed to hand it ──────────────────────────────────────

def test_the_scanner_records_the_rows_it_creates():
    """The delete is only safe if `arrived` is strictly rows this scan created.
    The loop used to throw upsert's return value away and count creations in a
    bare integer, so "which rows are new" could not be answered - and the
    tempting substitute, "rows that are not missing", puts a row somebody has
    been playing for months within reach of a delete."""
    source = _source()
    assert "= await rom_handler.upsert(" in source, (
        "skaner nadal wyrzuca wynik upsert, wiec nie wie, ktore wiersze utworzyl"
    )


def test_nothing_builds_the_arrived_side_from_what_is_merely_present():
    source = _source()
    start = source.index("adopt_renamed_files(")
    call = source[start - 400:start + 200]
    assert "missing_from_fs == False" not in call and "not missing" not in call, (
        "strona 'przybylo' liczona z tego, co jest obecne, a nie z tego, co utworzono"
    )


def test_the_pass_runs_after_every_platform_directory_has_been_walked():
    """Alias directories mean one platform's rows come from several folders, so
    a row that looks gone halfway through the scan may turn up in the next one.
    The comment above mark_all_missing records that exact bug being fixed once.

    Asserted against the end of the platform loop rather than against the first
    mention of apply_disk_groups: that call sits INSIDE the loop, so comparing
    offsets to it would accept a call placed one line below it and still inside.
    """
    source = _source()
    loop_end = source.index("# Clean up platforms whose folder no longer exists")
    # The CALL SITE INSIDE THE WALK, not the first occurrence in the file. The
    # matching itself now lives in `_renames_this_run`, defined above the scan
    # function - so indexing on the bare name finds the definition and would
    # satisfy this assertion wherever the call went, which is the very
    # first-occurrence mistake this test exists to guard against. Searched from
    # the scan function on, because `_put_back_after_an_unfinished_scan` above it
    # makes the same call for the exits that did not finish.
    call = source.index("pairs = await _renames_this_run(",
                        source.index("async def scan_roms_path("))
    assert call > loop_end, (
        "przebieg zmiany nazwy dziala wewnatrz petli po katalogach platform"
    )


# ── Two holes an adversarial review found after the first version shipped ────
#
# Both were wrong-merge, both survived a refutation pass, and both are the same
# mistake in different clothes: a rule that is true of the case I tested and
# false of a case I did not think to test.

_EMPTY_FILE_SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def test_two_empty_files_are_not_the_same_game():
    """A truncated upload, an interrupted copy, a client that dropped before the
    first chunk: each leaves a 0-byte file, and nothing rejects one. The scan
    hashes it - the ceiling only declines files that are too BIG - so every empty
    file on a platform carries the same digest and the same size, and the pair
    sails through platform + sha1 + size + uniqueness.

    Measured: hashlib.sha1(b"") is exactly the constant below.
    """
    from handler.filesystem.rom_scanner import adopt_renamed_files

    gone = [_row(7, sha1=_EMPTY_FILE_SHA1, size=0)]
    arrived = [_row(9, sha1=_EMPTY_FILE_SHA1, size=0)]
    assert adopt_renamed_files(gone, arrived) == []


def test_a_file_of_no_size_is_never_matched():
    """Zero is not a size two files can be said to agree on, whatever digest
    happens to sit beside it."""
    from handler.filesystem.rom_scanner import adopt_renamed_files

    assert adopt_renamed_files(
        [_row(7, sha1="aaa", size=0)], [_row(9, sha1="aaa", size=0)]) == []


def test_the_scan_does_not_hash_an_empty_file_at_all():
    """Belt to the braces above: a row that never gets the empty digest cannot
    be half of an empty pair, and a file that shrank to nothing should lose the
    digests describing what it used to be rather than gain the digest of
    nothing."""
    source = _source()
    assert "fs_size == 0" in source or "not fs_size" in source, (
        "skan nadal liczy hasz pustego pliku"
    )


def test_a_row_that_was_already_missing_is_never_a_donor():
    """The hole the uniqueness rule could not see. Every row of every platform
    is marked missing at the start of a scan, so "missing at the end" means
    "not found this time" - which includes a file somebody deleted in January.

    That defeats the guarantee the uniqueness rule was written for. Two copies
    of one game are safe only while both are on disk in the same scan; once one
    has been gone a while it is the only candidate on its side, and a brand new
    game that happens to share its content merges into it. The live test that
    reassured me exercised precisely the safe half.

    So the donor side is intersected with what was present BEFORE the scan
    marked everything missing, which is the only moment that distinction exists.
    """
    source = _source()
    assert "present_before" in source, (
        "strona 'zaginionych' nie jest zawezona do tego, co bylo obecne przed skanem"
    )
    marked = source.index("mark_all_missing(p.id)")
    snapshot = source.index("present_before")
    assert snapshot < marked, (
        "migawka robiona po oznaczeniu wszystkiego jako zaginione, wiec jest pusta"
    )
