"""Unit tests for utils.ranged_file - byte ranges on library downloads.

Three routes served the largest files this application has and answered
`Accept-Ranges: none`, so a GOG installer that dropped at ninety percent began
again at zero. These tests cover the parsing, which is where range bugs
usually live, and the two pieces of bookkeeping that change meaning once a
download can arrive in more than one request:

  * progress has to be reported against the whole file, or a resumed transfer
    shows the dashboard bar jumping back to the start;
  * completion has to mean "the last byte went out", because a share link with
    a use limit is spent on completion and six dashboard aggregates count
    downloads by row.

Getting either of those wrong is invisible in a green "does it return 206"
test, which is why they are asserted directly.
"""
from __future__ import annotations

import pathlib

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from utils.ranged_file import (
    UnsatisfiableRange,
    content_disposition,
    parse_byte_range,
    ranged_file_response,
)

SIZE = 1000


# ── Parsing ───────────────────────────────────────────────────────────────────


def test_no_header_means_the_whole_file():
    assert parse_byte_range(None, SIZE) is None
    assert parse_byte_range("", SIZE) is None


def test_a_header_we_cannot_read_is_ignored_rather_than_refused():
    # A server may disregard a Range it does not understand. Refusing would
    # break a download that would otherwise have worked.
    assert parse_byte_range("rubbish", SIZE) is None
    assert parse_byte_range("bytes=abc-def", SIZE) is None
    assert parse_byte_range("bytes=-", SIZE) is None


def test_several_ranges_at_once_fall_back_to_the_whole_file():
    # multipart/byteranges buys nothing here and no client that matters asks.
    assert parse_byte_range("bytes=0-10,20-30", SIZE) is None


def test_a_plain_range():
    assert parse_byte_range("bytes=0-99", SIZE) == (0, 99)
    assert parse_byte_range("bytes=200-299", SIZE) == (200, 299)


def test_an_open_ended_range_runs_to_the_last_byte():
    # This is the shape a resuming client actually sends.
    assert parse_byte_range("bytes=400-", SIZE) == (400, SIZE - 1)


def test_a_suffix_range_counts_back_from_the_end():
    assert parse_byte_range("bytes=-100", SIZE) == (SIZE - 100, SIZE - 1)
    # Asking for more tail than the file has yields the whole file, not an error.
    assert parse_byte_range("bytes=-5000", SIZE) == (0, SIZE - 1)


def test_an_end_past_the_file_is_clamped_not_refused():
    assert parse_byte_range("bytes=900-999999", SIZE) == (900, SIZE - 1)


@pytest.mark.parametrize(
    "header",
    [
        "bytes=1000-",     # starts one past the end
        "bytes=5000-6000",
        "bytes=500-400",   # backwards
        "bytes=-0",        # a zero-length tail
    ],
)
def test_ranges_the_file_cannot_satisfy(header):
    with pytest.raises(UnsatisfiableRange):
        parse_byte_range(header, SIZE)


def test_an_empty_file_satisfies_no_range_at_all():
    with pytest.raises(UnsatisfiableRange):
        parse_byte_range("bytes=0-0", 0)


# ── Content-Disposition ───────────────────────────────────────────────────────


def test_disposition_carries_both_an_ascii_and_a_utf8_name():
    header = content_disposition("Wiedźmin 3.zip")
    assert 'filename="' in header          # the fallback older clients read
    assert "filename*=UTF-8''" in header   # the real name
    assert "Wied" in header


def test_disposition_never_leaves_the_ascii_name_empty():
    # A name written entirely in another script strips to nothing but the
    # suffix, and filename=".bin" is a hidden file with no name on most
    # systems. The extension is the half worth keeping.
    assert 'filename="download.bin"' in content_disposition("日本語.bin")
    assert 'filename="download"' in content_disposition("日本語")


def test_disposition_strips_what_would_break_the_quoting():
    header = content_disposition('we"ird\\name.zip')
    ascii_part = header.split('filename="')[1].split('"')[0]
    assert '"' not in ascii_part
    assert "\\" not in ascii_part


# ── Serving ───────────────────────────────────────────────────────────────────


@pytest.fixture
def payload(tmp_path) -> pathlib.Path:
    p = tmp_path / "game.bin"
    p.write_bytes(bytes(range(256)) * 4)   # 1024 bytes, every value distinct in place
    return p


def _serve(path: pathlib.Path, log: dict):
    size = path.stat().st_size

    async def endpoint(request):
        def _advance(position: int):
            log.setdefault("positions", []).append(position)

        async def _settle(moved):
            log["sent"] = moved.sent
            log["eof"] = moved.reached_end
            log["whole"] = moved.whole_file
            log["delivered"] = moved.delivered

        return ranged_file_response(
            path=str(path),
            file_size=size,
            filename="game.bin",
            media_type="application/octet-stream",
            range_header=request.headers.get("range"),
            speed_kbps=0,           # unthrottled, so the budget never waits
            chunk_size=100,
            budget_key="test:ranged",
            on_progress=_advance,
            on_finish=_settle,
        )

    return Starlette(routes=[Route("/f", endpoint)])


def test_a_request_without_a_range_gets_the_whole_file(payload):
    log: dict = {}
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f")
    assert r.status_code == 200
    assert r.headers["accept-ranges"] == "bytes"
    assert "content-range" not in r.headers
    assert r.content == payload.read_bytes()
    assert log["eof"] is True


def test_a_range_comes_back_as_206_with_exactly_those_bytes(payload):
    log: dict = {}
    whole = payload.read_bytes()
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == f"bytes 100-199/{len(whole)}"
    assert r.headers["content-length"] == "100"
    assert r.content == whole[100:200]


def test_resuming_reports_progress_against_the_whole_file(payload):
    """The regression this guards: a resumed transfer must not restart the bar.

    `on_progress` is handed the absolute position in the file. If it were
    handed the bytes sent in this request instead, a download resuming at 512
    would report 100, 200, 300 and the dashboard would show it starting over.
    """
    log: dict = {}
    whole = payload.read_bytes()
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": f"bytes=512-{len(whole) - 1}"})
    assert r.status_code == 206
    positions = log["positions"]
    assert positions[0] > 512              # never restarts from zero
    assert positions[-1] == len(whole)     # and lands on the true end


def test_a_range_that_stops_short_is_not_a_completed_download(payload):
    """A use of a share link, and a row in the download stats, are spent on the
    last byte. A client fetching the first half has not finished anything."""
    log: dict = {}
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206
    assert log["sent"] == 100
    assert log["eof"] is False


def test_the_final_range_of_a_resume_does_count_as_finished(payload):
    log: dict = {}
    whole = payload.read_bytes()
    with TestClient(_serve(payload, log)) as client:
        client.get("/f", headers={"Range": f"bytes=600-{len(whole) - 1}"})
    assert log["eof"] is True
    # But it is not the whole file, and what it delivered is everything up to
    # the end rather than only the part this request carried.
    assert log["whole"] is False
    assert log["sent"] == len(whole) - 600
    assert log["delivered"] == len(whole)


def test_a_request_for_the_last_byte_alone_is_not_a_download(payload):
    """`curl -r -1` used to spend a share link limited to one use.

    Nothing malicious required: every multi-threaded downloader asks for the
    tail as one of its segments, that segment is the smallest and finishes
    first, and the other three come back 410 - to a download we invited by
    answering `Accept-Ranges: bytes` in the first place.
    """
    log: dict = {}
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=-1"})
    assert r.status_code == 206
    assert log["eof"] is True, "it did end on the last byte, which is the trap"
    assert log["whole"] is False, "but one byte is not the file"


def test_a_download_in_four_segments_never_claims_to_be_a_whole_download(payload):
    """What aria2c -x4 or a download manager actually does."""
    log: dict = {}
    size = payload.stat().st_size
    quarters = [(0, 255), (256, 511), (512, 767), (768, size - 1)]
    with TestClient(_serve(payload, log)) as client:
        for first, last in quarters:
            r = client.get("/f", headers={"Range": f"bytes={first}-{last}"})
            assert r.status_code == 206
            assert log["whole"] is False


def test_the_plain_download_is_the_one_that_counts(payload):
    log: dict = {}
    with TestClient(_serve(payload, log)) as client:
        client.get("/f")
    assert log["whole"] is True
    assert log["delivered"] == payload.stat().st_size


def test_asking_for_the_file_as_one_range_counts_too(payload):
    """A client that spells out the whole range has still downloaded it."""
    log: dict = {}
    size = payload.stat().st_size
    with TestClient(_serve(payload, log)) as client:
        client.get("/f", headers={"Range": f"bytes=0-{size - 1}"})
    assert log["whole"] is True


def test_an_impossible_range_gets_416_and_says_how_big_the_file_is(payload):
    log: dict = {}
    size = payload.stat().st_size
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": f"bytes={size + 10}-"})
    assert r.status_code == 416
    assert r.headers["content-range"] == f"bytes */{size}"
    # Nothing was opened, so nothing should have been booked.
    assert "sent" not in log


def test_a_suffix_range_serves_the_tail(payload):
    log: dict = {}
    whole = payload.read_bytes()
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=-64"})
    assert r.status_code == 206
    assert r.content == whole[-64:]
    assert log["eof"] is True


# ── The routes actually use it ────────────────────────────────────────────────


def test_no_download_route_still_refuses_ranges():
    """The three routes carrying the biggest files hardcoded a refusal.

    A helper nothing calls fixes nothing, and this is cheaper than standing up
    the database to prove each route by request.
    """
    endpoints = pathlib.Path(__file__).resolve().parent.parent / "endpoints"
    offenders = []
    for path in endpoints.rglob("*.py"):
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            if "Accept-Ranges" in line and "none" in line:
                offenders.append(f"{path.name}:{number}")
    assert offenders == [], f"still refusing ranges: {offenders}"


# ── Serving whole, on purpose ────────────────────────────────────────────────
#
# A limit on how many times a link may be used and the ability to resume cannot
# both be had. Counting once the file has gone over in full is the honest way to
# count a resumable download and holds no limit at all: ask for byte nought,
# then ask for the rest, and the file arrives as two requests of which neither
# took it. So a link that carries a limit is served whole or not at all - and
# says so, rather than advertising a resume it will not honour.


def _serve_whole(path: pathlib.Path, log: dict):
    size = path.stat().st_size

    async def endpoint(request):
        async def _settle(moved):
            log["whole"] = moved.whole_file
            log["sent"] = moved.sent

        return ranged_file_response(
            path=str(path),
            file_size=size,
            filename="game.bin",
            media_type="application/octet-stream",
            range_header=request.headers.get("range"),
            allow_ranges=False,
            speed_kbps=0,
            chunk_size=100,
            budget_key="test:whole",
            on_finish=_settle,
        )

    return Starlette(routes=[Route("/f", endpoint)])


def test_a_range_asked_of_a_whole_only_response_gets_the_whole_file(payload):
    """The two-request trick, refused. `bytes=0-0` used to come back as one byte
    and count as nothing at all."""
    log: dict = {}
    with TestClient(_serve_whole(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=0-0"})
    assert r.status_code == 200
    assert "content-range" not in r.headers
    assert r.content == payload.read_bytes()
    assert log["whole"] is True, "a limited link served something it could not count"


def test_a_whole_only_response_does_not_advertise_resuming(payload):
    """Ignoring the range while still claiming to support it would leave a
    resuming client starting again from zero without being told why."""
    log: dict = {}
    with TestClient(_serve_whole(payload, log)) as client:
        r = client.get("/f")
    assert "accept-ranges" not in r.headers
    assert r.content == payload.read_bytes()


def test_a_range_past_the_end_is_not_refused_when_ranges_are_off(payload):
    """416 answers a question that was not asked: the header is not being read,
    so an unsatisfiable one is not unsatisfiable, it is irrelevant."""
    log: dict = {}
    with TestClient(_serve_whole(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=99999-"})
    assert r.status_code == 200
    assert r.content == payload.read_bytes()


def test_ranges_still_work_where_nothing_asked_for_them_to_stop(payload):
    """The cost is paid only by links that ask for a limit. Everything else
    resumes exactly as before, which is why resuming was added."""
    log: dict = {}
    with TestClient(_serve(payload, log)) as client:
        r = client.get("/f", headers={"Range": "bytes=10-19"})
    assert r.status_code == 206
    assert r.headers["accept-ranges"] == "bytes"
