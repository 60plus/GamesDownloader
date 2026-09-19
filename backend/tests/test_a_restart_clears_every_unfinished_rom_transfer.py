"""A restart clears the partial ROM transfers nothing can finish any more.

The job registry lives in memory, so a restart forgets every transfer that was
running, and the .part it was writing stays on the disk for good
(main._sweep_rom_parts). The sweep looked one level under the platform, which
is where every transfer wrote until 1.0.36 gave each game a folder of its own:
a download now writes into `{platform}/{game}/`, and "Add file" into the game's
extras/ or mods/. Each of those partials also kept its folder from ever
following its title again, since a .part is how a move sees a transfer running
(1.0.36 audit).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def library(tmp_path, monkeypatch):
    from handler.roms import rom_source_handler

    monkeypatch.setattr(rom_source_handler, "_roms_base", lambda: str(tmp_path))
    return tmp_path


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"half")


@pytest.mark.parametrize("where", [
    "psx/loose.chd.part",
    "psx/Final Fantasy IX/disc.chd.part",
    "psx/Final Fantasy IX/extras/Manual.pdf.part",
    "psx/Final Fantasy IX/mods/widescreen.zip.part",
    "psx/roms/loose.chd.part",
    "psx/roms/Crash/crash.chd.part",
    "psx/roms/Crash/extras/map.png.part",
])
def test_a_partial_anywhere_a_transfer_writes_is_cleared(library, where):
    import main

    _touch(library / where)

    main._sweep_rom_parts()

    assert not (library / where).exists(), f"{where} zostal na dysku po restarcie"


def test_deeper_down_only_a_platforms_folder_is_swept(library):
    """Round 2 of the audit: with the library set to a broad folder, four levels
    down reaches places that are not the library's - a torrent client's own
    partial files, for one. Below the first level only platform folders are
    walked; the first level is swept as it always was."""
    import main

    _touch(library / "downloads" / "torrents" / "x" / "Game" / "live.part")
    _touch(library / "downloads" / "top.part")

    main._sweep_rom_parts()

    assert (library / "downloads" / "torrents" / "x" / "Game" / "live.part").is_file()
    assert not (library / "downloads" / "top.part").exists()


def test_finished_files_stay(library):
    import main

    for name in ("psx/Crash/crash.chd", "psx/Crash/extras/Manual.pdf", "psx/loose.chd"):
        _touch(library / name)

    main._sweep_rom_parts()

    assert (library / "psx/Crash/crash.chd").is_file()
    assert (library / "psx/Crash/extras/Manual.pdf").is_file()
    assert (library / "psx/loose.chd").is_file()
