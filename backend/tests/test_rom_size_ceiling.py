"""The per-file download ceiling, and the setting that moves it.

The ceiling has to stay finite: it is the only thing stopping a mis-identified
whole-platform archive, which runs to hundreds of GB, from filling the disk. But
it was originally sized from DVDs (a dual-layer rip at ~8.5 GB, a packaged Xbox
360 title at ~13 GB), and a Blu-ray is not a DVD. Every PS3 disc sat above the
16 GiB result and was refused with "ROM exceeds the maximum allowed size" before
a single byte was written.

The sizes below are real: 28837490593 is the Metal Gear Solid 4 (Europe, v02.00)
archive as archive.org reports it, one of the files that failed.

The save path gets its own tests for a reason. save_section() replaces a whole
section, so this screen used to write its three known keys over everything else
the section held, and a max_rom_bytes set by hand disappeared on the first save
from that screen. That is the same defect that once wiped user preferences, in a
second place.
"""
from __future__ import annotations

import asyncio
import types

import pytest
from fastapi import HTTPException

import handler.roms.rom_source_handler as h
from endpoints.settings import roms_settings_router as r
from handler.auth.scopes import Scope

GIB = 1024 ** 3

MGS4_EUROPE_V0200 = 28_837_490_593   # measured on archive.org
FULL_DUAL_LAYER_BLU_RAY = 50 * 10 ** 9
WHOLE_PLATFORM_ARCHIVE = 400 * GIB


def _with_section(monkeypatch, section):
    """Point both the handler and the router at a fixed `roms` config."""
    monkeypatch.setattr(h.config_manager, "get_section",
                        lambda name: dict(section) if name == "roms" else {})


# ── The ceiling in force ──────────────────────────────────────────────────────

def test_default_clears_a_full_dual_layer_blu_ray(monkeypatch):
    _with_section(monkeypatch, {})
    assert h.max_rom_bytes() > FULL_DUAL_LAYER_BLU_RAY


def test_default_accepts_the_disc_that_used_to_be_refused(monkeypatch):
    _with_section(monkeypatch, {})
    assert MGS4_EUROPE_V0200 < h.max_rom_bytes()


def test_default_still_rejects_a_whole_platform_archive(monkeypatch):
    _with_section(monkeypatch, {})
    assert WHOLE_PLATFORM_ARCHIVE > h.max_rom_bytes()


def test_the_setting_moves_the_ceiling(monkeypatch):
    _with_section(monkeypatch, {"max_rom_bytes": 8 * GIB})
    assert h.max_rom_bytes() == 8 * GIB


@pytest.mark.parametrize("stored", [
    {},                            # never set
    {"max_rom_bytes": 0},          # explicitly "no override"
    {"max_rom_bytes": None},       # key present but empty
    {"max_rom_bytes": "sixty"},    # hand-edited nonsense
])
def test_unset_or_unusable_falls_back_to_the_default(monkeypatch, stored):
    _with_section(monkeypatch, stored)
    assert h.max_rom_bytes() == h._DEFAULT_MAX_ROM_BYTES


def test_a_broken_config_never_takes_the_downloader_down(monkeypatch):
    def _boom(_name):
        raise OSError("config unreadable")

    monkeypatch.setattr(h.config_manager, "get_section", _boom)
    assert h.max_rom_bytes() == h._DEFAULT_MAX_ROM_BYTES


# ── Room on the disk ──────────────────────────────────────────────────────────
#
# Raising the ceiling to 64 GiB made an old gap matter four times as much: the
# default compose puts the library and the database on one volume, so a download
# that fills it does not just fail itself. The check refuses only what would have
# failed anyway, but early, in words, and with a gigabyte still free.

def _free(monkeypatch, free_bytes):
    monkeypatch.setattr(
        h, "shutil",
        types.SimpleNamespace(disk_usage=lambda _p: types.SimpleNamespace(free=free_bytes)),
    )


def test_a_download_that_fits_is_allowed(monkeypatch):
    _free(monkeypatch, 200 * GIB)
    h.assert_room_for("/data/games/roms/ps3", 40 * GIB)      # must not raise


def test_a_download_larger_than_the_disk_is_refused(monkeypatch):
    _free(monkeypatch, 10 * GIB)
    with pytest.raises(ValueError):
        h.assert_room_for("/data/games/roms/ps3", 40 * GIB)


def test_filling_the_disk_to_the_last_byte_is_refused(monkeypatch):
    # Exactly enough room is still refused: the headroom is what keeps the
    # database writing while somebody clears space.
    _free(monkeypatch, 40 * GIB)
    with pytest.raises(ValueError):
        h.assert_room_for("/data/games/roms/ps3", 40 * GIB)


def test_the_refusal_names_both_numbers(monkeypatch):
    # A refusal that does not say how much is needed and how much there is leaves
    # the user with nothing to act on.
    _free(monkeypatch, 5 * GIB)
    with pytest.raises(ValueError) as err:
        h.assert_room_for("/data/games/roms/ps3", 40 * GIB)
    assert "40.0 GB" in str(err.value) and "5.0 GB" in str(err.value)


def test_an_unreadable_volume_does_not_refuse_a_good_download(monkeypatch):
    def _boom(_p):
        raise OSError("no such volume")

    monkeypatch.setattr(h, "shutil", types.SimpleNamespace(disk_usage=_boom))
    h.assert_room_for("/data/games/roms/ps3", 40 * GIB)      # must not raise


# ── The settings screen ───────────────────────────────────────────────────────

def _request(*scopes):
    """A request the scope decorator will accept, carrying exactly *scopes*."""
    return types.SimpleNamespace(
        state=types.SimpleNamespace(user=object(), scopes=set(scopes)),
    )


def _save(monkeypatch, stored, body):
    """Run the save endpoint against a captured write, return what it stores."""
    captured = {}

    monkeypatch.setattr(r.config_manager, "get_section",
                        lambda name: dict(stored) if name == "roms" else {})
    monkeypatch.setattr(r.config_manager, "save_section",
                        lambda name, values: captured.update(values))
    asyncio.run(r.save_rom_settings(_request(Scope.SETTINGS_WRITE), body))
    return captured


def test_saving_keeps_keys_the_screen_does_not_own(monkeypatch):
    out = _save(
        monkeypatch,
        stored={"max_rom_bytes": 32 * GIB, "some_future_key": "keep me"},
        body=r.RomSettingsBody(library_path="/data/games/roms"),
    )
    assert out["some_future_key"] == "keep me"


def test_saving_stores_the_new_ceiling(monkeypatch):
    out = _save(
        monkeypatch,
        stored={},
        body=r.RomSettingsBody(library_path="/data/games/roms",
                               max_rom_bytes=96 * GIB),
    )
    assert out["max_rom_bytes"] == 96 * GIB


def test_a_negative_ceiling_is_stored_as_no_override(monkeypatch):
    out = _save(
        monkeypatch,
        stored={},
        body=r.RomSettingsBody(library_path="/data/games/roms",
                               max_rom_bytes=-1),
    )
    assert out["max_rom_bytes"] == 0


def test_the_screen_reports_the_ceiling_actually_enforced(monkeypatch):
    # Nothing stored, so the screen must show the built-in ceiling rather than
    # the bare 0 that sits in the config. A screen showing a number the
    # downloader does not obey is worse than no screen.
    _with_section(monkeypatch, {})
    monkeypatch.setattr(r.config_manager, "get_section", lambda name: {})
    data = asyncio.run(r.get_rom_settings(_request(Scope.SETTINGS_READ)))
    assert data["max_rom_bytes"] == h._DEFAULT_MAX_ROM_BYTES


# ── Who may move it ───────────────────────────────────────────────────────────

def test_the_ceiling_cannot_be_changed_without_the_settings_scope():
    with pytest.raises(HTTPException) as err:
        asyncio.run(r.save_rom_settings(_request(Scope.SETTINGS_READ),
                                        r.RomSettingsBody(max_rom_bytes=1 * GIB)))
    assert err.value.status_code == 403


def test_the_ceiling_cannot_be_changed_anonymously():
    anon = types.SimpleNamespace(state=types.SimpleNamespace())
    with pytest.raises(HTTPException) as err:
        asyncio.run(r.save_rom_settings(anon, r.RomSettingsBody(max_rom_bytes=1 * GIB)))
    assert err.value.status_code == 401
