"""Restoring a metadata backup must not be able to damage anything else.

This module had no test at all, and three separate ways to go wrong.

An archive is supplied by whoever is restoring it. Extraction was rooted at
BASE_PATH, and BASE_PATH holds everything: emulator saves, installed plugin
code, firmware, the configuration. Rejecting `..` was never the whole problem,
because the paths that do the damage do not need to escape anywhere.

ROM rows were keyed on the containing directory, so every ROM of a platform
matched every other one.

And the whole restore ran in one transaction with row failures swallowed, so it
either answered 200 with an empty library or 500 with everything rolled back.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
import pytest_asyncio

from config import BASE_PATH, RESOURCES_PATH
from endpoints.settings.metadata_backup_router import (
    _MAX_MEDIA_FILE_BYTES,
    _TABLES,
    _import_model,
    _safe_extract_to,
)

ZRODLO = (pathlib.Path(__file__).resolve().parent.parent
          / "endpoints" / "settings" / "metadata_backup_router.py")


# ── Rozpakowanie archiwum ─────────────────────────────────────────────────────

def test_zwykla_okladka_przechodzi():
    dest = _safe_extract_to(BASE_PATH, "media/resources/library/42/cover/cover.jpg")
    assert dest is not None
    assert dest.startswith(str(pathlib.Path(RESOURCES_PATH).resolve()))


@pytest.mark.parametrize("member", [
    "media/saves/psx/9/1/Medievil.srm",        # zywa karta pamieci
    "media/saves/snes/1/1/Lost Vikings.srm",
    "media/plugins/gd3-vapor/__init__.py",     # kod, ktory serwer importuje
    "media/plugins/anything/plugin.py",
    "media/config/config.yml",
    "media/firmware/scph5501.bin",
    "media/games/CUSTOM/Gra/setup.exe",
])
def test_sciezki_poza_zasobami_sa_odrzucane(member):
    """Every one of these is inside BASE_PATH, so the old check let it through
    without needing a single `..`."""
    assert _safe_extract_to(BASE_PATH, member) is None, f"{member} dalej przechodzi"


@pytest.mark.parametrize("member", [
    "media/../../etc/passwd",
    "media//etc/passwd",
    "media/resources/../../saves/x.srm",
    "tables/roms.json",          # nie media/
    "media/",                    # sam katalog
    "media/resources/",          # katalog w zasobach
])
def test_stare_sztuczki_dalej_odrzucane(member):
    assert _safe_extract_to(BASE_PATH, member) is None


def test_ograniczenie_liczone_na_rozwiazanej_sciezce():
    """A symlink or a clever relative path must not get in through the front."""
    assert _safe_extract_to(BASE_PATH, "media/resources/../saves/a.srm") is None


# ── Klucz ROM-ow ──────────────────────────────────────────────────────────────

def test_romy_kluczowane_po_nazwie_pliku_nie_po_katalogu():
    """fs_path is the containing directory, so keying on it made three hundred
    carts in one folder into one row."""
    roms = next(t for t in _TABLES if t.name == "roms")
    assert "fs_name" in roms.upsert_keys
    assert "fs_path" not in roms.upsert_keys, "klucz dalej zlewa cala platforme w jeden wiersz"
    assert "platform_id" in roms.upsert_keys


def test_klucz_zgadza_sie_z_prawdziwym_upsertem():
    """rom_handler.upsert has always used (platform_id, fs_name); a restore
    keyed differently means the two disagree about what one ROM is."""
    zrodlo = (pathlib.Path(__file__).resolve().parent.parent
              / "handler" / "database" / "rom_handler.py").read_text(encoding="utf-8")
    assert "Rom.fs_name == fs_name" in zrodlo


# ── Klucze upsertu wobec prawdziwych modeli ───────────────────────────────────

@pytest.mark.parametrize("tbl", _TABLES, ids=lambda t: t.name)
def test_kazda_kolumna_klucza_naprawde_istnieje(tbl):
    """Asked of the model, not of the declaration.

    A key naming a column the model does not have is dropped rather than
    refused, so it fails silently: the key quietly becomes narrower, or empty.
    `library_torrents` was keyed on a library_game_id and a magnet, neither of
    which that table has ever had, so every torrent row was exported and then
    skipped on the way back in - and nothing said so.
    """
    model = _import_model(tbl.model_path)
    assert model is not None, f"nie da sie zaimportowac modelu dla {tbl.name}"
    columns = {c.key for c in model.__mapper__.columns}
    missing = [k for k in tbl.upsert_keys if k not in columns]
    assert not missing, f"{tbl.name}: klucz wskazuje na nieistniejace kolumny {missing}"


def test_gry_biblioteki_kluczowane_po_slugu():
    """slug is what the table is unique on.

    The key read ("igdb_id", "slug") and did no harm only because the model had
    no igdb_id: the export walks the mapper's columns, so nothing wrote one into
    a backup and the effective key was the slug. Adding the column made the
    declaration real, and a row whose saved igdb_id did not match the one in the
    database stopped matching at all - it was inserted instead, hit the unique
    index on slug, and came back "skipped", while its artwork unpacked in a
    separate pass and stayed on disk with no row pointing at it.
    """
    games = next(t for t in _TABLES if t.name == "library_games")
    assert games.upsert_keys == ("slug",)


# ── Prawdziwy upsert na prawdziwej bazie ──────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.library_torrent import LibraryTorrent

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        # The files come with it: a game eagerly loads them, so a query for one
        # touches the other table whether the test cares about it or not.
        for table in (LibraryGame, LibraryFile, LibraryTorrent):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _restore_one(session, row: dict) -> str:
    from endpoints.settings.metadata_backup_router import _upsert_row
    from models.library_game import LibraryGame

    tbl = next(t for t in _TABLES if t.name == "library_games")
    return await _upsert_row(session, tbl, LibraryGame, row)


@pytest.mark.asyncio
async def test_gra_wraca_do_wlasciwego_wiersza_mimo_innego_igdb_id(db):
    """The defect, run rather than read.

    A library scraped again since the backup was taken has an igdb_id the
    backup does not know about. Keyed on both columns that is a different game;
    keyed on the slug it is the same one, which it is.
    """
    from models.library_game import LibraryGame

    db.add(LibraryGame(slug="doom", title="Doom", igdb_id=None))
    await db.commit()

    result = await _restore_one(db, {"slug": "doom", "title": "DOOM (1993)", "igdb_id": 1234})
    assert result == "updated", "wiersz odpadl zamiast sie zaktualizowac"

    from sqlalchemy import select
    rows = (await db.execute(select(LibraryGame))).scalars().all()
    assert len(rows) == 1, "powstal drugi wiersz na ten sam slug"
    assert rows[0].title == "DOOM (1993)"


@pytest.mark.asyncio
async def test_gra_ktorej_nie_ma_jest_dodawana(db):
    assert await _restore_one(db, {"slug": "quake", "title": "Quake"}) == "inserted"


@pytest.mark.asyncio
async def test_wiersz_bez_kluczy_nie_trafia_nigdzie(db):
    """A backup row with no slug says nothing about which game it is, and
    guessing is how one game's metadata lands on another."""
    assert await _restore_one(db, {"title": "Bez sluga"}) == "skipped"
    assert await _restore_one(db, {"slug": None, "title": "Nadal bez"}) == "skipped"


# ── Transakcja ────────────────────────────────────────────────────────────────

def _funkcja(nazwa: str) -> str:
    for w in ast.walk(ast.parse(ZRODLO.read_text(encoding="utf-8"))):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)) and w.name == nazwa:
            return ast.unparse(w)
    raise AssertionError(f"nie ma {nazwa}")


def test_kazdy_wiersz_ma_wlasny_punkt_zapisu():
    """Without it a failed flush poisons the session and the next row's SELECT
    raises outside any try, taking the whole restore down."""
    assert "session.begin_nested()" in _funkcja("_upsert_row")


def test_odpowiedz_nie_klamie_gdy_wiersze_odpadly():
    src = _funkcja("restore_backup")
    assert '"ok": True' not in src, "odpowiedz dalej twierdzi ze sie udalo, cokolwiek sie stalo"
    assert "not problems" in src


def test_odrzucone_media_licza_sie_jako_problem():
    src = _funkcja("restore_backup")
    assert "media_skipped" in src and "problems" in src


# ── Limity rozmiaru ───────────────────────────────────────────────────────────

def test_jest_gorny_limit_na_plik():
    assert 0 < _MAX_MEDIA_FILE_BYTES <= 1024 * 1024 * 1024


def test_rozmiar_sprawdzany_takze_w_trakcie_czytania():
    """A ZIP entry can lie about its declared size, so the number that decides
    is what actually comes out of it."""
    src = _funkcja("restore_backup")
    assert "declares" in src or "declared" in src, "brak sprawdzenia deklarowanego rozmiaru"
    assert "larger than it declared" in src, "brak sprawdzenia rozmiaru w trakcie zapisu"


def test_nieudany_plik_nie_zostaje_w_polowie():
    """A half-written file wears the name of a cover the library will serve."""
    src = _funkcja("restore_backup")
    assert "os.unlink(dest)" in src
