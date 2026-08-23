"""Storage for the firmware the emulator cores ask for.

Files live under ``firmware_root()/<ejs_core>/<declared path>``, where the
declared path is spelled exactly as the core spells it, subdirectory included.
Keeping the core's own spelling means the bundle handed to the player can be
unpacked straight into the emulator without a translation step, and a file
whose name the core would not recognise never enters the store in the first
place.

Only paths the registry declares are accepted.  That is an allow-list rather
than a traversal check: a name that is not in the core's own list is refused
whether or not it looks dangerous, so there is no separate escaping to get
wrong.
"""

from __future__ import annotations

import hashlib
import io
import logging
import zipfile
from pathlib import Path

from config import CONFIG_PATH, FIRMWARE_PATH
from handler.roms.firmware_registry import (
    LIBRETRO_CORE,
    Firmware,
    for_core,
    known_paths,
)
from utils.volume_check import is_ephemeral

logger = logging.getLogger(__name__)

# A single firmware file is a BIOS image, not a disc. The largest thing any
# bundled core asks for is a few megabytes, so anything beyond this is either a
# mistake or an attempt to fill the disk.
MAX_FILE_BYTES = 32 * 1024 * 1024

# Where firmware goes when /data/firmware has no volume of its own. /data/config
# is mounted by every release of the compose file, so this survives a recreate.
FALLBACK_ROOT = CONFIG_PATH / "firmware"

_root_cache: Path | None = None


def firmware_root() -> Path:
    """The directory tree holding firmware.

    FIRMWARE_PATH normally. An install whose compose predates that mount would
    otherwise keep these files in the container's writable layer and lose every
    one of them on the next `up -d` - and unlike a cover or a scraped
    screenshot, firmware cannot be re-fetched: it is a file somebody supplied
    under their own licence. So when the directory is not on a volume we use a
    directory that is, and say so at every boot.
    """
    global _root_cache
    if _root_cache is not None:
        return _root_cache
    target = Path(FIRMWARE_PATH)
    if is_ephemeral(target):
        logger.error(
            "GD_FIRMWARE_PATH (%s) is not on a mounted volume - BIOS files "
            "written there would be lost the next time the container is "
            "recreated. Falling back to %s. Fix this by adding a volume for it "
            "to your docker-compose.yml:"
            "\n    - ${GD_BASE_DIR}/data/firmware:/data/firmware\n"
            "then restart; anything already stored is moved across on boot.",
            target, FALLBACK_ROOT,
        )
        _root_cache = FALLBACK_ROOT
    else:
        _root_cache = target
    return _root_cache


def adopt_fallback_firmware() -> int:
    """Move firmware out of the fallback once the real mount appears.

    Returns the number of files moved. Does nothing when the fallback is where
    firmware belongs, when it holds nothing, or when a file of the same name is
    already in the destination - the file in the mounted directory is the one
    the operator most recently put there, so it wins.
    """
    root = firmware_root()
    if root == FALLBACK_ROOT or not FALLBACK_ROOT.is_dir():
        return 0
    moved = 0
    for src in sorted(FALLBACK_ROOT.rglob("*")):
        if not src.is_file():
            continue
        dest = root / src.relative_to(FALLBACK_ROOT)
        if dest.exists():
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            src.replace(dest)
            moved += 1
        except OSError as exc:
            logger.warning("Could not move firmware %s across: %s", src, exc)
    if moved:
        logger.info(
            "Moved %d firmware file(s) from %s onto the mounted volume at %s",
            moved, FALLBACK_ROOT, root,
        )
    return moved


def _core_dir(ejs_core: str) -> Path:
    """Where files for *ejs_core* live.

    Named after the libretro core rather than the EmulatorJS name, because
    several EmulatorJS names share one core: sega, segaMD, segaCD and segaGG
    all run genesis_plus_gx and all want the same twelve files. Storing per
    EmulatorJS name would make someone with a Mega Drive and a Mega CD supply
    the same BIOS four times over, and three of the four would still read as
    missing.
    """
    return firmware_root() / LIBRETRO_CORE.get(ejs_core, ejs_core)


def _resolved(ejs_core: str, path: str) -> Path:
    """Absolute location of *path* for *ejs_core*, or raise if it is not declared."""
    if path not in known_paths(ejs_core):
        raise ValueError(f"{ejs_core} does not ask for a file named {path!r}")
    return _core_dir(ejs_core) / path


def _digest(p: Path) -> tuple[str, int]:
    md5 = hashlib.md5()
    size = 0
    with p.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            md5.update(chunk)
            size += len(chunk)
    return md5.hexdigest(), size


def status(ejs_core: str, *, with_hash: bool = True) -> list[dict]:
    """Every file *ejs_core* declares, each marked present or missing.

    The MD5 of a stored file is reported so the caller can compare it against a
    reference set; nothing here decides whether a dump is the right one, only
    whether a file is there and what it hashes to.

    `with_hash=False` answers the cheap question - is the file there, how big -
    without reading it. The overview screen only ever asked that, and hashing
    every stored file of all twenty-seven cores to answer it was expensive
    enough to be felt: five of the core names alias onto genesis_plus_gx, so
    that set was read five times in a single request.

    One deliberate difference between the two modes: presence comes from
    `is_file()` here, while the hashing path only sets it after a successful
    read. A file that exists but cannot be read therefore counts as present
    without a hash, which matches what `missing_required` and `bundle` already
    believe.
    """
    out: list[dict] = []
    for fw in for_core(ejs_core):
        p = _core_dir(ejs_core) / fw.path
        entry: dict = {
            "path": fw.path,
            "desc": fw.desc,
            "optional": fw.optional,
            "present": False,
            "size": None,
            "md5": None,
        }
        if p.is_file():
            if with_hash:
                try:
                    entry["md5"], entry["size"] = _digest(p)
                    entry["present"] = True
                except OSError as exc:
                    logger.warning("could not read firmware %s/%s: %s", ejs_core, fw.path, exc)
            else:
                entry["present"] = True
                try:
                    entry["size"] = p.stat().st_size
                except OSError:
                    pass
        out.append(entry)
    return out


def missing_required(ejs_core: str) -> list[Firmware]:
    """Mandatory files that are not on disk, so a caller can say what to supply."""
    return [
        fw
        for fw in for_core(ejs_core)
        if not fw.optional and not (_core_dir(ejs_core) / fw.path).is_file()
    ]


def store(ejs_core: str, path: str, data: bytes) -> dict:
    """Put *data* under the name *path* that *ejs_core* looks for."""
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("firmware file is larger than any core would ask for")
    if not data:
        raise ValueError("firmware file is empty")
    dest = _resolved(ejs_core, path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    md5 = hashlib.md5(data).hexdigest()
    logger.info("stored firmware %s/%s (%d bytes, md5 %s)", ejs_core, path, len(data), md5)
    return {"path": path, "size": len(data), "md5": md5}


def remove(ejs_core: str, path: str) -> bool:
    """Drop a stored file. Returns False when there was nothing to drop."""
    dest = _resolved(ejs_core, path)
    if not dest.is_file():
        return False
    dest.unlink()
    logger.info("removed firmware %s/%s", ejs_core, path)
    return True


def bundle(ejs_core: str) -> bytes | None:
    """Everything stored for *ejs_core*, zipped under the core's own paths.

    Returns None when nothing is stored, so a caller can skip the transfer
    entirely rather than hand the player an empty archive.  Stored without
    compression: BIOS images are already dense and the player unpacks this on
    the main thread while the user waits.
    """
    present = [fw for fw in for_core(ejs_core) if (_core_dir(ejs_core) / fw.path).is_file()]
    if not present:
        return None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for fw in present:
            zf.write(_core_dir(ejs_core) / fw.path, arcname=fw.path)
    return buf.getvalue()


# ── Optional plugin sourcing ──────────────────────────────────────────────────
# Everything above works with no plugin installed, which is the point: a ROM can
# be copied in by hand and firmware must be no harder. What follows only adds a
# way to fetch a file the user would otherwise go hunting for, and it stays on
# core's terms - core decides the filename, core performs the download through
# the SSRF guard, the plugin supplies a URL and its own credentials.


def _plugin_instances() -> list:
    from plugins.manager import plugin_manager

    return list(plugin_manager.get_plugin_instances())


def offers(ejs_core: str) -> dict[str, dict]:
    """What installed plugins say they could supply for the files still missing.

    Keyed by path. Empty whenever no plugin offers anything, which is also the
    answer when none is installed at all.
    """
    wanted = [
        fw.path
        for fw in for_core(ejs_core)
        if not (_core_dir(ejs_core) / fw.path).is_file()
    ]
    if not wanted:
        return {}
    libretro = LIBRETRO_CORE.get(ejs_core, ejs_core)
    found: dict[str, dict] = {}
    for inst in _plugin_instances():
        fn = getattr(inst, "firmware_offers", None)
        if not callable(fn):
            continue
        try:
            result = fn(libretro, list(wanted)) or {}
        except Exception:
            logger.warning("firmware_offers raised for %s", libretro, exc_info=True)
            continue
        if not isinstance(result, dict):
            logger.warning("firmware_offers returned %s, not a dict", type(result).__name__)
            continue
        name = ""
        try:
            name = getattr(inst, "firmware_source_name", lambda: "")() or ""
        except Exception:
            pass
        for path, meta in result.items():
            # A plugin offering something this core never asked for is a bug in
            # the plugin, not an instruction: the same allow-list that guards
            # uploads guards this.
            if path not in wanted or path in found:
                continue
            found[path] = {
                "source": name,
                "label": (meta or {}).get("label") if isinstance(meta, dict) else None,
                "size": (meta or {}).get("size") if isinstance(meta, dict) else None,
                "md5": (meta or {}).get("md5") if isinstance(meta, dict) else None,
            }
    return found


def _resolve(libretro: str, path: str) -> dict | None:
    for inst in _plugin_instances():
        fn = getattr(inst, "firmware_resolve_download", None)
        if not callable(fn):
            continue
        try:
            spec = fn(libretro, path) or {}
        except Exception:
            logger.warning("firmware_resolve_download raised for %s", path, exc_info=True)
            continue
        if isinstance(spec, dict) and spec.get("url"):
            return spec
    return None


async def fetch_from_plugin(ejs_core: str, path: str) -> dict:
    """Download one firmware file a plugin offered, and store it.

    Raises ValueError when nothing offers the file, when the name is not one the
    core asks for, or when the download is refused or oversized.
    """
    import asyncio

    import httpx

    from utils.net_guard import assert_fetch_allowed, make_request_guard

    if path not in known_paths(ejs_core):
        raise ValueError(f"{ejs_core} does not ask for a file named {path!r}")
    libretro = LIBRETRO_CORE.get(ejs_core, ejs_core)
    spec = await asyncio.to_thread(_resolve, libretro, path)
    if not spec:
        raise ValueError("no installed plugin offers that file")

    url = str(spec["url"])
    assert_fetch_allowed(url)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=60.0,
        headers=spec.get("headers") or {},
        cookies=spec.get("cookies") or {},
        event_hooks={"request": [make_request_guard()]},
    ) as client:
        # Streamed with a running total: a ceiling checked after the bytes have
        # already arrived is not a ceiling.
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            declared = int(resp.headers.get("content-length") or 0)
            if declared > MAX_FILE_BYTES:
                raise ValueError("offered file is larger than any core would ask for")
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise ValueError("offered file is larger than any core would ask for")
                chunks.append(chunk)

    stored = store(ejs_core, path, b"".join(chunks))
    # The source's own checksum, when it publishes one, is worth comparing: a
    # truncated or substituted file is otherwise indistinguishable from a good
    # one until a game refuses to boot.
    expected = (spec.get("md5") or "").lower()
    if expected and expected != stored["md5"]:
        remove(ejs_core, path)
        raise ValueError("downloaded file does not match the checksum the source published")
    return stored
