"""Reading an upload without letting it decide how much memory we spend.

The pattern these replace is `data = await file.read()` followed by
`if len(data) > LIMIT`. The check is real but it runs one step too late: the
bytes are already in the process by the time it says no, so the limit describes
what we accept rather than what we are willing to hold.

The body-size middleware now turns away anything over a route's ceiling before
a handler sees it, so this is the second line rather than the first. It still
earns its place twice over. A route whose real limit is five megabytes should
not hold sixteen just because that is where the outer ceiling sits, and the
plugin installer used to pull an entire archive into memory before writing it
straight back out to a temporary file, which no ceiling makes sensible.

`utils.http.read_capped` is the same idea for a response we fetched. This is
the inbound half.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

#: Big enough that a few-megabyte upload is a handful of reads, small enough
#: that the overshoot past a limit is never more than this.
_CHUNK = 1024 * 1024


def _refuse(what: str, max_bytes: int) -> HTTPException:
    megabytes = max_bytes // (1024 * 1024)
    size = f"{megabytes} MB" if megabytes else f"{max_bytes} bytes"
    return HTTPException(status_code=413, detail=f"{what} too large (max {size})")


async def read_upload_capped(upload, max_bytes: int, *, what: str = "File") -> bytes:
    """Collect an upload, refusing as the bytes arrive rather than after.

    Raises `HTTPException(413)` the moment the ceiling is passed, so the most
    that is ever held is the limit plus one chunk. Every caller here is an
    endpoint, which is why the refusal is already in the shape a route returns.
    """
    buffer = bytearray()
    while True:
        chunk = await upload.read(_CHUNK)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise _refuse(what, max_bytes)
    return bytes(buffer)


async def spool_upload_capped(
    upload, destination: str | Path, max_bytes: int, *, what: str = "File"
) -> int:
    """Write an upload to `destination` under a ceiling, never holding it whole.

    For the uploads that are going to end up on disk anyway. Returns the number
    of bytes written; on refusal the partial file is removed, so a rejected
    upload does not leave a stump behind for something else to trip over.
    """
    path = Path(destination)
    written = 0
    try:
        with path.open("wb") as out:
            while True:
                chunk = await upload.read(_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise _refuse(what, max_bytes)
                out.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return written
