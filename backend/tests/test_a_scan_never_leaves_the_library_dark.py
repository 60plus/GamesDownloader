"""Three ways the library could be left claiming its games are gone.

A scan marks EVERY row missing up front and un-marks each one as the walk finds
it on disk. That is fine while the walk finishes. Every one of these is a way it
might not, and every listing, count and search filters missing rows out - so the
symptom is not an error message, it is a library that has gone dark.

1. THE WALK RAISES. A container restart, a disappearing mount, one MariaDB error
   among the thousands of per-row transactions. The cancelled path restores what
   it marked; the exception path did not exist.

2. AN ALIAS FOLDER. Several directory names map to one platform row, and the row
   keeps whichever name it was created with. Consolidate `snesna/` into `snes/`
   and the cleanup for folders that have disappeared marks the platform missing
   immediately after the walk found every one of its files.

3. THE FLAG IS BELIEVED WITHOUT ASKING THE DISK. The screen that lists missing
   entries offers them all for removal in one act, with saves and play history
   cascading. If the flag is ever wrong - and 1 and 2 above are two ways it can
   be - that is a real deletion of entries whose files are sitting there.

The third is the one that makes the other two expensive, and it is also the
cheapest to make safe: one stat per listed row.
"""
from __future__ import annotations

import asyncio
import types

import pytest


class _FakeRequest:
    def __init__(self, scopes):
        self.state = types.SimpleNamespace(user=object(), scopes=set(scopes))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


# ── 1. The walk raises ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_walk_that_raises_puts_the_library_back(tmp_path, monkeypatch):
    from handler.filesystem import rom_scanner as scanner

    library = tmp_path / "roms" / "psx"
    library.mkdir(parents=True)
    (library / "game.iso").write_bytes(b"x")

    restored: list = []

    async def _nothing(*a, **k):
        return None

    async def _present(*a, **k):
        return [11, 22, 33]

    async def _restore(ids, **k):
        restored.append(sorted(ids))

    async def _counts(*a, **k):
        return {}

    async def _upsert_platform(*a, **k):
        return types.SimpleNamespace(id=1, slug="psx", fs_slug="psx", scan_exclude=None)

    async def _boom(*a, **k):
        raise RuntimeError("dysk zniknal w polowie skanu")

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _fake_async([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _counts)
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert", _upsert_platform)
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _present)
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _restore)
    # The walk falls over on the first row it looks up.
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _boom)

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert restored == [[11, 22, 33]], (
        "skan przerwany bledem nie przywrocil tego, co sam oznaczyl jako "
        "zaginione, wiec biblioteka zostaje ciemna"
    )


@pytest.mark.asyncio
async def test_the_failure_is_still_raised_after_restoring(tmp_path, monkeypatch):
    """Restoring is not swallowing. Whatever went wrong still has to reach the
    caller and the log, or a scan that never works looks like a scan that keeps
    finding nothing."""
    from handler.filesystem import rom_scanner as scanner

    (tmp_path / "roms" / "psx").mkdir(parents=True)
    (tmp_path / "roms" / "psx" / "g.iso").write_bytes(b"x")

    async def _nothing(*a, **k):
        return None

    async def _boom(*a, **k):
        raise RuntimeError("konkretny blad")

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _fake_async([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _fake_async({}))
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert",
                        _fake_async(types.SimpleNamespace(id=1, slug="psx", fs_slug="psx",
                                                          scan_exclude=None)))
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _fake_async([1]))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _boom)

    with pytest.raises(RuntimeError, match="konkretny blad"):
        await scanner.scan_roms_path(str(tmp_path / "roms"))


# ── 2. An alias folder ───────────────────────────────────────────────────────


def test_a_platform_the_walk_visited_is_never_marked_gone():
    """Several folder names map to one platform row, and upsert deliberately
    reuses the row by slug without changing its stored fs_slug. So the cleanup
    for folders that have disappeared has to ask "did I visit this platform",
    not "is there a folder with its name"."""
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "handler" / "filesystem" / "rom_scanner.py",
        encoding="utf-8").read()
    at = source.index("scanned_fs_slugs")
    block = source[at:source.index("# ── Renames", at)]
    assert "seen_platform_ids" in block, (
        "sprzatanie po zniknietych folderach nie sprawdza, czy platforma zostala "
        "odwiedzona, wiec folder-alias kasuje platforme tuz po jej znalezieniu"
    )


# ── 3. The flag is believed without asking the disk ──────────────────────────


def test_a_missing_entry_whose_file_is_there_is_not_removed(tmp_path, monkeypatch):
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    real = tmp_path / "still-here.iso"
    real.write_bytes(b"x")

    rows = [
        {"id": 1, "name": "Gone", "fs_name": "gone.iso", "fs_path": str(tmp_path),
         "size_bytes": 1, "platform_slug": "psx", "platform_name": "PlayStation"},
        {"id": 2, "name": "Here", "fs_name": real.name, "fs_path": str(tmp_path),
         "size_bytes": 1, "platform_slug": "psx", "platform_name": "PlayStation"},
    ]
    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async(rows))

    deleted = []

    async def _delete(rom_id, **k):
        deleted.append(rom_id)
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.remove_missing_roms(
        _FakeRequest({Scope.ROMS_WRITE}), rr.MissingRemoveBody(ids=[1, 2])))

    assert deleted == [1], (
        "skasowano wpis, ktorego plik LEZY na dysku - flaga w bazie byla "
        "nieaktualna, a nikt nie zapytal dysku"
    )
    assert 2 in (got.get("skipped") or []), "pominiecie nie zostalo zgloszone"


def test_the_listing_does_not_show_an_entry_whose_file_is_there(tmp_path, monkeypatch):
    """Same check on the way in, so the screen never offers a row it would then
    refuse to remove."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    real = tmp_path / "present.iso"
    real.write_bytes(b"x")
    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([
        {"id": 1, "name": "Gone", "fs_name": "gone.iso", "fs_path": str(tmp_path),
         "size_bytes": 1, "platform_slug": "psx", "platform_name": "PlayStation"},
        {"id": 2, "name": "Here", "fs_name": real.name, "fs_path": str(tmp_path),
         "size_bytes": 1, "platform_slug": "psx", "platform_name": "PlayStation"},
    ]))

    got = _run(rr.list_missing_roms(_FakeRequest({Scope.ROMS_WRITE})))
    assert [r["id"] for r in got["roms"]] == [1]
    assert got["count"] == 1
