"""The administrator's dashboard draws every cover in its own shape.

Reported by the owner (2026-09-17), after the same fix in My uploads: Recently
added and Top downloaded had the problem too. Recently added put every tile in
one portrait frame, so a Super Nintendo box or a square Game Boy Advance case
was cut to a tall rectangle; the cover strip already sizes a tile by `aspect`,
but this list never sent one. Top downloaded cut every cover to a 30x40 slot.

So a ROM in Recently added carries `rom_cover_aspect`, the rule every other ROM
surface uses. A library game has no measured shape stored, so the strip takes it
from the picture once it loads. Top downloaded shows the whole cover in its slot.
"""

from __future__ import annotations

import datetime
import io
import pathlib
import re

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SRC = BACKEND.parent / "frontend" / "src"
STRIP = SRC / "components" / "DashCoverStrip.vue"
VIEW = SRC / "views" / "DashboardView.vue"


@pytest_asyncio.fixture
async def session():
    from models.gog_game import GogGame
    from models.library import Library, LibraryMembership
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for model in (GogGame, LibraryGame, LibraryFile, Library, LibraryMembership,
                      RomPlatform, Rom):
            await conn.run_sync(model.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    def _rom(rid, platform_id, fs_name, minutes_ago, **kw):
        stem, ext = fs_name.rsplit(".", 1)
        return Rom(id=rid, platform_id=platform_id, fs_name=fs_name, fs_name_no_ext=stem,
                   fs_extension=ext, fs_path="/roms", name=stem, slug=stem.lower(),
                   fs_size_bytes=10, cover_path=f"/resources/roms/{rid}/cover.jpg",
                   created_at=datetime.datetime(2026, 9, 17, 12, 0) - datetime.timedelta(minutes=minutes_ago),
                   **kw)

    async with maker() as s:
        s.add(RomPlatform(id=1, slug="snes", name="Super Nintendo", fs_slug="snes"))
        s.add(RomPlatform(id=2, slug="psx", name="PlayStation", fs_slug="psx"))
        s.add(_rom(1, 1, "Final Fantasy 6.sfc", 1))
        s.add(_rom(2, 2, "Army Men.chd", 2, cover_aspect="7/6"))
        s.add(_rom(3, 2, "Ace Combat 2.chd", 3, cover_type="box-3D"))
        s.add(LibraryGame(id=10, title="Hitman", slug="hitman", source="custom", is_active=True,
                          cover_path="/resources/games/10/cover.jpg",
                          created_at=datetime.datetime(2026, 9, 17, 11, 0)))
        await s.commit()
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_rom_in_recently_added_carries_the_shape_of_its_cover(session):
    from handler.dashboard.dashboard_handler import _recently_added
    from handler.metadata.rom_platform_map import rom_cover_aspect

    items = {(i["kind"], i["id"]): i for i in await _recently_added(session)}

    assert items[("rom", 1)]["aspect"] == rom_cover_aspect(None, None, "snes"), (
        "pudelko SNES w Recently added dostaje pionowa ramke"
    )
    assert items[("rom", 2)]["aspect"] == "7/6"
    assert items[("rom", 3)]["aspect"] == "16/9"
    assert items[("custom", 10)].get("aspect") is None, (
        "gra z biblioteki nie ma zapisanego ksztaltu - pasek bierze go z obrazka"
    )


def _read(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


def test_the_view_hands_the_shape_to_the_strip():
    view = _read(VIEW)
    ra = view[view.index("const raItems"):]
    ra = ra[:ra.index("})));")]
    assert re.search(r"aspect:\s*it\.aspect", ra), "Recently added nie przekazuje ksztaltu okladki"


def test_a_tile_without_a_stored_shape_takes_the_pictures_own():
    strip = _read(STRIP)
    cover = re.search(r'<span class="dcs-cover" :style="\{ aspectRatio: ([^}]*) \}"', strip)
    assert cover, "nie znalazlem ramki okladki"
    assert "it.aspect" in cover.group(1) and "natural" in cover.group(1), (
        "kafel bez zapisanego ksztaltu nadal dostaje stala ramke"
    )
    assert re.search(r'<img v-if="it\.cover"[^>]*@load="', strip), "obrazek nie mowi, jaki ma ksztalt"
    body = strip[strip.index("function onCoverLoad"):]
    body = body[:body.index("\n}")]
    assert "naturalWidth" in body and "naturalHeight" in body
    assert re.search(r"if \(it\.aspect\) return", body), (
        "zmierzony obrazek nadpisuje ksztalt ROM-u z serwera"
    )


def test_top_downloaded_shows_the_whole_cover():
    style = _read(VIEW).split("<style", 1)[1]
    img = re.search(r"\.dash-td-cover img\s*\{([^}]*)\}", style)
    assert img and re.search(r"object-fit:\s*contain", img.group(1)), (
        "Top downloaded nadal przycina okladke do waskiego prostokata"
    )
