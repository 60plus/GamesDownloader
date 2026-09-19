"""A game's manual, fetched with the rest of what a scrape brings.

ScreenScraper has a manual for most of what people own: measured on the
owner's library, 45 of the 54 games it knows, every one a PDF, typically three
megabytes, the largest under fifteen. It usually has several - the Japanese,
the American, the European, a French and a German one - so which to take is a
real choice, and the owner made it: the ROM's own region first, because a
manual that matches the text on the screen is the one that helps; then Europe,
America, the world release, and Japan last, since for most people it cannot be
read at all. Anything else found goes between the world and Japan.

ScreenScraper names Spain `sp`, not `es`. That was measured too, and it is the
kind of detail a region table gets wrong by assuming.

A manual comes back from a URL that may answer with anything - an error page,
a "no media" text, a truncated body. What gets written must be a PDF, checked
by the four bytes every PDF starts with, and a manual already on the disk is
not lost to a download that failed.

Off unless the platform's Scrape Preset asks for it: the owner's rule from the
last release, default small.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from handler.metadata import manuals, scrape_presets


def _m(region: str, fmt: str = "pdf", url: str | None = None) -> dict:
    return {"type": "manuel", "region": region, "format": fmt,
            "url": url or f"https://example.test/manual-{region}.pdf"}


EVERYTHING = [_m("jp"), _m("us"), _m("eu"), _m("fr"), _m("de")]


# ── Which one ───────────────────────────────────────────────────────────────


def test_a_european_game_gets_the_european_manual():
    assert manuals.pick_manual(EVERYTHING, ["Europe"])["region"] == "eu"


def test_an_american_game_gets_the_american_manual():
    assert manuals.pick_manual(EVERYTHING, ["USA"])["region"] == "us"


def test_a_japanese_game_gets_the_japanese_manual():
    """The ROM's own region first, even when it is Japan: the manual then
    matches what is on the screen."""
    assert manuals.pick_manual(EVERYTHING, ["Japan"])["region"] == "jp"


def test_a_game_with_no_region_prefers_europe_then_america():
    assert manuals.pick_manual(EVERYTHING, [])["region"] == "eu"
    assert manuals.pick_manual([_m("jp"), _m("us")], None)["region"] == "us"


def test_another_european_language_comes_before_japanese():
    assert manuals.pick_manual([_m("jp"), _m("fr")], [])["region"] == "fr"


def test_spain_is_sp_as_screenscraper_spells_it():
    """Measured on the owner's library: ten Spanish manuals, all `sp`."""
    assert manuals.pick_manual([_m("jp"), _m("us"), _m("sp")], ["Spain"])["region"] == "sp"


def test_a_japanese_manual_is_still_better_than_none():
    assert manuals.pick_manual([_m("jp")], ["Europe"])["region"] == "jp"


def test_no_manual_is_no_manual():
    assert manuals.pick_manual([], ["Europe"]) is None
    assert manuals.pick_manual([{"type": "ss", "region": "eu"}], ["Europe"]) is None


def test_only_a_pdf_is_taken():
    """Everything measured was a PDF, and the browser opens a PDF by itself.
    Anything else would need a reader nobody asked for."""
    assert manuals.pick_manual([_m("eu", fmt="cbz")], ["Europe"]) is None


# ── What gets written ───────────────────────────────────────────────────────

PDF = b"%PDF-1.4\n%fake but shaped like one\n" + b"x" * 64


@pytest.mark.asyncio
async def test_a_pdf_is_written(tmp_path, monkeypatch):
    async def fetch(url, **k):
        return PDF, "application/pdf"

    monkeypatch.setattr(manuals, "fetch_media_bytes", fetch)
    dest = tmp_path / "manual.pdf"

    assert await manuals.fetch_manual("https://example.test/m.pdf", dest) == dest
    assert dest.read_bytes() == PDF


@pytest.mark.asyncio
async def test_an_error_page_is_not_a_manual(tmp_path, monkeypatch):
    async def fetch(url, **k):
        return b"<html>NOMEDIA</html>", "text/html"

    monkeypatch.setattr(manuals, "fetch_media_bytes", fetch)
    dest = tmp_path / "manual.pdf"

    assert await manuals.fetch_manual("https://example.test/m.pdf", dest) is None
    assert not dest.exists()


@pytest.mark.asyncio
async def test_a_failed_download_keeps_the_manual_already_there(tmp_path, monkeypatch):
    async def fetch(url, **k):
        raise TimeoutError("provider having a bad afternoon")

    monkeypatch.setattr(manuals, "fetch_media_bytes", fetch)
    dest = tmp_path / "manual.pdf"
    dest.write_bytes(PDF)

    assert await manuals.fetch_manual("https://example.test/m.pdf", dest) is None
    assert dest.read_bytes() == PDF, "nieudane pobranie skasowalo dobra instrukcje"


# ── Asked for, not assumed ──────────────────────────────────────────────────


def test_the_manual_is_a_tick_the_scrape_obeys():
    assert scrape_presets.MANUAL in scrape_presets.TICKS


def test_nobody_gets_a_manual_they_did_not_ask_for():
    """The default is small: the cover and gameplay screenshots, nothing else."""
    assert scrape_presets.MANUAL not in scrape_presets.wanted_media(None)
    assert scrape_presets.MANUAL not in scrape_presets.DEFAULT_MEDIA


# ── Somewhere to keep it ────────────────────────────────────────────────────


def test_a_rom_has_a_place_for_its_manual():
    from models.rom import Rom

    assert "manual_path" in Rom.__table__.columns


def test_an_existing_database_is_given_the_column_too():
    """A fresh database takes it from the model; one that was migrated takes it
    from the list the app walks at every start."""
    import io
    import pathlib

    main = (pathlib.Path(__file__).resolve().parent.parent / "main.py")
    assert '"manual_path"' in io.open(main, encoding="utf-8").read()


def _source(*parts) -> str:
    import io
    import pathlib

    return io.open(pathlib.Path(__file__).resolve().parent.parent.joinpath(*parts),
                   encoding="utf-8").read()


# ── Where it lives: beside the game, in its extras ──────────────────────────
#
# The owner's decision: the manual goes into the game's own folder, under
# extras/, where it can be seen over FTP and travels with the game.


def test_a_game_with_its_own_folder_keeps_it_in_extras(tmp_path):
    shelf = tmp_path / "psx"
    game = shelf / "Final Fantasy 9"
    assert manuals.manual_dest(game, shelf, "Final Fantasy 9", "ff9.chd") == (
        game / "extras" / "Manual.pdf"
    )


def test_a_flat_rom_names_its_manual_after_the_game(tmp_path):
    """A shelf that has not been moved into folders shares one extras/ between
    every game on it, so a bare Manual.pdf there would be everybody's."""
    shelf = tmp_path / "psx"
    dest = manuals.manual_dest(shelf, shelf, "Crash Bandicoot", "crash.chd")
    assert dest == shelf / "extras" / "Crash Bandicoot - Manual.pdf"


def test_a_rom_flat_under_roms_is_on_a_shared_shelf_too(tmp_path):
    """`{platform}/roms/` is the other shape a platform may keep, and it is just
    as shared: every ROM in it would claim the one Manual.pdf."""
    shelf = tmp_path / "psx"
    dest = manuals.manual_dest(shelf / "roms", shelf, "Crash Bandicoot", "crash.chd")
    assert dest == shelf / "roms" / "extras" / "Crash Bandicoot - Manual.pdf"


def test_a_folder_several_games_share_names_each_ones_manual(tmp_path):
    """A folder holding several games - a Zelda/ with three regions - is as
    shared as a shelf: a bare Manual.pdf there was adopted by every game in it,
    one region's booklet for all three (1.0.36 audit)."""
    shelf = tmp_path / "psx"
    game = shelf / "Zelda"
    dest = manuals.manual_dest(game, shelf, "The Legend of Zelda", "Zelda (Japan).sfc", shared=True)
    assert dest == game / "extras" / "The Legend of Zelda - Manual.pdf"


@pytest_asyncio.fixture
async def shared_folder(tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    shelf = tmp_path / "snes"
    game = shelf / "Zelda"
    (game / "extras").mkdir(parents=True)
    async with maker() as db:
        db.add(RomPlatform(id=1, fs_slug="snes", slug="snes", name="SNES"))
        for rid, region, manual in ((1, "Europe", "extras/The Legend of Zelda - Manual.pdf"),
                                    (2, "Japan", None)):
            db.add(Rom(id=rid, platform_id=1, name="The Legend of Zelda",
                       fs_name=f"Zelda ({region}).sfc", fs_name_no_ext="Zelda",
                       fs_extension="sfc", fs_path=str(game), fs_size_bytes=1,
                       manual_path=manual))
        await db.commit()
        yield db, shelf, game
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_manual_another_game_already_has_is_not_taken_over(shared_folder):
    """Two regions of one title in one folder, or loose on one shelf, want the
    same name. The one already there is the other game's; this one gets a name
    of its own, after its file, and fetches its own region."""
    db, shelf, game = shared_folder
    (game / "extras" / "The Legend of Zelda - Manual.pdf").write_bytes(PDF)
    from models.rom import Rom

    japan = await db.get(Rom, 2)
    dest = await manuals.manual_home(japan, "The Legend of Zelda", shelf, session=db)

    assert dest == game / "extras" / "Zelda (Japan) - Manual.pdf", (
        "japonska wersja przejelaby europejska instrukcje"
    )


@pytest.mark.asyncio
async def test_a_name_another_game_still_holds_is_not_reused_when_its_file_is_gone(shared_folder):
    """Round 2 of the audit: asked only when the file was there, so a manual
    deleted over FTP left its name free, the next scrape fetched another
    region's booklet into it, and the first game's page opened that one."""
    db, shelf, game = shared_folder
    from models.rom import Rom

    japan = await db.get(Rom, 2)
    dest = await manuals.manual_home(japan, "The Legend of Zelda", shelf, session=db)

    assert dest == game / "extras" / "Zelda (Japan) - Manual.pdf"


@pytest.mark.asyncio
async def test_a_game_alone_in_its_folder_keeps_the_plain_name(shared_folder):
    db, shelf, game = shared_folder
    from models.rom import Rom

    await db.delete(await db.get(Rom, 1))
    await db.commit()
    japan = await db.get(Rom, 2)

    assert await manuals.manual_home(japan, "The Legend of Zelda", shelf, session=db) == (
        game / "extras" / "Manual.pdf"
    )


def test_the_row_keeps_the_path_relative_to_the_game(tmp_path):
    """So the folder can be renamed after the title without the row going
    stale: the manual moves with it, and the relative path still points at it."""
    game = tmp_path / "psx" / "Final Fantasy 9"
    assert manuals.stored_path(game / "extras" / "Manual.pdf", game) == "extras/Manual.pdf"


def _rom(fs_path, manual_path):
    return type("Rom", (), {"fs_path": str(fs_path), "manual_path": manual_path})()


def test_a_stored_manual_is_found_again(tmp_path):
    game = tmp_path / "psx" / "Game"
    (game / "extras").mkdir(parents=True)
    (game / "extras" / "Manual.pdf").write_bytes(PDF)

    assert manuals.resolve_manual(_rom(game, "extras/Manual.pdf"), str(tmp_path)) == (
        game / "extras" / "Manual.pdf"
    )


def test_a_path_that_walks_out_of_the_library_is_refused(tmp_path):
    """The column is written by the scraper, but a restored backup writes rows
    too. A path that climbs out of the library answers nothing."""
    game = tmp_path / "library" / "psx" / "Game"
    game.mkdir(parents=True)
    (tmp_path / "secret.pdf").write_bytes(PDF)

    assert manuals.resolve_manual(
        _rom(game, "../../../secret.pdf"), str(tmp_path / "library")) is None


def test_a_manual_that_is_no_longer_there_is_no_manual(tmp_path):
    game = tmp_path / "psx" / "Game"
    game.mkdir(parents=True)
    assert manuals.resolve_manual(_rom(game, "extras/Manual.pdf"), str(tmp_path)) is None


def test_the_game_page_is_told_whether_there_is_a_manual():
    """Whether, not where. The page never needs a path on the server's disk."""
    router = _source("endpoints", "roms", "roms_router.py")
    assert '"has_manual":' in router, "strona gry nie wie, czy gra ma instrukcje"
    assert '"manual_path":' not in router, "sciezka z dysku serwera trafia do przegladarki"


def test_the_manual_opens_through_a_ticket():
    """A navigation carries no Authorization header, which is why ROM downloads
    go through a short-lived ticket; a manual in the ROM tree does the same."""
    router = _source("endpoints", "roms", "roms_router.py")
    assert '"/{rom_id}/manual-ticket"' in router
    assert 'kind="manual"' in router, "bilet instrukcji mozna by uzyc na cos innego"


@pytest.fixture
def manual_route(tmp_path, monkeypatch):
    """The two manual routes, over a game folder this test owns."""
    from types import SimpleNamespace

    from endpoints.roms import roms_router as R

    game = tmp_path / "psx" / "Game"
    (game / "extras").mkdir(parents=True)
    row = SimpleNamespace(id=5, fs_path=str(game), manual_path="extras/Manual.pdf")

    async def get_by_id(rom_id):
        return row if rom_id == 5 else None

    async def roms_path():
        return str(tmp_path)

    monkeypatch.setattr(R.rom_handler, "get_by_id", get_by_id)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    return R, game / "extras" / "Manual.pdf"


@pytest.mark.asyncio
async def test_a_ticket_opens_the_manual_in_the_browsers_viewer(manual_route):
    from utils import download_tickets

    R, manual = manual_route
    manual.write_bytes(PDF)
    expires_at, sig = download_tickets.issue(5, 1, kind="manual")

    response = await R.rom_manual_with_ticket(5, 1, expires_at, sig)

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline"), (
        "instrukcja sciaga sie zamiast otworzyc"
    )
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_a_download_ticket_does_not_open_a_manual(manual_route):
    """Each ticket names what it is for; one issued for a ROM download is not
    a pass to anything else."""
    from fastapi import HTTPException

    from utils import download_tickets

    R, manual = manual_route
    manual.write_bytes(PDF)
    expires_at, sig = download_tickets.issue(5, 1)

    with pytest.raises(HTTPException) as refused:
        await R.rom_manual_with_ticket(5, 1, expires_at, sig)
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_something_that_is_not_a_pdf_is_not_served_as_one(manual_route):
    """The folder is written to over FTP, so what is at the path now is not
    necessarily what the scraper checked."""
    from fastapi import HTTPException

    from utils import download_tickets

    R, manual = manual_route
    manual.write_bytes(b"<html><script>alert(1)</script></html>")
    expires_at, sig = download_tickets.issue(5, 1, kind="manual")

    with pytest.raises(HTTPException) as refused:
        await R.rom_manual_with_ticket(5, 1, expires_at, sig)
    assert refused.value.status_code == 415


def test_a_file_already_in_extras_is_not_written_over():
    """Somebody may have put their own scan there over FTP. The scrape takes it
    as the game's manual rather than replacing it."""
    scrape = _source("handler", "metadata", "rom_scrape_handler.py")
    at = scrape.index("manuals.manual_home(")
    window = scrape[at:at + 900]
    assert ".exists()" in window, "scrape nadpisuje instrukcje wrzucona recznie"


def test_the_scrape_fetches_it_only_when_asked():
    scrape = _source("handler", "metadata", "rom_scrape_handler.py")
    at = scrape.index("manuals.manual_home(")
    window = scrape[at - 1400:at]
    assert "scrape_presets.MANUAL in wanted" in window, (
        "instrukcja pobiera sie bez pytania presetu"
    )
    assert "keep_existing_media(rom, \"manual_path\"" in window, (
        "wymuszony scrape nadpisalby instrukcje dodana recznie"
    )


def test_a_set_of_discs_fetches_one_manual_not_one_per_disc():
    """Found by the dry run of the backfill before a byte was fetched: every
    disc of a set is a row with its own ScreenScraper record, so a four disc
    title asked four times and would have stored the same booklet four times.
    The disc that stands for the game keeps it; the extras do not ask."""
    scrape = _source("handler", "metadata", "rom_scrape_handler.py")
    at = scrape.index("manuals.manual_home(")
    assert 'getattr(rom, "extra_disk", False)' in scrape[at - 1400:at], (
        "kazda plyta zestawu pobiera wlasna kopie tej samej instrukcji"
    )


def test_the_editor_can_write_it_and_clearing_metadata_takes_it():
    from handler.database import rom_handler as rh

    assert "manual_path" in rh._METADATA_FIELDS
    assert "manual_path" in rh.SCRAPED_METADATA_FIELDS
