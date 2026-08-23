"""A battery save must not be able to go backwards.

The server keeps one row per (user, rom) and wrote it unconditionally, so
whichever browser left the game last won. Playing the same game in two browsers
could therefore undo an evening's progress, silently. Observed on the test
server rather than reasoned about: a card with a file time of 21:10 whose
contents were the 19:38 version.

The sender now says which version it started from, and the server refuses to
write over anything else. These are the corners of that decision.
"""
from __future__ import annotations

import pytest

from endpoints.roms.savestate_router import _is_stale_write

A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
C = "cccccccccccccccccccccccccccccccc"


def test_pisanie_na_tej_wersji_od_ktorej_zaczelismy_przechodzi():
    """The ordinary save: nobody else touched it."""
    assert not _is_stale_write(base=A, stored=A, incoming=B)


def test_pisanie_na_cudzej_nowszej_wersji_jest_odrzucane():
    """The bug, stated directly."""
    assert _is_stale_write(base=A, stored=B, incoming=C)


def test_brak_deklaracji_wersji_nie_blokuje():
    """A player from before this change has to keep being able to save."""
    assert not _is_stale_write(base=None, stored=B, incoming=C)
    assert not _is_stale_write(base="", stored=B, incoming=C)


def test_pierwszy_zapis_dla_gry_przechodzi():
    """Nothing stored means nothing to lose."""
    assert not _is_stale_write(base=A, stored=None, incoming=B)
    assert not _is_stale_write(base=A, stored="", incoming=B)


def test_identyczna_tresc_nie_jest_konfliktem():
    """Two machines arriving at the same card agree with each other. Refusing
    would mean a browser that is right about the contents gets told it is
    wrong, and then never syncs again."""
    assert not _is_stale_write(base=A, stored=B, incoming=B)


def test_wyslanie_dokladnie_tego_co_juz_lezy_przechodzi():
    """The auto sync re-sends an unchanged card on its timer."""
    assert not _is_stale_write(base=A, stored=A, incoming=A)


@pytest.mark.parametrize("base,stored,incoming,odrzuc", [
    (A, B, C, True),    # ktos pisal w miedzyczasie, tresc inna
    (A, A, C, False),   # nikt nie pisal
    (A, B, B, False),   # zgoda co do tresci
    (None, B, C, False),  # stary odtwarzacz
    (A, None, C, False),  # pierwszy zapis
])
def test_tabela_decyzji(base, stored, incoming, odrzuc):
    assert _is_stale_write(base, stored, incoming) is odrzuc


def test_odpowiedz_niesie_skrot_tresci():
    """The client cannot say what version it holds if the server never tells
    it. The column has existed since the beginning and was simply not sent."""
    import ast
    import pathlib

    zrodlo = (pathlib.Path(__file__).resolve().parent.parent
              / "endpoints" / "roms" / "savestate_router.py").read_text(encoding="utf-8")
    drzewo = ast.parse(zrodlo)
    for w in ast.walk(drzewo):
        if isinstance(w, ast.FunctionDef) and w.name == "_save_dict":
            assert "content_hash" in ast.unparse(w), "_save_dict nie oddaje wersji karty"
            return
    raise AssertionError("nie ma _save_dict")
