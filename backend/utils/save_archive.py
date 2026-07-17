"""Save archive (ZIP) - export and restore emulator saves.

A bare .state download drops everything around the save: the screenshot stays on
the server, and nothing records which game or slot the bytes belonged to, so a
round-trip through a reinstall cannot put them back. The archive carries the
save, its screenshot and a manifest naming the ROM, so an import can route every
file home without asking.

The layout is the same whether the archive holds one save or every save - import
therefore does not care which it was handed:

    gd-saves.json
    Pitfall - The Mayan Adventure/slot 1.state
    Pitfall - The Mayan Adventure/slot 1.png
    Super Mario World/battery.srm

Paths are human-readable on purpose: unzipping to feed a save into a desktop
emulator should not mean hunting through `files/0.bin`. (game, slot) is unique,
so the names cannot collide.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

MANIFEST_NAME = "gd-saves.json"
# Bump only on a breaking layout change; readers accept anything <= this.
ARCHIVE_VERSION = 1
# The manifest is JSON describing entries - kilobytes even for a full library.
# It is read through the same cap as every other member: an uncapped read let a
# few MB of zeros in a zip inflate to gigabytes before json.loads ever saw them.
MAX_MANIFEST_SIZE = 4 * 1024 * 1024


def safe_name(name: str) -> str:
    """One path segment, safe on every OS - ROM names are scanned off disk and
    can carry separators ("Sonic 1/2") that would fork the archive layout."""
    cleaned = "".join("_" if c in '/\\:*?"<>|' else c for c in name).strip(" .")
    return (cleaned or "rom")[:80]


def _entry_stem(kind: str, slot: int | None, row_id: int) -> str:
    if kind == "battery":
        return "battery"
    if slot:
        return f"slot {slot}"
    # Legacy savestates predate slots; the id keeps them distinct.
    return f"older-{row_id}"


def build_archive(items: list[dict]) -> Path:
    """Zip `items` into a temp file and return its path (caller deletes it).

    Each item: {rom, row, kind, file_path, screenshot_path}. Written to disk
    rather than memory because "export everything" is bounded by the save quota
    (100 MB by default), not by anything smaller.
    """
    tmp = tempfile.NamedTemporaryFile(prefix="gd-saves-", suffix=".zip", delete=False)
    tmp.close()
    manifest: dict = {
        "gd_saves": ARCHIVE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "entries": [],
    }

    # Only a returned path gets cleaned up (the response carries a BackgroundTask
    # that unlinks it). Any escape before the return - a save deleted between the
    # exists() check and the read, a full disk - would otherwise strand the temp
    # file forever, and /tmp is a tmpfs on plenty of installs.
    try:
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
            for it in items:
                rom, row, kind = it["rom"], it["row"], it["kind"]
                src = Path(it["file_path"])
                if not src.exists():
                    logger.warning("Export: %s is missing on disk, skipping", src)
                    continue

                folder = safe_name(
                    (rom.name or rom.fs_name_no_ext or f"rom {rom.id}") if rom else f"rom {row.rom_id}"
                )
                stem = _entry_stem(kind, getattr(row, "slot", None), row.id)
                ext = ".srm" if kind == "battery" else ".state"
                arc_file = f"{folder}/{stem}{ext}"
                try:
                    zf.write(src, arc_file)
                except OSError:
                    # Deleted or unreadable between the check and the read - skip
                    # it like any other missing save rather than failing a whole
                    # library export over one file.
                    logger.warning("Export: could not read %s, skipping", src)
                    continue

                arc_shot = None
                shot = it.get("screenshot_path")
                if shot and Path(shot).exists():
                    try:
                        arc_shot = f"{folder}/{stem}.png"
                        zf.write(shot, arc_shot)
                    except OSError:
                        logger.warning("Export: could not read %s, skipping shot", shot)
                        arc_shot = None

                plat = getattr(rom, "platform", None) if rom else None
                manifest["entries"].append({
                    "kind":          kind,
                    "slot":          getattr(row, "slot", None),
                    "file":          arc_file,
                    "screenshot":    arc_shot,
                    "emulator_core": row.emulator_core,
                    "created_at":    row.created_at.isoformat() if row.created_at else None,
                    "updated_at":    row.updated_at.isoformat() if row.updated_at else None,
                    # Enough to find the ROM again on another install: the hash is
                    # exact, the filename survives a re-scan, the name is the last
                    # resort.
                    "rom": {
                        "name":          (rom.name or rom.fs_name_no_ext) if rom else None,
                        "fs_name":       rom.fs_name if rom else None,
                        "sha1":          rom.sha1_hash if rom else None,
                        "platform_slug": plat.slug if plat else None,
                    },
                })

            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, ensure_ascii=False))
    except BaseException:
        Path(tmp.name).unlink(missing_ok=True)
        raise

    return Path(tmp.name)


def read_manifest(zf: zipfile.ZipFile) -> dict | None:
    """The archive's manifest, or None if this zip is not one of ours.

    Raises ValueError on a manifest that is oversized or from a newer release -
    both are a bad archive, not a missing one, and the caller answers 400.
    """
    try:
        raw = member_bytes(zf, MANIFEST_NAME, MAX_MANIFEST_SIZE)
    except KeyError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or "entries" not in data:
        return None
    if int(data.get("gd_saves") or 0) > ARCHIVE_VERSION:
        raise ValueError(
            "This archive was made by a newer GamesDownloader and cannot be read here."
        )
    return data


def member_bytes(zf: zipfile.ZipFile, name: str, max_size: int) -> bytes:
    """Read one member, refusing paths that escape the archive and members that
    inflate past `max_size` - a manifest is attacker-supplied like any upload."""
    if not name:
        raise ValueError("empty member name")
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe path in archive: {name}")
    info = zf.getinfo(name)
    if info.file_size > max_size:
        raise ValueError(f"{name} is too large ({info.file_size} bytes)")
    with zf.open(info) as fh:
        data = fh.read(max_size + 1)
    if len(data) > max_size:
        raise ValueError(f"{name} is too large")
    return data
