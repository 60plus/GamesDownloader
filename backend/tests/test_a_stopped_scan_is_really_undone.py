"""Stopping a scan has to put the library back, all of it.

The stop exit restored the missing flags and left the rows the partial walk had
already CREATED sitting there. That reads as harmless until it meets the feature
this release is named for.

Rename 300 ROMs on disk and scan: the walk creates 300 new rows, and at the end,
once every directory has been walked, the adoption pairs each new row with the
old row whose content hash matches and carries the artwork, the saves and the
play history across. Press Stop after the first platform and:

  - the 300 new rows stay, because nothing removed them;
  - the old rows are restored to "present" although their files are gone, so
    they are not even listed on the missing-entries screen;
  - and no later scan can ever repair it. Adoption can only pair a donor with a
    row THIS scan created, and the rows now exist, so no scan will create them
    again. The old rows go missing for good and the only thing left to do with
    the row holding the saves is delete it.

So stopping is a full rollback now: what the run created goes with it. Rows
only, never files - the files on disk are what the next scan will find again.
"""

from __future__ import annotations

import types

import pytest


async def _nothing_moved(*_a, **_k):
    """Nothing in these trees moved: every file found is new."""
    return []


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """A one-platform tree, with the database replaced by a record of calls."""
    from handler.filesystem import rom_scanner as scanner

    library = tmp_path / "roms" / "psx"
    library.mkdir(parents=True)
    for name in ("one.iso", "two.iso"):
        (library / name).write_bytes(b"x" * 8)

    seen = types.SimpleNamespace(restored=[], deleted=[], next_id=500)

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

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _fake_async([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _fake_async({}))
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert", _fake_async(
        types.SimpleNamespace(id=1, slug="psx", fs_slug="psx", scan_exclude=None)))
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _fake_async([11, 22]))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _restore)
    monkeypatch.setattr(scanner.rom_handler, "delete", _delete)
    # Nobody has played anything in these tests. Stubbed because the rollback
    # asks unconditionally now: a row somebody saved against is kept, since
    # deleting it would take their savestates by cascade.
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data", _fake_async(set()))
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _fake_async(None))
    monkeypatch.setattr(scanner.rom_handler, "rows_named_in",
                        _nothing_moved)
    monkeypatch.setattr(scanner.rom_handler, "upsert", _upsert)
    monkeypatch.setattr(scanner.rom_handler, "apply_disk_groups", _nothing)
    # The adoption pass at the end of a completed walk. Empty here: what these
    # tests are about is which rows survive, not which get paired.
    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _fake_async([]))
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([]))
    monkeypatch.setattr(scanner, "_announce_scan_finished", _nothing)
    scanner.reset_scan_progress()
    return scanner, seen, tmp_path


@pytest.mark.asyncio
async def test_a_scan_that_finishes_keeps_what_it_created(scan):
    """The half that has to keep working. A rollback on the ordinary path would
    be a scan that never adds anything."""
    scanner, seen, tmp_path = scan
    stats = await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert stats["roms_new"] == 2
    assert seen.deleted == [], "zwykly skan skasowal to, co sam dodal"


@pytest.mark.asyncio
async def test_stopping_takes_back_the_rows_that_run_created(scan):
    scanner, seen, tmp_path = scan

    real_upsert = scanner.rom_handler.upsert

    async def _upsert_then_stop(*a, **k):
        row = await real_upsert(*a, **k)
        scanner.request_scan_stop()      # the Stop button, mid-walk
        return row

    scanner.rom_handler.upsert = _upsert_then_stop
    stats = await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert stats.get("cancelled") is True
    assert seen.deleted, (
        "przerwany skan zostawil wiersze, ktore sam utworzyl - adopcja po "
        "zmianie nazwy nigdy juz ich nie sparuje"
    )
    assert seen.restored == [[11, 22]], "przerwany skan nie przywrocil flag"


@pytest.mark.asyncio
async def test_stopping_removes_exactly_what_it_created_and_nothing_else(scan):
    scanner, seen, tmp_path = scan

    real_upsert = scanner.rom_handler.upsert
    created: list[int] = []

    async def _upsert_then_stop(*a, **k):
        row = await real_upsert(*a, **k)
        created.append(row.id)
        scanner.request_scan_stop()
        return row

    scanner.rom_handler.upsert = _upsert_then_stop
    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert seen.deleted == created, (
        "przerwany skan skasowal cos innego niz wlasnie utworzone wiersze"
    )
    assert 11 not in seen.deleted and 22 not in seen.deleted


@pytest.mark.asyncio
async def test_stopping_a_scan_that_added_nothing_deletes_nothing(scan, monkeypatch):
    """Every file already has a row, so the walk creates none. Stopping then has
    nothing to take back, and must not reach for the rows that were already
    here - which is the whole reason the rollback is keyed on what this run
    created rather than on what is new-looking."""
    scanner, seen, tmp_path = scan

    async def _existing(*a, **k):
        # Mid-walk, because starting a scan clears any stop asked for before it.
        scanner.request_scan_stop()
        return types.SimpleNamespace(id=11, fs_size_bytes=8, crc_hash="dead",
                                     md5_hash="beef", sha1_hash="cafe")

    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _existing)

    monkeypatch.setattr(scanner.rom_handler, "rows_named_in",

                        _nothing_moved)

    stats = await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert stats.get("cancelled") is True
    assert seen.deleted == []
    assert seen.restored == [[11, 22]]
