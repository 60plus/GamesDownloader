"""Two enablers: a plugin may ship WebAssembly, and a core gets its threads.

Neither changes anything visible today. Both are the difference between a
future plugin working and failing in a way that reads as a broken product.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from endpoints.settings.plugins_router import ASSET_MEDIA_TYPES


# ── A plugin may ship a module and a wasm blob ────────────────────────────────


def test_a_module_is_served_as_javascript():
    """A browser refuses to import() anything served as a byte stream.

    Not a preference on its part: the module fetch is rejected on the media
    type before the file is parsed, so a plugin shipping an emulator loader
    fails with nothing useful in the way of an explanation.
    """
    assert ASSET_MEDIA_TYPES[".js"] == "text/javascript"
    assert ASSET_MEDIA_TYPES[".mjs"] == "text/javascript"


def test_wasm_is_served_as_wasm():
    """instantiateStreaming accepts application/wasm and nothing else.

    This is the single line standing between us and Ruffle for Flash or js-dos
    for DOS, both of which are on the roadmap as plugins.
    """
    assert ASSET_MEDIA_TYPES[".wasm"] == "application/wasm"


def test_the_artwork_that_already_worked_still_does():
    for ext, expected in (
        (".webp", "image/webp"), (".png", "image/png"),
        (".jpg", "image/jpeg"), (".svg", "image/svg+xml"),
        (".xml", "application/xml"), (".json", "application/json"),
    ):
        assert ASSET_MEDIA_TYPES[ext] == expected


def test_jpeg_and_gif_are_no_longer_missing():
    # .jpg was listed and .jpeg was not, so half the spellings of one format
    # went out as a byte stream.
    assert ASSET_MEDIA_TYPES[".jpeg"] == "image/jpeg"
    assert ASSET_MEDIA_TYPES[".gif"] == "image/gif"


# ── A core that needs threads gets them ───────────────────────────────────────


def _player_source() -> str:
    """The player page, or a skip where the frontend tree is not present.

    The suite is run two ways: from the repository root in CI, and from /app
    inside the image, where only the backend was copied. A test that reads a
    frontend file has to say so rather than fail, or the local run grows a
    false negative that trains everyone to ignore it.
    """
    here = pathlib.Path(__file__).resolve().parent.parent.parent
    player = here / "frontend" / "public" / "player.html"
    if not player.is_file():
        pytest.skip("frontend tree not present in this environment")
    return player.read_text(encoding="utf-8", errors="ignore")


def test_threads_are_decided_by_the_core_not_only_by_a_switch():
    """Needing threads is a property of the core, not a preference.

    Without them EmulatorJS will not start the game at all: it shows "Error for
    site owner" and writes the real reason only to the console, so to whoever
    is trying to play, the game is broken. Leaving that behind a switch nobody
    knew to turn on is how PSP came to be quietly unplayable.
    """
    source = _player_source()
    match = re.search(r"CORES_NEEDING_THREADS\s*=\s*\[([^\]]*)\]", source)
    assert match, "the core list is gone from player.html"
    listed = {piece.strip().strip("'\"") for piece in match.group(1).split(",") if piece.strip()}

    # EmulatorJS's own answer is requiresThreads(core) -> ppsspp, dosbox_pure.
    # Both spellings are covered because we hand over the platform name and it
    # resolves that to a core: psp becomes ppsspp, dos becomes dosbox_pure.
    assert {"psp", "ppsspp", "dosbox_pure"} <= listed

    # And the switch still works for everything else.
    assert "gd_ejs_threads" in source
