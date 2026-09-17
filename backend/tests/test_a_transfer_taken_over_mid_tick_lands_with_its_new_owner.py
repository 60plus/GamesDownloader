"""A transfer taken over while the monitor is busy lands with the account that took it.

The monitor loads every downloading row once a tick and works through them, and
one of them landing takes minutes: every file is virus scanned, then copied
between bind mounts. An administrator who takes the upload right away in that
time hands the account's transfers over (`hand_running_torrents_to`), but the
monitor was still holding rows read before the handover. So the next transfer in
the tick was weighed against the demoted account's allowance, and a game filed
in that window went to the demoted account.

The owner is now read when it decides something: each row as the tick reaches
it, and the transfer's current owner when its game is created.

A real database throughout, because the whole point is what it says NOW.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.torrent_download import TorrentDownload
from models.user import User

UPLOADER, ADMIN = 3, 1


@pytest_asyncio.fixture
async def maker(monkeypatch):
    from handler.database import session as S

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in (User, LibraryGame, LibraryFile, TorrentDownload):
            await conn.run_sync(table.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(S, "async_session_factory", factory)
    yield factory
    await engine.dispose()


def _transfer(row_id, **extra):
    fields = dict(
        id=row_id, title=f"Gra {row_id}", os="windows", download_dir=f"/d/{row_id}",
        status="downloading", created_by="gdtest",
        created_by_id=UPLOADER, uploaded_by_id=UPLOADER,
    )
    fields.update(extra)
    return TorrentDownload(**fields)


@pytest.mark.asyncio
async def test_a_game_filed_after_a_takeover_belongs_to_the_new_owner(maker, tmp_path, monkeypatch):
    import config
    from handler.torrent import seed_monitor as M
    from plugins import events

    download = tmp_path / "downloads" / "gra"
    download.mkdir(parents=True)
    (download / "gra.bin").write_bytes(b"x" * 10)

    async with maker() as db:
        # Taken over while it was being scanned: the row already says ADMIN.
        db.add(_transfer(9, status="complete", download_dir=str(download), created_by_id=ADMIN))
        await db.commit()

    # What the monitor was holding: the row as it read it at the start of the tick.
    held = SimpleNamespace(id=9, title="Gra 9", download_dir=str(download), os="windows",
                           library=None, created_by_id=UPLOADER, uploaded_by_id=UPLOADER)

    async def _clean(_files):
        return None

    async def _default_shelf(_td):
        return "CUSTOM", None

    monkeypatch.setattr(M, "_threat_in", _clean)
    monkeypatch.setattr(M, "_resolve_target_library", _default_shelf)
    monkeypatch.setattr(config, "BASE_PATH", str(tmp_path))
    monkeypatch.setattr(events, "game_added", lambda *a, **k: None)
    monkeypatch.setattr(events, "download_complete", lambda *a, **k: None)
    from handler.notifications import recently_added
    monkeypatch.setattr(recently_added, "schedule_library_game", lambda *a, **k: None)

    game_id, why_not, _code, _detail = await M._auto_register_game(held)

    assert game_id, f"gra nie powstala: {why_not}"
    async with maker() as db:
        game = await db.get(LibraryGame, game_id)
    assert game.published_by == ADMIN, (
        "gra z przejetego transferu trafila do konta, ktore stracilo prawo wgrywania"
    )
    assert game.uploaded_by == UPLOADER, "zginal slad po tym, kto transfer wniosl"


@pytest.mark.asyncio
async def test_the_next_transfer_in_the_tick_is_weighed_against_its_new_owner(maker, monkeypatch):
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH
    from handler.torrent.torrent_ownership import hand_running_torrents_to

    async with maker() as db:
        db.add(_transfer(1, transmission_id=1, info_hash="h1", total_size=0))
        db.add(_transfer(2, transmission_id=2, info_hash="h2", total_size=0))
        await db.commit()

    async def _get_torrent(ref):
        if ref == "h1":
            # The first transfer takes its time, and the upload right is taken
            # away meanwhile.
            async with maker() as db:
                await hand_running_torrents_to(UPLOADER, ADMIN, session=db)
            return {"hashString": "h1", "status": 4, "percentDone": 0.1,
                    "totalSize": 0, "rateDownload": 0, "eta": -1, "error": 0}
        return {"hashString": "h2", "status": 4, "percentDone": 0.1,
                "totalSize": 5000, "rateDownload": 0, "eta": -1, "error": 0}

    weighed: list = []

    async def _over_quota(td, total_size):
        weighed.append((td.id, td.created_by_id))
        return False

    async def _quiet(*a, **k):
        return None

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)
    monkeypatch.setattr(M, "_over_quota", _over_quota)
    monkeypatch.setattr(M, "_emit_to_owner", _quiet)

    await M._check_downloads()

    assert weighed == [(2, ADMIN)], (
        "drugi transfer w tym samym tiku zostal zwazony limitem konta, ktore juz "
        f"go nie posiada: {weighed}"
    )


@pytest.mark.asyncio
async def test_a_row_that_stopped_downloading_meanwhile_is_left_alone(maker, monkeypatch):
    """The same read settles a row paused or removed while the tick was busy
    elsewhere: it is no longer the monitor's to update."""
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    async with maker() as db:
        db.add(_transfer(1, transmission_id=1, info_hash="h1", total_size=0))
        db.add(_transfer(2, transmission_id=2, info_hash="h2", total_size=0))
        await db.commit()

    asked: list = []

    async def _get_torrent(ref):
        asked.append(ref)
        if ref == "h1":
            async with maker() as db:
                row = await db.get(TorrentDownload, 2)
                row.status = "paused"
                await db.commit()
        return {"hashString": ref, "status": 4, "percentDone": 0.1,
                "totalSize": 0, "rateDownload": 0, "eta": -1, "error": 0}

    async def _quiet(*a, **k):
        return None

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)
    monkeypatch.setattr(M, "_emit_to_owner", _quiet)

    await M._check_downloads()

    assert asked == ["h1"], "wstrzymany w trakcie tiku transfer zostal i tak odpytany"
    async with maker() as db:
        assert (await db.get(TorrentDownload, 2)).status == "paused"
