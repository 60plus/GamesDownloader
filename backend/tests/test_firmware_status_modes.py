"""The firmware overview asks a cheap question, so it should pay a cheap price.

`GET /api/firmware` reports, per core, how many declared files are on hand. It
built that by calling `status()` for all twenty-seven cores, and `status()`
MD5-hashed every stored file to fill in a field the overview never reads. Five
of the EmulatorJS core names alias onto genesis_plus_gx and share one
directory, so that set was read five times in a single request - and the screen
reloads after every upload, fetch and delete.

`with_hash=False` answers presence and size from a stat. The hashing mode stays
for the per-core screen, where the operator does compare a dump against a
reference set, and that one now runs off the event loop.
"""
from __future__ import annotations

import hashlib
import inspect

import handler.roms.firmware_handler as fh
from handler.roms.firmware_registry import FIRMWARE, for_core

# A core with at least one declared file, chosen from the registry itself so the
# test does not go stale if the registry is re-ordered.
CORE = next(c for c in sorted(FIRMWARE) if for_core(c))
FIRST = for_core(CORE)[0]
CONTENT = b"not a real bios, but a real file" * 16


def _store(tmp_path, monkeypatch, *, present: bool = True):
    core_dir = tmp_path / "core"
    core_dir.mkdir()
    if present:
        target = core_dir / FIRST.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(CONTENT)
    monkeypatch.setattr(fh, "_core_dir", lambda _core: core_dir)
    return core_dir


def _entry(rows):
    return next(r for r in rows if r["path"] == FIRST.path)


# ── The cheap mode ───────────────────────────────────────────────────────────

def test_without_a_hash_a_stored_file_is_still_present_and_sized(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    row = _entry(fh.status(CORE, with_hash=False))
    assert row["present"] is True
    assert row["size"] == len(CONTENT)
    assert row["md5"] is None


def test_without_a_hash_a_missing_file_is_still_missing(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch, present=False)
    row = _entry(fh.status(CORE, with_hash=False))
    assert row["present"] is False
    assert row["size"] is None
    assert row["md5"] is None


def test_the_file_is_not_read_at_all_in_the_cheap_mode(tmp_path, monkeypatch):
    """The whole point. A firmware store is tens of megabytes and this runs for
    every core on every load of the screen."""
    _store(tmp_path, monkeypatch)
    monkeypatch.setattr(
        fh, "_digest",
        lambda p: (_ for _ in ()).throw(AssertionError("hashed in the cheap mode")),
    )
    assert _entry(fh.status(CORE, with_hash=False))["present"] is True


# ── The hashing mode is unchanged ────────────────────────────────────────────

def test_hashing_is_still_the_default(tmp_path, monkeypatch):
    """Every other caller keeps what it had."""
    _store(tmp_path, monkeypatch)
    row = _entry(fh.status(CORE))
    assert row["md5"] == hashlib.md5(CONTENT).hexdigest()
    assert row["size"] == len(CONTENT)
    assert row["present"] is True


def test_both_modes_agree_on_which_files_are_declared(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    cheap = [r["path"] for r in fh.status(CORE, with_hash=False)]
    full = [r["path"] for r in fh.status(CORE)]
    assert cheap == full


def test_both_modes_agree_on_presence(tmp_path, monkeypatch):
    _store(tmp_path, monkeypatch)
    cheap = {r["path"]: r["present"] for r in fh.status(CORE, with_hash=False)}
    full = {r["path"]: r["present"] for r in fh.status(CORE)}
    assert cheap == full


# ── Who uses which ───────────────────────────────────────────────────────────

def test_the_overview_asks_for_the_cheap_one_and_counts_from_it():
    from endpoints.roms import firmware_router

    source = inspect.getsource(firmware_router.list_cores)
    assert "with_hash=False" in source
    # It used to walk the disk a second time to count the missing required
    # files; those are already in the rows it just read.
    assert "firmware_handler.missing_required(core)" not in source


def test_the_per_core_screen_still_hashes_but_not_on_the_event_loop():
    from endpoints.roms import firmware_router

    source = inspect.getsource(firmware_router.core_status)
    assert "asyncio.to_thread" in source
    assert "with_hash=False" not in source
