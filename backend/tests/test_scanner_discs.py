"""Discs: one game per sheet, and a CHD identified by what it carries.

Two defects, both of which look like nothing until you have the files.

A disc kept as a sheet plus its track files arrived in the library twice,
because the scanner treats one file as one game and both extensions are ones
it recognises. The duplicate standing for the .bin cannot even be launched,
since the emulator wants the sheet.

A CHD was hashed like any other file, which measures the compressed container.
No signature database holds those, so the ROM quietly stopped being identified
by hash and fell back to matching on its filename. Worse, chdman does not
produce byte-identical output for the same source disc, so two correct rips of
one game have different container hashes - which is exactly why the format
writes the source hash into its own header.

The folding tests below were rewritten after the first attempt at them missed
four separate defects in the code they were supposed to cover. They had built
the input by hand: a dict of filenames mapped to tuples, assembled to look like
what the scanner produces. Every one of them passed while a .gdi was never
scanned at all, a cue with a byte order mark parsed to nothing, a two-disc set
came apart into two titles, and two disks both called themselves Disk 2. So
these lay real files in a real directory and run the two functions the scan
runs, in the order the scan runs them.
"""
from __future__ import annotations

import pathlib

from handler.filesystem.rom_scanner import (
    _chd_header_sha1,
    _compute_hashes,
    plan_disk_assignments,
    scan_candidates,
    tracks_referenced_by,
)

# ── Reading a sheet ───────────────────────────────────────────────────────────


def test_a_plain_cue_names_its_bin(tmp_path):
    cue = tmp_path / "Game.cue"
    cue.write_text('FILE "Game.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    assert tracks_referenced_by(cue) == {"game.bin"}


def test_a_multi_track_rip_names_every_one(tmp_path):
    """The reason this reads the sheet instead of matching on the stem."""
    cue = tmp_path / "Game.cue"
    cue.write_text(
        'FILE "Game (Track 1).bin" BINARY\n  TRACK 01 MODE1/2352\n'
        'FILE "Game (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n'
        'FILE "Game (Track 3).bin" BINARY\n  TRACK 03 AUDIO\n'
    )
    assert tracks_referenced_by(cue) == {
        "game (track 1).bin", "game (track 2).bin", "game (track 3).bin",
    }


def test_an_unquoted_name_is_read_too(tmp_path):
    cue = tmp_path / "Game.cue"
    cue.write_text("FILE Game.bin BINARY\n  TRACK 01 MODE1/2352\n")
    assert tracks_referenced_by(cue) == {"game.bin"}


def test_a_sheet_pointing_through_a_directory_keeps_only_the_name(tmp_path):
    """A sheet written elsewhere may carry a path, including a Windows one.

    We are not going to follow it out of the directory, so only the filename is
    of any interest.
    """
    cue = tmp_path / "Game.cue"
    cue.write_text('FILE "..\\\\other\\\\Game.bin" BINARY\n')
    assert tracks_referenced_by(cue) == {"game.bin"}


def test_a_gdi_names_its_tracks(tmp_path):
    gdi = tmp_path / "Game.gdi"
    gdi.write_text(
        "3\n"
        "1 0 4 2352 track01.bin 0\n"
        "2 756 0 2352 track02.raw 0\n"
        '3 45000 4 2352 "track03.bin" 0\n'
    )
    assert tracks_referenced_by(gdi) == {"track01.bin", "track02.raw", "track03.bin"}


def test_a_byte_order_mark_does_not_hide_the_first_track(tmp_path):
    """Windows tools write one, and read as plain utf-8 it sits in front of the
    F of the first FILE line, so the line never matches.

    On a single-track disc that loses the only track and the duplicate entry
    comes back. On a multi-track rip it loses track one and keeps the rest,
    which is worse: the log reports the others as folded and looks like success.
    """
    cue = tmp_path / "Game.cue"
    cue.write_bytes(
        b"\xef\xbb\xbf"
        b'FILE "Game (Track 1).bin" BINARY\n'
        b'FILE "Game (Track 2).bin" BINARY\n'
    )
    assert tracks_referenced_by(cue) == {"game (track 1).bin", "game (track 2).bin"}


def test_something_absurd_claiming_to_be_a_sheet_is_ignored(tmp_path):
    cue = tmp_path / "Huge.cue"
    cue.write_bytes(b"FILE \"x.bin\" BINARY\n" + b"\0" * (2 * 1024 * 1024))
    assert tracks_referenced_by(cue) == set()


# ── What the scan actually collects ───────────────────────────────────────────


def test_a_gdi_is_a_file_the_scan_collects(tmp_path):
    """It was not, and that alone made the whole .gdi branch dead code.

    The walk is an allow-list, and everything after it iterates what the walk
    returned. A sheet the walk never picks up cannot claim its tracks, so a
    Dreamcast rip imported as loose track01.bin and track03.bin while the file
    the emulator actually needs was not in the library at all.
    """
    (tmp_path / "Game.gdi").write_text("1\n1 0 4 2352 track01.bin 0\n")
    (tmp_path / "track01.bin").write_bytes(b"data")
    assert [p.name for p in scan_candidates(tmp_path)] == ["Game.gdi", "track01.bin"]


def test_a_raw_track_is_still_not_treated_as_a_rom(tmp_path):
    """Deliberate: .raw is far too generic a name to claim on sight.

    It is picked up for downloading and deleting through the sheet that names
    it, which is where it belongs, rather than by being called a game.
    """
    (tmp_path / "track02.raw").write_bytes(b"audio")
    assert scan_candidates(tmp_path) == []


# ── Sorting a directory into titles ───────────────────────────────────────────


def _plan(tmp_path):
    """Exactly what the scan does: collect, then decide."""
    return plan_disk_assignments(scan_candidates(tmp_path))


def _write(tmp_path, name: str, body: str | bytes = b"data"):
    path = tmp_path / name
    path.write_text(body) if isinstance(body, str) else path.write_bytes(body)
    return path


def test_the_sheet_stays_a_game_and_its_tracks_do_not(tmp_path):
    _write(tmp_path, "Game.cue",
           'FILE "Game (Track 1).bin" BINARY\nFILE "Game (Track 2).bin" BINARY\n')
    _write(tmp_path, "Game (Track 1).bin")
    _write(tmp_path, "Game (Track 2).bin")

    plan = _plan(tmp_path)

    assert plan["Game.cue"] == (None, None, False, None)      # still a title
    for track in ("Game (Track 1).bin", "Game (Track 2).bin"):
        group, number, extra, sheet = plan[track]
        assert extra is True, "a track must not appear as a game"
        assert sheet == "Game.cue", "and must be able to say which disc it is part of"
        # Not a disk: no group and no number, so no disk selector offers it.
        assert (group, number) == (None, None)


def test_a_single_disc_kept_as_cue_and_bin_is_one_title_that_knows_its_data(tmp_path):
    """The plainest possible PlayStation rip, and the case that broke.

    The .bin was hidden from the listings while nothing tied it to the .cue, so
    the download handed over two kilobytes of text and deleting the game left
    the data behind.
    """
    _write(tmp_path, "Game.cue", 'FILE "Game.bin" BINARY\n')
    _write(tmp_path, "Game.bin")

    plan = _plan(tmp_path)

    assert plan["Game.cue"] == (None, None, False, None)
    assert plan["Game.bin"] == (None, None, True, "Game.cue")


def test_a_bin_nobody_claims_is_left_alone(tmp_path):
    """A Mega Drive dump is a .bin too, and it is a game in its own right."""
    _write(tmp_path, "Sonic.bin")
    assert _plan(tmp_path) == {"Sonic.bin": (None, None, False, None)}


def test_a_two_disc_game_kept_as_sheets_is_one_title_with_two_disks(tmp_path):
    """Grouping ran on whichever file came first alphabetically, and .bin beats
    .cue, so both sheets were left ungrouped and each data file became a set of
    one. A two-disc game showed up as two separate titles."""
    _write(tmp_path, "Game (Disc 1).cue", 'FILE "Game (Disc 1).bin" BINARY\n')
    _write(tmp_path, "Game (Disc 1).bin")
    _write(tmp_path, "Game (Disc 2).cue", 'FILE "Game (Disc 2).bin" BINARY\n')
    _write(tmp_path, "Game (Disc 2).bin")

    plan = _plan(tmp_path)

    disks = {name: (g, n) for name, (g, n, _e, t) in plan.items() if g and not t}
    assert disks == {"Game (Disc 1).cue": ("game", 1), "Game (Disc 2).cue": ("game", 2)}
    # One title: disc 1 stands for it, disc 2 is hidden behind it.
    assert plan["Game (Disc 1).cue"][2] is False
    assert plan["Game (Disc 2).cue"][2] is True
    # And each data file belongs to its own sheet, not to the other one.
    assert plan["Game (Disc 1).bin"][3] == "Game (Disc 1).cue"
    assert plan["Game (Disc 2).bin"][3] == "Game (Disc 2).cue"


def test_no_two_disks_of_a_title_are_given_the_same_number(tmp_path):
    """This is what the old numbering produced: the tracks were numbered from
    the next real disk's number, so a two-disc game offered two buttons both
    saying Disk 2 - and one of them handed the emulator a raw data file."""
    _write(tmp_path, "Game (Disc 1).cue", 'FILE "Game (Disc 1).bin" BINARY\n')
    _write(tmp_path, "Game (Disc 1).bin")
    _write(tmp_path, "Game (Disc 2).cue", 'FILE "Game (Disc 2).bin" BINARY\n')
    _write(tmp_path, "Game (Disc 2).bin")

    numbers = [n for (_g, n, _e, track) in _plan(tmp_path).values() if n is not None]
    assert sorted(numbers) == [1, 2]
    assert len(numbers) == len(set(numbers))


def test_the_redump_layout_numbers_two_discs_and_not_six_files(tmp_path):
    """Discs whose tracks are named separately, which is how redump ships them.

    "Game (Disc 1) (Track 01).bin" sorts before "Game (Disc 1).cue" and reads
    as disc 1 just as convincingly, so a track could take the disc's place in
    the grouping.
    """
    for disc in (1, 2):
        _write(tmp_path, f"Game (Disc {disc}).cue",
               f'FILE "Game (Disc {disc}) (Track 01).bin" BINARY\n'
               f'FILE "Game (Disc {disc}) (Track 02).bin" BINARY\n')
        _write(tmp_path, f"Game (Disc {disc}) (Track 01).bin")
        _write(tmp_path, f"Game (Disc {disc}) (Track 02).bin")

    plan = _plan(tmp_path)

    numbered = {name for name, (_g, n, _e, _t) in plan.items() if n is not None}
    assert numbered == {"Game (Disc 1).cue", "Game (Disc 2).cue"}
    assert sum(1 for (_g, _n, _e, track) in plan.values() if track) == 4


def test_a_dreamcast_rip_folds_into_its_gdi(tmp_path):
    """The tracks that were scanned belong to the sheet; the .raw is not
    scanned at all and is reached through the sheet instead."""
    _write(tmp_path, "Game.gdi",
           "3\n1 0 4 2352 track01.bin 0\n2 756 0 2352 track02.raw 0\n"
           '3 45000 4 2352 "track03.bin" 0\n')
    _write(tmp_path, "track01.bin")
    _write(tmp_path, "track02.raw")
    _write(tmp_path, "track03.bin")

    plan = _plan(tmp_path)

    assert plan["Game.gdi"] == (None, None, False, None)
    assert plan["track01.bin"][3] == "Game.gdi"
    assert plan["track03.bin"][3] == "Game.gdi"
    assert "track02.raw" not in plan


def test_a_sheet_is_never_swallowed_by_another_sheet(tmp_path):
    """A malformed rip naming a sheet as its data file must not make one disc
    disappear into another."""
    _write(tmp_path, "A.cue", 'FILE "B.cue" BINARY\n')
    _write(tmp_path, "B.cue", 'FILE "B.bin" BINARY\n')
    _write(tmp_path, "B.bin")

    plan = _plan(tmp_path)

    assert plan["B.cue"] == (None, None, False, None)
    assert plan["B.bin"][3] == "B.cue"


# ── CHD ───────────────────────────────────────────────────────────────────────


def _chd(tmp_path, *, version=5, signature=b"MComprHD", sha1=b"\xab" * 20) -> pathlib.Path:
    header = bytearray(124)
    header[0:8] = signature
    header[8:12] = (124).to_bytes(4, "big")
    header[12:16] = version.to_bytes(4, "big")
    header[64:84] = b"\x11" * 20      # rawsha1, the tempting wrong field
    header[84:104] = sha1             # combined raw+meta, the one that counts
    path = tmp_path / "disc.chd"
    path.write_bytes(bytes(header) + b"compressed hunks go here")
    return path


def test_a_chd_is_identified_by_the_hash_it_carries(tmp_path):
    path = _chd(tmp_path, sha1=b"\xcd" * 20)
    assert _chd_header_sha1(path) == "cd" * 20


def test_the_combined_hash_is_taken_not_the_raw_one(tmp_path):
    """Offset 64 holds a raw-only digest and is the wrong answer.

    The metadata carries the disc's track layout, so two rips differing only
    there are not the same disc. The databases index the combined value.
    """
    path = _chd(tmp_path, sha1=b"\xcd" * 20)
    assert _chd_header_sha1(path) != "11" * 20


def test_the_scanner_returns_that_hash_and_no_container_digests(tmp_path):
    """A CRC or MD5 of the container would describe the compression.

    Leaving them empty is honest; filling them with something that matches
    nothing is worse, because it looks usable.
    """
    path = _chd(tmp_path, sha1=b"\xef" * 20)
    crc, md5, sha1 = _compute_hashes(path)
    assert sha1 == "ef" * 20
    assert crc == "" and md5 == ""


def test_a_chd_without_a_source_hash_is_left_without_hashes(tmp_path):
    """It used to fall back to hashing the container, and that never stopped.

    The scan re-hashes a row with no CRC; the fallback produced a CRC; and the
    pass that clears a stale CRC declined to run while one was there. So every
    scan read the whole multi-gigabyte file again, and a scan runs after every
    ROM download. The digest it produced matched nothing in any database, which
    is the reason the format writes its own hash into the header.
    """
    crc, md5, sha1 = _compute_hashes(_chd(tmp_path, version=4))
    assert (crc, md5, sha1) == ("", "", "")


def test_the_container_is_not_read_to_produce_that_answer(tmp_path, monkeypatch):
    """The point is the reading, not the answer. Asserting on empty strings
    alone would pass just as well if the file had been hashed and the result
    thrown away."""
    from handler.filesystem import rom_scanner

    hashed = []
    monkeypatch.setattr(
        rom_scanner, "_hash_stream",
        lambda *a, **kw: (hashed.append(1), ("", "", ""))[1],
    )
    rom_scanner._unreadable_chds.clear()
    rom_scanner._compute_hashes(_chd(tmp_path, version=4))
    assert hashed == [], "the container was read after all"


def test_a_v5_chd_is_hashed_from_its_header_and_not_read_either(tmp_path, monkeypatch):
    from handler.filesystem import rom_scanner

    hashed = []
    monkeypatch.setattr(
        rom_scanner, "_hash_stream",
        lambda *a, **kw: (hashed.append(1), ("", "", ""))[1],
    )
    _, _, sha1 = rom_scanner._compute_hashes(_chd(tmp_path, sha1=b"\xab" * 20))
    assert sha1 == "ab" * 20 and hashed == []


def test_a_row_identified_by_its_header_is_not_hashed_again(tmp_path):
    """The other half of the loop. "No CRC" was read as "never hashed", and a
    CHD is never going to have a CRC."""
    from types import SimpleNamespace

    from handler.filesystem.rom_scanner import _has_hashes

    assert _has_hashes(SimpleNamespace(crc_hash=None, sha1_hash="ab" * 20))
    assert _has_hashes(SimpleNamespace(crc_hash="DEADBEEF", sha1_hash=None))
    assert not _has_hashes(SimpleNamespace(crc_hash=None, sha1_hash=None))
    assert not _has_hashes(SimpleNamespace(crc_hash="", sha1_hash=""))


def test_the_complaint_about_an_old_chd_is_said_once_not_every_scan(tmp_path, caplog):
    from handler.filesystem import rom_scanner

    rom_scanner._unreadable_chds.clear()
    path = _chd(tmp_path, version=4)
    with caplog.at_level("INFO"):
        for _ in range(5):
            rom_scanner._compute_hashes(path)
    said = [r for r in caplog.records if "not a CHD v5" in r.getMessage()]
    assert len(said) == 1, f"expected one line, got {len(said)}"


def test_a_file_that_is_not_a_chd_yields_nothing(tmp_path):
    assert _chd_header_sha1(_chd(tmp_path, signature=b"NOTACHD!")) == ""


def test_an_older_chd_version_yields_nothing(tmp_path):
    # v4 puts its fields elsewhere, and no database would match it anyway.
    assert _chd_header_sha1(_chd(tmp_path, version=4)) == ""


def test_a_truncated_chd_yields_nothing(tmp_path):
    path = tmp_path / "short.chd"
    path.write_bytes(b"MComprHD" + b"\0" * 20)
    assert _chd_header_sha1(path) == ""
