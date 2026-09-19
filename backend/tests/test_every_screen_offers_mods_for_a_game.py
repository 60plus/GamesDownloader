"""Every screen that adds, lists or bundles a game's files knows a mod.

The server takes a fourth kind of file (test_a_game_takes_mods_like_its_dlc_and_
extras.py). A form that cannot send it leaves the kind unreachable from that
theme, and a download picker that does not know it draws the group under the
DLC heading - the nested ternaries fell through to "DLC" for anything that was
not a game or an extra.

  upload     AddFileForm (Modern, Classic), GamesLibrary (Modern), ClassicLayout,
             NeonHorizonLibrary, VaporUploadDialog
  download   GamesGameDetail (Modern, Neon Horizon), ClassicGameDetail,
             VaporDownloadDialog, VaporGameDetail's file list
  package    PackageDialog (Modern, Classic), VaporPackageDialog
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / "frontend" / "src"
WORK = REPO.parent
VAPOR = WORK / "vapor_build" / "gd3-vapor"
NH = WORK / "nh_build" / "neon-horizon"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} nie jest obecny w tym drzewie")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("form", [
    FRONTEND / "components" / "games" / "AddFileForm.vue",
    FRONTEND / "views" / "games" / "GamesLibrary.vue",
    FRONTEND / "layouts" / "ClassicLayout.vue",
    NH / "NeonHorizonLibrary.vue",
    VAPOR / "VaporUploadDialog.vue",
])
def test_every_upload_form_can_send_a_mod(form):
    assert '<option value="mod">' in _read(form), "formularz nie pozwala wgrac moda"


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "games" / "GamesGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
])
def test_the_download_picker_has_a_mods_group_under_its_own_name(page):
    source = _read(page)
    assert "'extra', 'mod']" in source, "mody nie maja swojej grupy w oknie pobierania"
    assert "t('detail.type_mods')" in source
    assert ": t('detail.type_dlc') }}" not in source, "nieznany rodzaj nadal wychodzi jako DLC"


def test_vapor_orders_and_colours_the_mods_group():
    dialog = _read(VAPOR / "VaporDownloadDialog.vue")
    assert '"extra", "mod"]' in dialog
    detail = _read(VAPOR / "VaporGameDetail.vue")
    assert ".vp-dlfile-type.t-mod" in detail, "chip MOD bez koloru w Show details"


@pytest.mark.parametrize("dialog", [
    FRONTEND / "components" / "games" / "PackageDialog.vue",
    VAPOR / "VaporPackageDialog.vue",
])
def test_the_package_dialog_names_the_mods_group(dialog):
    assert "'mods'" in _read(dialog).replace('"', "'"), "grupa mods/ bez nazwy w oknie pakowania"
