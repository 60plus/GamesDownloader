"""Serving a file with byte ranges, so an interrupted download can resume.

The three routes that hand out library files all used to answer
`Accept-Ranges: none` and stream from the first byte every time. Those are the
routes carrying the largest files this application has: a GOG installer that
drops at ninety percent started again from zero, and no desktop client could
ever be built against them. Meanwhile GD speaks Range fluently in the other
direction, as a client, with a guard for the CDN that ignores it.

What makes this more than a `seek()` is the bookkeeping that hangs off these
routes, and both pieces of it change meaning once a download can arrive in
several requests:

  * Progress on the dashboard is reported against the whole file, not against
    the piece being sent, or a resumed transfer would appear to start over.

  * A record of the download is written when the last byte of the file goes
    out, not whenever bytes move. Six dashboard aggregates count these rows to
    answer "how many downloads", so writing one per request would let a single
    resumed download report as several. The same rule keeps a share link with a
    use limit from being spent by a transfer that dropped, which is a bug this
    file would otherwise have introduced and which the old code already had in
    a milder form.

Bandwidth on a transfer that never finishes is therefore not recorded. That is
a deliberate trade: the count of downloads is the number people actually read,
and it now excludes attempts that failed rather than including them.

The first version of this collapsed both of those into one flag, "did this
request end on the last byte", and the two callers wanted different answers.
A share link limited to a single use died on `curl -r -1`, and it died on any
ordinary multi-threaded downloader too: the segment holding the last byte
finishes first, spends the only use, and the other segments come back 410 - an
invitation we issued ourselves with `Accept-Ranges: bytes`. So a transfer now
reports what it did rather than one verdict about it, and each caller asks the
question it actually means.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import quote

from starlette.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)

# A single range. A request for several at once is answered with the whole file
# instead, which the specification explicitly allows: a multipart/byteranges
# reply buys nothing here and no client that matters asks for one.
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


@dataclass(frozen=True)
class Transfer:
    """What one request moved, for whoever has bookkeeping hanging off it.

    Deliberately facts rather than a verdict. "Ended on the last byte" and "was
    the whole file" are different claims, and handing out only the first is how
    a one-use share link came to be spent by a request for a single byte.
    """

    sent: int          #: bytes this request actually handed over
    first: int         #: the offset in the file it started from
    file_size: int
    duration_ms: int

    @property
    def reached_end(self) -> bool:
        """This request finished on the last byte of the file."""
        return self.sent > 0 and self.first + self.sent >= self.file_size

    @property
    def whole_file(self) -> bool:
        """This request was the entire file, on its own, start to finish.

        What "one download" has to mean for anything that counts uses. A client
        that took the file in four segments never satisfies this, and that is
        the lenient direction to be wrong in: the alternative spent the quota on
        the first segment to finish and refused the rest of its own download.
        """
        return self.first == 0 and self.reached_end

    @property
    def delivered(self) -> int:
        """How much of the file the client holds now this request is done.

        Not the same as `sent` on a resumed transfer, where the client already
        had everything before `first`. Recording `sent` there described a
        nine gigabyte download as the two megabytes it took to finish it.
        """
        return self.first + self.sent


class UnsatisfiableRange(Exception):
    """The client asked for bytes this file does not have."""


def parse_byte_range(header: str | None, file_size: int) -> tuple[int, int] | None:
    """Resolve a Range header to inclusive (first, last), or None for the lot.

    None means "ignore the header and send the whole file", which is the right
    answer for a malformed header too: a server is free to disregard a Range it
    does not understand, and refusing would break a download that would
    otherwise have worked.
    """
    if not header:
        return None
    match = _RANGE_RE.match(header.strip())
    if not match:
        return None

    raw_first, raw_last = match.group(1), match.group(2)
    if not raw_first and not raw_last:
        return None

    if file_size == 0:
        # There is no byte to hand over, so every range misses.
        raise UnsatisfiableRange

    if not raw_first:
        # "bytes=-500" is the last 500 bytes, not a range starting at zero.
        suffix = int(raw_last)
        if suffix == 0:
            raise UnsatisfiableRange
        first = max(0, file_size - suffix)
        return first, file_size - 1

    first = int(raw_first)
    if first >= file_size:
        raise UnsatisfiableRange
    if not raw_last:
        return first, file_size - 1

    last = min(int(raw_last), file_size - 1)
    if last < first:
        raise UnsatisfiableRange
    return first, last


def content_disposition(filename: str) -> str:
    """An attachment header both halves of the world can read.

    `filename*` carries the real name in UTF-8 and wins wherever it is
    understood. The plain `filename` beside it is the fallback that some proxies
    and older clients need, so a name with an accent in it does not arrive as an
    empty string.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", filename)
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace('"', "")
        .replace("\\", "")
        .strip()
    )
    # A name written entirely in another script leaves nothing but the suffix,
    # and "game.bin" would arrive as ".bin": on most systems a hidden file with
    # no name at all. Keep the extension, which is the useful half, and give it
    # something to hang off.
    stem, dot, extension = ascii_name.rpartition(".")
    if dot and not stem:
        ascii_name = f"download.{extension}"
    elif not ascii_name:
        ascii_name = "download"
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def ranged_file_response(
    *,
    path: str,
    file_size: int,
    filename: str,
    media_type: str,
    range_header: str | None,
    speed_kbps: int,
    chunk_size: int,
    budget_key: str,
    allow_ranges: bool = True,
    on_start: Callable[[int], None] | None = None,
    on_progress: Callable[[int], None] | None = None,
    on_finish: Callable[[Transfer], Awaitable[None]] | None = None,
) -> Response:
    """Stream `path`, honouring `range_header`.

    `on_progress` is handed the absolute position reached in the file, so a
    resumed transfer keeps counting from where the earlier one stopped rather
    than from zero. `on_finish` is handed a `Transfer` describing what this
    request moved; it runs even when the client disappears part way.

    `allow_ranges=False` serves the whole file whatever was asked for, and says
    so by leaving out the Accept-Ranges header rather than advertising something
    it will not do. It is one flag rather than two so a caller cannot get half
    of it right: ignoring the range while still advertising support would leave
    a resuming client restarting from zero without being told.

    Some things cannot be counted and resumed at once. A link with a limit on
    how many times it may be used is one: the count only means anything if a
    request either takes the file or does not, and a file taken in two ranges
    is neither.
    """
    from utils.throttle import bucket_for

    # Every transfer on the same budget draws from one bucket, so a user with
    # four downloads open gets their limit once rather than four times.
    budget = bucket_for(budget_key, speed_kbps)

    try:
        span = parse_byte_range(range_header if allow_ranges else None, file_size)
    except UnsatisfiableRange:
        # 416 has to say how big the file actually is, or the client has no way
        # to work out what it should have asked for.
        return Response(
            status_code=416,
            headers={"Content-Range": f"bytes */{file_size}", "Accept-Ranges": "bytes"},
        )

    if span is None:
        first, last = 0, max(file_size - 1, 0)
        partial = False
    else:
        first, last = span
        partial = True

    length = 0 if file_size == 0 else last - first + 1

    async def _stream():
        sent = 0
        loop = asyncio.get_running_loop()
        started = loop.time()
        if on_start is not None:
            # Handed where in the file this request begins, because progress and
            # speed are measured from different places on a resume.
            on_start(first)
        # Held for as long as this generator is alive, including while it is
        # parked on a yield nobody is reading. A paused download draws nothing,
        # and a bucket judged idle on that basis was swept out from under a
        # transfer that then resumed against a second budget of its own.
        budget.hold()
        try:
            with open(path, "rb") as fh:
                if first:
                    fh.seek(first)
                remaining = length
                while remaining > 0:
                    want = min(chunk_size, remaining)
                    chunk = await loop.run_in_executor(None, fh.read, want)
                    if not chunk:
                        # The file shrank under us. Stop rather than pad the
                        # response out to the length we already promised.
                        logger.warning("%s ended early: %d of %d bytes", path, sent, length)
                        break
                    sent += len(chunk)
                    remaining -= len(chunk)
                    if on_progress is not None:
                        on_progress(first + sent)
                    await budget.take(len(chunk))
                    yield chunk
        finally:
            budget.release()
            if on_finish is not None:
                moved = Transfer(
                    sent=sent, first=first, file_size=file_size,
                    duration_ms=int((loop.time() - started) * 1000),
                )
                try:
                    await on_finish(moved)
                except Exception:
                    logger.exception("Bookkeeping failed after streaming %s", path)

    headers = {
        "Content-Disposition": content_disposition(filename),
        "Content-Length": str(length),
    }
    if allow_ranges:
        headers["Accept-Ranges"] = "bytes"
    if partial:
        headers["Content-Range"] = f"bytes {first}-{last}/{file_size}"

    return StreamingResponse(
        _stream(),
        status_code=206 if partial else 200,
        media_type=media_type,
        headers=headers,
    )
