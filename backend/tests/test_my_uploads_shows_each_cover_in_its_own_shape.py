"""My uploads draws every cover in its own shape.

Reported by the owner (2026-09-17): the covers in My uploads looked wrong,
square PlayStation cases forced into tall rectangles. The panel put every tile
in a fixed 2:3 frame, while every other place that mixes covers - the home
page rails, the Game Saves panel, the dashboard - takes the shape from the ROM:
`rom_cover_aspect`, which reads the scraped cover's measured ratio, the 3D box,
and the platform's usual case, in that order.

So a ROM row carries that same answer, and the panel sizes each tile by it.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.rom import Rom
from models.rom_platform import RomPlatform

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PANEL = BACKEND.parent / "frontend" / "src" / "components" / "MyUploadsPanel.vue"
ME = 3


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
        from models.library import Library, LibraryMembership
        from models.library_file import LibraryFile
        from models.library_game import LibraryGame
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    from handler.library import quota
    monkeypatch.setattr(quota, "async_session_factory", maker, raising=False)

    def _rom(rid, platform_id, fs_name, **kw):
        stem, ext = fs_name.rsplit(".", 1)
        return Rom(id=rid, platform_id=platform_id, fs_name=fs_name, fs_name_no_ext=stem,
                   fs_extension=ext, fs_path="/roms", name=stem, slug=stem.lower(),
                   published_by=ME, missing_from_fs=False, fs_size_bytes=10,
                   cover_path=f"/resources/roms/{rid}/cover.jpg", **kw)

    async with maker() as session:
        session.add(RomPlatform(id=1, slug="psx", name="PlayStation", fs_slug="psx"))
        session.add(RomPlatform(id=2, slug="snes", name="Super Nintendo", fs_slug="snes"))
        # A jewel case the scrape measured.
        session.add(_rom(1, 1, "Army Men.chd", cover_aspect="7/6"))
        # Nothing measured: the platform's usual case.
        session.add(_rom(2, 2, "Mario World.sfc"))
        # A 3D box is wide whatever was measured.
        session.add(_rom(3, 1, "Ace Combat 2.chd", cover_type="box-3D", cover_aspect="7/6"))
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_rom_row_carries_the_shape_of_its_cover(db):
    from handler.library import quota
    from handler.metadata.rom_platform_map import rom_cover_aspect

    rows = {r["id"]: r for r in await quota.owned_games(ME) if r["kind"] == "rom"}

    assert rows[1]["aspect"] == "7/6", "zmierzona okladka pudelka CD dostaje ramke 2:3"
    assert rows[2]["aspect"] == rom_cover_aspect(None, None, "snes")
    assert rows[3]["aspect"] == "16/9"


def _panel() -> str:
    return io.open(PANEL, encoding="utf-8").read()


def test_the_panel_sizes_each_tile_by_its_cover():
    source = _panel()
    img = re.search(r'<img v-if="g\.cover_path"[^>]*class="mup-cover"[^>]*/>', source)
    assert img, "nie znalazlem okladki kafla"
    assert re.search(r'aspectRatio:\s*g\.aspect', img.group(0)), (
        "kafel w Moje wgrania nie bierze ksztaltu okladki z wiersza"
    )
    empty = re.search(r'<span v-else class="mup-cover mup-cover--none"[^>]*>', source)
    assert empty and re.search(r'aspectRatio:\s*g\.aspect', empty.group(0)), (
        "pusty kafel ma inny ksztalt niz okladka, ktora by w nim byla"
    )


def test_no_fixed_frame_is_left_in_the_stylesheet():
    style = _panel().split("<style", 1)[1]
    rule = re.search(r"\.mup-cover\s*\{([^}]*)\}", style)
    assert rule and "aspect-ratio" not in rule.group(1), (
        "styl nadal wymusza jedna ramke na kazda okladke"
    )


def test_tiles_of_different_heights_line_up_on_their_names():
    """A shelf, not a staircase: covers of different heights sit on one line,
    so the titles under them do too."""
    style = _panel().split("<style", 1)[1]
    grid = re.search(r"\.mup-grid\s*\{([^}]*)\}", style)
    assert grid and re.search(r"align-items:\s*end", grid.group(1))
