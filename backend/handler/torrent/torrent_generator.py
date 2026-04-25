"""Torrent file generator.

Uses `transmission-create` (bundled with transmission-cli) to build a .torrent
file from an existing file on disk, embedding public trackers from ngosang/trackerslist.

Tracker list is fetched once per process lifetime and cached in memory.
Falls back to a small built-in list if the remote fetch fails.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time

import httpx

logger = logging.getLogger(__name__)

_TRACKER_URL = (
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
)
_FALLBACK_TRACKERS = [
    "udp://open.tracker.cl:1337/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.openbittorrent.com:6969/announce",
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
]

_tracker_cache: list[str] = []
_tracker_cache_ts: float  = 0.0
_TRACKER_CACHE_TTL: float = 86400.0   # refresh daily


async def get_trackers() -> list[str]:
    """Return a list of public tracker announce URLs, cached for 24 h."""
    global _tracker_cache, _tracker_cache_ts

    if _tracker_cache and (time.monotonic() - _tracker_cache_ts) < _TRACKER_CACHE_TTL:
        return _tracker_cache

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(_TRACKER_URL)
            resp.raise_for_status()
            trackers = [
                line.strip()
                for line in resp.text.splitlines()
                if line.strip() and not line.startswith("#")
            ]
            if trackers:
                _tracker_cache    = trackers
                _tracker_cache_ts = time.monotonic()
                logger.info("Tracker list refreshed: %d trackers", len(trackers))
                return _tracker_cache
    except Exception as exc:
        logger.warning("Failed to fetch tracker list: %s - using fallback", exc)

    _tracker_cache    = _FALLBACK_TRACKERS
    _tracker_cache_ts = time.monotonic()
    return _tracker_cache


async def create_torrent(file_path: str, output_dir: str) -> str:
    """Generate a .torrent file for `file_path` using transmission-create.

    Returns the absolute path to the created .torrent file.
    Raises RuntimeError on failure.
    """
    if not os.path.exists(file_path):
        raise RuntimeError(f"Source file not found: {file_path}")

    trackers = await get_trackers()
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{base_name}.torrent")

    # Build transmission-create command
    cmd = ["transmission-create", "-o", output_path]
    for tracker in trackers[:10]:   # embed top 10 trackers
        cmd += ["-t", tracker]
    cmd.append(file_path)

    logger.debug("Creating torrent: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"transmission-create failed (rc={proc.returncode}): {err}")

    if not os.path.exists(output_path):
        raise RuntimeError("transmission-create exited 0 but .torrent not found")

    logger.info("Torrent created: %s", output_path)
    return output_path
