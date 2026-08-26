"""The ROM scanner's archive handling: hash the right member, within limits.

`_compute_hashes` opens whatever is sitting in the ROM directory, which is to
say a file it did not write. Two things it used to take on trust:

  * how far a member is allowed to inflate. Hashing streams rather than
    buffers, so a bomb costs time rather than memory, but the scanner runs
    unattended and would pay that time again on every pass.
  * the member's own name, which for the 7z branch was handed straight to an
    extractor. That is the shape of a zip slip.

The ceiling deliberately has no compression-ratio rule beside it, and one of
the tests below pins that decision: disc images are mostly padding and compress
enormously, so a ratio tight enough to catch anything would start refusing real
ISOs, and the punishment for refusing is a ROM that silently loses its hashes.
"""
from __future__ import annotations

import hashlib
import io
import zipfile
import zlib

import pytest

from handler.filesystem import rom_scanner
from handler.filesystem.rom_scanner import (
    _compute_hashes,
    _hash_stream,
    _reject_unsafe_member,
)


def _expected(data: bytes) -> tuple[str, str, str]:
    return (
        format(zlib.crc32(data) & 0xFFFFFFFF, "08X"),
        hashlib.md5(data).hexdigest(),
        hashlib.sha1(data).hexdigest(),
    )


def _zip_with(tmp_path, members: dict[str, bytes]):
    path = tmp_path / "rom.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    return path


# ── Member names ──────────────────────────────────────────────────────────────


def test_an_ordinary_member_name_is_fine():
    _reject_unsafe_member("Chrono Trigger (USA).sfc")
    _reject_unsafe_member("subdir/rom.bin")


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/etc/passwd",
        "../../etc/passwd",
        "subdir/../../escape.bin",
    ],
)
def test_a_name_that_would_escape_is_refused(name):
    with pytest.raises(ValueError):
        _reject_unsafe_member(name)


def test_a_windows_style_walk_upwards_is_refused_too():
    """On Linux this is one component, not a traversal, so it needs its own check.

    An archive written on Windows is exactly where such a name comes from, and
    a guard that only splits on forward slashes would wave it through.
    """
    with pytest.raises(ValueError):
        _reject_unsafe_member("..\\..\\etc\\passwd")


# ── Hashing the right thing ───────────────────────────────────────────────────


def test_a_zip_is_hashed_by_its_contents_not_the_archive(tmp_path):
    """This is how ScreenScraper identifies a ROM, so it is the whole point."""
    rom = b"NES\x1a" + bytes(range(256)) * 40
    path = _zip_with(tmp_path, {"game.nes": rom})
    assert _compute_hashes(path) == _expected(rom)


def test_the_largest_member_is_the_one_that_counts(tmp_path):
    rom = b"R" * 8192
    path = _zip_with(tmp_path, {"readme.txt": b"notes", "game.bin": rom})
    assert _compute_hashes(path) == _expected(rom)


def test_a_scanned_manual_does_not_get_hashed_instead_of_the_rom(tmp_path):
    """Largest-member is the obvious rule and it loses to a PDF booklet.

    A scan of a Super Nintendo manual comfortably outweighs the cartridge dump
    beside it. Hashing the manual produces a hash that matches nothing, and the
    failure is silent: the ROM just stops being identified, which is
    indistinguishable from a title the databases do not carry.
    """
    rom = b"SNES" * 512                      # 2 KB
    manual = b"%PDF-1.4" + b"\xff" * 40000   # 40 KB, and not a ROM
    path = _zip_with(tmp_path, {"manual.pdf": manual, "game.sfc": rom})
    assert _compute_hashes(path) == _expected(rom)


def test_an_archive_of_nothing_recognisable_falls_back_to_the_largest(tmp_path):
    """The old behaviour, kept, so an unlisted extension is no worse off."""
    big = b"B" * 4096
    path = _zip_with(tmp_path, {"small.xyz": b"tiny", "big.xyz": big})
    assert _compute_hashes(path) == _expected(big)


def test_a_plain_file_is_hashed_as_itself(tmp_path):
    rom = b"cartridge dump"
    path = tmp_path / "game.sfc"
    path.write_bytes(rom)
    assert _compute_hashes(path) == _expected(rom)


def test_an_empty_archive_yields_no_hashes(tmp_path):
    path = _zip_with(tmp_path, {})
    assert _compute_hashes(path) == ("", "", "")


# ── Limits ────────────────────────────────────────────────────────────────────


def test_a_member_declaring_more_than_the_ceiling_is_turned_away(tmp_path, monkeypatch):
    """Refused on the declared size alone, before a byte is decompressed."""
    monkeypatch.setattr(rom_scanner, "_MAX_MEMBER_BYTES", 1024)
    path = _zip_with(tmp_path, {"game.bin": b"\0" * 65536})
    # The failure is swallowed into empty hashes rather than raised: a ROM the
    # scanner cannot hash is still a ROM, and the scan must not stop.
    assert _compute_hashes(path) == ("", "", "")


def test_a_member_under_the_ceiling_still_hashes(tmp_path, monkeypatch):
    monkeypatch.setattr(rom_scanner, "_MAX_MEMBER_BYTES", 65536)
    rom = b"\0" * 4096
    path = _zip_with(tmp_path, {"game.bin": rom})
    assert _compute_hashes(path) == _expected(rom)


def test_the_running_total_catches_a_stream_that_lies_about_its_size():
    """The declared size is a claim; this is the measurement.

    A crafted archive can understate a member and sail past the header check,
    so the hashing loop counts what actually arrives.
    """
    with pytest.raises(ValueError, match="inflates past"):
        _hash_stream(io.BytesIO(b"x" * 5000), 1000)


def test_hashing_without_a_ceiling_is_still_allowed():
    # The plain-file path passes no ceiling, since a file on disk cannot
    # inflate and its size is already known.
    data = b"abc"
    assert _hash_stream(io.BytesIO(data)) == _expected(data)


def test_a_wildly_compressible_member_is_not_refused_for_being_compressible(tmp_path):
    """Pins the decision to have no compression-ratio rule.

    Four megabytes of zeros compress to a few kilobytes, a ratio in the
    thousands. Real disc images look like this because they are mostly padding,
    so a ratio rule would refuse them, and the punishment for refusing is a ROM
    that silently drops to matching by filename. If somebody adds a ratio later,
    this test is the argument against it.
    """
    rom = b"\0" * (4 * 1024 * 1024)
    path = _zip_with(tmp_path, {"disc.iso": rom})
    assert path.stat().st_size < 64 * 1024      # genuinely compressed enormously
    assert _compute_hashes(path) == _expected(rom)
