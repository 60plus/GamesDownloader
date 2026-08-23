"""Plugin installation, discovery, and removal logic.

Handles ZIP extraction, manifest validation, dependency installation,
and filesystem operations for the plugin system.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from config import GD_VERSION, PLUGINS_PATH

logger = logging.getLogger(__name__)

# A plugin archive carries its assets: a theme is hundreds of files of images
# and fonts. High enough that no real plugin meets it, low enough that a store
# serving something enormous is refused before it fills the disk.
MAX_PLUGIN_ZIP_BYTES = 256 * 1024 * 1024

REQUIRED_MANIFEST_FIELDS = ["id", "name", "version", "author", "type", "entry"]
# "catalog" is a storefront plugin (library_catalog_* hooks): it lists games a
# server could download. "rom_source" is a ROM source plugin (rom_source_* hooks):
# it lists ROMs a server could download into roms/. Without a type here
# read_manifest rejects the manifest and the plugin, though it loads and works,
# never shows in Settings > Plugins - so its config (the credentials a fetch
# needs) is unreachable.
ALLOWED_TYPES = ["metadata", "download", "library", "catalog", "rom_source", "theme", "widget", "lifecycle"]


def _version_tuple(v: str) -> tuple[int, ...]:
    """Lenient version parse: '1.0.15' / 'v1.0' -> numeric tuple, () if none."""
    return tuple(int(p) for p in re.findall(r"\d+", v or "")[:3])


async def install_plugin_from_url(url: str) -> dict:
    """Download ZIP from a URL, then install it. Returns parsed manifest."""
    import httpx

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            # Streamed to disk rather than read whole into memory: the archive
            # is whatever the store serves, and nothing checked its size at all
            # before. The ceiling is deliberately generous - a theme ships its
            # assets, and Neon Horizon alone is close to six hundred files - so
            # it stops a runaway without refusing a real plugin.
            async with client.stream("GET", url) as r:
                if r.status_code == 404:
                    raise ValueError(f"Plugin package not found: {url}")
                r.raise_for_status()
                written = 0
                with tmp_path.open("wb") as fh:
                    async for chunk in r.aiter_bytes(1 << 20):
                        written += len(chunk)
                        if written > MAX_PLUGIN_ZIP_BYTES:
                            raise ValueError(
                                "Plugin package is larger than "
                                f"{MAX_PLUGIN_ZIP_BYTES // (1024 * 1024)} MB"
                            )
                        fh.write(chunk)
        return await install_plugin_from_zip(tmp_path)
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Download failed ({exc.response.status_code}): {url}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


async def install_plugin_from_zip(zip_path: Path) -> dict:
    """Extract ZIP, validate plugin.json manifest, install deps, copy to plugins dir.

    Returns the parsed manifest dict on success.
    Raises ValueError on validation failure, RuntimeError on install failure.

    The work runs in a thread. It contains no awaits at all - a `pip install`
    with a two-minute timeout, a per-member copy of the archive and a copytree
    of the result - and it used to run on the event loop, so installing any
    store plugin that ships a requirements.txt froze the entire server for the
    length of the pip run: every request, the health check and Socket.IO.

    Loading the installed plugin is deliberately *not* moved off the loop. That
    step imports and constructs third-party code, some of which does its
    startup work in __init__ because lifecycle_on_startup does not fire on a
    hot load, and a worker thread has no running event loop for it to reach.
    An import costs milliseconds; pip costs minutes.
    """
    return await asyncio.to_thread(_install_plugin_from_zip_sync, zip_path)


def _install_plugin_from_zip_sync(zip_path: Path) -> dict:
    plugins_dir = Path(PLUGINS_PATH)
    plugins_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # 1. Extract ZIP (with Zip Slip protection + Windows backslash fix)
        #
        # PowerShell `Compress-Archive` on Windows writes backslashes in archive
        # entries (e.g. `assets\pop\file.webp`), violating the ZIP spec which
        # mandates forward slashes (APPNOTE 4.4.17). The default
        # `ZipFile.extractall()` treats backslashes as part of the filename on
        # Linux, so a Windows-built plugin ZIP would land as a single file
        # called `assets\pop\file.webp` instead of being placed inside
        # `assets/pop/file.webp`. Normalize to forward slashes during
        # extraction to defensively handle Windows-built archives.
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    # Normalize separator before any safety check
                    safe_name = member.replace("\\", "/")
                    if not safe_name or safe_name.endswith("/"):
                        # Directory entry - mkdir and continue
                        if safe_name:
                            (tmp_path / safe_name).mkdir(parents=True, exist_ok=True)
                        continue
                    member_path = Path(safe_name)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise ValueError(
                            f"Unsafe path in ZIP: {member!r} - rejecting archive"
                        )
                    target = tmp_path / member_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Invalid ZIP file: {exc}") from exc

        # 2. Find plugin.json - check root first, then first subdirectory
        manifest_path = tmp_path / "plugin.json"
        plugin_root = tmp_path

        if not manifest_path.exists():
            # Check first subdirectory (common when ZIP contains a folder)
            subdirs = [
                d for d in tmp_path.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            ]
            if len(subdirs) == 1:
                manifest_path = subdirs[0] / "plugin.json"
                plugin_root = subdirs[0]

        if not manifest_path.exists():
            raise ValueError("plugin.json not found in ZIP archive")

        # 3. Parse and validate manifest
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid plugin.json: {exc}") from exc

        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                raise ValueError(f"plugin.json missing required field: {field}")

        if manifest["type"] not in ALLOWED_TYPES:
            raise ValueError(
                f"Invalid plugin type '{manifest['type']}'. "
                f"Allowed: {', '.join(ALLOWED_TYPES)}"
            )

        # 3.5 Version gate: refuse plugins that require a newer GD than this
        # image. Unparseable values skip the check rather than block installs.
        min_gd = str(manifest.get("min_gd_version") or "").strip()
        if min_gd:
            need = _version_tuple(min_gd)
            have = _version_tuple(GD_VERSION)
            if need and have and have < need:
                raise ValueError(
                    f"Plugin '{manifest.get('name', manifest['id'])}' requires "
                    f"GamesDownloader {min_gd} or newer, but this server runs "
                    f"{GD_VERSION}. Update GamesDownloader first."
                )

        # 4. Security: plugin_id must not contain path separators or dots
        plugin_id = manifest["id"]
        if "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
            raise ValueError(
                f"Invalid plugin id '{plugin_id}': must not contain "
                "path separators or '..'"
            )

        # 5. Install Python dependencies if requirements.txt exists
        dest_dir = plugins_dir / plugin_id
        requirements = plugin_root / "requirements.txt"
        if requirements.exists():
            vendor_dir = plugin_root / "vendor"
            vendor_dir.mkdir(exist_ok=True)
            try:
                subprocess.check_call(
                    [
                        sys.executable, "-m", "pip", "install",
                        "--target", str(vendor_dir),
                        "-r", str(requirements),
                        "--quiet",
                    ],
                    timeout=120,
                )
                logger.info("Installed dependencies for plugin '%s'", plugin_id)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(
                    f"Failed to install plugin dependencies: {exc}"
                ) from exc

        # 6. Copy plugin directory to PLUGINS_PATH/{plugin_id}/
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(plugin_root, dest_dir)

        logger.info("Plugin '%s' installed to %s", plugin_id, dest_dir)

        # 7. Return manifest
        manifest["has_logo"] = (
            (dest_dir / "logo.png").exists()
            or (dest_dir / "logo.svg").exists()
        )
        return manifest


def read_manifest(plugin_dir: Path) -> dict | None:
    """Read plugin.json from a plugin directory. Return None if invalid."""
    manifest_path = plugin_dir / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path) as f:
            data = json.load(f)
        # Validate required fields
        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in data:
                return None
        if data.get("type") not in ALLOWED_TYPES:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def list_installed_plugins() -> list[dict]:
    """Scan PLUGINS_PATH for installed plugins with valid manifests."""
    plugins_dir = Path(PLUGINS_PATH)
    if not plugins_dir.exists():
        return []
    result = []
    for d in sorted(plugins_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        manifest = read_manifest(d)
        if manifest:
            manifest["has_logo"] = (
                (d / "logo.png").exists() or (d / "logo.svg").exists()
            )
            result.append(manifest)
    return result


async def uninstall_plugin(plugin_id: str) -> bool:
    """Remove plugin directory. Returns True if removed, False if not found."""
    # Security: prevent path traversal
    if "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
        return False
    plugin_dir = Path(PLUGINS_PATH) / plugin_id
    if not plugin_dir.exists() or not plugin_dir.is_dir():
        return False
    shutil.rmtree(plugin_dir)
    logger.info("Plugin '%s' uninstalled (directory removed)", plugin_id)
    return True
