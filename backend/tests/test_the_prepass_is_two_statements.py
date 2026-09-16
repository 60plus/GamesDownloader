"""The pre-pass costs two statements, not two per platform.

Before walking the directories a scan takes a snapshot of what is currently on
disk and then marks every ROM missing, so the walk can un-mark what it finds.
That has to happen up front rather than per directory, because several alias
folders resolve to one platform row and the last empty alias would otherwise
re-mark what the populated one had just found.

Up front, though, is not the same as one platform at a time. It ran a SELECT and
an UPDATE for each platform, and GD creates a folder for every platform it
knows: measured on a real install, 214 of the scan's 420 statements were this
loop, and 192 of those were for platforms holding nothing.

Both questions are table-wide. Asking them table-wide is two statements whatever
the platform count, and the answers are identical - every ROM belongs to a
platform, so "every platform's rows" and "every row" are the same set.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from models.rom import Rom
from models.rom_platform import RomPlatform


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        for pid, slug in ((1, "psx"), (2, "snes"), (3, "amiga")):
            session.add(RomPlatform(id=pid, fs_slug=slug, slug=slug, name=slug.upper()))
        rid = 0
        for pid in (1, 2, 3):
            for n in (1, 2):
                rid += 1
                session.add(Rom(
                    id=rid, platform_id=pid, fs_name=f"{pid}-{n}.rom",
                    fs_name_no_ext=f"{pid}-{n}", fs_extension="rom",
                    fs_path=f"/roms/{pid}", fs_size_bytes=1,
                    missing_from_fs=(rid == 6),
                ))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_snapshot_covers_every_platform_at_once(db):
    """Five of the six rows are present; the sixth was already missing and is
    not evidence of anything."""
    ids = await rom_handler.present_ids(session=db)
    assert sorted(ids) == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_one_platform_can_still_be_asked_about(db):
    """The folder-gone cleanup at the end of a scan asks about exactly one."""
    assert sorted(await rom_handler.present_ids(2, session=db)) == [3, 4]


@pytest.mark.asyncio
async def test_marking_everything_missing_reaches_every_platform(db):
    await rom_handler.mark_all_missing(session=db)
    await db.commit()
    assert await rom_handler.present_ids(session=db) == []


@pytest.mark.asyncio
async def test_marking_one_platform_leaves_the_others_alone(db):
    """The cleanup for a platform whose folder disappeared must not touch the
    rest of the library."""
    await rom_handler.mark_all_missing(1, session=db)
    await db.commit()
    assert sorted(await rom_handler.present_ids(session=db)) == [3, 4, 5]


def test_the_scan_asks_once_rather_than_per_platform():
    import io
    import pathlib

    scanner = (pathlib.Path(__file__).resolve().parent.parent
               / "handler" / "filesystem" / "rom_scanner.py")
    source = io.open(scanner, encoding="utf-8").read()
    at = source.index("present_before")
    block = source[at:at + 900]
    assert "for p in await rom_platform_handler.get_all_simple()" not in block, (
        "przebieg wstepny nadal chodzi platforma po platformie"
    )
