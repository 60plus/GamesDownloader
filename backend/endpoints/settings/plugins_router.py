"""Plugin management endpoints - install, enable/disable, configure, uninstall.

Requires PLUGINS_READ (GET) or PLUGINS_WRITE (POST/PUT/DELETE) scope.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import GD_VERSION, PLUGINS_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
# Imported at module level on purpose: it pulls in models.catalog_entry, and a
# model that is not imported before startup is missing from Base.metadata, so
# create_all never makes its table. An import inside the endpoint looks tidier
# and silently ships a feature whose table does not exist.
from handler.library.catalog_sync_handler import (
    DownloadInProgress,
    SyncInProgress,
    count_entries,
    downloaded_entry_game_ids,
    entry_to_dict,
    get_entry,
    list_catalogs,
    list_entries,
    queue_entry_downloads,
    store_catalog_media,
    sync_catalog,
)
from handler.library.catalog_meta_handler import (
    MetaScrapeInProgress,
    scrape_catalog,
    set_search_term,
)
from handler.database.session import async_session_factory
from handler.plugins.install_handler import (
    install_plugin_from_zip,
    list_installed_plugins,
    read_manifest,
    uninstall_plugin,
)
from models.plugin_config import PluginConfig
from plugins.manager import plugin_manager
from schemas.plugin import PluginConfigUpdate, PluginInfo
from sqlalchemy import select

logger = logging.getLogger(__name__)

plugins_router = APIRouter(prefix="/api/plugins", tags=["plugins"])


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_db_config(plugin_id: str) -> PluginConfig | None:
    """Fetch a PluginConfig row by plugin_id."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
        )
        return result.scalar_one_or_none()


async def _upsert_db_config(
    plugin_id: str,
    manifest: dict,
    enabled: bool = True,
    config_json: str | None = None,
) -> PluginConfig:
    """Insert or update a PluginConfig row from a manifest dict."""
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
            )
            row = result.scalar_one_or_none()

            schema_raw = manifest.get("config_schema")
            schema_json = json.dumps(schema_raw) if schema_raw else None

            if row is None:
                row = PluginConfig(
                    plugin_id=plugin_id,
                    name=manifest.get("name", plugin_id),
                    version=manifest.get("version", "0.0.0"),
                    author=manifest.get("author", ""),
                    description=manifest.get("description"),
                    plugin_type=manifest.get("type", "library"),
                    enabled=enabled,
                    config_json=config_json,
                    config_schema_json=schema_json,
                )
                session.add(row)
            else:
                row.name = manifest.get("name", plugin_id)
                row.version = manifest.get("version", "0.0.0")
                row.author = manifest.get("author", "")
                row.description = manifest.get("description")
                row.plugin_type = manifest.get("type", "library")
                row.enabled = enabled
                if config_json is not None:
                    row.config_json = config_json
                if schema_json is not None:
                    row.config_schema_json = schema_json

            return row


async def _delete_db_config(plugin_id: str) -> bool:
    """Delete a PluginConfig row. Returns True if deleted."""
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                return False
            await session.delete(row)
            return True


def _redact_config(
    config: dict | None,
    config_schema: dict | None,
    is_admin: bool,
) -> dict | None:
    """Withhold secret config values from readers who cannot manage plugins.

    Plugin config is stored cleartext and routinely holds credentials - the PC
    Ports catalogue keeps a GitHub token here. PLUGINS_READ is a base-user scope
    (themes and the translate button both need the plugin list), so a plain user
    reaching GET /api/plugins or /{id}/config must not receive those secrets;
    only PLUGINS_WRITE (admin) sees the real values. Fields the schema types as
    "password" are dropped. A plugin with no schema is redacted whole - we can't
    tell which of its values are safe, so we withhold all of them.
    """
    if is_admin or config is None:
        return config
    if not isinstance(config, dict) or not isinstance(config_schema, dict):
        return None
    secret_keys = {
        key
        for key, spec in config_schema.items()
        if isinstance(spec, dict) and spec.get("type") == "password"
    }
    if not secret_keys:
        return config
    return {k: v for k, v in config.items() if k not in secret_keys}


def _merge_plugin_info(
    manifest: dict, db_row: PluginConfig | None, is_admin: bool
) -> dict:
    """Merge filesystem manifest with DB state into a PluginInfo-compatible dict."""
    config = None

    # The schema is static - it is declared in plugin.json - so it comes from the
    # manifest, and the DB row only holds the saved VALUES. Reading the schema
    # from the DB meant a plugin that was dropped in by hand (never through the
    # install flow, so no DB row) showed no config gear at all, and its settings
    # - the GitHub token a catalogue sync needs - were unreachable.
    config_schema = manifest.get("config_schema")

    if db_row:
        if db_row.config_json:
            try:
                config = json.loads(db_row.config_json)
            except json.JSONDecodeError:
                config = None
        if config_schema is None and db_row.config_schema_json:
            try:
                config_schema = json.loads(db_row.config_schema_json)
            except json.JSONDecodeError:
                config_schema = None

    config = _redact_config(config, config_schema, is_admin)

    return {
        "plugin_id": manifest.get("id", ""),
        "name": manifest.get("name", ""),
        "version": manifest.get("version", "0.0.0"),
        "author": manifest.get("author", ""),
        "description": manifest.get("description"),
        "plugin_type": manifest.get("type", "library"),
        "enabled": db_row.enabled if db_row else True,
        "has_logo": manifest.get("has_logo", False),
        "installed_at": db_row.created_at if db_row else None,
        "config": config,
        "config_schema": config_schema,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@protected_route(
    plugins_router.get, "", scopes=[Scope.PLUGINS_READ], response_model=list[PluginInfo]
)
async def list_plugins(request: Request) -> list[dict]:
    """List all installed plugins (filesystem scan merged with DB state)."""
    is_admin = Scope.PLUGINS_WRITE in getattr(request.state, "scopes", set())
    manifests = list_installed_plugins()

    # Bulk-load DB rows
    plugin_ids = [m["id"] for m in manifests]
    db_map: dict[str, PluginConfig] = {}
    if plugin_ids:
        async with async_session_factory() as session:
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id.in_(plugin_ids))
            )
            for row in result.scalars().all():
                db_map[row.plugin_id] = row

    return [_merge_plugin_info(m, db_map.get(m["id"]), is_admin) for m in manifests]


@protected_route(plugins_router.post, "/install", scopes=[Scope.PLUGINS_WRITE])
async def install_plugin(request: Request, file: UploadFile) -> dict:
    """Upload and install a plugin from a ZIP file."""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="File must be a .zip archive")

    # Write upload to a temp file
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        manifest = await install_plugin_from_zip(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)

    # Save/update DB record
    plugin_id = manifest["id"]
    await _upsert_db_config(plugin_id, manifest, enabled=True)

    # Load the plugin into the runtime
    try:
        plugin_manager.load_single(plugin_id)
    except Exception:
        logger.exception("Plugin '%s' installed but failed to load", plugin_id)

    return {"ok": True, "plugin_id": plugin_id, "name": manifest.get("name", "")}


@protected_route(
    plugins_router.post, "/{plugin_id}/enable", scopes=[Scope.PLUGINS_WRITE]
)
async def enable_plugin(request: Request, plugin_id: str) -> dict:
    """Enable a plugin and load it into the runtime."""
    # Read manifest from filesystem
    plugin_dir = Path(PLUGINS_PATH) / plugin_id
    manifest = read_manifest(plugin_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Plugin not found on disk")

    await _upsert_db_config(plugin_id, manifest, enabled=True)

    try:
        plugin_manager.load_single(plugin_id)
    except Exception:
        logger.exception("Failed to load plugin '%s'", plugin_id)

    return {"ok": True}


@protected_route(
    plugins_router.post, "/{plugin_id}/disable", scopes=[Scope.PLUGINS_WRITE]
)
async def disable_plugin(request: Request, plugin_id: str) -> dict:
    """Disable a plugin and unload it from the runtime."""
    plugin_dir = Path(PLUGINS_PATH) / plugin_id
    manifest = read_manifest(plugin_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Plugin not found on disk")

    await _upsert_db_config(plugin_id, manifest, enabled=False)

    try:
        plugin_manager.unload_single(plugin_id)
    except Exception:
        logger.exception("Failed to unload plugin '%s'", plugin_id)

    return {"ok": True}


@protected_route(
    plugins_router.delete, "/{plugin_id}", scopes=[Scope.PLUGINS_WRITE]
)
async def delete_plugin(request: Request, plugin_id: str) -> dict:
    """Uninstall a plugin - remove files, DB record, and any storefront it owned."""
    from handler.library.catalog_sync_handler import (
        catalog_ids_for_plugin,
        remove_catalog_store,
        remove_catalog_stores_for_plugin,
    )
    # A store records which plugin owns it, so the catalogue id off the live
    # instance is only a fallback - for a store made before that column and not
    # yet backfilled, while the plugin is loaded here to read it.
    catalog_ids = catalog_ids_for_plugin(plugin_id)

    # Unload from runtime first
    try:
        plugin_manager.unload_single(plugin_id)
    except Exception:
        pass

    # Remove files
    removed = await uninstall_plugin(plugin_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Plugin not found")

    # Remove DB record
    await _delete_db_config(plugin_id)

    # A storefront the plugin registered comes and goes with the plugin. Remove
    # it now so it does not linger in the navigation - by owner first (this works
    # even if the plugin was disabled, so never loaded this run), then by any
    # catalogue id we did read as a fallback. Downloaded games stay in Games.
    try:
        await remove_catalog_stores_for_plugin(plugin_id)
    except Exception:
        logger.exception(
            "Failed to remove catalogue store(s) for %s on uninstall", plugin_id,
        )
    for cid in catalog_ids:
        try:
            await remove_catalog_store(cid)
        except Exception:
            logger.exception(
                "Failed to remove catalogue store %s on uninstall of %s",
                cid, plugin_id,
            )

    return {"ok": True}


@protected_route(
    plugins_router.get, "/{plugin_id}/config", scopes=[Scope.PLUGINS_READ]
)
async def get_plugin_config(request: Request, plugin_id: str) -> dict:
    """Get plugin configuration from DB."""
    db_row = await _get_db_config(plugin_id)
    if db_row is None:
        raise HTTPException(status_code=404, detail="Plugin not found in database")

    config = None
    config_schema = None
    if db_row.config_json:
        try:
            config = json.loads(db_row.config_json)
        except json.JSONDecodeError:
            config = None
    if db_row.config_schema_json:
        try:
            config_schema = json.loads(db_row.config_schema_json)
        except json.JSONDecodeError:
            config_schema = None

    is_admin = Scope.PLUGINS_WRITE in getattr(request.state, "scopes", set())
    config = _redact_config(config, config_schema, is_admin)

    return {
        "plugin_id": db_row.plugin_id,
        "config": config,
        "config_schema": config_schema,
    }


@protected_route(
    plugins_router.put, "/{plugin_id}/config", scopes=[Scope.PLUGINS_WRITE]
)
async def update_plugin_config(
    request: Request, plugin_id: str
) -> dict:
    """Update plugin configuration in DB."""
    body = await request.json()
    # Accept config directly as root object: {"enabled": true, "search_engine": "bing"}
    # or wrapped: {"config": {"enabled": true}}
    config_data = body.get("config", body) if isinstance(body, dict) else body
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(PluginConfig).where(PluginConfig.plugin_id == plugin_id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise HTTPException(
                    status_code=404, detail="Plugin not found in database"
                )
            row.config_json = json.dumps(config_data)

    return {"ok": True}


@plugins_router.get("/{plugin_id}/logo")
async def get_plugin_logo(plugin_id: str) -> FileResponse:
    """Serve plugin logo file (PNG or SVG)."""
    # Security: prevent path traversal
    if "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
        raise HTTPException(status_code=400, detail="Invalid plugin ID")

    plugin_dir = Path(PLUGINS_PATH) / plugin_id

    png = plugin_dir / "logo.png"
    if png.exists():
        return FileResponse(
            png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
        )

    svg = plugin_dir / "logo.svg"
    if svg.exists():
        return FileResponse(
            svg,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    raise HTTPException(status_code=404, detail="Logo not found")


@plugins_router.get("/{plugin_id}/assets/{file_path:path}")
async def get_plugin_asset(plugin_id: str, file_path: str) -> FileResponse:
    """Serve static asset files from a plugin's assets/ directory.

    Theme plugins use this to serve artwork, icons, metadata XML etc.
    Only files inside the plugin's assets/ subdirectory are served.
    """
    # Security: prevent path traversal
    if "/" in plugin_id or "\\" in plugin_id or ".." in plugin_id:
        raise HTTPException(status_code=400, detail="Invalid plugin ID")
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    asset_dir = Path(PLUGINS_PATH) / plugin_id / "assets"
    target = (asset_dir / file_path).resolve()

    # Ensure resolved path is inside assets dir
    try:
        target.relative_to(asset_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    # Determine media type from extension
    ext = target.suffix.lower()
    media_types = {
        ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
        ".svg": "image/svg+xml", ".xml": "application/xml", ".json": "application/json",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        target, media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── Plugin Store ─────────────────────────────────────────────────────────────

from models.plugin_config import PluginStoreSource
from utils.async_utils import fire_task


@protected_route(plugins_router.get, "/store/sources", scopes=[Scope.PLUGINS_READ])
async def list_store_sources(request: Request) -> list[dict]:
    """List all configured store sources."""
    async with async_session_factory() as session:
        result = await session.execute(select(PluginStoreSource))
        rows = result.scalars().all()
        return [{"id": r.id, "name": r.name, "url": r.url, "enabled": r.enabled} for r in rows]


@protected_route(plugins_router.post, "/store/sources", scopes=[Scope.PLUGINS_WRITE])
async def add_store_source(request: Request) -> dict:
    """Add a new store source URL."""
    body = await request.json()
    url = (body.get("url") or "").strip()
    name = (body.get("name") or "").strip() or url.split("/")[-2] if "/" in url else "Store"
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    async with async_session_factory() as session:
        async with session.begin():
            existing = await session.execute(
                select(PluginStoreSource).where(PluginStoreSource.url == url)
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="Source already exists")
            row = PluginStoreSource(name=name, url=url, enabled=True)
            session.add(row)
    return {"ok": True}


@protected_route(plugins_router.delete, "/store/sources/{source_id}", scopes=[Scope.PLUGINS_WRITE])
async def delete_store_source(request: Request, source_id: int) -> dict:
    """Remove a store source."""
    async with async_session_factory() as session:
        async with session.begin():
            result = await session.execute(
                select(PluginStoreSource).where(PluginStoreSource.id == source_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail="Source not found")
            await session.delete(row)
    return {"ok": True}


@protected_route(plugins_router.get, "/store/browse", scopes=[Scope.PLUGINS_READ])
async def browse_store(request: Request) -> dict:
    """Fetch and merge plugin listings from all enabled store sources."""
    import httpx

    async with async_session_factory() as session:
        result = await session.execute(
            select(PluginStoreSource).where(PluginStoreSource.enabled == True)
        )
        sources = result.scalars().all()

    # Get installed plugin versions for comparison
    installed = {m["id"]: m["version"] for m in list_installed_plugins()}

    all_plugins = []
    errors = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        for src in sources:
            try:
                r = await client.get(src.url)
                r.raise_for_status()
                data = r.json()
                for p in data.get("plugins", []):
                    p["_source"] = src.name
                    p["_sourceUrl"] = src.url
                    pid = p.get("id", "")
                    if pid in installed:
                        p["installed"] = True
                        p["installedVersion"] = installed[pid]
                        p["updateAvailable"] = _version_gt(p.get("version", "0"), installed[pid])
                    else:
                        p["installed"] = False
                        p["installedVersion"] = None
                        p["updateAvailable"] = False
                    all_plugins.append(p)
            except Exception as exc:
                errors.append({"source": src.name, "error": str(exc)})
                logger.warning("Failed to fetch store %s: %s", src.url, exc)

    return {"plugins": all_plugins, "errors": errors, "gd_version": GD_VERSION}


@protected_route(plugins_router.get, "/store/updates", scopes=[Scope.PLUGINS_READ])
async def check_store_updates(request: Request) -> dict:
    """Quick check: how many plugin updates are available?

    Lightweight alternative to /store/browse - returns only update info.
    Result is cached in-memory for 5 minutes to avoid hammering store sources.
    """
    import httpx, time

    now = time.time()
    cache = getattr(check_store_updates, "_cache", None)
    if cache and now - cache["ts"] < 300:
        return cache["data"]

    installed = {m["id"]: m.get("version", "0") for m in list_installed_plugins()}
    if not installed:
        result = {"count": 0, "updates": []}
        check_store_updates._cache = {"ts": now, "data": result}
        return result

    async with async_session_factory() as session:
        rows = await session.execute(
            select(PluginStoreSource).where(PluginStoreSource.enabled == True)
        )
        sources = rows.scalars().all()

    updates = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as c:
        for src in sources:
            try:
                r = await c.get(src.url)
                r.raise_for_status()
                for p in r.json().get("plugins", []):
                    pid = p.get("id", "")
                    if pid in installed and _version_gt(p.get("version", "0"), installed[pid]):
                        updates.append({
                            "id": pid,
                            "name": p.get("name", pid),
                            "installed": installed[pid],
                            "available": p.get("version", "?"),
                        })
            except Exception:
                pass

    result = {"count": len(updates), "updates": updates}
    check_store_updates._cache = {"ts": now, "data": result}
    return result


def _version_gt(a: str, b: str) -> bool:
    """Simple semver comparison: is version a > b?"""
    try:
        va = [int(x) for x in a.split(".")]
        vb = [int(x) for x in b.split(".")]
        return va > vb
    except (ValueError, AttributeError):
        return False


_ICON_MAX_BYTES = 2 * 1024 * 1024


async def store_icon_hosts() -> set[str]:
    """Hosts whose icons this server will proxy.

    GitHub plus every enabled store source, read from the same table
    `browse_store` reads. It used to consult a config key named
    "plugin_store_sources" that nothing anywhere ever writes, so the set was
    always just GitHub: a self-hosted store installed fine (that path reads the
    table) while every one of its icons came back 400.
    """
    from urllib.parse import urlparse

    hosts = {"github.com", "raw.githubusercontent.com", "objects.githubusercontent.com"}
    async with async_session_factory() as session:
        result = await session.execute(
            select(PluginStoreSource).where(PluginStoreSource.enabled == True)  # noqa: E712
        )
        for src in result.scalars().all():
            h = (urlparse(src.url).hostname or "").lower()
            if h:
                hosts.add(h)
    return hosts


@plugins_router.get("/store/icon")
async def proxy_store_icon(url: str = Query(..., description="Remote icon URL")):
    """Proxy a remote plugin icon to avoid CORS issues.

    Unauthenticated on purpose, for the same reason the theme CSS/JS routes
    below are: the store list renders these through <img src=...>, which cannot
    carry a bearer token. What keeps an open route cheap is that it fetches
    only an image, only from a host the admin registered as a store source,
    only without redirects, and only up to two megabytes counted as the body
    arrives - the size test used to run against an already-buffered response,
    so a highly compressible file cost the caller almost nothing and the server
    its full decompressed size in memory.
    """
    import asyncio
    from urllib.parse import urlparse

    import httpx
    from starlette.responses import Response

    from utils.http import MediaTooLarge, read_capped
    from utils.net_guard import UnsafeURLError, assert_fetch_allowed

    if not url.startswith("https://") and not url.startswith("http://"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")

    if hostname not in await store_icon_hosts():
        raise HTTPException(status_code=400, detail="Icon host not in store sources allowlist")

    # A store may legitimately live on the operator's LAN, so RFC-1918 is
    # allowed here - loopback, link-local and the cloud metadata address are
    # not. Resolution is a blocking syscall and this route is public, so it
    # does not run on the event loop.
    try:
        await asyncio.to_thread(assert_fetch_allowed, url, allow_private_lan=True)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as c:
            async with c.stream("GET", url) as r:
                if r.is_redirect:
                    raise HTTPException(status_code=400, detail="Redirects not allowed")
                if r.status_code != 200:
                    raise HTTPException(status_code=404, detail="Icon not found")
                ct = r.headers.get("content-type", "").split(";")[0].strip()
                if not ct.startswith("image/") and not ct.startswith("text/xml"):
                    raise HTTPException(status_code=400, detail="Only image content types allowed")
                try:
                    body = await read_capped(r, _ICON_MAX_BYTES, what="icon")
                except MediaTooLarge:
                    raise HTTPException(status_code=400, detail="Icon too large (max 2 MB)")
            return Response(
                content=body, media_type=ct,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Icon not found")


@protected_route(plugins_router.post, "/store/install", scopes=[Scope.PLUGINS_WRITE])
async def install_from_store(request: Request) -> dict:
    """Download and install a plugin from its store download URL."""
    from handler.plugins.install_handler import install_plugin_from_url

    body = await request.json()
    download_url = (body.get("downloadUrl") or "").strip()
    if not download_url:
        raise HTTPException(status_code=400, detail="downloadUrl is required")

    # Only install from GitHub or a configured store-source host. Without this,
    # an attacker-supplied downloadUrl points install_plugin_from_url (which runs
    # pip on the package) at any server, turning this into arbitrary-URL RCE.
    # Allowlisted hosts skip an IP check, so a LAN-hosted store (e.g. a local
    # gitea) keeps working.
    from urllib.parse import urlparse
    dl_host = (urlparse(download_url).hostname or "").lower()
    if urlparse(download_url).scheme not in ("http", "https") or not dl_host:
        raise HTTPException(status_code=400, detail="Invalid download URL")
    allowed_hosts = {"github.com", "raw.githubusercontent.com",
                     "objects.githubusercontent.com", "codeload.github.com"}
    async with async_session_factory() as session:
        result = await session.execute(select(PluginStoreSource))
        for src in result.scalars().all():
            h = (urlparse(src.url).hostname or "").lower()
            if h:
                allowed_hosts.add(h)
    if dl_host not in allowed_hosts:
        raise HTTPException(
            status_code=400,
            detail=f"Refusing to install from '{dl_host}': not a configured store source",
        )

    try:
        manifest = await install_plugin_from_url(download_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    # Upsert DB config
    plugin_id = manifest["id"]
    await _upsert_db_config(plugin_id, manifest, enabled=True)

    # Load into runtime
    try:
        plugin_manager.load_single(plugin_id)
    except Exception as exc:
        logger.warning("Plugin %s installed but failed to load: %s", plugin_id, exc)

    # This route is PLUGINS_WRITE (admin-only), so the installer always sees the
    # full config - is_admin=True. _merge_plugin_info now requires the flag.
    return {"ok": True, "plugin": _merge_plugin_info(manifest, await _get_db_config(plugin_id), True)}


# ── Frontend theme/CSS hooks ─────────────────────────────────────────────────
# These are public because <link> and <script> tags cannot send Bearer tokens.
# Security: only admin can INSTALL plugins; serving admin-approved CSS/JS is safe.


@plugins_router.get("/frontend/css")
async def get_plugin_css():
    """Concatenate CSS from all enabled theme plugins."""
    from starlette.responses import Response

    css_parts = plugin_manager.hook.frontend_get_css()
    css = "\n".join(c for c in css_parts if c)
    return Response(
        content=css,
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=300"},
    )


@plugins_router.get("/frontend/themes")
async def get_plugin_themes() -> list:
    """Return theme definitions from all enabled theme plugins."""
    themes = plugin_manager.hook.frontend_get_theme()
    return [t for t in themes if t]


@plugins_router.get("/frontend/routes")
async def get_plugin_routes() -> list:
    """Custom nav routes declared by enabled plugins (frontend_get_routes hook).

    Each entry is {path, label, icon}. `path` is namespaced under /x/ in the SPA
    so it cannot collide with a core route. The plugin's injected JS supplies the
    page CONTENT by calling window.__GD__.registerRoute({ path, mount }).
    """
    out: list[dict] = []
    try:
        for parts in plugin_manager.hook.frontend_get_routes():
            for r in (parts or []):
                if isinstance(r, dict) and r.get("path"):
                    out.append({
                        "path": str(r["path"]).lstrip("/"),
                        "label": r.get("label", ""),
                        "icon": r.get("icon", ""),
                    })
    except Exception:
        logger.warning("frontend_get_routes aggregation failed")
    return out


@plugins_router.get("/dashboard/cards")
async def get_dashboard_cards() -> list:
    """Aggregate dashboard widget cards declared by plugins (widget_get_cards hook).

    Each card is a small data tile: {id, title, value?, subtitle?, icon?, link?}.
    Rendered by the core Dashboard page. `link` may be an internal route
    (e.g. /x/<pluginpath>) the card navigates to on click.
    """
    out: list[dict] = []
    try:
        for parts in plugin_manager.hook.widget_get_cards():
            for c in (parts or []):
                if isinstance(c, dict) and (c.get("title") or c.get("id")):
                    out.append({
                        "id": str(c.get("id") or c.get("title")),
                        "title": c.get("title", ""),
                        "value": c.get("value"),
                        "subtitle": c.get("subtitle", ""),
                        "icon": c.get("icon", ""),
                        "link": c.get("link", ""),
                    })
    except Exception:
        logger.warning("widget_get_cards aggregation failed")
    return out


# ── Plugin download providers (download_provider_* hooks) ─────────────────────

def _instance_by(id_attr: str, value: str):
    """Find a registered plugin instance whose <id_attr>() returns `value`."""
    for inst in plugin_manager.get_plugin_instances():
        fn = getattr(inst, id_attr, None)
        try:
            if callable(fn) and fn() == value:
                return inst
        except Exception:
            continue
    return None


@protected_route(plugins_router.get, "/download/providers", scopes=[Scope.LIBRARY_READ])
async def list_download_providers(request: Request, game_id: str | None = Query(None)) -> list:
    """Plugin-provided download sources (download_provider_id/name). With game_id,
    also reports which can handle it (download_can_handle)."""
    out: list[dict] = []
    for inst in plugin_manager.get_plugin_instances():
        pid_fn = getattr(inst, "download_provider_id", None)
        if not callable(pid_fn):
            continue
        try:
            pid = pid_fn()
        except Exception:
            continue
        if not pid:
            continue
        name_fn = getattr(inst, "download_provider_name", None)
        can = None
        if game_id is not None:
            ch = getattr(inst, "download_can_handle", None)
            try:
                can = bool(ch(game_id)) if callable(ch) else None
            except Exception:
                can = None
        out.append({"id": pid, "name": (name_fn() if callable(name_fn) else pid), "can_handle": can})
    return out


class _PluginDownloadStart(BaseModel):
    game_id: str
    destination: str | None = None


@protected_route(plugins_router.post, "/download/providers/{provider_id}/start", scopes=[Scope.LIBRARY_ADMIN])
async def start_plugin_download(request: Request, provider_id: str, body: _PluginDownloadStart) -> dict:
    """Start a download through a plugin download provider (download_start)."""
    inst = _instance_by("download_provider_id", provider_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Download provider not found")
    fn = getattr(inst, "download_start", None)
    if not callable(fn):
        raise HTTPException(status_code=400, detail="Provider cannot start downloads")
    try:
        return dict(fn(body.game_id, body.destination or "") or {})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")


@protected_route(plugins_router.get, "/download/providers/{provider_id}/status/{task_id}", scopes=[Scope.LIBRARY_READ])
async def plugin_download_status(request: Request, provider_id: str, task_id: str) -> dict:
    """Progress of a plugin-provider download (download_get_status)."""
    inst = _instance_by("download_provider_id", provider_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Download provider not found")
    fn = getattr(inst, "download_get_status", None)
    if not callable(fn):
        raise HTTPException(status_code=400, detail="Provider has no status")
    try:
        return dict(fn(task_id) or {})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Provider error: {e}")


# ── Plugin library sources (library_source_* hooks) ──────────────────────────

@protected_route(plugins_router.get, "/library/sources", scopes=[Scope.LIBRARY_READ])
async def list_library_sources(request: Request) -> list:
    """Plugin-provided library sources (library_source_id/name)."""
    out: list[dict] = []
    for inst in plugin_manager.get_plugin_instances():
        sid_fn = getattr(inst, "library_source_id", None)
        if not callable(sid_fn):
            continue
        try:
            sid = sid_fn()
        except Exception:
            continue
        if not sid:
            continue
        name_fn = getattr(inst, "library_source_name", None)
        out.append({"id": sid, "name": (name_fn() if callable(name_fn) else sid)})
    return out


class _LibrarySourceScan(BaseModel):
    path: str


@protected_route(plugins_router.post, "/library/sources/{source_id}/scan", scopes=[Scope.LIBRARY_ADMIN])
async def scan_library_source(request: Request, source_id: str, body: _LibrarySourceScan) -> dict:
    """Scan a path through a plugin library source (library_scan) and return the
    discovered games/ROMs. Adoption into the library is left to the caller."""
    inst = _instance_by("library_source_id", source_id)
    if not inst:
        raise HTTPException(status_code=404, detail="Library source not found")
    fn = getattr(inst, "library_scan", None)
    if not callable(fn):
        raise HTTPException(status_code=400, detail="Source cannot scan")
    try:
        discovered = fn(body.path) or []
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Source error: {e}")
    return {"discovered": list(discovered)}


# ── Plugin catalogues (library_catalog_* hooks) ──────────────────────────────
# Unlike a library source, a catalogue IS adopted here: core creates the rows,
# fetches the artwork through the SSRF guard and stores it locally. The plugin
# only describes what is on offer.

@protected_route(plugins_router.get, "/library/catalogs", scopes=[Scope.LIBRARY_READ])
async def list_library_catalogs(request: Request) -> list:
    """Catalogues offered by loaded plugins (library_catalog_id/name)."""
    return list_catalogs()


class _CatalogSync(BaseModel):
    # Kept for backward compatibility and ignored: the catalogue owns its store
    # library now, created on first sync, so the caller does not name one.
    library_slug: str | None = None


@protected_route(plugins_router.post, "/library/catalogs/{catalog_id}/sync",
                 scopes=[Scope.LIBRARY_ADMIN])
async def sync_library_catalog(request: Request, catalog_id: str, body: _CatalogSync | None = None) -> dict:
    """Fetch a plugin catalogue into its store library, and report what happened.

    Slow by nature - it is one network round trip per entry on the plugin's side
    - so callers should treat it as a job, not a click that returns instantly.
    """
    try:
        return await sync_catalog(catalog_id)
    except SyncInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Catalogue sync failed for %s", catalog_id)
        raise HTTPException(status_code=502, detail=f"Catalogue error: {e}")


@protected_route(plugins_router.post, "/library/catalogs/{catalog_id}/clear-metadata",
                 scopes=[Scope.LIBRARY_ADMIN])
async def clear_catalog_metadata(request: Request, catalog_id: str) -> dict:
    """Wipe every listing's scraped metadata in one store, the store-side twin of
    the GOG library's 'clear all metadata'.

    Clears exactly what the metadata pass derives - the same set a single-entry
    correction clears - and reopens each row for the next pass. The catalogue's
    own facts (title, subtitle, category, the offered builds) are the plugin's,
    not the scrape's, so they stay. Downloaded games live in the Games library,
    a different library, and are left alone; a re-scrape here pushes fresh data
    onto them the usual way.
    """
    from handler.library.catalog_meta_handler import _clear_scraped_fields
    from models.catalog_entry import CatalogEntry

    async with async_session_factory() as s:
        async with s.begin():
            rows = (await s.execute(
                select(CatalogEntry).where(CatalogEntry.catalog_id == catalog_id)
            )).scalars().all()
            for r in rows:
                _clear_scraped_fields(r)
                r.meta_scraped_at = None
                r.meta_source = None
                r.meta_matched_title = None
                r.meta_confidence = None
    return {"cleared": len(rows)}


async def _user_can_browse_catalog(request: Request, catalog_id: str) -> bool:
    """Whether the requester may see a catalogue, by its store's visibility.

    The store library a catalogue lives in is created restricted - admin-only
    until an admin opens it - and the Games listing already hides a restricted
    library from anyone not allowlisted. The catalogue's own read and download
    routes have to honour the same rule, or the shelf is private while the
    catalogue behind it is not. Admins bypass. No store row yet (before the first
    sync) leaves nothing to gate.
    """
    from handler.database.library_registry_handler import library_registry_handler
    from models.library import Library

    user = getattr(request.state, "user", None)
    async with async_session_factory() as session:
        store = (await session.execute(
            select(Library).where(
                Library.catalog_id == catalog_id, Library.is_store.is_(True)
            )
        )).scalars().first()
    if store is None:
        return True
    return await library_registry_handler.user_can_access(user, store)


@protected_route(plugins_router.get, "/library/catalogs/{catalog_id}/entries",
                 scopes=[Scope.LIBRARY_READ])
async def list_catalog_entries(request: Request, catalog_id: str) -> list:
    """Everything the last sync recorded, including what it could not offer."""
    # A restricted store returns empty here just as its library listing does.
    if not await _user_can_browse_catalog(request, catalog_id):
        return []
    return await list_entries(catalog_id)


@protected_route(plugins_router.get, "/library/catalogs/{catalog_id}/entries/count",
                 scopes=[Scope.LIBRARY_READ])
async def count_catalog_entries(request: Request, catalog_id: str) -> dict:
    """Just how many entries a store holds, for a card that only shows the number.

    The home page was pulling the whole catalogue - every entry's description,
    screenshots and assets - only to read its length. This returns the count
    alone.
    """
    if not await _user_can_browse_catalog(request, catalog_id):
        return {"count": 0}
    return {"count": await count_entries(catalog_id)}


class _CatalogDownload(BaseModel):
    # Omitted means every build this entry offers. Naming them is how a caller
    # takes just the Windows one instead of all four platforms.
    assets: list[str] | None = None


@protected_route(plugins_router.get, "/library/catalog-entries/{entry_id}",
                 scopes=[Scope.LIBRARY_READ])
async def get_catalog_entry(request: Request, entry_id: int) -> dict:
    """One catalogue entry, dressed for the storefront detail page.

    The detail view (GOG-style) reads this: the scraped presentation for the
    hero and facts, the builds on offer, and library_game_id so a downloaded
    listing can link straight to its game in the Games library.
    """
    from config import GAMES_PATH
    from endpoints.library.upload_router import _sanitize
    from models.library import Library
    from models.library_game import LibraryGame
    import os as _os

    row = await get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    # A restricted store hides its entries from anyone not allowlisted, the same
    # 404 the library detail gives - the catalogue detail is not a way around it.
    if not await _user_can_browse_catalog(request, row.catalog_id):
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    # Where a download would land, so the picker can show it the way the GOG
    # dialog shows its save location instead of leaving it a mystery. It goes
    # through the same sanitiser the download itself uses: a title with a colon
    # or an accent in it lands in a folder that does not spell the title, and a
    # save location that names a directory the server never creates is worse
    # than none at all.
    async with async_session_factory() as session:
        downloaded = await downloaded_entry_game_ids(session, [row])
        store = (await session.execute(
            select(Library).where(
                Library.catalog_id == row.catalog_id, Library.is_store.is_(True)
            )
        )).scalars().first()
        # Once downloaded, the folder follows the game's title, not the entry's.
        # The two part company when the listing is renamed after the fact, and
        # the next build goes where the game already is.
        title = row.title
        if row.library_game_id:
            game_title = (await session.execute(
                select(LibraryGame.title).where(LibraryGame.id == row.library_game_id)
            )).scalars().first()
            if game_title:
                title = game_title
    data = entry_to_dict(row, downloaded)
    # save_root is an absolute server path, and only whoever can download needs
    # it (the picker shows where files will land). Withhold it from a plain
    # reader, who has no download action and no reason to see the disk layout.
    if Scope.LIBRARY_UPLOAD in getattr(request.state, "scopes", set()):
        folder = (store.storage_folder if store and store.storage_folder else "CUSTOM")
        data["save_root"] = _os.path.join(GAMES_PATH, folder, _sanitize(title)).replace("\\", "/")
    return data


@protected_route(plugins_router.post, "/library/catalog-entries/{entry_id}/download",
                 scopes=[Scope.LIBRARY_UPLOAD])
async def download_catalog_entry(request: Request, entry_id: int, body: _CatalogDownload) -> dict:
    """Pull an entry's builds onto the server, one download job per build."""
    from endpoints.library.upload_router import _max_upload_bytes
    user = getattr(request.state, "user", None)
    # A restricted store is admin-only until opened: an uploader who is not on it
    # must not download from it, matching what its library listing already allows.
    row = await get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    if not await _user_can_browse_catalog(request, row.catalog_id):
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    try:
        return await queue_entry_downloads(
            entry_id, body.assets,
            actor=(user.username if user else None),
            max_bytes=await _max_upload_bytes(user),
        )
    except DownloadInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class _CatalogScrape(BaseModel):
    # A catalogue of hundreds is hundreds of third-party calls; one run is
    # bounded so an admin can see it work without waiting for all of it.
    limit: int | None = None
    # False re-scrapes entries a previous run already looked at. On by default
    # because the common case is filling in what is still blank.
    only_missing: bool = True


@protected_route(plugins_router.post, "/library/catalogs/{catalog_id}/scrape-metadata",
                 scopes=[Scope.LIBRARY_ADMIN])
async def scrape_catalog_metadata(request: Request, catalog_id: str, body: _CatalogScrape) -> dict:
    """Match this catalogue's entries to real games and fill in their metadata.

    Separate from sync on purpose: it is two rate-limited searches per entry, so
    it is a job to be started and left, not part of the reconcile. Resumable -
    a second run picks up where a timeout left off.
    """
    try:
        return await scrape_catalog(
            catalog_id, limit=body.limit, only_missing=body.only_missing,
        )
    except MetaScrapeInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Catalogue metadata pass failed for %s", catalog_id)
        raise HTTPException(status_code=502, detail=f"Metadata error: {e}")


@protected_route(plugins_router.post, "/library/catalog-entries/{entry_id}/scrape-metadata",
                 scopes=[Scope.LIBRARY_ADMIN])
async def scrape_one_entry(request: Request, entry_id: int) -> dict:
    """Re-run the metadata match for a single entry.

    The escape hatch for a wrong guess: fix the search term, then re-scrape just
    this one instead of the whole catalogue.
    """
    from handler.database.session import async_session_factory
    from models.catalog_entry import CatalogEntry

    async with async_session_factory() as s:
        row = (await s.execute(
            select(CatalogEntry).where(CatalogEntry.id == entry_id)
        )).scalars().first()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
        catalog_id = row.catalog_id
    try:
        # A single-entry re-scrape is an explicit redo, so it clears what the
        # last match wrote and derives fresh - not a blank-filling top-up.
        return await scrape_catalog(
            catalog_id, only_missing=False, entry_ids=[entry_id], force_refresh=True,
        )
    except MetaScrapeInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class _SearchTerm(BaseModel):
    # None clears the override and lets the parsed title drive the search again.
    term: str | None = None


@protected_route(plugins_router.put, "/library/catalog-entries/{entry_id}/search-term",
                 scopes=[Scope.LIBRARY_ADMIN])
async def set_entry_search_term(request: Request, entry_id: int, body: _SearchTerm) -> dict:
    """Give one entry its own search phrase for the next metadata pass.

    For the entries no database lists under the name the catalogue used. Setting
    it also clears the entry's scraped mark, so the next pass acts on the new
    phrase rather than skipping the entry as already done.
    """
    try:
        await set_search_term(entry_id, body.term)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "entry_id": entry_id, "term": body.term}


# ── Catalogue entry editor (the GOG-style Edit Metadata panel) ───────────────
# A catalogue entry is not a game, so the library game's edit endpoints do not
# fit it. These three mirror what that panel needs - save fields, search art,
# search sources - pointed at the catalog_entries row instead, so the panel can
# be reused as-is with apiPrefix "/plugins/library/catalog-entries".

# Only these columns are an admin's to set from the editor; the sync owns the
# rest (external_id, assets, availability, the meta_* match record).
_CATALOG_EDIT_STR = {
    "title", "subtitle", "description", "developer", "publisher",
    "release_date", "category",
}
_CATALOG_EDIT_JSON = {"genres", "meta_ratings", "languages", "requirements"}
_CATALOG_EDIT_NUM = {"rating", "hltb_main_s", "hltb_complete_s"}
_CATALOG_ART = {
    "cover_path": "entry", "background_path": "hero", "logo_path": "logo",
    "icon_path": "icon",
}
_CATALOG_COVER_DIR = "catalog-covers"


def _is_external_url(v) -> bool:
    return isinstance(v, str) and v.startswith(("http://", "https://"))


def _needs_fetch(v) -> bool:
    """Values the editor hands back that must be downloaded to local storage: an
    external http(s) URL, or a /api/media/proxy token for a picked ScreenScraper
    image (store_catalog_media resolves the token to the real credentialed URL
    server-side). A value already local (a /resources path) is left as-is, and
    must never be re-fetched - and a proxy token must never be persisted, since
    it would serve the credentialed URL live on every page load."""
    from utils.media_proxy import PROXY_PREFIX
    return _is_external_url(v) or (isinstance(v, str) and v.startswith(PROXY_PREFIX))


@protected_route(plugins_router.patch, "/library/catalog-entries/{entry_id}",
                 scopes=[Scope.LIBRARY_ADMIN])
async def update_catalog_entry(request: Request, entry_id: int, body: dict) -> dict:
    """Save an admin's edits to one catalogue entry.

    External artwork URLs the editor hands back are downloaded to local storage
    first (the house rule: no page hot-links a CDN), exactly as the library game
    editor does, so a picked cover ends up served locally like a scraped one.
    """
    from models.catalog_entry import CatalogEntry

    async with async_session_factory() as session:
        async with session.begin():
            row = (await session.execute(
                select(CatalogEntry).where(CatalogEntry.id == entry_id)
            )).scalars().first()
            if row is None:
                raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")

            data = dict(body or {})
            # The panel names art as *_url; the entry stores *_path. Map, then
            # download anything external so it is served locally.
            for path_field, stem in _CATALOG_ART.items():
                url_field = path_field.replace("_path", "_url")
                val = data.pop(url_field, data.get(path_field, ...))
                if val is ...:
                    continue
                data.pop(path_field, None)
                if val and _needs_fetch(val):
                    stored = await store_catalog_media(
                        _CATALOG_COVER_DIR, f"{stem}-{entry_id}", val, max_bytes=8 * 1024 * 1024,
                    )
                    setattr(row, path_field, stored or getattr(row, path_field))
                else:
                    setattr(row, path_field, val or None)

            # Screenshots: a list mixing local paths (keep) and external URLs
            # (download). Anything already local stays put.
            if "screenshots" in data:
                shots = data.pop("screenshots") or []
                stored_shots = []
                for i, url in enumerate(shots if isinstance(shots, list) else []):
                    if _needs_fetch(url):
                        p = await store_catalog_media(
                            _CATALOG_COVER_DIR, f"shot-{entry_id}-{i}", url,
                            max_bytes=8 * 1024 * 1024,
                        )
                        if p:
                            stored_shots.append(p)
                    elif isinstance(url, str) and url:
                        stored_shots.append(url)
                row.screenshots = stored_shots or None

            for field, value in data.items():
                if field in _CATALOG_EDIT_STR:
                    setattr(row, field, (str(value).strip() or None) if value is not None else None)
                elif field in _CATALOG_EDIT_JSON:
                    setattr(row, field, value or None)
                elif field in _CATALOG_EDIT_NUM:
                    setattr(row, field, value if value not in ("", None) else None)

            # The store is the source: an edit here is what the game shows too,
            # once this listing has been downloaded. Inside the transaction, so
            # a failed push takes the edit down with it rather than leaving the
            # two halves disagreeing.
            from handler.library.catalog_sync_handler import push_entry_to_game
            await push_entry_to_game(session, row)

        await session.refresh(row)
        downloaded = await downloaded_entry_game_ids(session, [row])
        return entry_to_dict(row, downloaded)


@protected_route(plugins_router.get, "/library/catalog-entries/{entry_id}/covers",
                 scopes=[Scope.LIBRARY_ADMIN])
async def catalog_entry_covers(
    request: Request, entry_id: int,
    source: str = Query(default="steamgriddb"),
    q: str = Query(default=""),
    asset_type: str = Query(default="grids"),
    animated: str = Query(default="any"),
) -> list:
    """Cover/hero/logo/icon options for the entry's title, for the editor's art tabs."""
    from handler.metadata.external_art import search_cover_options

    row = await get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    term = q or row.meta_matched_title or row.title
    return await search_cover_options(source, term, asset_type, animated, gog_game_id=None)


@protected_route(plugins_router.get, "/library/catalog-entries/{entry_id}/screenshots",
                 scopes=[Scope.LIBRARY_ADMIN])
async def catalog_entry_screenshots(
    request: Request, entry_id: int,
    source: str = Query(default="all"),
    q: str = Query(default=""),
) -> list:
    """Screenshot options for the entry's title, for the editor's Screenshots tab.

    The editor calls the same {prefix}/{id}/screenshots path a library game does;
    without this route it 404'd and the tab showed empty tiles. A listing is not
    a GOG game, so gog_game_id is None and the GOG branch searches by title.
    """
    from endpoints.library.library_router import search_screenshot_options

    row = await get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    term = q or row.meta_matched_title or row.title
    # Include ScreenScraper here (catalogue editor only): PC Ports are ports of
    # console games, which SS indexes well, and the catalogue save path resolves
    # the proxy tokens SS results use.
    return await search_screenshot_options(
        term, source, gog_game_id=None, include_screenscraper=True,
    )


@protected_route(plugins_router.get, "/library/catalog-entries/{entry_id}/meta-sources",
                 scopes=[Scope.LIBRARY_ADMIN])
async def catalog_entry_meta_sources(
    request: Request, entry_id: int,
    source: str = Query(default="rawg"),
    q: str = Query(default=""),
) -> dict:
    """Fetch metadata from an external source for the editor's search buttons."""
    from handler.metadata.meta_sources import fetch_meta_source

    row = await get_entry(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No catalogue entry {entry_id}")
    term = q or row.meta_matched_title or row.title
    return await fetch_meta_source(source, search_term=term, q=q, gog_id=None)


@plugins_router.get("/frontend/js")
async def get_plugin_js():
    """Concatenate JavaScript from all enabled theme plugins."""
    from starlette.responses import Response

    js_parts = plugin_manager.hook.frontend_get_js()
    js = "\n".join(j for j in js_parts if j)
    return Response(
        content=js,
        media_type="application/javascript",
        headers={"Cache-Control": "public, max-age=300"},
    )


@plugins_router.get("/frontend/i18n")
async def get_plugin_i18n():
    """Return merged i18n translations from all installed plugins.

    Each plugin can have an i18n.json file with format:
    { "en": { "nh.key": "value" }, "pl": { "nh.key": "wartosc" } }
    """
    import json as _json
    merged: dict[str, dict[str, str]] = {}
    plugins_dir = Path(PLUGINS_PATH)
    if not plugins_dir.exists():
        return merged
    for d in sorted(plugins_dir.iterdir()):
        if not d.is_dir():
            continue
        i18n_file = d / "i18n.json"
        if not i18n_file.exists():
            continue
        try:
            data = _json.loads(i18n_file.read_text(encoding="utf-8"))
            for lang, msgs in data.items():
                if not isinstance(msgs, dict):
                    continue
                if lang not in merged:
                    merged[lang] = {}
                merged[lang].update(msgs)
        except Exception as exc:
            logger.warning("Failed to load i18n.json from plugin %s: %s", d.name, exc)
    return merged


# ── Plugin metadata providers info ────────────────────────────────────────────


@protected_route(
    plugins_router.get, "/metadata/providers", scopes=[Scope.PLUGINS_READ]
)
async def plugin_metadata_providers(request: Request) -> list[dict]:
    """Return list of installed metadata provider plugins with id, name,
    logo_url and whether the provider serves numeric ratings (badge-style
    providers like Steam Deck tiers report ratings=False)."""
    from pathlib import Path
    providers = []
    try:
        for plug in plugin_manager.get_plugin_instances():
            pid_fn = getattr(plug, "metadata_provider_id", None)
            if not callable(pid_fn):
                continue
            try:
                pid = pid_fn()
            except Exception:
                continue
            if not pid:
                continue
            name_fn = getattr(plug, "metadata_provider_name", None)
            try:
                pname = name_fn() if callable(name_fn) else None
            except Exception:
                pname = None
            ratings_fn = getattr(plug, "metadata_provider_ratings", None)
            try:
                # No hook = classic rating provider (backward compatible).
                ratings = bool(ratings_fn()) if callable(ratings_fn) else True
            except Exception:
                ratings = True
            # Resolve plugin_id for logo URL (provider_id may differ from plugin_id)
            plugin_id = pid
            if not Path(PLUGINS_PATH, pid).is_dir():
                # Try common suffixes
                for suffix in ["-metadata", "-scraper", "-plugin"]:
                    if Path(PLUGINS_PATH, pid + suffix).is_dir():
                        plugin_id = pid + suffix
                        break
            providers.append({
                "id": pid,
                "name": pname or pid,
                "logo_url": f"/api/plugins/{plugin_id}/logo",
                "ratings": ratings,
            })
    except Exception as e:
        logger.warning("Failed to list metadata providers: %s", e)
    return providers


# ── Plugin metadata hooks (search + fetch) ──────────────────────────────────


@protected_route(
    plugins_router.get, "/metadata/search", scopes=[Scope.PLUGINS_READ]
)
async def plugin_metadata_search(request: Request, q: str = Query(...)) -> list[dict]:
    """Search all metadata provider plugins for a game title."""
    results = []
    try:
        all_results = plugin_manager.hook.metadata_search_game(query=q)
        for provider_results in all_results:
            if isinstance(provider_results, list):
                results.extend(provider_results)
    except Exception as e:
        logger.warning("Plugin metadata search error: %s", e)
    return results


@protected_route(
    plugins_router.get, "/metadata/fetch", scopes=[Scope.PLUGINS_READ]
)
async def plugin_metadata_fetch(
    request: Request,
    provider_id: str = Query(...),
    game_id: str = Query(..., alias="game_id"),
) -> dict:
    """Fetch full metadata for a game from a specific plugin provider."""
    try:
        all_results = plugin_manager.hook.metadata_get_game(provider_game_id=game_id)
        for result in all_results:
            if isinstance(result, dict) and result.get("provider_id") == provider_id:
                # Fallback: if the provider's game dict carries no cover, ask its
                # dedicated cover hook (metadata_get_cover_url) and fold it in.
                if not result.get("cover_url") and not result.get("cover"):
                    try:
                        for cu in plugin_manager.hook.metadata_get_cover_url(provider_game_id=game_id):
                            if cu:
                                result["cover_url"] = cu
                                break
                    except Exception:
                        pass
                return result
    except Exception as e:
        logger.warning("Plugin metadata fetch error: %s", e)
    raise HTTPException(status_code=404, detail="No result from plugin")


# ── Collection metadata (Wikipedia + IGDB franchises + plugin hooks) ─────────


@protected_route(
    plugins_router.get, "/metadata/collections/search", scopes=[Scope.PLUGINS_READ]
)
async def plugin_collection_metadata_search(request: Request, q: str = Query(...)) -> list[dict]:
    """Search every provider (Wikipedia, IGDB franchises, plugins) for a collection."""
    from handler.metadata.collection_meta_handler import search as _search
    try:
        return await _search(q)
    except Exception as e:
        logger.warning("Collection metadata search error: %s", e)
        return []


@protected_route(
    plugins_router.get, "/metadata/collections/fetch", scopes=[Scope.PLUGINS_READ]
)
async def plugin_collection_metadata_fetch(
    request: Request,
    provider_id: str = Query(...),
    id: str = Query(...),
) -> dict:
    """Fetch full collection metadata from one provider by its collection id."""
    from handler.metadata.collection_meta_handler import get as _get
    try:
        result = await _get(provider_id, id)
    except Exception as e:
        logger.warning("Collection metadata fetch error: %s", e)
        result = None
    if result is None:
        raise HTTPException(status_code=404, detail="No result from provider")
    return result


@protected_route(
    plugins_router.get, "/metadata/collections/covers", scopes=[Scope.PLUGINS_READ]
)
async def plugin_collection_metadata_covers(request: Request, q: str = Query(...)) -> list[dict]:
    """Cover-art candidates for a collection name (IGDB + SteamGridDB + Wikipedia + plugins)."""
    from handler.metadata.collection_meta_handler import covers as _covers
    try:
        return await _covers(q)
    except Exception as e:
        logger.warning("Collection covers error: %s", e)
        return []


@protected_route(
    plugins_router.get, "/metadata/collections/heroes", scopes=[Scope.PLUGINS_READ]
)
async def plugin_collection_metadata_heroes(request: Request, q: str = Query(...)) -> list[dict]:
    """Hero/background art for a collection name (SteamGridDB + plugins)."""
    from handler.metadata.collection_meta_handler import heroes as _heroes
    try:
        return await _heroes(q)
    except Exception as e:
        logger.warning("Collection heroes error: %s", e)
        return []


@protected_route(
    plugins_router.get, "/metadata/collections/logos", scopes=[Scope.PLUGINS_READ]
)
async def plugin_collection_metadata_logos(request: Request, q: str = Query(...)) -> list[dict]:
    """Logo/clearlogo art for a collection name (SteamGridDB + plugins)."""
    from handler.metadata.collection_meta_handler import logos as _logos
    try:
        return await _logos(q)
    except Exception as e:
        logger.warning("Collection logos error: %s", e)
        return []


# ── Translation endpoint (used by gd3-translator plugin) ────────────────────


@protected_route(
    plugins_router.post, "/translate", scopes=[Scope.PLUGINS_WRITE]
)
async def translate_text_endpoint(request: Request) -> dict:
    """Translate text using the gd3-translator plugin.

    POST body: {text: str, from_lang?: str, to_lang?: str}
    Returns: {ok: bool, text: str, from_lang: str, to_lang: str, error?: str}
    """
    body = await request.json()
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No text provided")

    # Read translator config from DB
    from_lang = body.get("from_lang")
    to_lang = body.get("to_lang")

    if not from_lang or not to_lang:
        async with async_session_factory() as session:
            result = await session.execute(
                select(PluginConfig).where(
                    PluginConfig.plugin_id == "gd3-translator"
                )
            )
            row = result.scalar_one_or_none()
            if row and row.config_json:
                cfg = json.loads(row.config_json)
                if not from_lang:
                    from_lang = cfg.get("from_lang", "en")
                if not to_lang:
                    to_lang = cfg.get("to_lang", "pl")
        if not from_lang:
            from_lang = "en"
        if not to_lang:
            to_lang = "pl"

    # Import and call the translator
    try:
        translator_dir = Path(PLUGINS_PATH) / "gd3-translator"
        vendor_dir = translator_dir / "vendor"
        import sys
        if str(vendor_dir) not in sys.path and vendor_dir.is_dir():
            sys.path.append(str(vendor_dir))
        if str(translator_dir) not in sys.path:
            sys.path.append(str(translator_dir))

        # Import from the plugin module directly
        from importlib import import_module
        mod_name = "gd3_translator_mod"
        if mod_name in sys.modules:
            mod = sys.modules[mod_name]
        else:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                mod_name, str(translator_dir / "plugin.py")
            )
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

        result = mod.translate_text(text, from_lang=from_lang, to_lang=to_lang)
        return result
    except Exception as e:
        logger.exception("Translation error")
        raise HTTPException(status_code=500, detail=str(e)[:200])


# ── Container restart (for theme plugin .vue recompilation) ──────────────────

@protected_route(plugins_router.post, "/restart", scopes=[Scope.SETTINGS_WRITE])
async def restart_container(request: Request) -> dict:
    """Gracefully restart the container so theme plugins are recompiled.

    Works because docker-compose has ``restart: unless-stopped`` - the container
    comes back automatically after the process exits.
    """
    import asyncio, signal, os

    logger.info("Admin requested container restart via Plugin Store")

    async def _delayed_exit():
        await asyncio.sleep(1)  # give time for HTTP response to flush
        os.kill(os.getpid(), signal.SIGTERM)

    fire_task(_delayed_exit())
    return {"ok": True, "message": "Restarting..."}
