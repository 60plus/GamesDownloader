"""What a scan that dies partway is allowed to take with it, and what it must say.

The exception exit does three things, and each of them was wrong in a different
direction.

IT DELETED EVERYTHING IT HAD MADE. The reason to take back a row this run
created is narrow and worth stating: adoption can only ever pair a vanished row
with a row the CURRENT run created, so a new row left behind by a failed run is
one no future scan will make again - the old row holding the artwork, the saves
and the play history stays missing for good and the shelf shows the title twice.
That argument covers exactly the rows a rename would have absorbed. It does not
cover a genuinely new ROM, which the next scan simply finds again. Deleting
those as well meant one transient database error near the end of a long scan
threw away every row the run had made, and the next scan re-read and re-hashed
the whole library from nothing.

IT DID THE EXPENSIVE HALF WHILE THE PROCESS WAS DYING. `except BaseException`
catches `asyncio.CancelledError`, which is how a container stop reaches a scan
running as a background task, and shutdown is on a five second clock. A delete
per row, each in its own transaction, does not finish - so the run was undone
PARTWAY, and the second cancellation went through the inner `except Exception`
untouched, skipping the progress reset and the log.

IT ASKED FOR THE RENAMES TOO LATE, AND THE SHUTDOWN EXIT NEVER ASKED. The
vanished side of a rename is found by its missing flag, and the failure exit put
the flags back first - so it found no donor and took nothing back, while the log
said the library was as it was. The shutdown exit, kept cheap for the reason
above, left every rename row in place. Either way the old row holding the
artwork, the saves and the play history stayed missing for good. Both exits now
read the renames before the flags go back and take those rows back in one
statement, which fits the shutdown clock.

IT SAID NOTHING. Both other exits announce, because the views hang their reload
on that event and the sidebar clears its spinner there. This one left the bar
turning, and the watchdog eventually filled it in as an ordinary finish.
"""

from __future__ import annotations

import asyncio
import types

import pytest

SHA = "a" * 40


async def _nothing_moved(*_a, **_k):
    """Nothing in these trees moved: every file found is new."""
    return []


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


async def _nothing(*a, **k):
    return None


@pytest.fixture
def scan(tmp_path, monkeypatch):
    """A walk over four files that creates three rows and then falls over.

    The tests that were here before all failed on the FIRST row lookup, so
    `created_ids` was empty and the loop that takes rows back never turned once.
    """
    from handler.filesystem import rom_scanner as scanner

    shelf = tmp_path / "roms" / "psx"
    shelf.mkdir(parents=True)
    for name in ("a.iso", "b.iso", "c.iso", "d.iso"):
        (shelf / name).write_bytes(b"x" * 10)

    made: list[int] = []
    log: dict = {"restored": [], "deleted": [], "taken_back": [], "announced": []}
    # The missing flag as the database keeps it. The fake that stood here before
    # answered with the vanished row whatever the flags said, and that is how a
    # failure exit asking for renames AFTER putting the flags back looked like it
    # worked: the real query filters on the flag and, by then, finds nothing.
    missing: set[int] = set()

    async def _upsert(*a, **k):
        if len(made) == 3:
            raise RuntimeError("baza odmowila w polowie skanu")
        made.append(101 + len(made))
        return types.SimpleNamespace(id=made[-1])

    async def _mark_all_missing(*a, **k):
        missing.add(55)

    async def _restore(ids, **k):
        log["restored"].append(sorted(ids))
        missing.difference_update(ids)

    async def _vanished(*a, **k):
        return [
            {"id": 55, "platform_id": 1, "sha1": SHA, "size": 10,
             "track_of": None, "ext": "iso"},
        ] if 55 in missing else []

    async def _delete(rom_id, **k):
        log["deleted"].append(rom_id)
        return True

    async def _delete_many(rom_ids, **k):
        log["taken_back"].append(sorted(rom_ids))
        return len(rom_ids)

    async def _announce(stats):
        log["announced"].append(dict(stats))

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _fake_async([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _fake_async({}))
    monkeypatch.setattr(
        scanner.rom_platform_handler, "upsert",
        _fake_async(types.SimpleNamespace(id=1, slug="psx", fs_slug="psx",
                                          scan_exclude=None)))
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _fake_async([55]))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _mark_all_missing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _restore)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _fake_async(None))
    monkeypatch.setattr(scanner.rom_handler, "rows_named_in",
                        _nothing_moved)
    monkeypatch.setattr(scanner.rom_handler, "upsert", _upsert)
    monkeypatch.setattr(scanner.rom_handler, "delete", _delete)
    monkeypatch.setattr(scanner.rom_handler, "delete_many", _delete_many, raising=False)
    monkeypatch.setattr(scanner, "_announce_scan_finished", _announce)
    # One vanished row that matches the FIRST arrival, so a rename really is on
    # the table - and two arrivals that match nothing, which is the ordinary
    # case of a scan simply finding new games. The vanished row is only there
    # while its flag says so.
    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _vanished)
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([
        {"id": 101, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
        {"id": 102, "platform_id": 1, "sha1": "b" * 40, "size": 10,
         "track_of": None, "ext": "iso"},
        {"id": 103, "platform_id": 1, "sha1": "c" * 40, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data", _fake_async(set()))
    return scanner, tmp_path / "roms", log, made


@pytest.mark.asyncio
async def test_the_walk_really_creates_rows_before_it_dies(scan):
    """A guard on the fixture. Every assertion below is about what happens to
    the rows a run created, and the tests this file replaces had none."""
    scanner, root, _log, made = scan

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(root))

    assert made == [101, 102, 103], (
        "walk nie utworzyl wierszy, wiec ten plik nie bada tego, o czym mysli"
    )


@pytest.mark.asyncio
async def test_only_the_rows_a_rename_would_have_absorbed_are_taken_back(scan):
    scanner, root, log, _made = scan

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(root))

    assert log["taken_back"] == [[101]], (
        "awaria nie cofa wiersza zmiany nazwy (dawca szukany po przywroceniu flag), "
        "albo cofa CALY dorobek biegu - a wiersz bez dawcy nastepny skan po prostu "
        "znajdzie znowu"
    )
    assert log["deleted"] == [], "cofanie wiersz po wierszu zamiast jednym poleceniem"


@pytest.mark.asyncio
async def test_the_flags_go_back_first(scan):
    """The cheaper half and the more important one: a failure while removing
    rows must not leave the library with half its shelf marked missing."""
    scanner, root, log, _made = scan

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(root))

    assert log["restored"] == [[55]]


@pytest.mark.asyncio
async def test_a_row_somebody_played_is_never_taken_back(scan, monkeypatch):
    """Deleting a ROM row takes its savestates, memory cards and play history by
    cascade. A scan of a large library runs for many minutes with every new row
    visible and playable the moment it lands."""
    scanner, root, log, _made = scan
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data",
                        _fake_async({101}))

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(root))

    assert log["deleted"] == [] and log["taken_back"] == [], (
        "skasowano wiersz, przeciw ktoremu ktos juz gral albo zapisywal"
    )


@pytest.mark.asyncio
async def test_the_failure_is_announced(scan):
    """Both other exits say they ended. The views hang their reload on this
    event and the sidebar clears its spinner there."""
    scanner, root, log, _made = scan

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(root))

    assert log["announced"], (
        "wyjscie przez wyjatek jako jedyne nic nie oglasza, wiec pasek kreci "
        "sie dalej, a straznik dopisuje mu zwykle zakonczenie"
    )
    assert log["announced"][-1].get("error") == "failed", (
        "zdarzenie nie mowi, ze skan PADL - ekran narysuje zwykle zakonczenie"
    )


@pytest.mark.asyncio
async def test_the_original_failure_still_reaches_the_caller(scan):
    scanner, root, _log, _made = scan

    with pytest.raises(RuntimeError, match="baza odmowila"):
        await scanner.scan_roms_path(str(root))


# ── Shutting down ────────────────────────────────────────────────────────────

def _cancelled_after_three(scanner, made, monkeypatch):
    async def _cancel(*a, **k):
        if len(made) == 3:
            raise asyncio.CancelledError()
        made.append(101 + len(made))
        return types.SimpleNamespace(id=made[-1])

    monkeypatch.setattr(scanner.rom_handler, "upsert", _cancel)


@pytest.mark.asyncio
async def test_a_cancelled_scan_does_the_cheap_half_only(scan, monkeypatch):
    """A container stop cancels the background task and gives it five seconds.
    A delete per row, each its own transaction, does not finish in that - so the
    run gets undone PARTWAY, which is the one outcome nobody wanted."""
    scanner, root, log, made = scan
    _cancelled_after_three(scanner, made, monkeypatch)

    with pytest.raises(asyncio.CancelledError):
        await scanner.scan_roms_path(str(root))

    assert log["restored"] == [[55]], "flagi nie wrocily przy zamykaniu"
    assert log["deleted"] == [], (
        "przy zamykaniu serwera skaner zabiera sie za kasowanie wierszy po "
        "jednym, a ma na to piec sekund - wiec bieg zostaje cofniety CZESCIOWO"
    )


@pytest.mark.asyncio
async def test_a_rename_is_taken_back_on_shutdown_too(scan, monkeypatch):
    """Left in place, the new row is one no later scan creates again, so the old
    row with the saves is never paired and stays missing for good. One
    statement for the renames only, not a delete per row this run made."""
    scanner, root, log, made = scan
    _cancelled_after_three(scanner, made, monkeypatch)

    with pytest.raises(asyncio.CancelledError):
        await scanner.scan_roms_path(str(root))

    assert log["taken_back"] == [[101]], (
        "zamkniecie serwera w trakcie skanu zostawia wiersz zmiany nazwy, wiec "
        "stary wiersz z zapisami zostaje brakujacy na zawsze"
    )


@pytest.mark.asyncio
async def test_a_played_rename_is_not_taken_back_on_shutdown_either(scan, monkeypatch):
    scanner, root, log, made = scan
    _cancelled_after_three(scanner, made, monkeypatch)
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data", _fake_async({101}))

    with pytest.raises(asyncio.CancelledError):
        await scanner.scan_roms_path(str(root))

    assert log["taken_back"] == [] and log["deleted"] == [], (
        "przy zamykaniu skasowano wiersz, przeciw ktoremu ktos juz gral"
    )


@pytest.mark.asyncio
async def test_a_second_cancellation_while_reading_still_puts_the_flags_back(
    scan, monkeypatch
):
    """Reading the renames first widens the window a second cancellation can
    land in. Landing there must cost the renames, never the flags: a library
    left with its shelf marked missing is the outcome all of this exists to
    prevent."""
    scanner, root, log, made = scan
    _cancelled_after_three(scanner, made, monkeypatch)

    async def _cancelled_again(*a, **k):
        raise asyncio.CancelledError()

    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _cancelled_again)

    with pytest.raises(asyncio.CancelledError):
        await scanner.scan_roms_path(str(root))

    assert log["restored"] == [[55]], (
        "drugie anulowanie w trakcie czytania zmian nazw zostawilo biblioteke ciemna"
    )
    assert log["taken_back"] == []


# ── The rule both exits share ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_arrival_somebody_played_still_counts_as_a_candidate(monkeypatch):
    """`adopt_renamed_files` refuses a pair unless it is the only candidate on
    either side, and its docstring says why: SHA-1 equality is not identity.

    The guard for player data was applied to the LIST HANDED IN, so a key with
    two arrivals became a key with one as soon as somebody played one of them -
    and the pair was then accepted. Two rows a person can fix is the outcome
    that rule exists to produce; a donor merged into the wrong one of two
    identical files is not.
    """
    from handler.filesystem import rom_scanner as scanner

    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _fake_async([
        {"id": 55, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([
        {"id": 101, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
        {"id": 102, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data",
                        _fake_async({101}))

    pairs = await scanner._renames_this_run([101, 102], {55}, {1})

    assert pairs == [], (
        "zawezenie listy kandydatow o wiersze z danymi gracza robi z dwoch "
        "kandydatow jednego, wiec dawca zostaje przypiety do JEDNEJ Z DWOCH "
        "identycznych kopii - dokladnie temu ten warunek mial zapobiegac"
    )


@pytest.mark.asyncio
async def test_an_unambiguous_rename_is_still_adopted(monkeypatch):
    """The legal case. This whole mechanism exists so that renaming a file does
    not cost somebody their artwork, saves and play history."""
    from handler.filesystem import rom_scanner as scanner

    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _fake_async([
        {"id": 55, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([
        {"id": 101, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data",
                        _fake_async(set()))

    assert await scanner._renames_this_run([101], {55}, {1}) == [(55, 101)]


@pytest.mark.asyncio
async def test_a_played_arrival_is_still_a_rename(monkeypatch):
    """Whether somebody played it is not part of "is this the same file renamed".

    It used to be, and the answer was to abandon the merge - which protected one
    session and gave up every save from before the rename. The pair is found
    here; what to do about the player's data is decided where the merge happens,
    and the failure exit uses the same list to know what it may take back.
    """
    from handler.filesystem import rom_scanner as scanner

    monkeypatch.setattr(scanner.rom_handler, "missing_with_hashes", _fake_async([
        {"id": 55, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "rows_for_matching", _fake_async([
        {"id": 101, "platform_id": 1, "sha1": SHA, "size": 10,
         "track_of": None, "ext": "iso"},
    ]))
    monkeypatch.setattr(scanner.rom_handler, "ids_with_player_data",
                        _fake_async({101}))

    assert await scanner._renames_this_run([101], {55}, {1}) == [(55, 101)]


# ── The one statement, against a real database ──────────────────────────────

@pytest.mark.asyncio
async def test_taking_rows_back_in_one_statement_takes_exactly_those():
    """Everything above fakes the handler, which is how the flag bug hid. The
    bulk delete the shutdown exit now relies on is run for real."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from handler.database.rom_handler import rom_handler
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            session.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
            for rom_id in (55, 101, 102):
                session.add(Rom(id=rom_id, platform_id=1, fs_name=f"{rom_id}.iso",
                                fs_name_no_ext=str(rom_id), fs_extension="iso",
                                fs_path="/roms/psx", fs_size_bytes=10))
            await session.commit()

            assert await rom_handler.delete_many([], session=session) == 0
            assert await rom_handler.delete_many([101], session=session) == 1
            await session.commit()

            left = (await session.execute(select(Rom.id).order_by(Rom.id))).scalars().all()
            assert left == [55, 102], "zabrano inne wiersze niz podane"
    finally:
        await engine.dispose()
