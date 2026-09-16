"""Merging a renamed file must not make anybody choose between two histories.

A scan that spots a rename moves the file fields onto the row the file was
renamed FROM and deletes the new row, so the cover, the description and the
saves from before the rename stay attached to the game. `rom_saves`,
`rom_save_states` and `rom_plays` hang off the deleted row by cascade, so a
player who launched the new row during the scan - it is visible and playable the
moment it lands, and a large library takes many minutes - would lose what they
did in that session.

The guard for that gave up on the merge instead. It protected the one save made
during the scan and, in exchange, abandoned everything from before the rename:
the old row keeps `missing_from_fs`, which every listing, count and search
filters out; no later scan can pair it again, because the new name is already in
the database and never enters `created_ids` a second time; and it lands on the
missing-entries screen, where one click now removes the savestate and memory
card FILES from disk as well.

So the data is carried across instead, and what the schema allows decides how:

  rom_plays        one row per (user, rom), holding launches, seconds and a
                   last-played stamp. Two rows for one game add up.
  rom_save_states  one row per (user, rom, slot). Slots are numbers, so a
                   colliding state takes the first free one.
  rom_saves        ONE memory card per (user, rom). Two cards cannot become
                   one, so a collision there refuses the whole merge and leaves
                   both rows - two entries a person can sort out, rather than a
                   card replaced without asking.
"""

from __future__ import annotations

import types
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

OLD, NEW = 1, 2
ME, SOMEBODY_ELSE = 7, 9


@pytest_asyncio.fixture
async def db():
    from models.rom import Rom
    from models.rom_platform import RomPlatform
    from models.rom_play import RomPlay
    from models.rom_save_state import RomSave, RomSaveState

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
        await conn.run_sync(RomSaveState.__table__.create)
        await conn.run_sync(RomSave.__table__.create)
        await conn.run_sync(RomPlay.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    def _rom(rid, fs_name):
        return Rom(id=rid, platform_id=1, fs_name=fs_name, fs_name_no_ext=fs_name,
                   fs_extension="sfc", fs_path="/roms/snes", name=fs_name,
                   slug=fs_name.lower(), missing_from_fs=False, fs_size_bytes=10)

    async with maker() as session:
        session.add(RomPlatform(id=1, slug="snes", name="SNES", fs_slug="snes"))
        session.add(_rom(OLD, "Zelda (USA).sfc"))
        session.add(_rom(NEW, "Zelda (USA) (Rev 1).sfc"))
        await session.commit()
    yield maker
    await engine.dispose()


def _state(rom_id, user_id, slot, name="s.state"):
    from models.rom_save_state import RomSaveState
    return RomSaveState(rom_id=rom_id, user_id=user_id, slot=slot,
                        file_name=name, file_path="/saves", file_size_bytes=1)


def _card(rom_id, user_id, name="card.srm"):
    from models.rom_save_state import RomSave
    return RomSave(rom_id=rom_id, user_id=user_id, file_name=name,
                   file_path="/saves", file_size_bytes=1)


def _play(rom_id, user_id, count, seconds, when):
    from models.rom_play import RomPlay
    return RomPlay(rom_id=rom_id, user_id=user_id, play_count=count,
                   seconds_played=seconds, last_played_at=when)


# ── Savestates ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_savestate_that_would_collide_takes_a_free_slot(db):
    from handler.database.rom_handler import RomHandler
    from models.rom_save_state import RomSaveState

    async with db() as session:
        session.add(_state(OLD, ME, 0, "przed.state"))
        session.add(_state(NEW, ME, 0, "w trakcie.state"))
        await session.commit()

        assert await RomHandler().move_player_data(NEW, OLD, session=session) is True
        await session.commit()

        mine = (await session.execute(
            select(RomSaveState).where(RomSaveState.rom_id == OLD)
        )).scalars().all()

    assert {s.file_name for s in mine} == {"przed.state", "w trakcie.state"}, (
        "scalenie zgubilo jeden z savestate'ow"
    )
    assert sorted(s.slot for s in mine) == [0, 1], (
        "kolidujacy savestate nie dostal wolnego slotu"
    )


@pytest.mark.asyncio
async def test_another_persons_slot_is_not_a_collision(db):
    """Slots are per user. Treating them as global would push people's states
    around for no reason."""
    from handler.database.rom_handler import RomHandler
    from models.rom_save_state import RomSaveState

    async with db() as session:
        session.add(_state(OLD, SOMEBODY_ELSE, 0))
        session.add(_state(NEW, ME, 0))
        await session.commit()
        await RomHandler().move_player_data(NEW, OLD, session=session)
        await session.commit()

        mine = (await session.execute(
            select(RomSaveState).where(RomSaveState.rom_id == OLD,
                                       RomSaveState.user_id == ME)
        )).scalars().all()

    assert [s.slot for s in mine] == [0]


# ── Play history ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_play_records_for_one_game_add_up(db):
    from handler.database.rom_handler import RomHandler
    from models.rom_play import RomPlay

    before = datetime(2026, 1, 1, 12, 0, 0)
    during = datetime(2026, 9, 6, 9, 30, 0)
    async with db() as session:
        session.add(_play(OLD, ME, 40, 3600, before))
        session.add(_play(NEW, ME, 1, 300, during))
        await session.commit()
        await RomHandler().move_player_data(NEW, OLD, session=session)
        await session.commit()

        rows = (await session.execute(
            select(RomPlay).where(RomPlay.rom_id == OLD))).scalars().all()

    assert len(rows) == 1, "zostaly dwa wiersze historii dla jednej gry"
    assert rows[0].play_count == 41
    assert rows[0].seconds_played == 3900
    assert rows[0].last_played_at == during, "ostatnie granie cofnelo sie w czasie"


# ── The memory card, which is the one that cannot be merged ──────────────────

@pytest.mark.asyncio
async def test_two_memory_cards_refuse_the_whole_move(db):
    """One card per game per person. Picking a winner would delete a save
    nobody was asked about, so nothing moves and the caller keeps both rows."""
    from handler.database.rom_handler import RomHandler
    from models.rom_play import RomPlay
    from models.rom_save_state import RomSave

    async with db() as session:
        session.add(_card(OLD, ME, "przed.srm"))
        session.add(_card(NEW, ME, "w trakcie.srm"))
        session.add(_play(NEW, ME, 1, 60, datetime(2026, 9, 6)))
        await session.commit()

        assert await RomHandler().move_player_data(NEW, OLD, session=session) is False
        await session.commit()

        cards = (await session.execute(select(RomSave))).scalars().all()
        plays = (await session.execute(select(RomPlay))).scalars().all()

    assert {(c.rom_id, c.file_name) for c in cards} == {
        (OLD, "przed.srm"), (NEW, "w trakcie.srm")}, "karta pamieci zostala ruszona"
    assert [p.rom_id for p in plays] == [NEW], (
        "odmowa przeniesienia zostawila polowe danych po drugiej stronie"
    )


@pytest.mark.asyncio
async def test_one_card_on_each_side_for_different_people_is_fine(db):
    from handler.database.rom_handler import RomHandler
    from models.rom_save_state import RomSave

    async with db() as session:
        session.add(_card(OLD, SOMEBODY_ELSE, "ich.srm"))
        session.add(_card(NEW, ME, "moja.srm"))
        await session.commit()

        assert await RomHandler().move_player_data(NEW, OLD, session=session) is True
        await session.commit()

        cards = (await session.execute(select(RomSave))).scalars().all()

    assert {c.rom_id for c in cards} == {OLD}


# ── What the scan does with the answer ───────────────────────────────────────

def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


@pytest.mark.asyncio
async def test_a_played_arrival_is_merged_after_its_data_is_carried_across(monkeypatch):
    """The whole point. Before this the merge was abandoned and the row holding
    the pre-rename saves stayed missing for ever."""
    from handler.filesystem import rom_scanner as scanner

    moved: list = []
    adopted: list = []

    async def _move(from_id, to_id):
        moved.append((from_id, to_id))
        return True

    async def _adopt(old_id, new_id):
        adopted.append((old_id, new_id))
        return True

    monkeypatch.setattr(scanner.rom_handler, "move_player_data", _move)
    monkeypatch.setattr(scanner.rom_handler, "adopt_renamed", _adopt)

    merged = await scanner._merge_renamed([(OLD, NEW)], {NEW})

    assert moved == [(NEW, OLD)], "dane gracza nie zostaly przeniesione"
    assert adopted == [(OLD, NEW)], "scalenie nie doszlo do skutku"
    assert merged == 1


@pytest.mark.asyncio
async def test_a_refused_move_leaves_both_rows_alone(monkeypatch):
    from handler.filesystem import rom_scanner as scanner

    adopted: list = []

    monkeypatch.setattr(scanner.rom_handler, "move_player_data", _fake_async(False))
    monkeypatch.setattr(scanner.rom_handler, "adopt_renamed",
                        lambda *a, **k: adopted.append(a))

    assert await scanner._merge_renamed([(OLD, NEW)], {NEW}) == 0
    assert adopted == [], (
        "scalenie poszlo mimo odmowy przeniesienia, wiec karta pamieci zniknela "
        "przez kaskade"
    )


@pytest.mark.asyncio
async def test_an_untouched_arrival_is_merged_without_moving_anything(monkeypatch):
    """The common case, and it must not pay for the rare one."""
    from handler.filesystem import rom_scanner as scanner

    moved: list = []

    async def _move(from_id, to_id):
        moved.append((from_id, to_id))
        return True

    monkeypatch.setattr(scanner.rom_handler, "move_player_data", _move)
    monkeypatch.setattr(scanner.rom_handler, "adopt_renamed", _fake_async(True))

    assert await scanner._merge_renamed([(OLD, NEW)], set()) == 1
    assert moved == [], "pytanie o dane gracza zadawane dla kazdej pary"
