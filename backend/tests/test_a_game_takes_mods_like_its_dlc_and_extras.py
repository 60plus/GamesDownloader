"""A GOG or custom game keeps mods beside its DLC and extras.

The owner (2026-09-18): a library game had three kinds of file - the game, a
DLC and an extra - and nowhere to put a mod. It gets a fourth, `mod`, the same
word a ROM's mods/ folder is offered under, and it goes the way the other two
kinds beside the game do:

  * on disk in the game's own `mods/` folder, which a folder scan also reads
    back as mods (and `mod/`, the way it reads `extra/` and `extras/` alike) -
    inside a game's folder only, never at the top of a library;
  * an uploader may add one to a game somebody else added, as they may a DLC
    or an extras pack, charged to their own account;
  * the Package button bundles the folder into its own `mods.zip`.

And the kind of a file is one of those four. It used to be whatever the form
sent: an upload stored any sixteen characters it was given, and every screen
drew a kind it did not know as a DLC.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from models.library_file import FILE_TYPES, file_type_of


# ── The four kinds ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("given, kind", [
    ("game", "game"), ("dlc", "dlc"), ("extra", "extra"), ("mod", "mod"),
    ("extras", "extra"), ("bonus", "extra"), ("mods", "mod"), ("MODS", "mod"), ("Mod", "mod"),
])
def test_every_way_of_saying_a_kind_comes_to_one(given, kind):
    assert file_type_of(given) == kind


@pytest.mark.parametrize("given", ["zzz", "", None, "../x", "installer", "patch", "mods/"])
def test_a_kind_that_is_not_one_of_the_four_is_not_one(given):
    assert file_type_of(given) is None


def test_there_are_four_kinds():
    assert set(FILE_TYPES) == {"game", "dlc", "extra", "mod"}


# ── Where an upload lands ───────────────────────────────────────────────────


@pytest.fixture
def games(tmp_path, monkeypatch):
    import endpoints.library.upload_router as ur
    monkeypatch.setattr(ur, "GAMES_PATH", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("kind", ["mod", "mods"])
def test_a_mod_goes_into_the_games_mods_folder(games, kind):
    from endpoints.library.upload_router import _dest_dir_for

    assert _dest_dir_for("Doom", "windows", kind) == games / "CUSTOM" / "Doom" / "mods"


def test_the_other_kinds_land_where_they_always_did(games):
    from endpoints.library.upload_router import _dest_dir_for

    assert _dest_dir_for("Doom", "windows", "game") == games / "CUSTOM" / "Doom" / "windows"
    assert _dest_dir_for("Doom", "all", "extra") == games / "CUSTOM" / "Doom" / "extra"
    assert _dest_dir_for("Doom", "linux", "dlc") == games / "CUSTOM" / "Doom" / "dlc"


@pytest.mark.parametrize("kind", ["zzz", "../../plugins", "installer", ""])
def test_an_upload_of_no_known_kind_is_refused(games, kind):
    from endpoints.library.upload_router import _dest_dir_for

    with pytest.raises(ValueError):
        _dest_dir_for("Doom", "windows", kind)


def test_the_row_says_mod_whatever_the_form_called_it():
    source = (Path(__file__).resolve().parent.parent / "endpoints" / "library"
              / "upload_router.py").read_text(encoding="utf-8")
    body = source[source.index("async def _finalize_upload("):]
    body = body[:body.index("\n@")]
    assert "file_type_of(file_type)" in body, "wiersz dostaje surowy rodzaj z formularza"


# ── What a folder scan makes of it ──────────────────────────────────────────


def test_a_folder_scan_reads_mods_as_mods(tmp_path, monkeypatch):
    from endpoints.library import library_router as L

    monkeypatch.setattr(L, "_rel_path", lambda p: p)
    game = tmp_path / "Doom"
    for folder, name in (("windows", "setup.exe"), ("mods", "brutal.pk3"),
                         ("Mod", "hd.pk3"), ("extras", "manual.pdf"), ("dlc", "sigil.wad")):
        (game / folder).mkdir(parents=True)
        (game / folder / name).write_bytes(b"x")

    kinds = {f.filename: f.file_type for f in L._scan_folder_files(str(game), 1, "custom")}

    assert kinds == {"setup.exe": "game", "brutal.pk3": "mod", "hd.pk3": "mod",
                     "manual.pdf": "extra", "sigil.wad": "dlc"}


def test_a_mods_folder_at_the_top_of_a_library_stays_what_it_was():
    """Only inside a game's folder. At the top of a library a mods/ folder has
    long been a folder of its own that people exclude by name
    (test_the_scan_and_the_preview_agree_about_a_game.py); read as a container,
    every subfolder of it would become a game on the next scan."""
    from endpoints.library import library_router as L

    assert not {"mods", "mod"} & L._TYPE_CONTAINER_NAMES


# ── Packing ─────────────────────────────────────────────────────────────────


def test_the_package_button_bundles_mods_into_their_own_archive():
    from handler.gog import zip_packer as Z

    assert ("mods", "all", "mod") in Z._TYPE_GROUPS and ("mod", "all", "mod") in Z._TYPE_GROUPS
    assert Z._group_archive_name("Doom", "mods", "mod") == "mods.zip"


def test_a_game_titled_mods_is_still_its_own_folder(tmp_path, monkeypatch):
    """The title folder is never taken for a content group, whatever it is called."""
    from handler.gog import zip_packer as Z
    from types import SimpleNamespace

    monkeypatch.setattr(Z, "GAMES_PATH", str(tmp_path / "games"))
    monkeypatch.setattr(Z, "BASE_PATH", str(tmp_path))
    files = [SimpleNamespace(file_path="games/CUSTOM/Mods/windows/setup.exe")]

    assert Z._game_base_dir(files, title="Mods") == str(Path(tmp_path / "games" / "CUSTOM" / "Mods"))


# ── Edited by hand ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("body", ["FileCreateBody", "FileUpdateBody"])
def test_an_administrator_cannot_set_a_kind_that_is_not_one(body):
    from pydantic import ValidationError

    from endpoints.library import library_router as L

    fields = {"filename": "a.zip", "file_path": "games/CUSTOM/A/a.zip"} if body == "FileCreateBody" else {}
    with pytest.raises(ValidationError):
        getattr(L, body)(**fields, file_type="zzz")
    assert getattr(L, body)(**fields, file_type="mods").file_type == "mod"
