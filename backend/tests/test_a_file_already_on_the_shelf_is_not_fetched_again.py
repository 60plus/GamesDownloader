"""A ROM lying loose on its shelf is not fetched a second time.

Before 1.0.36 a download asked whether `{platform}/{file}` was there. With game
folders it asks where the library says the game is, and the library only knows
what a scan has seen: a file dropped on the shelf over FTP and not scanned yet
was fetched again into a folder of its own, and the next scan made two games of
it (1.0.36 audit). The upload already looked in both places.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    from handler.roms import rom_source_handler as rsh

    async def nowhere_known(fs_slug, filename):
        # The library has no row for it: where a fresh download would go.
        return tmp_path / fs_slug / "Game"

    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))
    monkeypatch.setattr(rsh, "_home_for", nowhere_known)
    monkeypatch.setattr(rsh, "assert_fetch_allowed", lambda *a, **k: None)
    (tmp_path / "psx").mkdir()
    return rsh, tmp_path / "psx"


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["", "roms"])
async def test_a_loose_file_nobody_scanned_yet_is_already_here(shelf, where):
    rsh, psx = shelf
    (psx / where).mkdir(exist_ok=True)
    (psx / where / "Game.chd").write_bytes(b"disc")

    out = await rsh.import_rom("https://example.test/Game.chd", "psx", "Game.chd")

    assert out == {"queued": False, "reason": "already downloaded", "filename": "Game.chd"}
    assert not (psx / "Game").exists(), "drugi egzemplarz w nowym folderze"


@pytest.mark.asyncio
async def test_a_game_the_library_has_in_its_folder_is_already_here(shelf):
    rsh, psx = shelf
    (psx / "Game").mkdir()
    (psx / "Game" / "Game.chd").write_bytes(b"disc")

    out = await rsh.import_rom("https://example.test/Game.chd", "psx", "Game.chd")

    assert out["reason"] == "already downloaded"


@pytest.mark.asyncio
async def test_the_queue_asks_the_same_question(shelf):
    """Both roads in say "already downloaded" from one helper."""
    rsh, psx = shelf
    (psx / "Game.chd").write_bytes(b"disc")

    assert await rsh._already_here("psx", "Game.chd") is True
    assert await rsh._already_here("psx", "Other.chd") is False
