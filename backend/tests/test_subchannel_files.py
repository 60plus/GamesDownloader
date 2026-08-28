"""Subchannel files, which decide whether a PAL PlayStation disc runs at all.

LibCrypt is a copy protection Sony put on European discs from 1998, and it
lives in the disc's subchannel - which a .bin dump does not carry. Without the
matching .sbi the game boots, finds the check failed, and hangs on a black
screen. The core says so plainly and nobody ever sees it:

    LibCrypt game detected with missing SBI/subchannel

Redump publishes one .sbi per disc, 452 bytes, named exactly like the image:
"Final Fantasy IX (Europe) (Disc 1).sbi" beside "... (Disc 1).chd". So GD
never has to construct a name - it has to carry the file that is already
there, which today it does not: .sbi is not a ROM extension, no sheet names
it, and nothing therefore knows it exists.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


def _disc(name):
    return SimpleNamespace(fs_name=name, track_of=None)


def test_a_subchannel_file_is_matched_to_its_disc_by_name(tmp_path):
    from handler.filesystem.rom_scanner import subchannel_files_for

    for n in ("Game (Disc 1).chd", "Game (Disc 2).chd"):
        (tmp_path / n).write_bytes(b"disc")
    (tmp_path / "Game (Disc 1).sbi").write_bytes(b"\x00" * 452)
    (tmp_path / "Game (Disc 2).sbi").write_bytes(b"\x00" * 452)

    found = subchannel_files_for(
        tmp_path, ["Game (Disc 1).chd", "Game (Disc 2).chd"])
    assert sorted(p.name for p in found) == [
        "Game (Disc 1).sbi", "Game (Disc 2).sbi",
    ]


def test_a_subchannel_file_belonging_to_another_game_is_left_alone(tmp_path):
    """A shelf holds many titles in one directory. Carrying somebody else's
    subchannel data with this disc would put it in the emulator under a name
    the core then trusts."""
    from handler.filesystem.rom_scanner import subchannel_files_for

    (tmp_path / "Game (Disc 1).chd").write_bytes(b"disc")
    (tmp_path / "Other Game.sbi").write_bytes(b"\x00" * 452)

    assert subchannel_files_for(tmp_path, ["Game (Disc 1).chd"]) == []


def test_a_full_subchannel_dump_counts_too(tmp_path):
    """.sbi is the small form, holding only the sectors the check reads. A rip
    made with the whole subchannel has a .sub beside it instead, and the core
    reads that as readily."""
    from handler.filesystem.rom_scanner import subchannel_files_for

    (tmp_path / "Game.img").write_bytes(b"disc")
    (tmp_path / "Game.sub").write_bytes(b"\x00" * 4096)

    assert [p.name for p in subchannel_files_for(tmp_path, ["Game.img"])] == [
        "Game.sub",
    ]


def test_nothing_is_claimed_when_there_is_nothing_beside_the_disc(tmp_path):
    from handler.filesystem.rom_scanner import subchannel_files_for

    (tmp_path / "Game.chd").write_bytes(b"disc")
    assert subchannel_files_for(tmp_path, ["Game.chd"]) == []


@pytest.mark.asyncio
async def test_the_emulator_can_fetch_the_subchannel_files_for_a_disc(
    tmp_path, monkeypatch
):
    """The discs reach the emulator's filesystem one per library row, and a
    subchannel file has no row of its own. This is how it gets there."""
    import io
    import zipfile

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    psx = library / "psx"
    psx.mkdir(parents=True)
    (psx / "Game (Disc 1).chd").write_bytes(b"disc")
    (psx / "Game (Disc 2).chd").write_bytes(b"disc")
    (psx / "Game (Disc 1).sbi").write_bytes(b"\x01" * 452)
    (psx / "Game (Disc 2).sbi").write_bytes(b"\x02" * 452)
    (psx / "Somebody Else.sbi").write_bytes(b"\xff" * 452)

    async def _roms_path():
        return str(library)

    async def _get_by_id(rom_id):
        return SimpleNamespace(id=rom_id, fs_path=str(psx),
                               fs_name="Game (Disc 1).chd")

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(
        [_disc("Game (Disc 1).chd"), _disc("Game (Disc 2).chd")]))

    one = await roms_router.rom_sidecars.__wrapped__(None, 5, whole_set=False)
    with zipfile.ZipFile(io.BytesIO(one.body)) as archive:
        assert archive.namelist() == ["Game (Disc 1).sbi"]
        assert archive.read("Game (Disc 1).sbi") == b"\x01" * 452

    whole = await roms_router.rom_sidecars.__wrapped__(None, 5, whole_set=True)
    with zipfile.ZipFile(io.BytesIO(whole.body)) as archive:
        assert sorted(archive.namelist()) == [
            "Game (Disc 1).sbi", "Game (Disc 2).sbi",
        ], "somebody else's stays out of it"


@pytest.mark.asyncio
async def test_a_disc_with_no_subchannel_file_says_so_with_no_content(
    tmp_path, monkeypatch
):
    """Most discs need nothing. Answering 204 rather than an empty archive
    keeps the player from unpacking a zip to discover it is empty, the same
    way the firmware bundle already answers."""
    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    psx = tmp_path / "roms" / "psx"
    psx.mkdir(parents=True)
    (psx / "Game.chd").write_bytes(b"disc")

    async def _roms_path():
        return str(tmp_path / "roms")

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "get_by_id", lambda rom_id: _as_async(
        SimpleNamespace(id=rom_id, fs_path=str(psx), fs_name="Game.chd")))
    monkeypatch.setattr(rom_handler, "disk_set", lambda rom_id: _as_async(
        [_disc("Game.chd")]))

    out = await roms_router.rom_sidecars.__wrapped__(None, 5, whole_set=False)
    assert out.status_code == 204
    assert not out.body


async def _as_async(value):
    return value


def test_a_subchannel_file_never_becomes_a_game_of_its_own():
    """The same guarantee the playlist has, and for the same reason: these sit
    in the library beside the discs, and a scanner that claimed them would put
    452 byte phantom entries on the shelf."""
    from handler.filesystem.rom_scanner import _ROM_EXTENSIONS

    assert "sbi" not in _ROM_EXTENSIONS
    assert "sub" not in _ROM_EXTENSIONS
