"""A GOG download that arrives wrong must not become a finished game.

The job was written `status="completed"` before verification ran, and the
mismatch branch only logged. So a corrupt installer flipped the game to
downloaded, got a LibraryFile marked available, fired the plugin
download_complete event and was packed by zip_packer. Verification that changes
nothing is not verification.

Separately: the downlink URL carries the GOG access token in its query string,
and httpx puts the whole URL into the message of an HTTP error. That message
was logged and stored on the job row, which the download API serves.
"""
from __future__ import annotations

import ast
import pathlib

import httpx

from utils.http import loggable_error

ZRODLO = (pathlib.Path(__file__).resolve().parent.parent
          / "handler" / "gog" / "gog_download_handler.py")


def _tekst() -> str:
    return ZRODLO.read_text(encoding="utf-8")


# ── Uszkodzony plik nie trafia do biblioteki ──────────────────────────────────

def test_adopcja_wymaga_i_czystosci_i_poprawnej_sumy():
    src = _tekst()
    assert "if not infected and not corrupt:" in src, (
        "adopcja dalej patrzy tylko na antywirusa")


def test_niezgodna_suma_md5_oznacza_zadanie_jako_nieudane():
    src = _tekst()
    poczatek = src.index("MD5 MISMATCH")
    okno = src[poczatek - 400:poczatek + 700]
    assert "corrupt = True" in okno
    assert 'status="failed"' in okno, "niezgodna suma dalej zostawia zadanie ukonczone"


def test_niezgodny_rozmiar_tez_oznacza_nieudane():
    """Without an MD5 this is the only check there is."""
    src = _tekst()
    poczatek = src.index("size MISMATCH")
    okno = src[poczatek - 400:poczatek + 700]
    assert "corrupt = True" in okno
    assert 'status="failed"' in okno


def test_flaga_uszkodzenia_zaczyna_od_falszu():
    """Declared before the verification block, or a skipped verification would
    leave it undefined and take the whole job down with a NameError."""
    src = _tekst()
    assert src.index("corrupt = False") < src.index("if verify_checksum:")


# ── Token nie wycieka ─────────────────────────────────────────────────────────

def test_downlink_nie_uzywa_raise_for_status():
    """Its message is the whole URL, and this URL has the token in it."""
    drzewo = ast.parse(_tekst())
    for w in ast.walk(drzewo):
        if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef)) and "downlink" in w.name.lower():
            assert "raise_for_status" not in ast.unparse(w), (
                f"{w.name} oddaje wyjatkowi caly adres z tokenem")


def test_blad_zadania_zapisuje_oczyszczona_tresc():
    src = _tekst()
    assert "safe = loggable_error(exc)" in src
    assert "error_msg=str(exc)" not in src, "surowy wyjatek dalej ladzie w bazie"


def test_pomocnik_nie_przepuszcza_adresu_z_tokenem():
    """The guarantee the fix rests on, checked against a real httpx error."""
    url = "https://api.gog.com/downlink/abc?access_token=TAJNE-123"
    req = httpx.Request("GET", url)
    resp = httpx.Response(403, request=req)
    exc = httpx.HTTPStatusError("403 Forbidden for " + url, request=req, response=resp)
    wynik = loggable_error(exc)
    assert "TAJNE-123" not in wynik
    assert "access_token" not in wynik
    assert "403" in wynik, "oczyszczanie zabralo tez kod odpowiedzi, ktory jest potrzebny"


def test_stare_wpisy_sa_czyszczone_na_starcie():
    """The same leak is in the released version, so rows written by it are out
    there in databases that will be upgraded onto this one."""
    main = (pathlib.Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    assert "download_jobs" in main and "access_token" in main, (
        "brak czyszczenia starych error_msg na starcie")
