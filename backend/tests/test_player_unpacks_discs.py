"""The player opens an archived disc itself, and gets the bytes back exactly.

A disc that comes down as a .zip cannot be put into the emulator's filesystem
as it arrived: the core opens a disc image, not an archive. EmulatorJS has an
extractor of its own and GD deliberately does not use it on this road - it
copies every extracted byte out of the worker's heap one at a time from
JavaScript, which for one PlayStation disc is 740 million round trips and is
why its progress bar parks at 99% for minutes.

These tests run the real reader, out of player.html, in node, against archives
written by Python's zipfile - not against a helper of our own. That is the
whole point of them. A floppy image once passed twenty two green tests and
then destroyed itself on the first write, because the test read the format
back through the same mistaken helper the code wrote it with. A binary format
gets checked against a file something else produced, or it does not get
checked.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import zipfile

import pytest

PLAYER = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "frontend" / "public" / "player.html")

# The reader lives inside a <script> in player.html, under its own section
# header. Sliced out by that header rather than by line numbers, so it moves
# with the file and fails loudly instead of quietly testing the wrong lines.
_START = "// ── Archive reader"
_NEXT = "\n// ── "


@pytest.fixture(scope="module")
def reader_source() -> str:
    if not PLAYER.is_file():
        pytest.skip("player.html nie jest kopiowany do obrazu")
    if not shutil.which("node"):
        pytest.skip("brak node do uruchomienia czytnika")
    text = PLAYER.read_text(encoding="utf-8")
    start = text.index(_START)
    end = text.index(_NEXT, start + len(_START))
    return text[start:end]


def _run(reader_source, zip_path, tmp_path) -> list[dict]:
    """Unpack *zip_path* with the player's own reader and report what came out."""
    script = tmp_path / "harness.mjs"
    script.write_text(
        reader_source
        + """
import fs from 'node:fs';
import crypto from 'node:crypto';

const buf = fs.readFileSync(process.argv[2]);
const members = await readZipBlob(new Blob([buf]));
console.log(JSON.stringify(members.map(m => ({
  name: m.name,
  size: m.data.length,
  sha256: crypto.createHash('sha256')
    .update(Buffer.from(m.data.buffer, m.data.byteOffset, m.data.length))
    .digest('hex'),
}))));
""",
        encoding="utf-8",
    )
    done = subprocess.run(
        ["node", str(script), str(zip_path)],
        capture_output=True, text=True, timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _disc_bytes(megabytes: int) -> bytes:
    """Something bigger than one deflate window, and not all the same byte, so
    the reader has to carry state across chunks rather than getting lucky."""
    block = bytes(range(256)) * 64                      # 16 KiB, compressible
    return (block * (megabytes * 64))[: megabytes * 1024 * 1024]


def test_a_deflated_disc_comes_back_byte_for_byte(reader_source, tmp_path):
    """The one that matters. Anything less than an exact match is a disc that
    boots and then fails somewhere in the middle of a game."""
    disc = _disc_bytes(6)
    sheet = b'FILE "Game (Disc 1).bin" BINARY\n  TRACK 01 MODE2/2352\n'
    archive = tmp_path / "Game (Disc 1).zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Game (Disc 1).bin", disc)
        z.writestr("Game (Disc 1).cue", sheet)
    assert archive.stat().st_size < len(disc), "the fixture really is compressed"

    out = {m["name"]: m for m in _run(reader_source, archive, tmp_path)}
    assert sorted(out) == ["Game (Disc 1).bin", "Game (Disc 1).cue"]
    assert out["Game (Disc 1).bin"]["size"] == len(disc)
    assert out["Game (Disc 1).bin"]["sha256"] == hashlib.sha256(disc).hexdigest()
    assert out["Game (Disc 1).cue"]["sha256"] == hashlib.sha256(sheet).hexdigest()


def test_a_stored_member_beside_a_deflated_one_is_read_too(reader_source, tmp_path):
    """Archives in the wild mix the two. GD writes stored archives itself, for
    firmware and for the playlist, so this half has to keep working."""
    stored, deflated = b"\x00\x01\x02" * 4096, _disc_bytes(1)
    archive = tmp_path / "mixed.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(zipfile.ZipInfo("kept.bin"), stored)          # ZIP_STORED
        z.writestr("squeezed.bin", deflated, zipfile.ZIP_DEFLATED)

    out = {m["name"]: m for m in _run(reader_source, archive, tmp_path)}
    assert out["kept.bin"]["sha256"] == hashlib.sha256(stored).hexdigest()
    assert out["squeezed.bin"]["sha256"] == hashlib.sha256(deflated).hexdigest()


def test_directories_and_a_mac_resource_fork_are_not_discs(reader_source, tmp_path):
    """A folder entry has no content and __MACOSX carries a resource fork that
    would land in the emulator's filesystem as a file named like the disc."""
    archive = tmp_path / "tidy.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("Game/", b"")
        z.writestr("__MACOSX/._Game (Disc 1).cue", b"junk")
        z.writestr("Game/Game (Disc 1).cue", b"FILE\n")

    assert [m["name"] for m in _run(reader_source, archive, tmp_path)] == [
        "Game/Game (Disc 1).cue"
    ]


def test_a_zip64_archive_is_read_as_well(reader_source, tmp_path):
    """A PlayStation disc fits in the classic record; a DVD image does not.
    Forced on a small file, so the sixty four bit fields are exercised without
    writing four gigabytes to somebody's disk."""
    payload = _disc_bytes(1)
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as z:
        info = zipfile.ZipInfo("Game (Disc 1).iso")
        info.compress_type = zipfile.ZIP_DEFLATED
        with z.open(info, "w", force_zip64=True) as dest:
            dest.write(payload)

    out = _run(reader_source, archive, tmp_path)
    assert out[0]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_the_player_never_hands_an_archive_to_the_emulators_filesystem(reader_source):
    """Pinned because it is the bug this whole change exists to fix, and it
    fails silently: the discs load, the playlist loads, the core opens a .zip
    it cannot read and says so in a log line nobody sees."""
    if not PLAYER.is_file():
        pytest.skip("player.html nie jest kopiowany do obrazu")
    text = PLAYER.read_text(encoding="utf-8")
    assert "readZipBlob" in text, "brak czytnika archiwow w odtwarzaczu"
    assert "DecompressionStream" in text, "rozpakowywanie nie jest natywne"
    assert "fetchDiscSet" in text


def test_a_whole_set_asks_the_emulator_to_reset_itself_once(reader_source):
    """A set loaded from a playlist boots to a black screen until something
    resets it. The disc goes into the tray while the core is already reading,
    so the machine looks at an empty drive; pressing Restart makes it look
    again, which is what the player reported doing every time.

    EmulatorJS has the case built in: softLoad is a number of seconds after
    which it calls gameManager.restart() itself. Pinned here because it is one
    assignment with no visible effect in the source, and the failure it
    prevents looks exactly like a broken conversion.
    """
    if not PLAYER.is_file():
        pytest.skip("player.html nie jest kopiowany do obrazu")
    text = PLAYER.read_text(encoding="utf-8")
    assert "EJS_softLoad" in text, "brak automatycznego resetu dla kompletu"
    at = text.index("EJS_softLoad")
    around = text[at - 400:at + 100]
    assert "WHOLE_SET" in around, "reset ma dotyczyc tylko calego kompletu"
    assert "RESUME" in around, (
        "reset w trakcie wczytywania stanu zabralby wczytany stan"
    )
