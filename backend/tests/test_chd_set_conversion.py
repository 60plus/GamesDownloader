"""Converting a whole title, from the rows through the files to the playlist.

A multi-disc game is converted as one job, because converting three discs of
four leaves a set that is half one format and half another and a playlist
naming files that are no longer all there.

Everything below runs for real: a real database, real discs on disk, real
chdman, and afterwards the questions the library will actually ask - is the
row still the same row, does the playlist name what is on the shelf, is the
subchannel file still beside its disc.
"""
from __future__ import annotations

import shutil

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.rom import Rom
from models.rom_platform import RomPlatform

needs_chdman = pytest.mark.skipif(
    not shutil.which("chdman"), reason="chdman nie jest w tym obrazie")


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
        await session.commit()
        yield session
    await engine.dispose()


def _write_disc(directory, stem, sectors=512):
    (directory / f"{stem}.bin").write_bytes(bytes(range(256)) * 8 * sectors)
    (directory / f"{stem}.cue").write_text(
        f'FILE "{stem}.bin" BINARY\n  TRACK 01 MODE1/2048\n    INDEX 01 00:00:00\n',
        encoding="utf-8",
    )


async def _two_disc_game(db, tmp_path):
    """Two discs, their tracks, a subchannel file and a playlist: the shape
    the library is in after everything built so far."""
    psx = tmp_path / "psx"
    psx.mkdir()
    for n in (1, 2):
        stem = f"Game (Disc {n})"
        _write_disc(psx, stem)
        db.add(Rom(
            id=n, platform_id=1, name="Game",
            fs_name=f"{stem}.cue", fs_name_no_ext=stem, fs_extension="cue",
            fs_path=str(psx), fs_size_bytes=(psx / f"{stem}.cue").stat().st_size,
            disk_group="Game", disk_number=n,
        ))
        db.add(Rom(
            id=10 + n, platform_id=1,
            fs_name=f"{stem}.bin", fs_name_no_ext=stem, fs_extension="bin",
            fs_path=str(psx), fs_size_bytes=(psx / f"{stem}.bin").stat().st_size,
            disk_group="Game", disk_number=n, track_of=f"{stem}.cue",
        ))
    (psx / "Game (Disc 1).sbi").write_bytes(b"\0" * 452)
    (psx / "Game.m3u").write_text(
        "Game (Disc 1).cue\nGame (Disc 2).cue\n", encoding="utf-8")
    await db.commit()
    return psx


# ── The playlist, on its own ─────────────────────────────────────────────────

def test_the_playlist_follows_the_discs_to_their_new_names(tmp_path):
    from handler.roms.chd_convert import rewrite_playlists

    (tmp_path / "Game.m3u").write_text(
        "Game (Disc 1).cue\nGame (Disc 2).cue\n", encoding="utf-8")

    changed = rewrite_playlists(tmp_path, {
        "Game (Disc 1).cue": "Game (Disc 1).chd",
        "Game (Disc 2).cue": "Game (Disc 2).chd",
    })

    assert [p.name for p in changed] == ["Game.m3u"]
    assert (tmp_path / "Game.m3u").read_text(encoding="utf-8").splitlines() == [
        "Game (Disc 1).chd", "Game (Disc 2).chd",
    ]


def test_a_playlist_naming_someone_elses_discs_is_left_alone(tmp_path):
    from handler.roms.chd_convert import rewrite_playlists

    (tmp_path / "Other.m3u").write_text(
        "Other (Disc 1).cue\nOther (Disc 2).cue\n", encoding="utf-8")
    assert rewrite_playlists(tmp_path, {"Game (Disc 1).cue": "Game (Disc 1).chd"}) == []
    assert "Other (Disc 1).cue" in (tmp_path / "Other.m3u").read_text(encoding="utf-8")


def test_what_a_playlist_holds_besides_disc_names_survives(tmp_path):
    """Somebody's hand-written playlist may carry comments, and a line this
    conversion knows nothing about is not a line to drop."""
    from handler.roms.chd_convert import rewrite_playlists

    (tmp_path / "by hand.m3u").write_text(
        "# my four disc set\nGame (Disc 1).cue\n\nGame (Disc 9).cue\n",
        encoding="utf-8")

    rewrite_playlists(tmp_path, {"Game (Disc 1).cue": "Game (Disc 1).chd"})

    assert (tmp_path / "by hand.m3u").read_text(encoding="utf-8").splitlines() == [
        "# my four disc set", "Game (Disc 1).chd", "", "Game (Disc 9).cue",
    ]


# ── The whole title ──────────────────────────────────────────────────────────

@needs_chdman
@pytest.mark.asyncio
async def test_every_disc_of_the_set_is_converted_and_the_rows_survive(db, tmp_path):
    from handler.roms.chd_jobs import convert_set

    psx = await _two_disc_game(db, tmp_path)
    seen: list[float] = []

    result = await convert_set(1, delete_source=True, on_percent=seen.append,
                               session=db)

    assert result["discs"] == 2
    for n in (1, 2):
        assert (psx / f"Game (Disc {n}).chd").is_file()
        assert not (psx / f"Game (Disc {n}).cue").exists()
        assert not (psx / f"Game (Disc {n}).bin").exists()

    rows = (await db.execute(select(Rom).order_by(Rom.id))).scalars().all()
    assert [r.id for r in rows] == [1, 2], "sciezki znikly, plyty zostaly te same wiersze"
    assert [r.fs_name for r in rows] == ["Game (Disc 1).chd", "Game (Disc 2).chd"]
    assert [r.disk_number for r in rows] == [1, 2], "komplet sie nie rozpadl"
    assert all(len(r.sha1_hash or "") == 40 for r in rows)

    assert seen and seen[-1] >= seen[0], "postep calego kompletu nie plynal"


@needs_chdman
@pytest.mark.asyncio
async def test_the_playlist_and_the_subchannel_file_come_out_right(db, tmp_path):
    from handler.roms.chd_jobs import convert_set

    psx = await _two_disc_game(db, tmp_path)
    await convert_set(1, delete_source=True, session=db)

    assert (psx / "Game.m3u").read_text(encoding="utf-8").splitlines() == [
        "Game (Disc 1).chd", "Game (Disc 2).chd",
    ], "playlista wskazywalaby na pliki, ktorych juz nie ma"
    assert (psx / "Game (Disc 1).sbi").is_file(), (
        "bez tego pliku plyta PAL z LibCryptem wraca do czarnego ekranu"
    )


@needs_chdman
@pytest.mark.asyncio
async def test_keeping_the_originals_puts_them_where_the_scan_will_not_find_them(
    db, tmp_path
):
    from handler.roms.chd_jobs import convert_set

    psx = await _two_disc_game(db, tmp_path)
    await convert_set(1, delete_source=False, session=db)

    retired = {p.name for p in (psx / "_originals").iterdir()}
    assert retired == {
        "Game (Disc 1).cue", "Game (Disc 1).bin",
        "Game (Disc 2).cue", "Game (Disc 2).bin",
    }
    assert not (psx / "Game (Disc 1).cue").exists(), \
        "zostawiony obok stalby sie druga kopia gry przy nastepnym skanie"


@needs_chdman
@pytest.mark.asyncio
async def test_a_stopped_job_leaves_the_discs_it_had_not_reached(db, tmp_path):
    """Stopping is a button, and what it must never do is leave a set half
    converted with its playlist pointing at both halves."""
    from handler.roms.chd_jobs import convert_set

    psx = await _two_disc_game(db, tmp_path)

    with pytest.raises(Exception):
        await convert_set(1, delete_source=True, should_stop=lambda: True,
                          session=db)

    for n in (1, 2):
        assert (psx / f"Game (Disc {n}).cue").is_file(), "plyta znikla mimo przerwania"
        assert not (psx / f"Game (Disc {n}).chd").exists()
    rows = (await db.execute(select(Rom).order_by(Rom.id))).scalars().all()
    assert [r.fs_name for r in rows if not r.track_of] == [
        "Game (Disc 1).cue", "Game (Disc 2).cue",
    ], "wiersze zostaly ruszone mimo przerwania"
