"""A byte ceiling has to hold while the body arrives, not after.

The store-icon proxy is unauthenticated - it has to be, because the store list
renders icons through <img src=...>, which cannot carry a bearer token. It read
the whole response with `await c.get(url)` and only then measured
`len(r.content)` against 2 MB. httpx decompresses transparently, so a highly
compressible file cost the caller about a hundred kilobytes per hundred
megabytes of server memory, and the check ran once the memory was already gone.

`fetch_media_bytes` already had the streaming shape. These pin the shared
helper both now use.
"""
from __future__ import annotations

import pytest

from utils.http import MediaTooLarge, read_capped


class FakeResponse:
    """Just enough of an httpx streamed response, and it records what was read."""

    def __init__(self, chunks: list[bytes], headers: dict | None = None):
        self._chunks = chunks
        self.headers = headers or {}
        self.chunks_read = 0

    async def aiter_bytes(self, _size: int | None = None):
        for chunk in self._chunks:
            self.chunks_read += 1
            yield chunk


async def test_a_body_under_the_ceiling_comes_back_whole():
    resp = FakeResponse([b"abc", b"def"], {"content-length": "6"})
    assert await read_capped(resp, 1024) == b"abcdef"


async def test_an_honest_giant_is_refused_before_a_byte_is_read():
    """The cheap half: it said how big it was, so nothing needs fetching."""
    resp = FakeResponse([b"x" * 10], {"content-length": str(50 * 1024 * 1024)})
    with pytest.raises(MediaTooLarge):
        await read_capped(resp, 2 * 1024 * 1024)
    assert resp.chunks_read == 0


async def test_a_body_that_lies_about_its_length_is_still_stopped():
    """No Content-Length, or a false one, is exactly what the running total is
    for - and it is the case the old `len(r.content)` check answered too late."""
    resp = FakeResponse([b"x" * 1000] * 10, {"content-length": "1000"})
    with pytest.raises(MediaTooLarge):
        await read_capped(resp, 4096)


async def test_it_gives_up_partway_rather_than_reading_to_the_end():
    """The whole point: a hundred-megabyte decompressed stream must not be
    collected in full before anyone objects."""
    resp = FakeResponse([b"x" * 1024] * 1000)
    with pytest.raises(MediaTooLarge):
        await read_capped(resp, 4096)
    assert resp.chunks_read < 10


async def test_a_body_with_no_length_header_is_allowed_when_it_fits():
    resp = FakeResponse([b"tiny"])
    assert await read_capped(resp, 4096) == b"tiny"


async def test_a_nonsense_length_header_does_not_crash_the_read():
    """Upstreams send odd things; a bad header must fall through to the running
    total rather than raise ValueError out of an int()."""
    resp = FakeResponse([b"ok"], {"content-length": "not-a-number"})
    assert await read_capped(resp, 4096) == b"ok"


async def test_exactly_at_the_ceiling_is_allowed():
    resp = FakeResponse([b"x" * 4096], {"content-length": "4096"})
    assert len(await read_capped(resp, 4096)) == 4096
