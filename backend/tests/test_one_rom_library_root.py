"""Everything that touches the ROM tree has to agree where it is.

The ROM library root is `ROMS_PATH` unless an administrator moved it in
Settings > ROMs, in which case it is `roms.library_path`. Three places resolved
that correctly and each wrote the same two lines to do it. A fourth,
`rom_removal`, imported the bare constant instead.

On an install with a relocated library that is not a cosmetic difference. The
deleters check every path against their root before unlinking, so with the wrong
root the containment check fails for EVERY ROM: no file is deleted, the endpoint
reports `files_deleted: 0`, and the database row is removed anyway. The row is
gone, the file is still there, and the next scan puts it back with no cover, no
identifiers and no history. Silently, and only on somebody else's install.

One function now, and this test keeps it that way.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Everything that resolves the root, or that guards a path against it.
TOUCHES_THE_ROOT = [
    "handler/roms/rom_source_handler.py",
    "handler/roms/rom_removal.py",
    "endpoints/roms/roms_router.py",
    "endpoints/settings/roms_settings_router.py",
    "handler/filesystem/rom_scanner.py",
]


def _source(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


def test_the_rule_is_written_once():
    """`cfg.get("library_path") or ROMS_PATH` copied into four files is four
    chances for one of them to be forgotten, which is exactly what happened."""
    copies = []
    for rel in TOUCHES_THE_ROOT:
        found = re.findall(r'get\(\s*["\']library_path["\']\s*\)\s*or\s+ROMS_PATH',
                           _source(rel))
        copies.extend([rel] * len(found))
    assert len(copies) <= 1, (
        f"regula o korzeniu biblioteki ROM-ow jest przepisana w kilku miejscach: {copies}"
    )


def test_the_deleter_asks_for_the_configured_root():
    """The one that was wrong. It must not reach for the bare constant."""
    source = _source("handler/roms/rom_removal.py")
    assert "roms_library_path" in source, (
        "kasowanie ROM-ow nadal sprawdza sciezki wobec stalej z konfiguracji "
        "zamiast wobec katalogu ustawionego przez administratora"
    )


@pytest.mark.asyncio
async def test_the_scheduled_scan_walks_the_library_the_administrator_moved(monkeypatch):
    """Found by the 1.0.34 audit. The timed scan reached for the bare constant,
    so on an install whose library had been moved it walked the old, empty
    folder on every turn: nothing new ever appeared, and the setting looked as
    if it did nothing at all."""
    import asyncio

    from config import config_manager
    from handler.filesystem import rom_scanner as scanner

    def _moved(_name):
        return {"library_path": "/mnt/big/roms", scanner.SCAN_INTERVAL_KEY: "6"}

    walked = []

    async def _scan(path):
        walked.append(path)
        raise asyncio.CancelledError  # one turn is the whole question

    monkeypatch.setattr(config_manager, "get_section", _moved)
    monkeypatch.setattr(scanner, "scan_roms_path", _scan)
    monkeypatch.setattr(scanner, "_SCAN_LOOP_START_DELAY_S", 0)

    with pytest.raises(asyncio.CancelledError):
        await scanner.periodic_scan_loop()

    assert walked == ["/mnt/big/roms"], (
        f"skan z harmonogramu chodzi po domyslnym katalogu zamiast po bibliotece "
        f"przeniesionej w ustawieniach: {walked!r}"
    )


def test_the_helper_falls_back_to_the_constant():
    """Nobody has set a library path on a fresh install, and the fallback is
    what makes that work rather than crash."""
    from config import ROMS_PATH
    from handler.filesystem.rom_paths import roms_library_path

    class _Empty:
        @staticmethod
        def get_section(_name):
            return {}

    assert roms_library_path(_Empty()) == ROMS_PATH


def test_the_helper_prefers_what_the_administrator_set():
    from handler.filesystem.rom_paths import roms_library_path

    class _Moved:
        @staticmethod
        def get_section(_name):
            return {"library_path": "/mnt/big/roms"}

    assert roms_library_path(_Moved()) == "/mnt/big/roms"


def test_a_blank_setting_is_not_a_path():
    """An empty string in the config is somebody clearing the field, not a
    request to treat the filesystem root as the ROM library."""
    from config import ROMS_PATH
    from handler.filesystem.rom_paths import roms_library_path

    class _Blank:
        @staticmethod
        def get_section(_name):
            return {"library_path": "   "}

    assert roms_library_path(_Blank()) == ROMS_PATH
