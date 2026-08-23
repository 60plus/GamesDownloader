"""Pausing and resuming an actual transfer, byte for byte.

The state machine is tested next door; this is the part that can quietly ruin a
file. Resuming asks the source for the tail with a Range header and appends it
to what is already on disk - and a source that does not support Range answers
with the WHOLE file and HTTP 200 instead. Appending that would produce a file
of roughly the right size made of the wrong bytes: a ROM that looks downloaded
and does not run. So both kinds of source are served here by a local server,
and in each case the finished file is compared against the original.

Nothing here touches the real library: the ROM directory is a temporary one and
the registration/scrape step is stubbed out.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from handler.roms import rom_source_handler as rsh

BODY = bytes(range(256)) * 8192          # 2 MiB, and every byte position tells
FINGERPRINT = hashlib.sha256(BODY).hexdigest()


class _Source(BaseHTTPRequestHandler):
    """Serves BODY slowly, with or without Range support."""

    honours_range = True

    def do_GET(self):  # noqa: N802 - name fixed by the base class
        start = 0
        rng = self.headers.get("Range")
        if rng and self.honours_range:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range",
                             f"bytes {start}-{len(BODY) - 1}/{len(BODY)}")
        else:
            self.send_response(200)
        body = BODY[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        # Small pieces, paced: over a loopback socket an unthrottled 2 MiB
        # arrives faster than a test can react, and the pause would always be
        # racing a finished download.
        for i in range(0, len(body), 16384):
            try:
                self.wfile.write(body[i:i + 16384])
                self.wfile.flush()
                time.sleep(0.004)
            except (BrokenPipeError, ConnectionResetError):
                return

    def log_message(self, *a):
        pass


@pytest.fixture
def source_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Source)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/rom.bin"
    srv.shutdown()


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    """A temporary ROM directory, no SSRF guard, no database."""
    async def _allow(request):
        """httpx awaits its event hooks, so the stand-in has to be a coroutine."""

    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))
    monkeypatch.setattr(rsh, "make_request_guard", lambda **kw: _allow)
    monkeypatch.setattr(rsh, "max_rom_bytes", lambda: 64 * 1024 ** 3)
    monkeypatch.setattr(rsh, "assert_room_for", lambda *a, **kw: None)

    async def _no_database(fs_slug, filename):
        return None

    monkeypatch.setattr(rsh, "_register_and_scrape", _no_database)
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()
    _Source.honours_range = True
    yield tmp_path
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()


def _job(url: str) -> rsh._RomJob:
    job = rsh._RomJob(
        id=1, source_id="test", entry_id="e1", url=url, filename="rom.bin",
        fs_slug="snes", headers=None, cookies=None, actor=None,
        entry_key=("test", "e1"), dest_key=("snes", "rom.bin"))
    rsh._jobs[1] = job
    rsh._dest_locks.add(job.dest_key)
    rsh._in_flight.add(job.entry_key)
    return job


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_plain_download_lands_intact(source_url, sandbox):
    job = _job(source_url)
    asyncio.run(rsh._rom_download_job(job))
    assert job.status == "completed"
    assert _sha(sandbox / "snes" / "rom.bin") == FINGERPRINT


def test_pause_then_resume_rebuilds_the_same_file(source_url, sandbox):
    job = _job(source_url)

    async def scenario():
        task = asyncio.create_task(rsh._rom_download_job(job))
        # Let some of it arrive, then ask it to stop.
        for _ in range(200):
            await asyncio.sleep(0.01)
            if job.received > 128 * 1024:
                break
        await rsh.pause_job(1)
        await task
        part = (sandbox / "snes" / "rom.bin.part")
        assert job.status == "paused", "pause did not take"
        assert part.exists() and 0 < part.stat().st_size < len(BODY)
        assert not (sandbox / "snes" / "rom.bin").exists()
        # The lock has to stay while it is paused, or a second download could
        # start writing the same path.
        assert job.dest_key in rsh._dest_locks
        kept = part.stat().st_size

        await rsh.resume_job(1)
        await job.task
        return kept

    kept = asyncio.run(scenario())
    assert job.status == "completed"
    assert kept > 0, "nothing was kept, so nothing was resumed"
    assert _sha(sandbox / "snes" / "rom.bin") == FINGERPRINT
    assert not (sandbox / "snes" / "rom.bin.part").exists()


def test_a_source_that_ignores_range_starts_over_instead_of_corrupting(source_url, sandbox):
    """The dangerous case: 200 with the whole body where 206 was expected."""
    job = _job(source_url)

    async def scenario():
        task = asyncio.create_task(rsh._rom_download_job(job))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if job.received > 128 * 1024:
                break
        await rsh.pause_job(1)
        await task
        assert job.status == "paused"
        _Source.honours_range = False        # source loses the ability mid-way
        await rsh.resume_job(1)
        await job.task

    asyncio.run(scenario())
    assert job.status == "completed"
    landed = sandbox / "snes" / "rom.bin"
    assert landed.stat().st_size == len(BODY), "file grew: the tail was appended twice"
    assert _sha(landed) == FINGERPRINT


def test_cancelling_mid_transfer_leaves_nothing_behind(source_url, sandbox):
    job = _job(source_url)

    async def scenario():
        task = asyncio.create_task(rsh._rom_download_job(job))
        for _ in range(200):
            await asyncio.sleep(0.01)
            if job.received > 128 * 1024:
                break
        await rsh.cancel_or_forget_job(1)
        await task

    asyncio.run(scenario())
    assert job.status == "cancelled"
    assert not (sandbox / "snes" / "rom.bin").exists()
    assert not (sandbox / "snes" / "rom.bin.part").exists()
    assert job.dest_key not in rsh._dest_locks
    assert job.entry_key not in rsh._in_flight
