"""A row that goes has to take its files with it, whichever button sent it.

Deleting one ROM does this properly: `delete_rom` lists the savestates and the
battery saves, removes those files, removes the media directory, and only then
drops the row. `rom_removal.delete_save_files` even says so in its own docstring
- "Called whichever way the ROM goes".

It was not. Two mass buttons - "remove the rows for files that are gone" and
"apply these exclusions" - called `rom_handler.delete` alone. The row and its
`rom_save_states` / `rom_saves` / `rom_plays` rows go by database cascade; the
bytes on disk stay for ever.

And they stay unreachable, not merely untidy: the save path is keyed by the
ROM's autoincrement id (`utils/save_paths.py`), so a file that comes back on the
next scan gets a NEW id and a new directory. Nothing in the interface can ever
name the old one again. The screen meanwhile promises the opposite in as many
words: "Removing takes the entries and everything hanging off them: saves, play
history, collection membership."

Order matters and is asserted below: the files have to go BEFORE the row, because
the lists that name them are read through the row and the cascade takes them.
"""

from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _route(name: str) -> str:
    source = io.open(BACKEND / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index(f"async def {name}(")
    return source[at:source.index("\n@", at)]


def test_the_single_delete_is_still_the_shape_the_others_copy():
    """The reference. If this ever stops removing files, the assertions below
    are copying the wrong thing."""
    body = _route("delete_rom")
    assert "delete_save_files" in body
    assert body.index("delete_save_files") < body.index("rom_handler.delete("), (
        "nawet wzorcowa trasa kasuje pliki po wierszu - lista zapisow czytana "
        "jest przez wiersz, wiec po kaskadzie jest juz pusta"
    )


def _helper() -> str:
    source = io.open(BACKEND / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    at = source.index("async def _take_the_bytes_too(")
    return source[at:source.index("\nasync def ", at + 10)]


def test_the_shared_helper_removes_both_kinds_of_bytes():
    """The two mass buttons call one helper rather than each growing their own
    copy of `delete_rom`'s block - so there is one place to be wrong."""
    body = _helper()
    assert "delete_save_files" in body, "pomocnik nie kasuje plikow zapisow"
    assert "delete_media_dir" in body, "pomocnik nie kasuje katalogu mediow"


def test_one_rows_files_do_not_stop_the_rest():
    """Each delete is its own committed transaction and the loops already say
    that one row must not decide the others. The files have to be as forgiving,
    or a single unreadable directory strands every row after it."""
    assert "except Exception" in _helper(), (
        "wyjatek przy plikach jednego wiersza zatrzyma cala petle"
    )


def test_removing_missing_rows_removes_their_saves():
    body = _route("remove_missing_roms")
    assert "_take_the_bytes_too(" in body, (
        "kasowanie brakujacych wierszy zostawia pliki zapisow na dysku, a klucz "
        "sciezki to id z autoinkrementu - po ponownym skanie wiersz dostanie "
        "NOWE id i stary katalog jest nieosiagalny na trwale"
    )
    assert body.index("_take_the_bytes_too(") < body.index("rom_handler.delete("), (
        "pliki kasowane po wierszu - kaskada juz zabrala liste, ktora je nazywa"
    )


def test_applying_exclusions_removes_their_saves():
    body = _route("apply_platform_exclusions")
    assert "_take_the_bytes_too(" in body, (
        "zastosowanie wykluczen zostawia pliki zapisow na dysku"
    )
    assert body.index("_take_the_bytes_too(") < body.index("rom_handler.delete("), (
        "pliki kasowane po wierszu"
    )


def test_the_screen_still_promises_this():
    """If the promise is ever softened, this test should be re-read rather than
    deleted - the promise is the reason the behaviour has to hold."""
    panel = (BACKEND.parent / "frontend" / "src" / "views" / "settings"
             / "SettingsMissingRoms.vue")
    text = io.open(panel, encoding="utf-8").read()
    assert "saves" in text and "play history" in text, (
        "ekran przestal obiecywac, ze zapisy znikaja - sprawdz, co jest prawda"
    )
