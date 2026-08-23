"""ROM downloads need a ceiling on how many run at once.

`queue_downloads` created one task per selected entry with nothing in between,
and the browser ships a select-all over a sixty-row page. Sixty tasks meant
sixty sockets against one host, sixty .part files growing together, and - the
part that actually filled the disk - sixty calls to `assert_room_for`, each
asking the same instant whether there was room for one more four-gigabyte file.
All sixty were told yes.

A cap fixes the disk check as much as the fan-out: a job asks about free space
when its turn comes, by which time the ones ahead of it have really landed.
"""
from __future__ import annotations

import asyncio
import inspect

import handler.roms.rom_source_handler as rsh


class FakeConfig:
    def __init__(self, roms: dict):
        self._roms = roms

    def get_section(self, name: str) -> dict:
        return self._roms if name == "roms" else {}


def use_config(monkeypatch, roms: dict):
    monkeypatch.setattr(rsh, "config_manager", FakeConfig(roms))
    # The gate caches the limit it was built for; drop it between cases.
    monkeypatch.setattr(rsh, "_download_gate", None)
    monkeypatch.setattr(rsh, "_download_gate_limit", 0)


# ── The setting ──────────────────────────────────────────────────────────────

def test_the_default_applies_when_nothing_is_configured(monkeypatch):
    use_config(monkeypatch, {})
    assert rsh.max_parallel_rom_downloads() == rsh._DEFAULT_MAX_PARALLEL_ROM_DOWNLOADS


def test_an_explicit_limit_is_honoured(monkeypatch):
    use_config(monkeypatch, {"max_parallel_downloads": 7})
    assert rsh.max_parallel_rom_downloads() == 7


def test_zero_and_nonsense_fall_back_rather_than_stopping_downloads(monkeypatch):
    """A limit of zero would queue every download forever."""
    for value in (0, "", None, "lots", -4):
        use_config(monkeypatch, {"max_parallel_downloads": value})
        assert rsh.max_parallel_rom_downloads() == rsh._DEFAULT_MAX_PARALLEL_ROM_DOWNLOADS


# ── The gate ─────────────────────────────────────────────────────────────────

def test_the_gate_is_sized_to_the_setting(monkeypatch):
    use_config(monkeypatch, {"max_parallel_downloads": 4})
    assert rsh._gate()._value == 4


def test_the_same_gate_is_shared_while_the_setting_holds(monkeypatch):
    """Every job has to queue against one counter; a fresh gate per call would
    be no limit at all."""
    use_config(monkeypatch, {"max_parallel_downloads": 4})
    assert rsh._gate() is rsh._gate()


def test_raising_the_limit_takes_effect_without_a_restart(monkeypatch):
    use_config(monkeypatch, {"max_parallel_downloads": 2})
    first = rsh._gate()
    monkeypatch.setattr(rsh, "config_manager", FakeConfig({"max_parallel_downloads": 5}))
    second = rsh._gate()
    assert second is not first
    assert second._value == 5


async def test_the_gate_actually_holds_back_the_extra_jobs(monkeypatch):
    use_config(monkeypatch, {"max_parallel_downloads": 2})
    gate = rsh._gate()
    live = 0
    peak = 0

    async def pretend_download():
        nonlocal live, peak
        async with gate:
            live += 1
            peak = max(peak, live)
            await asyncio.sleep(0)
            live -= 1

    await asyncio.gather(*(pretend_download() for _ in range(10)))
    assert peak <= 2


# ── The job goes through it ──────────────────────────────────────────────────

def test_the_download_job_waits_for_a_slot_before_transferring():
    source = inspect.getsource(rsh._rom_download_job)
    assert "gate.acquire()" in source
    assert "_run_rom_download" in source


def test_a_job_stopped_while_queued_still_lets_go_of_its_claims():
    """It never opened a connection, but the destination was reserved the
    moment it was queued. Left held, nothing else could ever download there."""
    source = inspect.getsource(rsh._rom_download_job)
    assert "CancelledError" in source
    assert "_release_job_locks" in source


# ── What the slot must NOT be held for ───────────────────────────────────────
#
# Introducing the cap created a second problem. Registering a finished download
# walks the entire ROM tree and then scrapes metadata over the network, and
# both ran inside the transfer - so a job kept one of the three slots for the
# length of a scan. Worse, the scan coalesces: every other finishing job waited
# on _scan_cv while holding its own slot, so all three could sit idle behind
# one scan. Before the cap this cost nothing, because there were no slots.

def test_the_transfer_does_not_register_the_file_itself():
    source = inspect.getsource(rsh._run_rom_download)
    assert "_register_and_scrape" not in source, (
        "the scan and scrape must not run while the download slot is held"
    )


def test_registration_happens_after_the_slot_goes_back():
    source = inspect.getsource(rsh._rom_download_job)
    release = source.index("gate.release()")
    register = source.index("_register_after_download")
    assert release < register, "the slot is handed back before the scan starts"


def test_the_completion_event_carries_the_rom_id():
    """It is emitted after registration because the browser opens the game's
    page from it; announcing first would hand it a null."""
    source = inspect.getsource(rsh._register_after_download)
    rom_id = source.index("rom_id = await _register_and_scrape")
    emit = source.index("romsource:download_complete")
    assert rom_id < emit
