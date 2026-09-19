"""A refusal must not destroy the thing it refused to replace.

The ROM upload route opened the destination itself - `open(dest_path, "wb")` -
which truncates on the first byte. Everything after that is downhill:

  the quota is checked AS THE BYTES ARRIVE, because a streamed body has no
  length until it ends. So a replacement that turns out not to fit is
  discovered when the old file has already been emptied, and the branch then
  calls `dest_path.unlink(missing_ok=True)` - taking the good file with it.

  any other failure - a full volume, a name the filesystem will not take, a
  browser that goes away - leaves the wreckage wearing the name of something
  that used to work.

413 is only reached when the allowance is filled TO THE BYTE. The ordinary case
is worse: an account near its limit sends a better dump of a ROM it already has,
`ceiling_for` hands back a positive figure smaller than the new file, and the
refusal arrives with the old file gone. Swapping a bad dump for a good one is
the reason this route accepts the same name twice, and it is exactly the case
that lost both copies.

The library upload has done this correctly since `_part_path` was written, and
that docstring says why in the same words. This one never got it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from handler.auth.scopes import Scope

UPLOADER_ID = 7
SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
BUDGET = 1024
OLD = b"GOOD DUMP" * 8


class _Upload:
    def __init__(self, filename: str, size: int, *, blow_up_after: int | None = None):
        self.filename = filename
        self._data = b"x" * size
        self._at = 0
        self._blow_up_after = blow_up_after

    async def read(self, size: int) -> bytes:
        if self._blow_up_after is not None and self._at >= self._blow_up_after:
            raise OSError("no space left on device")
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


@pytest.fixture
def route(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    shelf = tmp_path / "psx"
    shelf.mkdir(parents=True)

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return BUDGET

    async def nothing(*a, **k):
        return None

    async def clam_off():
        return False

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="psx", fs_slug="psx")

    async def my_row(_platform_id, fs_name):
        # The file already on the shelf is MINE, so replacing it is allowed and
        # the only thing that can refuse this upload is the allowance. Without
        # this the test would be measuring the ownership gate instead.
        return SimpleNamespace(id=99, fs_name=fs_name, published_by=UPLOADER_ID,
                               fs_size_bytes=len(OLD), fs_path=str(shelf))

    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(R.rom_handler, "any_row_named", my_row)

    async def newest_rom_id():
        return 0

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)

    async def no_live_limit(_user, **_k):
        # The budget here is the ceiling above. Uploads running side by side
        # are checked live as well, and that has its own tests
        # (test_uploads_running_side_by_side_see_each_other).
        return quota.Reservation(None, limit=0)

    monkeypatch.setattr(quota, "reservation_for", no_live_limit)
    monkeypatch.setattr(rsh, "scan_after_write", nothing)
    monkeypatch.setattr(R, "_stamp_uploaded", nothing)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    return R, shelf


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=UPLOADER_ID, username="u"), scopes=set(SCOPES),
    ))


async def _upload(R, files):
    tasks = BackgroundTasks()
    return await R.upload_roms(_request(), slug="psx", background_tasks=tasks, files=files)


def _leftovers(shelf):
    return sorted(p.name for p in shelf.iterdir() if p.suffix == ".part")


# ── The refusal ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_refusal_leaves_the_file_it_could_not_replace_untouched(route):
    R, shelf = route
    (shelf / "game.iso").write_bytes(OLD)

    out = await _upload(R, [_Upload("game.iso", BUDGET * 3)])

    assert out.status_code == 413
    assert (shelf / "game.iso").read_bytes() == OLD, (
        "odmowa skasowala plik, ktorego odmowila podmienic - uzytkownik "
        "podmieniajacy zly zrzut na dobry zostaje bez zadnego"
    )


@pytest.mark.asyncio
async def test_a_refusal_leaves_no_part_file_behind(route):
    R, shelf = route
    (shelf / "game.iso").write_bytes(OLD)

    await _upload(R, [_Upload("game.iso", BUDGET * 3)])

    assert _leftovers(shelf) == [], (
        "po odmowie zostaje niedokonczony plik, czyli dokladnie te bajty, "
        "ktore odmowa miala oszczedzic"
    )


@pytest.mark.asyncio
async def test_a_write_that_fails_leaves_the_old_file_alone(route):
    """Not only the quota. The blanket handler below catches everything, and
    every one of those failures used to arrive with the old file already
    emptied."""
    R, shelf = route
    (shelf / "game.iso").write_bytes(OLD)

    out = await _upload(R, [_Upload("game.iso", BUDGET // 2, blow_up_after=64)])

    assert out.status_code == 500
    assert (shelf / "game.iso").read_bytes() == OLD, (
        "blad zapisu zostawia po sobie ogryzek pod nazwa dzialajacego pliku"
    )
    assert _leftovers(shelf) == []


@pytest.mark.asyncio
async def test_a_write_that_fails_does_not_show_an_uploader_the_servers_insides(route):
    """The text of an OSError is the full path it could not write to - the
    server's layout - and this route is an uploader's (1.0.34 audit, #16). The
    reason goes to the log under a reference; the answer names the file."""
    import json

    R, _shelf = route

    out = await _upload(R, [_Upload("game.iso", BUDGET // 2, blow_up_after=64)])

    detail = json.loads(out.body)["detail"]
    assert "no space left on device" not in detail, (
        f"uploader dostal tekst wyjatku z wnetrza serwera: {detail!r}"
    )
    assert "game.iso" in detail and "ref " in detail


# ── ...and the legal case still passes ───────────────────────────────────────
#
# The lesson this round keeps teaching: a fix that only ever refuses is not a
# fix. Replacing your own file is the reason the route accepts a name twice.

@pytest.mark.asyncio
async def test_replacing_my_own_file_still_replaces_it(route):
    R, shelf = route
    (shelf / "game.iso").write_bytes(OLD)

    out = await _upload(R, [_Upload("game.iso", 40)])

    assert out["saved"] == ["game.iso"]
    assert (shelf / "game.iso").read_bytes() == b"x" * 40, (
        "podmiana wlasnego pliku przestala dzialac - to jest zwykly powod, dla "
        "ktorego ktos wysyla te sama nazwe drugi raz"
    )
    assert _leftovers(shelf) == []


@pytest.mark.asyncio
async def test_an_allowance_filled_by_this_very_file_can_still_replace_it(route,
                                                                         monkeypatch):
    """The bytes about to stop existing are given back before the new ones are
    weighed.

    The library upload has done this since `room_left = quota - used +
    replacing`, and its comment says why: an account whose allowance is filled
    by the very file it is swapping is the ordinary reason to send the same
    name twice. This route counted the replacement on top of the original and
    refused, so a bad dump could never be swapped for a good one by the account
    that was near its limit.
    """
    from handler.library import quota

    R, shelf = route
    (shelf / "game.iso").write_bytes(OLD)

    # Nothing left at all: this ROM is what fills the account.
    async def no_room(_user, _max):
        return 0

    monkeypatch.setattr(quota, "ceiling_for", no_room)

    out = await _upload(R, [_Upload("game.iso", len(OLD))])

    assert out["saved"] == ["game.iso"], (
        "konto, ktorego limit wypelnia wlasnie ten plik, nie moze go podmienic "
        "na lepszy zrzut - trasa liczy nowe bajty NA WIERZCHU starych"
    )
    assert (shelf / "game.iso").read_bytes() == b"x" * len(OLD)


@pytest.mark.asyncio
async def test_the_credit_is_only_for_this_file(route, monkeypatch):
    """A subchannel file is governed by its DISC's row, so crediting that row's
    size for replacing 452 bytes would hand back somebody's whole disc."""
    from handler.library import quota

    R, shelf = route
    (shelf / "Game (Disc 1).cue").write_bytes(b"disc")
    (shelf / "Game (Disc 1).sbi").write_bytes(b"old patch")

    async def big_row(_platform_id, fs_name):
        # The disc's row, which is what the route finds for a .sbi.
        return SimpleNamespace(id=1, fs_name="Game (Disc 1).cue",
                               published_by=UPLOADER_ID, fs_size_bytes=10_000_000)

    async def tiny_room(_user, _max):
        return 8

    monkeypatch.setattr(R.rom_handler, "any_row_named", big_row)
    monkeypatch.setattr(quota, "ceiling_for", tiny_room)

    out = await _upload(R, [_Upload("Game (Disc 1).sbi", 4096)])

    assert getattr(out, "status_code", None) == 413, (
        "zwrot policzony z wiersza PLYTY przy podmianie 452-bajtowego pliku "
        "podkanalu - konto dostaje z powrotem miejsce, ktorego nie zwalnia"
    )
    assert (shelf / "Game (Disc 1).sbi").read_bytes() == b"old patch"


@pytest.mark.asyncio
async def test_a_new_file_lands_under_its_own_name(route):
    R, shelf = route

    out = await _upload(R, [_Upload("fresh.iso", 40)])

    assert out["saved"] == ["fresh.iso"]
    assert (shelf / "fresh.iso").read_bytes() == b"x" * 40
    assert _leftovers(shelf) == [], "plik zostal pod nazwa robocza"


@pytest.mark.asyncio
async def test_the_file_before_a_refusal_still_lands(route):
    """One bad file in a request must not undo the good ones that preceded it."""
    R, shelf = route

    out = await _upload(R, [_Upload("first.iso", 40), _Upload("second.iso", BUDGET * 3)])

    assert out.status_code == 413
    assert (shelf / "first.iso").read_bytes() == b"x" * 40
    assert not (shelf / "second.iso").exists()
    assert _leftovers(shelf) == []
