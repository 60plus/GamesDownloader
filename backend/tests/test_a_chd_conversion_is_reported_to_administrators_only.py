"""A CHD conversion is reported to administrators, and its failure names no paths.

Found by the 1.0.34 audit (#17), older than that release. A conversion is an
administrator's action - only ROMS_WRITE may start or cancel one - but it was
reported to everybody:

  - every progress and failure event went out with no room, which the socket
    layer turns into a broadcast to every signed-in account;
  - the list of conversions asked only ROMS_READ, which every account holds;
  - and a failure to put the converted disc in place carried the OSError's own
    text, where Python names both files: the temporary work folder and the path
    in the ROM library.

So the events go to the administrators' room, the list asks what starting one
asks, and the move failure says what went wrong without where. chdman's own
diagnosis stays in the report: an administrator is the one reading it now.
"""

from __future__ import annotations

import errno
import io
import pathlib
import re
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.asyncio
async def test_a_conversion_is_announced_to_the_administrators_room(monkeypatch):
    import asyncio

    from handler.roms import chd_jobs

    sent = []

    async def _emit(event, data, **kwargs):
        sent.append((event, kwargs))

    monkeypatch.setattr(chd_jobs, "emit_event", _emit)
    job = chd_jobs._ChdJob(id=1, rom_id=2, title="Crash", total_discs=1)
    chd_jobs._announce(job)
    await asyncio.sleep(0)

    assert sent, "nic nie wyszlo"
    event, kwargs = sent[0]
    assert event == chd_jobs.EVENT
    assert kwargs.get("to_role") == "admin", (
        f"konwersja CHD rozglaszana do wszystkich zalogowanych: {kwargs!r}"
    )


def test_the_list_asks_what_starting_one_asks():
    source = io.open(BACKEND / "endpoints" / "roms" / "roms_router.py", encoding="utf-8").read()
    listing = re.search(r'@protected_route\(router\.get, "/convert-chd/jobs", scopes=\[([^\]]*)\]\)', source)
    starting = re.search(r'@protected_route\(router\.post, "/\{rom_id\}/convert-chd", scopes=\[([^\]]*)\]\)', source)
    assert listing and starting
    assert listing.group(1) == starting.group(1) == "Scopes.ROMS_WRITE", (
        "liste konwersji z ich bledami czyta kazde konto"
    )


def test_a_failed_move_says_what_went_wrong_without_where():
    from handler.roms.chd_convert import ChdError, _move_failure

    err = OSError(errno.ENOSPC, "No space left on device",
                  "/tmp/gd-chd-abc/Game.chd", None, "/data/roms/psx/.Game.chd.part")
    failure = _move_failure(err)

    assert isinstance(failure, ChdError) and failure.code == "chd_move"
    said = str(failure)
    assert "No space left on device" in said, "komunikat nie mowi, co sie stalo"
    assert "/tmp/gd-chd" not in said and "/data/roms" not in said, (
        f"blad przeniesienia plyty niesie sciezki z wnetrza serwera: {said!r}"
    )


def test_a_move_failure_with_no_reason_still_says_something():
    from handler.roms.chd_convert import _move_failure

    said = str(_move_failure(OSError("/data/roms/psx/.Game.chd.part")))
    assert "/data/roms" not in said and said.strip()


def test_the_conversion_puts_its_move_failure_through_it():
    source = io.open(BACKEND / "handler" / "roms" / "chd_convert.py", encoding="utf-8").read()
    at = source.index("shutil.copyfile(out, staged)")
    block = source[at:at + 400]
    assert "raise _move_failure(err) from err" in block
    assert "{err}" not in block
