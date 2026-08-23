"""An upload that fails must not take a finished game file with it.

Both upload paths opened the final destination directly, so an upload of a name
that already existed truncated a completed install at the first byte. Worse,
the URL path's blanket error handler deleted that destination on ANY failure,
and the failures that reach it include ones that never wrote anything: a 404
from `raise_for_status`, a Content-Length over the limit, a redirect the SSRF
guard turned down. Pasting a dead link removed a healthy eight-gigabyte
installer whose only crime was sharing a filename.

Nothing here needs a server. The rule being tested is about which path gets
opened and which path gets deleted, and that is decided by two small functions
plus where they are used.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from endpoints.library.upload_router import _part_path, _refuse_existing

ZRODLO = (pathlib.Path(__file__).resolve().parent.parent
          / "endpoints" / "library" / "upload_router.py")


def _funkcja(nazwa: str) -> str:
    drzewo = ast.parse(ZRODLO.read_text(encoding="utf-8"))
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)) and w.name == nazwa:
            return ast.unparse(w)
    raise AssertionError(f"nie ma {nazwa}")


# ── Sciezka pliku tymczasowego ────────────────────────────────────────────────

def test_plik_tymczasowy_stoi_obok_docelowego():
    """Same directory, so the move at the end is a rename inside one
    filesystem rather than a copy across a mount."""
    cel = pathlib.Path("/data/games/CUSTOM/Gra/windows/setup.exe")
    part = _part_path(cel)
    assert part.parent == cel.parent
    assert part.name == "setup.exe.part"


def test_plik_tymczasowy_nigdy_nie_rowna_sie_docelowemu():
    for nazwa in ("a.bin", "gra.tar.gz", "bez-rozszerzenia", "kropka."):
        cel = pathlib.Path("/x") / nazwa
        assert _part_path(cel) != cel


# ── Odmowa nadpisania ─────────────────────────────────────────────────────────

def test_nieistniejacy_plik_przechodzi(tmp_path):
    _refuse_existing(tmp_path / "nowy.bin", overwrite=False)   # nie rzuca


def test_istniejacy_plik_jest_odrzucany(tmp_path):
    cel = tmp_path / "gotowa-gra.bin"
    cel.write_bytes(b"osiem gigabajtow, umownie")
    with pytest.raises(ValueError) as exc:
        _refuse_existing(cel, overwrite=False)
    assert "gotowa-gra.bin" in str(exc.value)
    assert cel.read_bytes() == b"osiem gigabajtow, umownie", "sprawdzenie ruszylo plik"


def test_jawna_zgoda_przepuszcza(tmp_path):
    cel = tmp_path / "gotowa-gra.bin"
    cel.write_bytes(b"x")
    _refuse_existing(cel, overwrite=True)   # nie rzuca


# ── Ksztalt obu sciezek ───────────────────────────────────────────────────────

def test_pobieranie_z_adresu_pisze_do_pliku_tymczasowego():
    src = _funkcja("_url_upload_job")
    assert "open(part_path, 'wb')" in src.replace('"', "'"), "pisze wprost do celu"


def test_pobieranie_z_adresu_kasuje_WYLACZNIE_plik_tymczasowy():
    """The bug itself: the delete named the destination and every failure
    reached it, including the ones that had written nothing."""
    src = _funkcja("_url_upload_job")
    assert "dest_path.unlink" not in src, (
        "nieudane pobranie dalej kasuje plik docelowy")
    assert "part_path.unlink" in src


def test_wysylka_pliku_pisze_do_pliku_tymczasowego():
    src = _funkcja("upload_game_file")
    assert "open(part_path, 'wb')" in src.replace('"', "'")
    assert "dest_path.unlink" not in src, (
        "przerwana wysylka dalej kasuje plik docelowy")


def test_obie_sciezki_pytaja_zanim_nadpisza():
    for nazwa in ("_url_upload_job", "upload_game_file"):
        assert "_refuse_existing" in _funkcja(nazwa), f"{nazwa} nadpisuje bez pytania"


def test_skan_antywirusa_biegnie_na_pliku_tymczasowym():
    """Scanning after the move would mean an infected upload had already
    replaced a good file by the time anything objected - and ClamAV's own
    quarantine step would then carry off the wrong one."""
    src = _funkcja("_finalize_upload")
    assert "scan_target = staged or dest_path" in src
    assert "scan_file(str(scan_target))" in src
    # ...i podmiana dopiero po skanie
    assert src.index("scan_file(str(scan_target))") < src.index("os.replace"), (
        "podmiana wyprzedza skan")


def test_zmiana_nazwy_przez_serwer_tez_sprawdza_kolizje():
    """Content-Disposition can rename the file after the first check, and the
    collision that matters is with the name actually used."""
    src = _funkcja("_url_upload_job")
    assert src.count("_refuse_existing") >= 2, (
        "nazwa podana przez serwer omija sprawdzenie kolizji")
