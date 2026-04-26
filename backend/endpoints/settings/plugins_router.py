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

from config import PLUGINS_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
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


def _merge_plugin_info(manifest: dict, db_row: PluginConfig | None) -> dict:
    """Merge filesystem manifest with DB state into a PluginInfo-compatible dict."""
    config = None
    config_schema = None

    if db_row:
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

    return [_merge_plugin_info(m, db_map.get(m["id"])) for m in manifests]


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
    """Uninstall a plugin - remove files and DB record."""
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

    return {"plugins": all_plugins, "errors": errors}


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


@plugins_router.get("/store/icon")
async def proxy_store_icon(url: str = Query(..., description="Remote icon URL")):
    """Proxy a remote plugin icon to avoid CORS issues.

    No auth required (icons are loaded by <img> tags) but restricted to
    hostnames from registered store sources + github.com.
    """
    import httpx
    import ipaddress
    import socket
    from urllib.parse import urlparse
    from starlette.responses import Response

    if not url.startswith("https://") and not url.startswith("http://"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    hostname = urlparse(url).hostname or ""
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL")

    # Allowlist: only fetch from known store hosts or well-known CDNs
    allowed_hosts = {"github.com", "raw.githubusercontent.com"}
    try:
        store_sources = await config_handler.get("plugin_store_sources")
        if store_sources:
            import json as _json
            for src in _json.loads(store_sources):
                h = urlparse(src.get("url", "")).hostname
                if h:
                    allowed_hosts.add(h)
    except Exception:
        pass

    if hostname not in allowed_hosts:
        raise HTTPException(status_code=400, detail="Icon host not in store sources allowlist")

    # SSRF protection: resolve hostname and check against private networks
    # Skip DNS check for allowlisted hosts (store sources may be on local network)
    _skip_dns = hostname in allowed_hosts
    if not _skip_dns:
        try:
            addr_infos = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            for af, _st, _proto, _cn, sa in addr_infos:
                ip = ipaddress.ip_address(sa[0])
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    raise HTTPException(status_code=400, detail="URLs resolving to private networks are blocked")
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Cannot resolve hostname")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        async with httpx.AsyncClient(follow_redirects=False, timeout=10) as c:
            r = await c.get(url)
            if r.is_redirect:
                raise HTTPException(status_code=400, detail="Redirects not allowed")
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if not ct.startswith("image/") and not ct.startswith("text/xml"):
                raise HTTPException(status_code=400, detail="Only image content types allowed")
            if len(r.content) > 2 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Icon too large (max 2 MB)")
            return Response(content=r.content, media_type=ct, headers={"Cache-Control": "public, max-age=86400"})
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

    return {"ok": True, "plugin": _merge_plugin_info(manifest, await _get_db_config(plugin_id))}


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
    """Return list of installed metadata provider plugins with id, name, has_logo."""
    providers = []
    try:
        ids = plugin_manager.hook.metadata_provider_id()
        names = plugin_manager.hook.metadata_provider_name()
        for pid, pname in zip(ids, names):
            if pid:
                # Resolve plugin_id for logo URL (provider_id may differ from plugin_id)
                from pathlib import Path
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
                return result
    except Exception as e:
        logger.warning("Plugin metadata fetch error: %s", e)
    raise HTTPException(status_code=404, detail="No result from plugin")


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

    asyncio.create_task(_delayed_exit())
    return {"ok": True, "message": "Restarting..."}
