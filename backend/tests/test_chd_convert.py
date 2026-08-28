"""Turning a disc image into a CHD, and knowing how far along it is.

Two things here are easy to get wrong in a way that looks fine:

  * chdman separates its progress updates with a carriage return, not a
    newline, so reading the output a line at a time yields nothing at all
    until the job is over. The bar would sit at zero and then jump to done,
    and the code would look correct.
  * a regex written against imagined output matches imagined output. The
    lines below were captured from a real run against a real PlayStation
    disc, carriage returns and all.

The conversion test at the end runs chdman for real on a disc built here,
because a wrapper around a program is only worth what the program does when
it is actually called.
"""
from __future__ import annotations

import shutil
import struct
import zipfile

import pytest


def test_progress_is_recovered_from_output_that_has_no_newlines():
    """Captured from a real run. Every update is separated by \\r, and the
    whole compression phase is one line as far as readline is concerned."""
    from handler.roms.chd_convert import split_chunks

    raw = (
        b"Input length: 69:59:12\n"
        b"Compressing, 0.0% complete... (ratio=100.0%)  \r"
        b"Compressing, 29.1% complete... (ratio=42.1%)  \r"
        b"Compressing, 99.5% complete... (ratio=56.3%)  \r"
        b"Compression complete ... final ratio = 56.0%            \n"
    )
    pieces = list(split_chunks(raw))
    assert any("29.1%" in p for p in pieces), (
        "podzial po samym \\n zgubilby caly postep"
    )
    assert len(pieces) >= 4


def test_the_percentage_is_read_from_the_line_chdman_really_prints():
    from handler.roms.chd_convert import parse_percent

    assert parse_percent("Compressing, 0.0% complete... (ratio=100.0%)") == 0.0
    assert parse_percent("Compressing, 29.1% complete... (ratio=42.1%)") == 29.1
    assert parse_percent("Compressing, 100.0% complete... (ratio=56.0%)") == 100.0

    # The ratio is also a percentage and sits on the same line. Reading it
    # instead would show a bar that wanders up and down and never finishes.
    assert parse_percent("Compressing, 5.5% complete... (ratio=38.8%)") == 5.5

    assert parse_percent("Input length: 69:59:12") is None
    assert parse_percent("Compression complete ... final ratio = 56.0%") is None
    assert parse_percent("") is None


def test_only_a_disc_image_is_offered_for_conversion():
    """A sheet, or a disc in one file. Never a .chd, which is already one,
    and never a playlist or a subchannel file, which are not discs at all."""
    from handler.roms.chd_convert import can_convert

    for name in ("Game (Disc 1).cue", "Game.iso", "Game.img", "Game.gdi",
                 "GAME.CUE", "Game.toc"):
        assert can_convert(name), name

    for name in ("Game.chd", "Game.m3u", "Game (Disc 1).sbi", "Game.zip",
                 "Game.7z", "Game.sfc", "Game.bin", ""):
        assert not can_convert(name), name


def test_a_bare_track_is_not_a_disc():
    """.bin is deliberately absent above and this says why. chdman opens the
    sheet, which names the track; handed the track it has no table of
    contents and refuses. Offering the button on a .bin row would produce a
    failure the person could do nothing about."""
    from handler.roms.chd_convert import can_convert

    assert not can_convert("Final Fantasy IX (Europe) (Disc 1).bin")


def _zip_of(path, *names):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            z.writestr(name, b"\0" * 64)
    return path


def test_an_archive_is_judged_by_what_is_inside_it(tmp_path):
    """The button lives on the ROM page and the job takes minutes, so the
    question has to be answered from the file rather than from its extension.
    A zipped cartridge ROM is a .zip exactly like a zipped disc is."""
    from handler.roms.chd_convert import convertible_disc

    assert convertible_disc(_zip_of(tmp_path / "disc.zip", "Game.cue", "Game.bin"))
    assert convertible_disc(_zip_of(tmp_path / "image.zip", "Game.iso"))

    assert not convertible_disc(_zip_of(tmp_path / "cart.zip", "Game.sfc")), \
        "zipowany kartridz nie jest plyta"
    assert not convertible_disc(_zip_of(tmp_path / "empty.zip", "readme.txt"))
    assert not convertible_disc(tmp_path / "missing.zip")


def test_a_disc_already_in_the_target_format_is_not_offered(tmp_path):
    """Converting a CHD to a CHD is work for nothing, and the page would be
    offering to save room on the format that already saved it."""
    from handler.roms.chd_convert import convertible_disc

    (tmp_path / "Game.chd").write_bytes(b"MComprHD")
    assert not convertible_disc(tmp_path / "Game.chd")
    assert not convertible_disc(_zip_of(tmp_path / "chd.zip", "Game.chd"))


def test_a_loose_disc_image_needs_no_archive_at_all(tmp_path):
    from handler.roms.chd_convert import convertible_disc

    (tmp_path / "Game.cue").write_text("FILE\n", encoding="utf-8")
    assert convertible_disc(tmp_path / "Game.cue")


def _tiny_disc(directory, stem="Test Disc", sectors=512):
    """A real, if pointless, Mode1/2048 disc: a sheet and its track.

    2048 bytes to a sector and a whole number of sectors, because chdman
    reads the track through the sheet and rejects a length that is not a
    multiple of the sector size. The content repeats, so it compresses hard
    and even the larger size below converts in a couple of seconds.
    """
    block = bytes(range(256)) * 8                 # one 2048 byte sector
    (directory / f"{stem}.bin").write_bytes(block * sectors)
    (directory / f"{stem}.cue").write_text(
        f'FILE "{stem}.bin" BINARY\n'
        "  TRACK 01 MODE1/2048\n"
        "    INDEX 01 00:00:00\n",
        encoding="utf-8",
    )
    return directory / f"{stem}.cue"


@pytest.mark.asyncio
async def test_a_disc_really_converts_and_reports_its_way_there(tmp_path):
    """The whole point, run rather than mocked.

    Bigger than the other discs here on purpose. chdman reports as it moves
    through the file, and one megabyte finishes inside a single update: the
    first version of this passed with a bar that had only ever said zero.

    This does NOT guard the carriage return; the test at the top of the file
    does. Breaking the splitter to end pieces on newline alone leaves this one
    green, because updates arrive in separate reads from the pipe and the read
    boundary happens to divide them. Live output is the weaker witness here,
    which is exactly why the captured output is kept as well.
    """
    from handler.roms.chd_convert import convert_to_chd

    if not shutil.which("chdman"):
        pytest.skip("chdman nie jest w tym obrazie")

    cue = _tiny_disc(tmp_path, sectors=16384)          # 32 MiB
    out = tmp_path / "out.chd"
    seen: list[float] = []

    await convert_to_chd(cue, out, on_percent=seen.append)

    assert out.is_file(), "nie powstal zaden plik"
    header = out.open("rb").read(8)
    assert header == b"MComprHD", f"to nie jest CHD: {header!r}"
    # More than one reading, and the last one a long way from the first. That
    # is what separates working progress from the carriage return bug, which
    # hands back a single 0.0 and nothing else however long the job runs.
    assert len(seen) >= 2, f"postep prawie nie zyje: {seen}"
    assert seen == sorted(seen), "postep sie cofal"
    assert seen[-1] > 50, f"postep zatrzymal sie na {seen[-1]}"


@pytest.mark.asyncio
async def test_the_hash_in_the_header_is_the_one_the_scanner_reads(tmp_path):
    """The scanner identifies a CHD by the SHA-1 in its header rather than by
    hashing the container. This pins that a file this code produces is one
    that path can actually read, which is what keeps a converted disc
    identifiable at all."""
    from handler.filesystem.rom_scanner import _chd_header_sha1
    from handler.roms.chd_convert import convert_to_chd

    if not shutil.which("chdman"):
        pytest.skip("chdman nie jest w tym obrazie")

    cue = _tiny_disc(tmp_path)
    out = tmp_path / "out.chd"
    await convert_to_chd(cue, out)

    assert _chd_header_sha1(out), "skaner nie odczyta hasza z tego pliku"
    version = struct.unpack(">I", out.open("rb").read(16)[12:16])[0]
    assert version == 5, f"skaner czyta tylko v5, a to v{version}"


@pytest.mark.asyncio
async def test_a_failed_conversion_leaves_no_half_written_file(tmp_path):
    """The output lands in the library eventually, so a partial one must never
    survive to be mistaken for a disc."""
    from handler.roms.chd_convert import ChdError, convert_to_chd

    if not shutil.which("chdman"):
        pytest.skip("chdman nie jest w tym obrazie")

    broken = tmp_path / "broken.cue"
    broken.write_text('FILE "nothing at all.bin" BINARY\n  TRACK 01 MODE1/2048\n',
                      encoding="utf-8")
    out = tmp_path / "out.chd"

    with pytest.raises(ChdError):
        await convert_to_chd(broken, out)
    assert not out.exists(), "zostal niedokonczony plik"


@pytest.mark.asyncio
async def test_a_converted_disc_passes_chdmans_own_check(tmp_path):
    """Verification is what stands between a conversion and deleting the
    source, so it is the one step that must not be taken on trust."""
    from handler.roms.chd_convert import convert_to_chd, verify_chd

    if not shutil.which("chdman"):
        pytest.skip("chdman nie jest w tym obrazie")

    cue = _tiny_disc(tmp_path)
    out = tmp_path / "out.chd"
    await convert_to_chd(cue, out)
    assert await verify_chd(out) is True

    # A file that is not a CHD at all must come back false rather than raise,
    # because the caller's next move is to decide whether to delete a disc.
    plain = tmp_path / "not-a-chd.chd"
    plain.write_bytes(b"nope" * 64)
    assert await verify_chd(plain) is False
