"""Stopping, resuming, repeating and forgetting a ROM download.

A ROM is often several gigabytes, so the states these functions move between
decide whether an interrupted download costs a click or an hour. Two of them
carry a lock: while a job is paused it still owns its half-written file and the
name that file will take, and letting go of either would let a second download
write the same path at the same time.

The transfer itself is not exercised here - that needs a network - but every
transition around it is, including the ones that must be refused.
"""
from __future__ import annotations

import asyncio

import pytest

from handler.roms import rom_source_handler as rsh


def _job(job_id: int, status: str, **kw) -> rsh._RomJob:
    job = rsh._RomJob(
        id=job_id, source_id="test-source", entry_id=f"e{job_id}",
        url="https://example.invalid/rom.zip", filename=f"rom{job_id}.zip",
        fs_slug="snes", headers=None, cookies=None, actor="tester",
        entry_key=("test-source", f"e{job_id}"), dest_key=("snes", f"rom{job_id}.zip"),
        status=status, **kw)
    rsh._jobs[job_id] = job
    return job


@pytest.fixture(autouse=True)
def clean_registry():
    """Every test starts with an empty registry and leaves one behind."""
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()
    yield
    rsh._jobs.clear()
    rsh._in_flight.clear()
    rsh._dest_locks.clear()


def test_list_puts_newest_first():
    _job(1, "completed")
    _job(2, "downloading")
    assert [j["id"] for j in rsh.list_jobs()] == [2, 1]


def test_pausing_an_unknown_job_is_a_no_op():
    assert asyncio.run(rsh.pause_job(999)) is False


def test_a_finished_job_cannot_be_paused():
    _job(1, "completed")
    assert asyncio.run(rsh.pause_job(1)) is False


def test_pausing_a_paused_job_changes_nothing():
    _job(1, "paused")
    assert asyncio.run(rsh.pause_job(1)) is True


def test_only_a_paused_job_can_resume():
    _job(1, "failed")
    assert asyncio.run(rsh.resume_job(1)) is False


def test_retry_takes_the_locks_back():
    job = _job(1, "failed")

    async def scenario() -> bool:
        ok = await rsh.retry_job(1)
        # The retry starts a real transfer task. It is stopped inside the same
        # loop that made it, otherwise it outlives the test as a pending task.
        if job.task:
            job.task.cancel()
            try:
                await job.task
            except (asyncio.CancelledError, Exception):
                pass
        return ok

    assert asyncio.run(scenario()) is True
    assert job.dest_key in rsh._dest_locks
    assert job.entry_key in rsh._in_flight
    assert job.error is None


def test_retry_yields_when_that_file_is_already_being_written():
    """Two entries can resolve to one filename; the second must not join in."""
    job = _job(1, "failed")
    rsh._dest_locks.add(job.dest_key)
    assert asyncio.run(rsh.retry_job(1)) is False
    assert job.status == "failed"


def test_a_running_job_cannot_be_retried():
    _job(1, "downloading")
    assert asyncio.run(rsh.retry_job(1)) is False


def test_forgetting_a_finished_job_drops_it():
    _job(1, "completed")
    assert asyncio.run(rsh.cancel_or_forget_job(1)) is True
    assert rsh._jobs == {}


def test_cancelling_a_paused_job_gives_the_locks_back():
    job = _job(1, "paused")
    rsh._dest_locks.add(job.dest_key)
    rsh._in_flight.add(job.entry_key)
    assert asyncio.run(rsh.cancel_or_forget_job(1)) is True
    assert job.status == "cancelled"
    assert job.dest_key not in rsh._dest_locks
    assert job.entry_key not in rsh._in_flight


def test_cancelling_an_unknown_job_reports_false():
    assert asyncio.run(rsh.cancel_or_forget_job(4242)) is False


def test_pruning_spares_live_and_paused_jobs():
    for i in range(rsh._KEEP_FINISHED + 25):
        _job(i + 1, "completed")
    live = _job(9001, "downloading")
    paused_job = _job(9002, "paused")
    rsh._prune_jobs()
    assert len([j for j in rsh._jobs.values() if j.terminal]) == rsh._KEEP_FINISHED
    assert live.id in rsh._jobs
    assert paused_job.id in rsh._jobs


def test_pruning_drops_the_oldest_first():
    for i in range(rsh._KEEP_FINISHED + 3):
        _job(i + 1, "completed")
    rsh._prune_jobs()
    assert 1 not in rsh._jobs
    assert rsh._KEEP_FINISHED + 3 in rsh._jobs


def test_job_summary_computes_percent():
    job = _job(1, "downloading", received=50, total=200)
    assert job.as_dict()["percent"] == 25.0


def test_job_summary_without_a_known_size():
    """A source that sends no content-length must not divide by zero."""
    job = _job(1, "downloading", received=50, total=0)
    assert job.as_dict()["percent"] == -1


# ── What the log is allowed to say when a download fails ───────────────────────

class _FakeUrl:
    def __init__(self, host):
        self.host = host


class _FakeReqResp:
    def __init__(self, host):
        self.url = _FakeUrl(host)


def test_failed_host_prefers_the_node_that_answered():
    """A redirect means the address that failed is not the one asked for."""
    job = _job(1, "failed")
    e = RuntimeError("boom")
    e.response = _FakeReqResp("ia902906.us.archive.org")
    e.request = _FakeReqResp("archive.org")
    assert rsh._failed_host(e, job) == "ia902906.us.archive.org"


def test_failed_host_falls_back_to_the_request_then_the_job():
    job = _job(1, "failed")
    e = RuntimeError("boom")
    e.request = _FakeReqResp("dn711508.ca.archive.org")
    assert rsh._failed_host(e, job) == "dn711508.ca.archive.org"
    assert rsh._failed_host(RuntimeError("boom"), job) == "example.invalid"


def test_failed_host_never_carries_a_path_or_query():
    """The reason the message itself is kept out of the log in the first place."""
    job = _job(1, "failed")
    job.url = "https://archive.org/download/item/rom.zip?token=secret-value"
    host = rsh._failed_host(RuntimeError("boom"), job)
    assert host == "archive.org"
    assert "?" not in host and "/" not in host and "secret" not in host
