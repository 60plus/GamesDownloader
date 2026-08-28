"""Converting a title to CHD as a job the tray can show and somebody can stop.

A multi-disc game is one job. Converting three discs of four would leave a set
that is half one format and half the other, with a playlist naming files that
are no longer all there, and the person watching would have no way to tell
that from a job still running.

Shape borrowed from the two things that already work this way: the payload and
the rehydration from the ZIP packer, the registry with a stop flag from the ROM
downloader. What is added here is the child process. Cancelling the task that
awaits a subprocess does not stop the subprocess, so the flag is read between
discs and passed into the converter, which terminates chdman itself.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException

from handler.database.rom_handler import rom_handler
from handler.roms.chd_convert import (
    ChdError,
    convert_disc_files,
    convertible_disc,
    retire_sources,
    rewrite_playlists,
)
from handler.socket_handler import emit_event

logger = logging.getLogger(__name__)

EVENT = "chd:convert"

# One at a time, always. chdman saturates a core and the machine this runs on
# is also serving the library, streaming a game and running a scan.
_gate = asyncio.Semaphore(1)

_job_seq = itertools.count(1)
_jobs: dict[int, "_ChdJob"] = {}
_KEEP_FINISHED = 50


@dataclass
class _ChdJob:
    id: int
    rom_id: int
    title: str
    total_discs: int
    done_discs: int = 0
    percent: float = 0.0
    status: str = "queued"          # queued|converting|completed|failed|cancelled
    error: str | None = None
    delete_source: bool = False
    saved_bytes: int = 0
    want: str | None = None         # "cancel"
    task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    def as_dict(self) -> dict:
        return {
            "id": f"chd-{self.id}",
            "job_id": self.id,
            "rom_id": self.rom_id,
            "title": self.title,
            "status": self.status,
            "percent": round(self.percent, 1),
            "done_discs": self.done_discs,
            "total_discs": self.total_discs,
            "saved_bytes": self.saved_bytes,
            "delete_source": self.delete_source,
            "error": self.error,
        }


def _announce(job: _ChdJob) -> None:
    try:
        asyncio.create_task(emit_event(EVENT, job.as_dict()))
    except RuntimeError:
        # No running loop, which happens in tests calling the work directly.
        pass


async def convert_set(
    rom_id: int,
    *,
    delete_source: bool,
    on_percent=None,
    should_stop=None,
    session=None,
) -> dict:
    """Convert every disc of this title, then fix up what named the old ones.

    The rows are updated one disc at a time, so a set stopped halfway is a set
    where the discs already done are correct and the rest are untouched. The
    playlists are rewritten at the end and only for discs that really changed.

    Raises ChdError if any disc fails, having left the rest of the library
    alone: a conversion that cannot finish must not be a conversion that
    half-deleted a game.
    """
    rom = await rom_handler.get_by_id(rom_id, session=session)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    members = await rom_handler.disk_set(rom_id, session=session)
    discs = [m for m in members if not m.track_of] or [rom]
    directory = Path(rom.fs_path)

    renames: dict[str, str] = {}
    retired: list[Path] = []
    saved = 0

    for index, disc in enumerate(discs):
        if should_stop is not None and should_stop():
            raise ChdError("cancelled")

        def _disc_progress(percent: float, _i=index) -> None:
            if on_percent is not None:
                on_percent((_i * 100.0 + percent) / len(discs))

        # Read off the row before it is updated. Writing the row can refresh
        # the object in this session, and then disc.fs_name is the new name:
        # the rename map came out as .chd to .chd, which is a no-op, and the
        # playlist was left naming files that had just been deleted.
        here = Path(disc.fs_path)
        was_called = disc.fs_name

        done = await convert_disc_files(
            here / was_called, here,
            on_percent=_disc_progress,
            should_stop=should_stop,
        )
        await rom_handler.adopt_converted_file(
            disc.id, done.path.name, done.now_bytes, done.sha1, session=session,
        )
        renames[was_called] = done.path.name
        saved += max(0, done.was_bytes - done.now_bytes)

        if delete_source:
            for path in done.replaced:
                _delete_inside(path, here)
        else:
            retired += retire_sources(done.replaced, here)

        if on_percent is not None:
            on_percent((index + 1) * 100.0 / len(discs))

    if renames:
        rewrite_playlists(directory, renames)

    return {
        "discs": len(discs),
        "saved_bytes": saved,
        "retired": [str(p) for p in retired],
    }


def _delete_inside(path: Path, directory: Path) -> None:
    """Remove a file the conversion replaced, refusing anything outside.

    The last guard before the one irreversible step in this feature. fs_path
    is a stored string, and this project has removed a user's data three times
    already, so the containment question is asked here as well as upstream
    rather than assumed to have been asked.
    """
    try:
        here = path.resolve()
        base = directory.resolve()
    except OSError:
        return
    if here.parent != base or not here.is_file():
        logger.warning("Refusing to delete %s: it is not in %s", path, directory)
        return
    try:
        os.unlink(here)
    except OSError as err:
        logger.warning("Could not remove %s: %s", here.name, err)


# ── The job the tray sees ─────────────────────────────────────────────────────

async def start(rom_id: int, *, delete_source: bool) -> dict:
    """Queue a conversion for this title and hand back the row for the tray."""
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    for job in _jobs.values():
        if job.rom_id == rom_id and not job.terminal:
            raise HTTPException(
                status_code=409, detail="This title is already being converted")

    members = await rom_handler.disk_set(rom_id)
    discs = [m for m in members if not m.track_of] or [rom]
    # Asked of the files, the same question the page asked before offering the
    # button. A zipped cartridge ROM passes any check made on the name alone.
    usable = await asyncio.to_thread(
        lambda: all(convertible_disc(Path(d.fs_path) / d.fs_name) for d in discs)
    )
    if not usable:
        raise HTTPException(
            status_code=422,
            detail="This title is not in a format that can be converted")

    job = _ChdJob(
        id=next(_job_seq),
        rom_id=rom_id,
        title=rom.name or rom.fs_name_no_ext or str(rom_id),
        total_discs=len(discs),
        delete_source=delete_source,
    )
    _jobs[job.id] = job
    _prune()
    job.task = asyncio.create_task(_run(job))
    _announce(job)
    return job.as_dict()


async def _run(job: _ChdJob) -> None:
    async with _gate:
        if job.want == "cancel":
            job.status = "cancelled"
            _announce(job)
            return
        job.status = "converting"
        _announce(job)
        last = 0.0

        def _progress(percent: float) -> None:
            nonlocal last
            job.percent = percent
            job.done_discs = min(job.total_discs, int(percent * job.total_discs / 100))
            # A second between updates: chdman reports hundreds of times per
            # disc and every one of these is a broadcast to every open tab.
            now = asyncio.get_running_loop().time()
            if now - last >= 1.0:
                last = now
                _announce(job)

        try:
            out = await convert_set(
                job.rom_id,
                delete_source=job.delete_source,
                on_percent=_progress,
                should_stop=lambda: job.want == "cancel",
            )
        except ChdError as err:
            job.status = "cancelled" if job.want == "cancel" else "failed"
            job.error = None if job.want == "cancel" else str(err)
            logger.info("CHD conversion of %s ended: %s", job.title, err)
        except Exception as err:                      # noqa: BLE001
            job.status = "failed"
            job.error = str(err)
            logger.exception("CHD conversion of %s failed", job.title)
        else:
            job.status = "completed"
            job.percent = 100.0
            job.done_discs = job.total_discs
            job.saved_bytes = out["saved_bytes"]
        _announce(job)


def list_jobs() -> list[dict]:
    return [job.as_dict() for job in _jobs.values()]


def get_job(job_id: int) -> _ChdJob | None:
    return _jobs.get(job_id)


async def cancel(job_id: int) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such conversion")
    if job.terminal:
        _jobs.pop(job_id, None)
        return job.as_dict()
    job.want = "cancel"
    _announce(job)
    return job.as_dict()


def _prune() -> None:
    finished = [j for j in _jobs.values() if j.terminal]
    for job in finished[:-_KEEP_FINISHED] if len(finished) > _KEEP_FINISHED else []:
        _jobs.pop(job.id, None)
