"""Plugin installation, discovery, and removal logic.

Handles ZIP extraction, manifest validation, dependency installation,
and filesystem operations for the plugin system.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from config import PLUGINS_PATH

logger = logging.getLogger(__name__)

REQUIRED_MANIFEST_FIELDS = ["id", "name", "version", "author", "type", "entry"]
ALLOWED_TYPES = ["metadata", "download", "library", "theme", "widget", "lifecycle"]


async def install_plugin_from_url(url: str) -> dict:
    """Download ZIP from a URL, then install it. Returns parsed manifest."""
    import httpx

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
            r = await client.get(url)
            if r.status_code == 404:
                raise ValueError(f"Plugin package not found: {url}")
            r.raise_for_status()
            tmp_path.write_bytes(r.content)
        return await install_plugin_from_zip(tmp_path)
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"Download failed ({exc.response.status_code}): {url}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)


async def install_plugin_from_zip(zip_path: Path) -> dict:
    """Extract ZIP, validate plugin.json manifest, install deps, copy to plugins dir.

    Returns the parsed manifest dict on success.
    Raises ValueError on validation failure, RuntimeError on install failure.
    """
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
