"""Unit tests for utils.uploads - reading an upload under a ceiling.

The pattern these replace was `data = await file.read()` followed by a length
check, which is a real limit applied one step too late: the bytes are already
in the process when it fires.

The assertions that matter here are not "does it raise". They are that it stops
reading at the ceiling rather than after, and that a refused spool does not
leave a stump on disk. Both are invisible to a test that only checks the status
code, and both are the reason the helper exists at all.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi import HTTPException

from utils.uploads import read_upload_capped, spool_upload_capped

_MB = 1024 * 1024


class FakeUpload:
    """An UploadFile as far as these helpers are concerned, plus a tally.

    `consumed` is the point: it shows how much was actually pulled off the
    wire, which is what separates a ceiling from a check.
    """

    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0
        self.consumed = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._offset:]
        else:
            chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        self.consumed += len(chunk)
        return chunk


# ── read_upload_capped ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_upload_under_the_ceiling_arrives_whole():
    payload = b"x" * (3 * _MB)
    upload = FakeUpload(payload)
    assert await read_upload_capped(upload, 5 * _MB) == payload


@pytest.mark.asyncio
async def test_exactly_at_the_ceiling_is_allowed():
    # The limit is what we accept, not one byte less. Getting this backwards
    # rejects a file of precisely the advertised maximum size.
    payload = b"x" * (2 * _MB)
    assert await read_upload_capped(FakeUpload(payload), 2 * _MB) == payload


@pytest.mark.asyncio
async def test_one_byte_over_is_refused():
    payload = b"x" * (2 * _MB + 1)
    with pytest.raises(HTTPException) as caught:
        await read_upload_capped(FakeUpload(payload), 2 * _MB)
    assert caught.value.status_code == 413


@pytest.mark.asyncio
async def test_it_stops_reading_instead_of_measuring_afterwards():
    """The whole point: a giant is refused without being taken in first."""
    upload = FakeUpload(b"x" * (200 * _MB))
    with pytest.raises(HTTPException):
        await read_upload_capped(upload, 4 * _MB)
    # At most the ceiling plus the chunk that crossed it.
    assert upload.consumed <= 5 * _MB
    assert upload.consumed < 200 * _MB


@pytest.mark.asyncio
async def test_the_refusal_names_the_thing_and_the_limit():
    with pytest.raises(HTTPException) as caught:
        await read_upload_capped(FakeUpload(b"x" * 4096), 1024, what="Avatar file")
    detail = caught.value.detail
    assert "Avatar file" in detail
    # Under a megabyte the message says bytes, because "max 0 MB" helps nobody.
    assert "1024 bytes" in detail


@pytest.mark.asyncio
async def test_an_empty_upload_is_not_an_error_here():
    # Emptiness is the route's business; several of them answer 400 for it with
    # their own wording.
    assert await read_upload_capped(FakeUpload(b""), _MB) == b""


# ── spool_upload_capped ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_spooled_upload_lands_on_disk(tmp_path: pathlib.Path):
    payload = b"PK\x03\x04" + b"y" * (2 * _MB)
    dest = tmp_path / "plugin.zip"
    written = await spool_upload_capped(FakeUpload(payload), dest, 8 * _MB)
    assert written == len(payload)
    assert dest.read_bytes() == payload


@pytest.mark.asyncio
async def test_a_refused_spool_leaves_nothing_behind(tmp_path: pathlib.Path):
    """A rejected upload must not leave a stump for something else to find.

    The installer hands this path straight to the unpacker, so a truncated file
    surviving the refusal would be read as a broken archive rather than as an
    upload that never happened.
    """
    dest = tmp_path / "plugin.zip"
    with pytest.raises(HTTPException) as caught:
        await spool_upload_capped(FakeUpload(b"z" * (20 * _MB)), dest, 4 * _MB)
    assert caught.value.status_code == 413
    assert not dest.exists()


@pytest.mark.asyncio
async def test_a_spool_does_not_take_the_whole_thing_in_first(tmp_path: pathlib.Path):
    upload = FakeUpload(b"z" * (300 * _MB))
    with pytest.raises(HTTPException):
        await spool_upload_capped(upload, tmp_path / "x.zip", 8 * _MB)
    assert upload.consumed <= 9 * _MB


# ── Nothing new slips back to reading the lot ─────────────────────────────────


def test_no_new_endpoint_reads_an_upload_without_a_ceiling():
    """Two routes are still on the old pattern, on purpose.

    Firmware and WHDLoad support files have no size of their own that anyone
    has established, they are administrator-only, and the body-size middleware
    already refuses anything over 128 MB before they are reached. Inventing a
    tighter number here risks turning away a legitimate BIOS or Amiga upload to
    buy nothing. They are named so that a third one cannot appear quietly.
    """
    allowed = {"firmware_router.py", "whdload_router.py"}
    endpoints = pathlib.Path(__file__).resolve().parent.parent / "endpoints"
    offenders = []
    for path in endpoints.rglob("*.py"):
        if path.name in allowed:
            continue
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ".read()" in stripped and "await" in stripped:
                offenders.append(f"{path.name}:{number}: {stripped}")
    assert offenders == [], f"unbounded upload reads: {offenders}"
