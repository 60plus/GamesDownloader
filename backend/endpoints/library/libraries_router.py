"""Library registry endpoints.

Prefix: /api/libraries

Phase 0: read-only discovery. The frontend (navbar, home, themes) reads this on
boot to render libraries data-driven instead of hard-coding GOG/Games/Emulation.
Admin write endpoints (enable/disable, reorder, create) are added in later phases.
"""

from __future__ import annotations

import glob
import logging
import os
import re

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from config import GAMES_PATH, RESOURCES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.library_registry_handler import ACL_KINDS, library_registry_handler
from handler.database.session import async_session_factory
from models.library_game import LibraryGame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/libraries", tags=["libraries"])

# Each library kind requires a scope to be visible, reusing the existing RBAC.
# A user with emulation access revoked (ROMS_READ stripped) stops seeing the
# emulation library; non-admins never see GOG. Unknown kinds fall back to
# LIBRARY_READ.
_KIND_SCOPE = {
    "gog":         Scopes.GOG_READ,
    "emulation":   Scopes.ROMS_READ,
    "couch":       Scopes.ROMS_READ,   # couch is a view of the ROM library
    "custom":      Scopes.LIBRARY_READ,
    "custom_lib":  Scopes.LIBRARY_READ,  # user-created separate libraries
    "collections": Scopes.LIBRARY_READ,  # built-in Collections index library
}


class LibraryUpdateBody(BaseModel):
    enabled: bool | None = None
    sort_order: int | None = None
    name: str | None = None
    color: str | None = None
    icon: str | None = None


# Uploaded library icons/logos. Raster only - SVG is offered exclusively via the
# built-in "builtin:<name>" picker so an uploaded file can never carry script.
_ICON_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_ICON_BYTES = 2 * 1024 * 1024  # 2 MB


class LibraryCreateBody(BaseModel):
    name: str
    color: str | None = None
    icon: str | None = None
    create_folder: bool = False
    is_collection: bool = False        # create a Collections container (kind 'collections')


class MembershipBody(BaseModel):
    in_default_library: bool = True
    collections: list[str] = []


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "collection"


def _library_to_dict(lib) -> dict:
    return {
        "slug":           lib.slug,
        "name":           lib.name,
        "kind":           lib.kind,
        "icon":           lib.icon,
        "color":          lib.color,
        "enabled":        lib.enabled,
        "sort_order":     lib.sort_order,
        "is_builtin":     lib.is_builtin,
        "storage_folder": lib.storage_folder,
        "visibility":     getattr(lib, "visibility", "public") or "public",
    }


@protected_route(router.get, "")
async def list_libraries(request: Request) -> list[dict]:
    """Enabled libraries visible to the current user.

    Filtered by RBAC scope and, for restricted libraries, by the per-user
    allowlist (admins bypass). Restricted libraries the user is not on stay
    hidden from nav/home; direct access is blocked at the games/GOG endpoints.
    """
    from models.user import Role
    user = getattr(request.state, "user", None)
    user_scopes = getattr(request.state, "scopes", set())
    is_admin = getattr(user, "role", None) == Role.ADMIN
    allowed: set[int] = set()
    if user is not None and not is_admin:
        allowed = await library_registry_handler.get_user_access_ids(user.id)

    libs = await library_registry_handler.get_all()
    out: list[dict] = []
    for lib in libs:
        if not lib.enabled:
            continue
        needed = _KIND_SCOPE.get(lib.kind, Scopes.LIBRARY_READ)
        if needed not in user_scopes:
            continue
        if not is_admin and (lib.visibility or "public") == "restricted" and lib.id not in allowed:
            continue
        out.append(_library_to_dict(lib))
    return out


@protected_route(router.get, "/all", scopes=[Scopes.SETTINGS_READ])
async def list_all_libraries(request: Request) -> list[dict]:
    """All libraries including disabled ones - for the admin management page."""
    libs = await library_registry_handler.get_all()
    return [_library_to_dict(lib) for lib in libs]


@protected_route(router.patch, "/{slug}", scopes=[Scopes.SETTINGS_WRITE])
async def update_library(request: Request, slug: str, body: LibraryUpdateBody) -> dict:
    """Toggle enabled, reorder, or restyle a library - name/color/icon (admin).

    Built-in library names are driven by UI translations, so a rename is ignored
    for them (color and icon are still editable). `icon` may be a "builtin:<name>"
    token or a /resources/... path produced by the icon-upload endpoint.
    """
    name = body.name
    if name is not None:
        existing = await library_registry_handler.get_by_slug(slug)
        if existing is not None and existing.is_builtin:
            name = None
        elif name is not None:
            name = name.strip() or None

    lib = await library_registry_handler.update(
        slug, enabled=body.enabled, sort_order=body.sort_order,
        name=name, color=body.color, icon=body.icon,
    )
    if lib is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return _library_to_dict(lib)


@protected_route(router.post, "/{slug}/icon", scopes=[Scopes.SETTINGS_WRITE])
async def upload_library_icon(
    request: Request, slug: str, file: UploadFile = File(...),
) -> dict:
    """Upload a custom icon/logo for a library (PNG, JPG, WEBP, max 2 MB)."""
    lib = await library_registry_handler.get_by_slug(slug)
    if lib is None:
        raise HTTPException(status_code=404, detail="Library not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ICON_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(_ICON_EXTS))}",
        )
    content = await file.read()
    if len(content) > _MAX_ICON_BYTES:
        raise HTTPException(status_code=413, detail="Icon too large (max 2 MB)")

    icons_dir = os.path.join(RESOURCES_PATH, "library-icons")
    os.makedirs(icons_dir, exist_ok=True)
    # Drop any previous icon files for this slug (extension may differ).
    for old in glob.glob(os.path.join(icons_dir, f"{slug}.*")):
        try:
            os.remove(old)
        except OSError:
            pass
    dest = os.path.join(icons_dir, f"{slug}{ext}")
    with open(dest, "wb") as fh:
        fh.write(content)

    # Cache-buster so the browser refetches when the icon is replaced.
    icon_url = f"/resources/library-icons/{slug}{ext}?v={int(os.path.getmtime(dest))}"
    updated = await library_registry_handler.update(slug, icon=icon_url)
    return _library_to_dict(updated)


@protected_route(router.post, "", scopes=[Scopes.SETTINGS_WRITE])
async def create_library(request: Request, body: LibraryCreateBody) -> dict:
    """Create a user library. With `is_collection` it is a Collections container
    (kind 'collections', no scan folder); otherwise a regular custom library,
    optionally with its own scan folder."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    slug = _slugify(name)
    if await library_registry_handler.get_by_slug(slug) is not None:
        raise HTTPException(status_code=409, detail="A library with this name already exists")

    # A collection container never owns a scan folder (it holds collections, not
    # files), so the folder option is ignored for it.
    storage_folder = None
    if body.create_folder and not body.is_collection:
        storage_folder = slug
        try:
            os.makedirs(os.path.join(GAMES_PATH, slug), exist_ok=True)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"Could not create folder: {e}")

    user = getattr(request.state, "user", None)
    lib = await library_registry_handler.create_user_library(
        name=name, slug=slug, kind="collections" if body.is_collection else "custom_lib",
        color=body.color, icon=body.icon,
        storage_folder=storage_folder, created_by=getattr(user, "id", None),
    )
    return _library_to_dict(lib)


@protected_route(router.delete, "/{slug}", scopes=[Scopes.SETTINGS_WRITE])
async def delete_library(request: Request, slug: str) -> dict:
    """Delete a user-created library (built-in libraries cannot be deleted). Files
    on disk are left untouched - only the library and its memberships go."""
    ok = await library_registry_handler.delete_user_library(slug)
    if not ok:
        raise HTTPException(status_code=400, detail="Library not found or is built-in")
    return {"ok": True}


@protected_route(router.get, "/membership/{game_id}", scopes=[Scopes.LIBRARY_READ])
async def get_game_membership(request: Request, game_id: int) -> dict:
    """A game's default-library flag and the collection slugs it belongs to."""
    async with async_session_factory() as s:
        game = await s.get(LibraryGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    member_ids = set(await library_registry_handler.get_member_library_ids(game_id))
    libraries = [
        lib.slug for lib in await library_registry_handler.get_all()
        if lib.kind == "custom_lib" and lib.id in member_ids
    ]
    return {"in_default_library": game.in_default_library, "collections": libraries}


@protected_route(router.put, "/membership/{game_id}", scopes=[Scopes.LIBRARY_WRITE])
async def set_game_membership(request: Request, game_id: int, body: MembershipBody) -> dict:
    """Set a game's default-library flag and its collection memberships."""
    libs = await library_registry_handler.get_all()
    slug_to_id = {lib.slug: lib.id for lib in libs if lib.kind == "custom_lib"}
    wanted_ids = [slug_to_id[s] for s in body.collections if s in slug_to_id]

    async with async_session_factory() as s:
        async with s.begin():
            game = await s.get(LibraryGame, game_id)
            if game is None:
                raise HTTPException(status_code=404, detail="Game not found")
            game.in_default_library = body.in_default_library

    await library_registry_handler.set_memberships(game_id, wanted_ids)
    return {"ok": True, "in_default_library": body.in_default_library, "collections": list(slug_to_id.keys() & set(body.collections))}


# ── Per-user access control ───────────────────────────────────────────────────


class LibraryAccessBody(BaseModel):
    visibility: str = "public"          # "public" | "restricted"
    user_ids: list[int] = []


@protected_route(router.get, "/{slug}/access", scopes=[Scopes.SETTINGS_READ])
async def get_library_access(request: Request, slug: str) -> dict:
    """A library's visibility and the user ids allowed when restricted (admin)."""
    data = await library_registry_handler.get_access(slug)
    if data is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return data


@protected_route(router.put, "/{slug}/access", scopes=[Scopes.SETTINGS_WRITE])
async def set_library_access(request: Request, slug: str, body: LibraryAccessBody) -> dict:
    """Set who can access a library (admin). Only collections / custom / GOG can
    be restricted - emulation and couch stay governed by the roms.read scope."""
    lib = await library_registry_handler.get_by_slug(slug)
    if lib is None:
        raise HTTPException(status_code=404, detail="Library not found")
    if lib.kind not in ACL_KINDS:
        raise HTTPException(status_code=400, detail="This library type cannot be restricted per user")
    if body.visibility not in ("public", "restricted"):
        raise HTTPException(status_code=400, detail="Invalid visibility")
    await library_registry_handler.set_access(slug, body.visibility, body.user_ids)
    return await library_registry_handler.get_access(slug)
