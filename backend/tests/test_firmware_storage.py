"""Firmware storage: the allow-list, and surviving a container recreate.

Firmware is the one class of file the application can never re-fetch. Covers
come back from a scraper and saves are re-made by playing; a Kickstart is a
file somebody supplied under their own licence, and losing it means asking
them for it again. Two things protect it and both are tested here:

- only paths a core actually declares are ever written or read, so a caller
  cannot walk out of the store by asking for a clever name;
- when /data/firmware has no volume of its own the store moves to a directory
  that does, and moves the files back once the volume appears.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from handler.roms import firmware_handler as fh


@pytest.fixture(autouse=True)
def _isolated_root(tmp_path, monkeypatch):
    """Point the store at a temp directory and forget any cached root."""
    monkeypatch.setattr(fh, "_root_cache", tmp_path / "firmware")
    yield
    monkeypatch.setattr(fh, "_root_cache", None)


# ── Allow-list ────────────────────────────────────────────────────────────────

def test_undeclared_path_is_refused():
    with pytest.raises(ValueError):
        fh._resolved("amiga", "../../etc/passwd")


def test_declared_path_resolves_under_the_core_directory():
    declared = next(iter(fh.known_paths("amiga")))
    p = fh._resolved("amiga", declared)
    assert fh.firmware_root() in p.parents


def test_cores_sharing_a_libretro_core_share_a_directory():
    # segaMD and segaCD both run genesis_plus_gx and want the same files;
    # storing per EmulatorJS name would make an operator supply each twice.
    assert fh._core_dir("segaMD") == fh._core_dir("segaCD")


# ── Persistence ───────────────────────────────────────────────────────────────

def test_ephemeral_path_falls_back_to_a_mounted_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "_root_cache", None)
    monkeypatch.setattr(fh, "FIRMWARE_PATH", str(tmp_path / "nowhere"))
    monkeypatch.setattr(fh, "FALLBACK_ROOT", tmp_path / "config" / "firmware")
    monkeypatch.setattr(fh, "is_ephemeral", lambda _p: True)
    assert fh.firmware_root() == tmp_path / "config" / "firmware"


def test_persistent_path_is_used_as_is(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "_root_cache", None)
    monkeypatch.setattr(fh, "FIRMWARE_PATH", str(tmp_path / "firmware"))
    monkeypatch.setattr(fh, "is_ephemeral", lambda _p: False)
    assert fh.firmware_root() == tmp_path / "firmware"


def test_files_move_onto_the_volume_once_it_appears(tmp_path, monkeypatch):
    fallback = tmp_path / "config" / "firmware"
    real = tmp_path / "firmware"
    (fallback / "puae").mkdir(parents=True)
    (fallback / "puae" / "kick34005.A500").write_bytes(b"rom")

    monkeypatch.setattr(fh, "_root_cache", real)
    monkeypatch.setattr(fh, "FALLBACK_ROOT", fallback)

    assert fh.adopt_fallback_firmware() == 1
    assert (real / "puae" / "kick34005.A500").read_bytes() == b"rom"
    assert not (fallback / "puae" / "kick34005.A500").exists()


def test_a_file_already_on_the_volume_is_not_overwritten(tmp_path, monkeypatch):
    fallback = tmp_path / "config" / "firmware"
    real = tmp_path / "firmware"
    (fallback / "puae").mkdir(parents=True)
    (fallback / "puae" / "kick34005.A500").write_bytes(b"old")
    (real / "puae").mkdir(parents=True)
    (real / "puae" / "kick34005.A500").write_bytes(b"current")

    monkeypatch.setattr(fh, "_root_cache", real)
    monkeypatch.setattr(fh, "FALLBACK_ROOT", fallback)

    assert fh.adopt_fallback_firmware() == 0
    assert (real / "puae" / "kick34005.A500").read_bytes() == b"current"


def test_adoption_is_a_no_op_when_the_fallback_is_the_store(tmp_path, monkeypatch):
    fallback = tmp_path / "config" / "firmware"
    fallback.mkdir(parents=True)
    monkeypatch.setattr(fh, "_root_cache", fallback)
    monkeypatch.setattr(fh, "FALLBACK_ROOT", fallback)
    assert fh.adopt_fallback_firmware() == 0
