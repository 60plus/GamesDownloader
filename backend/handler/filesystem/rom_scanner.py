"""ROM filesystem scanner.

Scans /data/games/roms/{platform_fs_slug}/ and syncs found files
with the database.  Supports ROMM-compatible folder structure:

  Structure A (default):
    /data/games/roms/{platform_fs_slug}/{game}.{ext}

  Structure B (alternative):
    /data/games/roms/{platform_fs_slug}/roms/{game}.{ext}
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import zlib
from pathlib import Path

from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.metadata.rom_platform_map import PLATFORM_MAP, slug_from_fs_slug

logger = logging.getLogger(__name__)

# Common ROM extensions - anything outside this list is silently skipped
_ROM_EXTENSIONS = {
    # Nintendo
    "nes", "fds", "smc", "sfc", "fig", "swc",          # NES / SNES
    "n64", "z64", "v64",                                 # N64
    "gb", "gbc", "gba",                                  # Game Boy
    "nds", "3ds", "cci", "cxi",                          # DS / 3DS
    "wbfs", "iso", "wad", "rvz",                         # Wii / Wii U
    # Sega
    "md", "gen", "bin", "sms", "gg", "32x",             # Genesis / SMS / GG / 32X
    "cue", "chd",                                        # CD-based (Saturn, Dreamcast, PS)
    # Sony
    "pbp", "psp", "cso",                                 # PSP
    "pkg",                                               # PS3 / PSN
    # Multi-format
    "img", "mdf", "nrg", "xex",                          # Various
    "zip", "7z", "rar",                                  # Compressed ROMs
    "rom", "a26", "a52", "lnx", "pce", "vb",            # Misc classics
    "ws", "wsc", "ngp", "ngc", "dsk", "adf",            # Handheld / Amiga
}


def _strip_tags(name: str) -> str:
    """Remove [tags] and (tags) from a ROM filename."""
    import re
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    return name.strip()


def _hash_stream(stream) -> tuple[str, str, str]:
    """Hash a readable stream → (crc32_hex_upper, md5_hex, sha1_hex)."""
    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    while chunk := stream.read(4 * 1024 * 1024):
        crc = zlib.crc32(chunk, crc)
        md5.update(chunk)
        sha1.update(chunk)
    crc_hex = format(crc & 0xFFFFFFFF, "08X")
    return crc_hex, md5.hexdigest(), sha1.hexdigest()


def _compute_hashes(path: Path) -> tuple[str, str, str]:
    """Return (crc32_hex_upper, md5_hex, sha1_hex) for ROM content.

    For .zip / .7z archives: hashes the LARGEST file inside (the actual ROM),
    not the archive itself.  This matches how ScreenScraper and EmulationStation
    identify ROMs - by the hash of the uncompressed content.

    Returns ('', '', '') on any error.
    """
    suffix = path.suffix.lower()

    try:
        # ── ZIP archive ──────────────────────────────────────────────────
        if suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(path, "r") as zf:
                # Pick largest file (the ROM)
                entries = sorted(zf.infolist(), key=lambda e: e.file_size, reverse=True)
                if not entries:
                    return "", "", ""
                with zf.open(entries[0]) as rom_stream:
                    logger.debug("Hashing ZIP member: %s (%d bytes)", entries[0].filename, entries[0].file_size)
                    return _hash_stream(rom_stream)

        # ── 7z archive ───────────────────────────────────────────────────
        if suffix == ".7z":
            try:
                import py7zr
            except ImportError:
                logger.warning("py7zr not installed - cannot hash .7z contents, hashing archive file instead")
                with path.open("rb") as fh:
                    return _hash_stream(fh)

            import io
            with py7zr.SevenZipFile(path, "r") as sz:
                # Pick largest file
                entries = sorted(sz.list(), key=lambda e: e.uncompressed or 0, reverse=True)
                if not entries:
                    return "", "", ""
                target = entries[0].filename
                logger.debug("Hashing 7z member: %s (%d bytes)", target, entries[0].uncompressed or 0)
                # Extract single file to memory via temporary dir
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    sz.extract(tmpdir, [target])
                    extracted = Path(tmpdir) / target
                    with extracted.open("rb") as fh:
                        return _hash_stream(fh)

        # ── Regular file ─────────────────────────────────────────────────
        with path.open("rb") as fh:
            return _hash_stream(fh)

    except Exception as e:
        logger.warning("Hash error for %s: %s", path.name, e)
        return "", "", ""


async def scan_roms_path(roms_path: str) -> dict:
    """
    Walk *roms_path*, detect platforms and ROMs, upsert into DB.

    Returns a summary dict:
      { platforms_found, roms_found, roms_new, roms_updated }
    """
    root = Path(roms_path)
    if not root.exists():
        logger.warning("ROM path does not exist: %s", roms_path)
        return {"platforms_found": 0, "roms_found": 0, "roms_new": 0, "roms_updated": 0}

    stats = {"platforms_found": 0, "roms_found": 0, "roms_new": 0, "roms_updated": 0}

    # Pre-pass: mark every DB-registered ROM as missing.  The directory walk
    # below re-unsets the flag for anything actually found on disk.  Doing
    # this ONCE up-front (instead of per-directory) is important because
    # multiple fs_slug alias directories can resolve to the same DB platform
    # row (e.g. `snes/`, `snesna/`, `super-nintendo/` all -> slug
    # super-nintendo-entertainment-system).  Marking missing inside the loop
    # caused the last-processed empty alias dir to silently re-mark ROMs that
    # the earlier, populated alias had just found.
    for p in await rom_platform_handler.get_all_simple():
        await rom_handler.mark_all_missing(p.id)

    for platform_dir in sorted(root.iterdir()):
        if not platform_dir.is_dir():
            continue

        fs_slug = platform_dir.name
        slug = slug_from_fs_slug(fs_slug)
        info = PLATFORM_MAP.get(fs_slug, {})
        display_name = info.get("name", fs_slug.upper())

        # Upsert platform (aliased fs_slugs reuse the existing row by slug)
        platform = await rom_platform_handler.upsert(fs_slug, slug, display_name)
        stats["platforms_found"] += 1

        # Support both structure A (roms directly) and B (roms/ subdir)
        roms_subdir = platform_dir / "roms"
        scan_dir = roms_subdir if roms_subdir.is_dir() else platform_dir

        # Walk ROM files
        rom_files = []
        try:
            for entry in sorted(scan_dir.iterdir()):
                if entry.is_file():
                    ext = entry.suffix.lstrip(".").lower()
                    if ext in _ROM_EXTENSIONS:
                        rom_files.append(entry)
        except PermissionError as e:
            logger.warning("Permission error reading %s: %s", scan_dir, e)
            continue

        for rom_file in rom_files:
            stats["roms_found"] += 1
            fs_name = rom_file.name
            fs_name_no_ext = _strip_tags(rom_file.stem)
            fs_extension = rom_file.suffix.lstrip(".")
            fs_path = str(rom_file.parent)
            try:
                fs_size = rom_file.stat().st_size
            except OSError:
                fs_size = 0

            existing = await rom_handler.get_by_fs_name(platform.id, fs_name)
            loop = asyncio.get_running_loop()
            if existing is None:
                stats["roms_new"] += 1
                crc_hash, md5_hash, sha1_hash = await loop.run_in_executor(
                    None, _compute_hashes, rom_file
                )
                logger.debug("Hashed %s  CRC=%s  MD5=%s  SHA1=%s", fs_name, crc_hash, md5_hash, sha1_hash[:8])
            else:
                stats["roms_updated"] += 1
                if existing.fs_size_bytes != fs_size or not existing.crc_hash:
                    crc_hash, md5_hash, sha1_hash = await loop.run_in_executor(
                        None, _compute_hashes, rom_file
                    )
                    logger.debug("Re-hashed %s  CRC=%s  MD5=%s  SHA1=%s", fs_name, crc_hash, md5_hash, sha1_hash[:8])
                else:
                    crc_hash = existing.crc_hash
                    md5_hash = existing.md5_hash or ""
                    sha1_hash = getattr(existing, "sha1_hash", None) or ""

            await rom_handler.upsert(
                platform_id=platform.id,
                fs_name=fs_name,
                fs_name_no_ext=fs_name_no_ext,
                fs_extension=fs_extension,
                fs_path=fs_path,
                fs_size_bytes=fs_size,
                crc_hash=crc_hash,
                md5_hash=md5_hash,
                sha1_hash=sha1_hash,
            )

        logger.info(
            "Scanned platform %s - %d ROM(s) found", fs_slug, len(rom_files)
        )

    # Clean up platforms whose folder no longer exists
    scanned_fs_slugs = {d.name for d in root.iterdir() if d.is_dir()}
    all_platforms = await rom_platform_handler.get_all_simple()
    for p in all_platforms:
        if p.fs_slug not in scanned_fs_slugs:
            logger.info("Platform folder gone for %s - marking all ROMs missing", p.fs_slug)
            await rom_handler.mark_all_missing(p.id)

    logger.info(
        "ROM scan complete: %d platforms, %d ROMs (%d new, %d updated)",
        stats["platforms_found"],
        stats["roms_found"],
        stats["roms_new"],
        stats["roms_updated"],
    )
    return stats
