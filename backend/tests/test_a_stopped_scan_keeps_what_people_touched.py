"""Undoing a scan's own work must not undo somebody else's.

A stopped scan takes back the rows it created, so that the rename adoption can
still pair them on a later run. That was written thinking of rows nobody had
seen yet - and on a real library it is not true. A scan of a big shelf runs for
many minutes, every row is visible and playable the moment it lands, and
`rom_handler.delete` says in its own docstring that savestates, memory cards and
play history follow the row by cascade.

So: a scan adds a freshly copied game at minute five, somebody plays it and
saves at minute ten, the administrator presses Stop at minute twenty - and the
save is gone, while the line on screen reads "nothing was marked missing".
Save games are the one thing here that cannot be rebuilt from the disk, and the
owner has lost them to this class of defect three times.

A row a person has touched stays. The adoption gives up on that one, which is
the smaller loss by a wide margin.

The same exit has a second half. Disc grouping edits rows that were ALREADY
HERE - a disc found now marks a disc found last year as an extra, and the
listings filter extras out. Undone halfway, that older game is simply gone from
the library with nothing deleted and nothing marked missing. Grouping is
therefore held back until the walk finishes, so a stopped scan never did it.
"""

from __future__ import annotations

import types

import pytest


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


@pytest.fixture
def scan(tmp_path, monkeypatch):
    from handler.filesystem import rom_scanner as scanner

    library = tmp_path / "roms" / "psx"
    library.mkdir(parents=True)
    for name in ("one.iso", "two.iso"):
        (library / name).write_bytes(b"x" * 8)

    seen = types.SimpleNamespace(deleted=[], grouped=[], restored=[], next_id=500,
                                 touched=set())

    async def _nothing(*a, **k):
        return None

    async def _restore(ids, **k):
        seen.restored.append(sorted(ids))

    async def _delete(rom_id, **k):
        seen.deleted.append(rom_id)
        return True

    async def _upsert(*a, **k):
        seen.next_id += 1
        return types.SimpleNamespace(id=seen.next_id)

    async def _groups(platform_id, assignments, **k):
        seen.grouped.append(platform_id)

    async def _touched(ids, **k):
        return {i for i in ids if i in seen.touched}

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _fake_async([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _fake_async({}))
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert", _fake_async(
        types.SimpleNamespace(id=1, slug="psx", fs_slug="psx", scan_exclude=None)))
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _fake_async([11, 22]))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _restore)
    monkeypatch.setattr(scanner.rom_handler, "delete", _delete)
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data", _touched)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _fake_async(None))
    monkeypatch.setattr(scanner.rom_handler, "upsert", _upsert)
    monkeypatch.setattr(scanner.rom_handler, "apply_disk_groups", _groups)
    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _fake_async([]))
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([]))
    monkeypatch.setattr(scanner, "_announce_scan_finished", _nothing)
    scanner.reset_scan_progress()
    return scanner, seen, tmp_path


def _stop_after_first(scanner, seen):
    """Create rows, then ask the scan to stop mid-walk."""
    real = scanner.rom_handler.upsert
    created = []

    async def _upsert_then_stop(*a, **k):
        row = await real(*a, **k)
        created.append(row.id)
        scanner.request_scan_stop()
        return row

    scanner.rom_handler.upsert = _upsert_then_stop
    return created


@pytest.mark.asyncio
async def test_a_row_somebody_saved_against_is_kept(scan):
    scanner, seen, tmp_path = scan
    created = _stop_after_first(scanner, seen)
    seen.touched = {501}                      # the first row this run creates

    stats = await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert stats.get("cancelled") is True
    assert 501 not in seen.deleted, (
        "przerwany skan skasowal wiersz, do ktorego ktos ma zapis gry - kaskada "
        "zabiera savestate'y, karty pamieci i historie grania"
    )
    assert created and set(seen.deleted) == set(created) - {501}


@pytest.mark.asyncio
async def test_untouched_rows_are_still_taken_back(scan):
    """The other half. Keeping everything would put the rename adoption back in
    the state it could never recover from."""
    scanner, seen, tmp_path = scan
    created = _stop_after_first(scanner, seen)
    seen.touched = set()

    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert seen.deleted == created and created


@pytest.mark.asyncio
async def test_a_stopped_scan_leaves_disc_grouping_alone(scan):
    """Grouping edits rows that were here before this run, and the listings
    hide whatever it marks as an extra."""
    scanner, seen, tmp_path = scan
    _stop_after_first(scanner, seen)

    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert seen.grouped == [], (
        "przerwany skan zdazyl przegrupowac plyty, wiec stara gra znika z "
        "listingow, choc nic nie zostalo skasowane"
    )


@pytest.mark.asyncio
async def test_a_finished_scan_still_groups_them(scan):
    """Held back, not dropped."""
    scanner, seen, tmp_path = scan

    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert seen.grouped == [1], "ukonczony skan przestal grupowac plyty"
    assert seen.deleted == []
