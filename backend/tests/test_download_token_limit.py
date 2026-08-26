"""A link that says it may be used once has to be usable once.

Two separate things were letting it be used more, and each on its own was
enough.

The count was taken at the end, once the file had gone over in full - which is
the only honest place to count it if the link is resumable, and no place at all
to enforce a limit from. Ask for byte nought, then ask for the rest: the whole
file arrives as two requests of which neither took the file, so neither spends a
use. A link limited to one download and given no expiry was a permanent public
address for the file behind it.

And the check and the increment sat at opposite ends of a transfer that runs for
minutes. Three requests arriving together all read a count of nought, all passed
the check, and all three were served.

So a limited link is served whole or not at all, and the use is taken before a
byte moves. That costs resuming, which is a real cost - resuming is here because
a GOG installer failing at ninety percent used to start again from zero - so it
is paid only by links that ask for a limit. A link with no limit resumes exactly
as before.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.download_token_handler import download_token_handler
from models.download_token import DownloadToken


@pytest_asyncio.fixture
async def db(monkeypatch):
    """A real database.

    Patched on the handler's own module and not on the one it imported from:
    the import is at the top of the file, so the name was bound when the module
    loaded and replacing the original leaves the handler holding the old one.
    A fixture that patches the wrong module still runs, still passes, and tests
    nothing at all.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(DownloadToken.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "handler.database.download_token_handler.async_session_factory", maker)
    yield maker
    await engine.dispose()


async def _token(maker, **kw) -> int:
    base = dict(token="t0ken", file_id=1, file_name="game.zip", created_by="admin",
                max_downloads=1, download_count=0, is_active=True)
    base.update(kw)
    async with maker() as session:
        row = DownloadToken(**base)
        session.add(row)
        await session.commit()
        return row.id


async def _count(maker, token_id: int) -> int:
    async with maker() as session:
        row = (await session.execute(
            select(DownloadToken).where(DownloadToken.id == token_id))).scalar_one()
        return row.download_count


@pytest.mark.asyncio
async def test_a_one_use_link_gives_out_one_use(db):
    tid = await _token(db)
    assert await download_token_handler.reserve_use(tid) is True
    assert await download_token_handler.reserve_use(tid) is False
    assert await _count(db, tid) == 1


@pytest.mark.asyncio
async def test_requests_arriving_together_do_not_all_get_one(db):
    """The race. All three used to read a count of nought before any of them
    wrote, so all three were served from a link limited to a single download."""
    tid = await _token(db)

    granted = await asyncio.gather(*[download_token_handler.reserve_use(tid) for _ in range(3)])

    assert sum(1 for g in granted if g) == 1, f"{sum(granted)} kopii z linku na jedno uzycie"
    assert await _count(db, tid) == 1


@pytest.mark.asyncio
async def test_a_link_for_three_hands_out_three(db):
    tid = await _token(db, max_downloads=3)
    granted = await asyncio.gather(*[download_token_handler.reserve_use(tid) for _ in range(6)])
    assert sum(1 for g in granted if g) == 3
    assert await _count(db, tid) == 3


@pytest.mark.asyncio
async def test_a_transfer_that_dropped_gives_its_use_back(db):
    """Taking the use up front is the only place a limit can be held, so the
    other half of that has to be here: a link for one download must not be spent
    by a request that died at four percent."""
    tid = await _token(db)
    assert await download_token_handler.reserve_use(tid) is True
    await download_token_handler.release_use(tid)

    assert await _count(db, tid) == 0
    assert await download_token_handler.reserve_use(tid) is True


@pytest.mark.asyncio
async def test_giving_back_more_than_was_taken_does_not_go_negative(db):
    tid = await _token(db)
    await download_token_handler.release_use(tid)
    await download_token_handler.release_use(tid)
    assert await _count(db, tid) == 0


@pytest.mark.asyncio
async def test_a_revoked_link_gets_nothing(db):
    tid = await _token(db, is_active=False)
    assert await download_token_handler.reserve_use(tid) is False


@pytest.mark.asyncio
async def test_an_unlimited_link_reserves_nothing(db):
    """It has no limit to hold, so it is served the resumable way and its count
    is written afterwards. reserve_use refusing here is what routes it there."""
    tid = await _token(db, max_downloads=None)
    assert await download_token_handler.reserve_use(tid) is False


@pytest.mark.asyncio
async def test_running_out_reads_as_exhausted_and_not_as_revoked(db):
    """Exhaustion used to switch the link off, and every place that works out a
    status asks about that switch first - so a link that ran out of uses always
    reported that somebody had revoked it, and the branch that says exhausted
    could not be reached at all."""
    from endpoints.settings.download_tokens_router import _token_status

    tid = await _token(db)
    await download_token_handler.reserve_use(tid)

    async with db() as session:
        row = (await session.execute(
            select(DownloadToken).where(DownloadToken.id == tid))).scalar_one()

    assert row.is_active is True, "wyczerpanie nadal wylacza link"
    assert _token_status(row) == "exhausted"
    assert download_token_handler.is_valid(row) is False
