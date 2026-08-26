"""What the artwork upload route does with a file it does not want.

The earlier version of this file asserted that "svg" was absent from the set of
allowed extensions and stopped there. That assertion passed while the route was
at its worst: it never validated the extension at all, it *forced* one, so an
SVG was written into cover.png, served as image/png behind nosniff, and
rendered nowhere - after the previous cover had already been deleted to make
room for it. A membership test on a constant cannot see any of that, because it
never calls the route.

So these tests call the route.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope as Scopes
from handler.metadata import rom_scrape_handler
from endpoints.library.library_router import _file_to_dict
from endpoints.roms import roms_router


class _Upload:
    """Only the two things the route touches: a name and an async read."""

    def __init__(self, filename: str | None, data: bytes = b"not really a picture"):
        self.filename = filename
        self._chunks = [data]

    async def read(self, _size: int = -1) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""


class _FailingUpload(_Upload):
    """A client that hangs up part way through, which is the ordinary way for
    an upload to fail."""

    async def read(self, _size: int = -1) -> bytes:
        raise ConnectionResetError("client went away")


def _request():
    state = SimpleNamespace(
        user=SimpleNamespace(id=1, username="admin"),
        scopes={Scopes.LIBRARY_WRITE, Scopes.ROMS_READ},
    )
    return SimpleNamespace(state=state)


@pytest.fixture
def media_dir(tmp_path, monkeypatch):
    """A ROM whose cover slot is already occupied, wired to a real directory."""
    directory = tmp_path / "psx" / "1"
    directory.mkdir(parents=True)
    (directory / "cover.png").write_bytes(b"the cover the user already has")

    rom = SimpleNamespace(
        id=1,
        platform=SimpleNamespace(slug="psx"),
        screenshots=[],
    )

    async def _get(_rom_id):
        return rom

    async def _update(_rom_id, _data):
        return None

    monkeypatch.setattr(roms_router.rom_handler, "get_with_platform", _get)
    monkeypatch.setattr(roms_router.rom_handler, "update_metadata", _update)
    monkeypatch.setattr(rom_scrape_handler, "_rom_media_dir", lambda *_a: directory)
    monkeypatch.setattr(rom_scrape_handler, "_resource_url", lambda *a: f"/resources/{a[-1]}")
    # Reading the proportions of a file that is not an image is not what is
    # under test here.
    monkeypatch.setattr(rom_scrape_handler, "_detect_cover_aspect", lambda _p: None)
    return directory


@pytest.mark.asyncio
async def test_an_svg_is_refused_instead_of_being_renamed(media_dir):
    with pytest.raises(HTTPException) as raised:
        await roms_router.upload_rom_media(
            request=_request(), rom_id=1, kind="cover",
            file=_Upload("logo.svg", b"<svg onload='alert(1)'></svg>"),
        )
    assert raised.value.status_code == 400
    assert "svg" not in raised.value.detail.lower(), "it must not read as an invitation"
    # Nothing was written under another name...
    assert not (media_dir / "cover.svg").exists()
    assert list(media_dir.glob("cover.*")) == [media_dir / "cover.png"]
    # ...and the cover the user already had is untouched.
    assert (media_dir / "cover.png").read_bytes() == b"the cover the user already has"


@pytest.mark.asyncio
async def test_a_file_with_no_extension_is_refused_too(media_dir):
    """This is the case the forcing branch existed for, and it was wrong about
    it as well: a name that says nothing became a png by fiat."""
    with pytest.raises(HTTPException) as raised:
        await roms_router.upload_rom_media(
            request=_request(), rom_id=1, kind="cover", file=_Upload("cover"),
        )
    assert raised.value.status_code == 400
    assert (media_dir / "cover.png").read_bytes() == b"the cover the user already has"


@pytest.mark.asyncio
async def test_a_format_we_accept_still_replaces_what_was_there(media_dir):
    """The refusal must not have cost us the ordinary case."""
    result = await roms_router.upload_rom_media(
        request=_request(), rom_id=1, kind="cover",
        file=_Upload("new.jpg", b"the new cover"),
    )
    assert result["ok"] is True
    assert (media_dir / "cover.jpg").read_bytes() == b"the new cover"
    # The old file went, so the slot holds exactly one cover.
    assert [p.name for p in media_dir.glob("cover.*")] == ["cover.jpg"]
    # And no staging file was left behind.
    assert list(media_dir.glob(".*")) == []


@pytest.mark.asyncio
async def test_an_upload_that_dies_half_way_does_not_cost_the_old_cover(media_dir):
    """Clearing the slot before the bytes arrive is the same data loss by a
    different route: the client only has to hang up."""
    with pytest.raises(ConnectionResetError):
        await roms_router.upload_rom_media(
            request=_request(), rom_id=1, kind="cover", file=_FailingUpload("new.jpg"),
        )
    assert (media_dir / "cover.png").read_bytes() == b"the cover the user already has"
    assert list(media_dir.glob(".*")) == [], "the partial file must be cleaned up"


@pytest.mark.asyncio
async def test_screenshots_go_through_the_same_gate(media_dir):
    """A screenshot never cleared a slot, so nothing was destroyed here, but it
    took the same forced extension and produced the same unrenderable file."""
    with pytest.raises(HTTPException) as raised:
        await roms_router.upload_rom_media(
            request=_request(), rom_id=1, kind="screenshot", file=_Upload("shot.svg"),
        )
    assert raised.value.status_code == 400
    assert list(media_dir.glob("screenshot_*")) == []


@pytest.mark.asyncio
async def test_a_video_upload_is_still_accepted(media_dir):
    await roms_router.upload_rom_media(
        request=_request(), rom_id=1, kind="video",
        file=_Upload("trailer.mp4", b"moving pictures"),
    )
    assert (media_dir / "video.mp4").read_bytes() == b"moving pictures"


def _file(**kw):
    base = dict(
        id=1, filename="setup.exe", display_name=None, file_type="installer",
        os="windows", language="en", version="1.0", size_bytes=123,
        file_path="games/GOG/Some Game/windows/setup.exe",
        checksum_md5=None, source="gog", is_available=True, is_archive=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_a_plain_response_does_not_carry_the_storage_layout():
    """Reading the library is a plain user permission.

    The path is relative to the base path rather than a host path, so this was
    never a serious leak, but a user has no use for the storage layout and no
    reason to be handed it. Downloading goes through the file id either way.
    """
    d = _file_to_dict(_file())
    assert "file_path" not in d
    # Everything a client actually needs is still there.
    assert d["id"] == 1 and d["filename"] == "setup.exe" and d["size_bytes"] == 123


def test_an_administrator_route_can_still_ask_for_it():
    d = _file_to_dict(_file(), include_path=True)
    assert d["file_path"] == "games/GOG/Some Game/windows/setup.exe"
