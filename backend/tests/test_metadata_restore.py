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

from config import BASE_PATH, RESOURCES_PATH
from endpoints.settings.metadata_backup_router import (
    _MAX_MEDIA_FILE_BYTES,
    _TABLES,
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
