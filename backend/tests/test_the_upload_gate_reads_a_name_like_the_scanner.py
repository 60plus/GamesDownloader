"""What the upload gate lets through, and what it must not turn away.

The gate exists because a file the scan does not recognise gets no row, and a
file with no row has no owner, so it counts against nobody's quota and can be
uploaded again for ever while the volume fills.

It got the question wrong in both directions.

TOO WIDE. It asked `safe_name.rsplit(".", 1)[-1]` while the scanner asks
`Path(...).suffix`, and the comment beside it claimed the two could not drift
apart. They differ for a name that is nothing but a dot and an extension: for
`.iso`, rsplit says "iso" and lets it through, while the scanner sees a hidden
file with no suffix and never registers it. Exactly the hole the gate was for,
once per recognised extension.

TOO NARROW. Subchannel files are deliberately NOT ROM extensions - a .sbi is
452 bytes that belong to a disc - so the gate refused them, and with the ROM
downloader applying the same rule (_safe_rom_filename) that left no way at all
to get one onto the shelf. LibCrypt support shipped in 1.0.33 and this made it
unusable for anybody without access to the volume.

So subchannel files are admitted, but only beside the disc they belong to:
matched by stem against a file already in that directory, which is the same
question `subchannel_files_for` asks when it goes looking for them.
"""

from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _gate_source() -> str:
    source = io.open(BACKEND / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index("async def upload_roms(")
    return source[at:source.index("\n@", at)]


# ── The two questions have to be the same question ───────────────────────────

def test_the_gate_and_the_scanner_read_a_name_the_same_way():
    """Measured against the real helpers, not asserted about the source."""
    from pathlib import Path

    from handler.filesystem import rom_scanner as scanner

    def gate_says(name: str) -> bool:
        return Path(name).suffix.lstrip(".").lower() in scanner._ROM_EXTENSIONS

    def scanner_says(name: str) -> bool:
        return Path(name).suffix.lstrip(".").lower() in scanner._ROM_EXTENSIONS

    for name in ("game.iso", ".iso", "iso", "game.ISO", "game.tar.iso",
                 "game.", ".hidden", "a.b.zip", "no-extension"):
        assert gate_says(name) == scanner_says(name), name


def test_a_name_that_is_only_an_extension_is_refused():
    """`.iso` is a hidden file with no suffix, so the scan will never make a row
    for it. The old gate read the letters after the last dot and let it in."""
    from pathlib import Path

    from handler.filesystem import rom_scanner as scanner

    assert Path(".iso").suffix == ""
    assert Path(".iso").suffix.lstrip(".").lower() not in scanner._ROM_EXTENSIONS
    # ...while the rule the gate used to apply says the opposite:
    assert ".iso".rsplit(".", 1)[-1].lower() in scanner._ROM_EXTENSIONS


def test_the_gate_asks_for_the_suffix_rather_than_the_last_dot():
    body = _gate_source()
    at = body.index("_ROM_EXTENSIONS")
    line = body[body.rindex("\n", 0, at):body.index("\n", at)]
    assert "rsplit" not in line, (
        "bramka nadal czyta nazwe inaczej niz skaner - plik `.iso` przechodzi "
        "ja, laduje na dysku i nigdy nie dostaje wiersza"
    )
    assert "suffix" in line, "bramka ma pytac o suffix, tak jak skaner"


# ── The files that belong to a disc ──────────────────────────────────────────

def test_the_scanner_still_says_a_subchannel_file_is_not_a_rom():
    """The premise of the exception below. If these ever became ROM extensions
    the special case would be dead code and should go."""
    from handler.filesystem import rom_scanner as scanner

    assert scanner.SUBCHANNEL_EXTENSIONS == (".sbi", ".sub")
    for ext in scanner.SUBCHANNEL_EXTENSIONS:
        assert ext.lstrip(".") not in scanner._ROM_EXTENSIONS


def test_the_gate_admits_a_subchannel_file_beside_its_disc(tmp_path):
    from endpoints.roms import roms_router as R

    (tmp_path / "Game (Disc 1).cue").write_bytes(b"x")
    assert R._sidecar_disc("Game (Disc 1).sbi", tmp_path)
    assert R._sidecar_disc("Game (Disc 1).sub", tmp_path)


def test_the_gate_says_WHICH_disc_it_matched(tmp_path):
    """Not a yes/no any more. A subchannel file can never hold a row of its own,
    so the only thing that can say who is allowed to write over one is the disc
    it belongs to - and the route has to be told which disc that is."""
    from endpoints.roms import roms_router as R

    (tmp_path / "Game (Disc 1).cue").write_bytes(b"x")
    assert R._sidecar_disc("Game (Disc 1).sbi", tmp_path).name == "Game (Disc 1).cue"


def test_the_gate_refuses_a_subchannel_file_with_no_disc(tmp_path):
    """Otherwise the exception is a hole of its own: a file with no row, no
    owner and no quota, uploadable under any name at all."""
    from endpoints.roms import roms_router as R

    assert not R._sidecar_disc("Nothing.sbi", tmp_path)
    (tmp_path / "Other Game.cue").write_bytes(b"x")
    assert not R._sidecar_disc("Nothing.sbi", tmp_path)


def test_the_disc_it_names_has_to_be_a_rom(tmp_path):
    """A stem match against another sidecar, or against any stray file, would
    let two uploads bootstrap each other."""
    from endpoints.roms import roms_router as R

    (tmp_path / "Game.txt").write_bytes(b"x")
    (tmp_path / "Game.sub").write_bytes(b"x")
    assert not R._sidecar_disc("Game.sbi", tmp_path)


def test_the_match_ignores_case_the_way_the_reader_does(tmp_path):
    """`subchannel_files_for` lowercases both sides, so the gate must too, or a
    file it admits is one the reader will not find - or the other way round."""
    from endpoints.roms import roms_router as R

    (tmp_path / "GAME (Disc 1).CUE").write_bytes(b"x")
    assert R._sidecar_disc("game (disc 1).sbi", tmp_path)


def test_what_the_gate_admits_is_what_the_reader_finds(tmp_path):
    """The pair that makes this worth doing: a file allowed in must be a file
    the LibCrypt reader actually picks up."""
    from handler.filesystem import rom_scanner as scanner

    from endpoints.roms import roms_router as R

    (tmp_path / "Game (Disc 1).cue").write_bytes(b"x")
    (tmp_path / "Game (Disc 1).sbi").write_bytes(b"x")

    assert R._sidecar_disc("Game (Disc 1).sbi", tmp_path)
    found = scanner.subchannel_files_for(tmp_path, ["Game (Disc 1).cue"])
    assert [p.name for p in found] == ["Game (Disc 1).sbi"]


def test_the_route_uses_the_exception():
    body = _gate_source()
    assert "_sidecar_disc(" in body, (
        "bramka nie ma wyjatku dla plikow podkanalu, wiec .sbi/.sub nie maja "
        "zadnej drogi wejscia i LibCrypt z 1.0.33 jest nieuzywalny"
    )
