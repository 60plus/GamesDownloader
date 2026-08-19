"""Taking a ROM off the disk.

Every test here is about something that would be unrecoverable if it went
wrong. Deleting is the one operation with no undo, so what is checked first is
not that the right file goes, but that the wrong one stays: a stored path is
data, and this is data deciding what gets unlinked.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from handler.roms import rom_removal as rr


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    """The three directories the deleter is allowed to touch, and one it is not."""
    roms = tmp_path / "roms"
    saves = tmp_path / "saves"
    resources = tmp_path / "resources"
    outside = tmp_path / "somebody-elses"
    for d in (roms, saves, resources, outside):
        d.mkdir()
    monkeypatch.setattr(rr, "ROMS_PATH", str(roms))
    monkeypatch.setattr(rr, "SAVES_PATH", str(saves))
    monkeypatch.setattr(rr, "RESOURCES_PATH", str(resources))
    return SimpleNamespace(roms=roms, saves=saves, resources=resources, outside=outside)


def _rom(path: Path, name: str):
    return SimpleNamespace(fs_path=str(path), fs_name=name)


def _state(directory: Path, name: str, shot: str | None = None):
    return SimpleNamespace(
        file_path=str(directory), file_name=name,
        screenshot_path=str(directory / shot) if shot else None,
    )


# ── Staying inside the lines ─────────────────────────────────────────────────

def test_a_rom_path_pointing_outside_its_root_is_refused(roots):
    victim = roots.outside / "important.txt"
    victim.write_text("not yours")
    assert rr.delete_rom_file(_rom(roots.outside, "important.txt")) is False
    assert victim.exists()


def test_a_rom_path_climbing_out_with_dot_dot_is_refused(roots):
    victim = roots.outside / "important.txt"
    victim.write_text("not yours")
    climb = roots.roms / ".." / "somebody-elses"
    assert rr.delete_rom_file(_rom(climb, "important.txt")) is False
    assert victim.exists()


def test_a_symlinked_rom_path_is_refused(roots):
    # The path resolves out of the root even though it starts inside it. This
    # is the case a string-prefix check gets wrong.
    victim = roots.outside / "important.txt"
    victim.write_text("not yours")
    link = roots.roms / "escape"
    try:
        link.symlink_to(roots.outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available here")
    assert rr.delete_rom_file(_rom(link, "important.txt")) is False
    assert victim.exists()


def test_a_save_path_outside_its_root_is_refused(roots):
    victim = roots.outside / "someones.srm"
    victim.write_bytes(b"x")
    removed = rr.delete_save_files([], [_state(roots.outside, "someones.srm")])
    assert removed == 0
    assert victim.exists()


def test_the_media_dir_of_a_made_up_platform_stays_inside_resources(roots):
    victim = roots.outside / "keep.png"
    victim.write_bytes(b"x")
    assert rr.delete_media_dir("../../somebody-elses", 1) is False
    assert victim.exists()


# ── Removing what it should ──────────────────────────────────────────────────

def test_the_rom_file_goes(roots):
    (roots.roms / "amiga").mkdir()
    rom_file = roots.roms / "amiga" / "Legion.adf"
    rom_file.write_bytes(b"ADF")
    assert rr.delete_rom_file(_rom(roots.roms / "amiga", "Legion.adf")) is True
    assert not rom_file.exists()


def test_the_directory_it_emptied_goes_too(roots):
    (roots.roms / "amiga").mkdir()
    (roots.roms / "amiga" / "Legion.adf").write_bytes(b"ADF")
    rr.delete_rom_file(_rom(roots.roms / "amiga", "Legion.adf"))
    assert not (roots.roms / "amiga").exists()
    # ...but never the root itself, which the next scan still needs.
    assert roots.roms.is_dir()


def test_a_directory_with_something_left_in_it_stays(roots):
    (roots.roms / "amiga").mkdir()
    (roots.roms / "amiga" / "Legion.adf").write_bytes(b"ADF")
    (roots.roms / "amiga" / "Ishar.adf").write_bytes(b"ADF")
    rr.delete_rom_file(_rom(roots.roms / "amiga", "Legion.adf"))
    assert (roots.roms / "amiga" / "Ishar.adf").exists()


def test_a_rom_file_that_is_already_gone_is_not_an_error(roots):
    assert rr.delete_rom_file(_rom(roots.roms, "never-existed.adf")) is False


def test_saves_and_their_thumbnails_go(roots):
    d = roots.saves / "amiga" / "22" / "states" / "1"
    d.mkdir(parents=True)
    (d / "slot1.state").write_bytes(b"S")
    (d / "slot1.png").write_bytes(b"P")
    removed = rr.delete_save_files([_state(d, "slot1.state", "slot1.png")], [])
    assert removed == 1                      # the save, not the picture of it
    assert not (d / "slot1.state").exists()
    assert not (d / "slot1.png").exists()


def test_battery_saves_go(roots):
    d = roots.saves / "amiga" / "22" / "saves" / "1"
    d.mkdir(parents=True)
    (d / "Legion.srm").write_bytes(b"SRM")
    assert rr.delete_save_files([], [_state(d, "Legion.srm")]) == 1
    assert not (d / "Legion.srm").exists()


def test_the_scraped_artwork_goes(roots):
    media = roots.resources / "roms" / "amiga" / "22"
    (media / "screenshots").mkdir(parents=True)
    (media / "cover.png").write_bytes(b"IMG")
    (media / "screenshots" / "1.png").write_bytes(b"IMG")
    assert rr.delete_media_dir("amiga", 22) is True
    assert not media.exists()


def test_artwork_for_another_rom_of_the_same_platform_stays(roots):
    keep = roots.resources / "roms" / "amiga" / "23"
    keep.mkdir(parents=True)
    (keep / "cover.png").write_bytes(b"IMG")
    (roots.resources / "roms" / "amiga" / "22").mkdir(parents=True)
    rr.delete_media_dir("amiga", 22)
    assert (keep / "cover.png").exists()


def test_a_rom_with_no_artwork_is_not_an_error(roots):
    assert rr.delete_media_dir("amiga", 999) is False


# ── The count that gets shown to somebody ────────────────────────────────────

def test_the_tally_reads_back_as_the_endpoint_reports_it():
    r = rr.Removal(roms=3, rom_files=3, saves=2, names=["a.adf", "b.adf", "c.adf"])
    assert r.as_dict() == {
        "roms_deleted": 3, "files_deleted": 3, "saves_deleted": 2,
        "names": ["a.adf", "b.adf", "c.adf"],
    }
