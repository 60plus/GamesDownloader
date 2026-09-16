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
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel

from utils.uploads import read_upload_capped
from config import GAMES_PATH, RESOURCES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.library_registry_handler import (
    ACL_KINDS,
    is_folder_scanned,
    library_registry_handler,
)
from handler.library.catalog_sync_handler import shelf_waiting_for_its_plugin
from handler.library.metadata_lock import assert_unlocked
from handler.database.session import async_session_factory
from utils.errors import safe_detail
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
    is_store: bool | None = None
    adds_to_default_library: bool | None = None


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
    is_store: bool = False             # a catalogue of what could be added, not what is
    adds_to_default_library: bool = False  # its games also join the Games library


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
        # getattr keeps a theme built against an older core from crashing on a
        # response that predates these columns.
        "is_store":       bool(getattr(lib, "is_store", False)),
        "adds_to_default_library": bool(getattr(lib, "adds_to_default_library", False)),
        # Set when this store is fed by a plugin catalogue. The UI uses it to keep
        # a plugin store from being hand-deleted (it comes and goes with the
        # plugin) and to route its page to the catalogue view.
        "catalog_id":     getattr(lib, "catalog_id", None),
        # Whether a folder scan ever walks this library, answered by the same
        # function the scan itself picks its targets with. Sent rather than left
        # for the screen to work out again from storage_folder and kind: that
        # second copy stopped matching the moment "a plugin's shelf whose plugin
        # is off" became part of the answer, and the screen went on offering an
        # exclusions box for a shelf nothing walks.
        "folder_scanned": is_folder_scanned(lib),
        # A plugin's shelf whose plugin is not in the runtime. The switch beside
        # it is refused while this is true, so the screen is told rather than
        # left to draw a control the server will turn down.
        "waiting_for_plugin": shelf_waiting_for_its_plugin(lib),
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
    existing = await library_registry_handler.get_by_slug(slug)

    # A plugin's shelf comes and goes with its plugin, so this switch does not
    # get to bring one back on its own. Disabling the plugin put the shelf away
    # and one click here used to take it out again, into the navigation, with
    # nothing behind it. Switching it OFF by hand stays allowed: that is already
    # the direction the plugin would take it.
    if (body.enabled is True and existing is not None
            and shelf_waiting_for_its_plugin(existing)):
        raise HTTPException(
            status_code=400,
            detail="This shelf belongs to a plugin that is switched off. Enable "
                   "the plugin and the shelf comes back with it.",
        )

    name = body.name
    if name is not None:
        if existing is not None and existing.is_builtin:
            name = None
        else:
            name = name.strip() or None

    # Captured before the write so the retroactive pass below can tell an actual
    # change from a PATCH that merely resent the same value.
    default_flag_changed = (
        body.adds_to_default_library is not None
        and existing is not None
        and bool(getattr(existing, "adds_to_default_library", False))
        != body.adds_to_default_library
    )

    lib = await library_registry_handler.update(
        slug, enabled=body.enabled, sort_order=body.sort_order,
        name=name, color=body.color, icon=body.icon,
        is_store=body.is_store,
        adds_to_default_library=body.adds_to_default_library,
    )
    if lib is None:
        raise HTTPException(status_code=404, detail="Library not found")

    # Answer the admin's expectation: flipping the switch applies to the shelf as
    # it stands, not only to whatever lands on it next.
    if default_flag_changed:
        moved = await library_registry_handler.apply_default_library_flag(
            lib.id, bool(body.adds_to_default_library),
        )
        if moved:
            logger.info(
                "Library %s: %s %d game(s) %s the default library",
                slug, "added" if body.adds_to_default_library else "removed",
                moved, "to" if body.adds_to_default_library else "from",
            )
    return _library_to_dict(lib)


class LibraryExclusionsBody(BaseModel):
    patterns: str = ""


class LibraryExclusionsApplyBody(BaseModel):
    """The games the person was looking at. Required, and for the same reason
    as on the ROM side: without it the server removes whatever matches at the
    moment of the click rather than what was confirmed."""

    ids: list[int]


def _game_folders(paths: list[str], root: str) -> list[str]:
    """The directories the scan would have called games, worked back from files.

    The scan holds a game's folder; the database holds the files inside it. The
    two sides have to reach the same folder or they answer differently about the
    same game, so the rule here is the one `_pending_game_dirs` applies, read
    backwards: the first segment under the library root is the game, unless it
    is an OS or container name, in which case the game is the segment after it.

    Paths are stored relative to BASE_PATH (`games/CUSTOM/Title/x.zip` on a real
    install) while the root is absolute, so they are joined first. Anything that
    lands outside this library - a GOG game carried into the default library by
    its flag, which is what nearly every game on a real server looks like -
    contributes no folder, and a game with no folder here is left alone.
    """
    from config import BASE_PATH
    from endpoints.library.library_router import _STRUCTURAL_NAMES

    base = str(BASE_PATH)
    top = str(root).replace("\\", "/").rstrip("/")
    out: list[str] = []
    for raw in paths:
        # normpath, because the stored path is relative to BASE_PATH and the
        # root comes from GAMES_PATH - two settings that need not sit inside one
        # another (utils/paths.py says so, and a test pins it). With the library
        # on another volume, relpath produces `../mnt/...` and a plain join
        # leaves `/data/../mnt/...`, which never starts with the root: every
        # game answered "outside this library" and the whole preview went quiet.
        absolute = os.path.normpath(os.path.join(base, str(raw))).replace("\\", "/")
        if not absolute.startswith(top + "/"):
            return []
        segments = absolute[len(top) + 1:].split("/")
        # A file directly in the library root is not in a game folder at all.
        if len(segments) < 2:
            return []
        depth = 2 if segments[0].lower() in _STRUCTURAL_NAMES and len(segments) > 2 else 1
        folder = "/".join([top, *segments[:depth]])
        if folder not in out:
            out.append(folder)
    return out


def _covered_here(game: dict, patterns: list[str], root: str | None = None) -> bool:
    """Does this library's patterns cover this game, cautiously.

    The question is the one the scan asks, about the thing the scan asks it
    about: a game is a FOLDER, and a pattern covers the game when it covers that
    folder. Asking it file by file instead - "every file it is made of is
    excluded" - answered differently for every shape except a folder pattern,
    and the disagreement ran the dangerous way: `*.zip` covered every custom
    game, so the button offered to delete the library, and the next scan added
    them all back blank because the folders matched nothing.

    Three conditions, and every one of them is a reason to leave a game alone
    rather than a reason to remove it:

    - it has files at all, because a game with none says nothing about where it
      sits;
    - EVERY folder it occupies is covered, because a title present in two places
      is one game and half of it is not an answer;
    - and no other library holds it. A pattern says "this is not a game HERE",
      and a game somebody deliberately put on a second shelf makes that sentence
      stop being obvious. Removing it took it off every shelf at once.
    """
    from handler.filesystem.exclusions import is_excluded_dir

    paths = game.get("paths") or []
    if not paths or int(game.get("libraries") or 1) > 1:
        return False
    folders = _game_folders(paths, str(root or ""))
    if not folders:
        return False
    return all(is_excluded_dir(f, patterns, root=root) for f in folders)



def _shown_path(stored: str) -> str:
    """The path this screen puts in front of somebody, as a full one.

    `LibraryFile.file_path` is stored relative to BASE_PATH, so the list under
    the exclusions box used to read `games/CUSTOM/Doom/doom.zip`. That is a
    perfectly reasonable thing to copy into the box above it - and it matches
    nothing: it is neither absolute, so nothing trims it, nor relative to the
    LIBRARY, which is what the matcher compares against. It saved without a
    word of complaint and covered nothing for ever.

    Shown absolute instead, the way the platform side already shows ROM paths.
    An absolute path pasted as a pattern IS handled: `_made_relative` cuts it
    down to the library root when it is saved.
    """
    from config import BASE_PATH

    text = str(stored or "")
    if not text or os.path.isabs(text):
        return text
    return os.path.normpath(os.path.join(str(BASE_PATH), text)).replace("\\", "/")


async def _library_excluded_games(library, patterns: list[str]) -> list[dict]:
    """Games in this library that the patterns cover.

    One rule, shared by the preview and the apply: two lists built two ways is
    how somebody confirms one thing and loses another.

    What counts as covered is `_covered_here` above, and it is deliberately
    cautious in three separate ways.
    """
    if not patterns:
        return []
    from config import GAMES_PATH

    root = str(Path(GAMES_PATH) / (library.storage_folder or ""))
    out = []
    for game in await library_registry_handler.games_with_paths(library):
        paths = game.get("paths") or []
        if _covered_here(game, patterns, root):
            out.append({"id": game["id"], "title": game["title"],
                        "files": len(paths), "path": _shown_path(paths[0])})
    return out


@protected_route(router.put, "/{slug}/exclusions", scopes=[Scopes.SETTINGS_WRITE])
async def set_library_exclusions(request: Request, slug: str, body: LibraryExclusionsBody) -> dict:
    """Paths this library's scan is told never to look at, one per line.

    Saving changes nothing that is already here; it only stops a future scan
    adding something, which is undone by deleting the line.
    """
    from handler.filesystem.exclusions import parse_patterns

    library = await library_registry_handler.get_by_slug(slug)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")
    # The folder this library is scanned from. Passed so an absolute path typed
    # off the screen is cut down HERE, before the guard judges it - the guard
    # and the matcher have to be looking at the same text or `<root>/*` is
    # saved as an ordinary path and then means everything.
    root = str(Path(GAMES_PATH) / (library.storage_folder or ""))
    kept = parse_patterns(body.patterns, root=root)
    # Refusing to ADD a pattern nobody would read is not the same as refusing to
    # take one away. A library can stop being scanned - its folder taken away,
    # its kind changed - with patterns already saved on it, and a guard on every
    # write would strand those where nothing could reach them.
    if kept and not is_folder_scanned(library):
        raise HTTPException(
            status_code=400,
            detail="This library is not walked by a folder scan, so an "
                   "exclusion pattern would never be read.",
        )
    await library_registry_handler.set_scan_exclude(slug, "\n".join(kept) or None)
    typed = [ln.strip() for ln in (body.patterns or "").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    # Asked of the parser per line, not by comparing typed text with stored
    # text. The parser rewrites an absolute path into a relative one on the way
    # in, so those two stopped being equal for every pattern it cuts down - and
    # a pattern that was stored AND WORKING came back under a message saying it
    # would have swallowed the whole library. The screen then dropped the line
    # from the box, and the next Save really did delete it.
    return {"patterns": kept,
            "ignored": [ln for ln in typed if not parse_patterns(ln, root=root)]}


@protected_route(router.get, "/{slug}/exclusions", scopes=[Scopes.SETTINGS_WRITE])
async def get_library_exclusions(request: Request, slug: str) -> dict:
    """What is saved, without working out what it covers - see the ROM side."""
    from handler.filesystem.exclusions import parse_patterns

    library = await library_registry_handler.get_by_slug(slug)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")
    return {"patterns": parse_patterns(getattr(library, "scan_exclude", None))}


@protected_route(router.get, "/{slug}/exclusions/preview", scopes=[Scopes.SETTINGS_WRITE])
async def preview_library_exclusions(request: Request, slug: str) -> dict:
    """What applying the saved patterns would remove, before anything is."""
    from handler.filesystem.exclusions import parse_patterns

    library = await library_registry_handler.get_by_slug(slug)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")
    patterns = parse_patterns(getattr(library, "scan_exclude", None))
    matches = await _library_excluded_games(library, patterns)
    return {"patterns": patterns, "count": len(matches), "games": matches}


@protected_route(router.post, "/{slug}/exclusions/apply", scopes=[Scopes.LIBRARY_ADMIN])
async def apply_library_exclusions(
    request: Request, slug: str, body: LibraryExclusionsApplyBody,
) -> dict:
    """Remove the games the saved patterns cover. Files on disk are left alone.

    A different permission from saving a pattern, not a wider audience: both
    live only in ADMIN_SCOPES. It asks for the one that governs deleting games,
    for the same reason as on the ROM side - saving a pattern changes what a
    future scan adds, this deletes rows and everything hanging off them.
    """
    from handler.filesystem.exclusions import parse_patterns
    # No module-level singleton here, unlike most handlers - the library
    # router builds its own.
    from handler.database.library_handler import LibraryHandler

    _lib = LibraryHandler()

    library = await library_registry_handler.get_by_slug(slug)
    if library is None:
        raise HTTPException(status_code=404, detail="Library not found")
    patterns = parse_patterns(getattr(library, "scan_exclude", None))
    matches = await _library_excluded_games(library, patterns)

    # Same rule as the ROM side: the list that was shown is an upper bound on
    # what may go. See ExclusionsApplyBody in roms_router for why.
    shown = set(body.ids)
    still_matching = {entry["id"] for entry in matches}
    to_remove = [entry for entry in matches if entry["id"] in shown]
    skipped = sorted(shown - still_matching)

    # Per row, for the same reason as the ROM side: a failure partway must not
    # report that nothing happened when part of it already has.
    removed = 0
    failed: list[int] = []
    for entry in to_remove:
        try:
            game = await _lib.get_by_id(entry["id"])
            if game is None:
                failed.append(entry["id"])
                continue
            await _lib.delete(game)
            removed += 1
        except Exception:  # noqa: BLE001 - one game must not decide the rest
            logger.exception("Could not remove game %s in %s", entry["id"], slug)
            failed.append(entry["id"])
    if failed:
        logger.warning("%d game(s) in %s could not be removed", len(failed), slug)
    if removed:
        logger.info("Removed %d game(s) in %s matching its scan exclusions "
                    "(files left on disk)", removed, slug)
    if skipped:
        logger.info("Left %d game(s) in %s alone: they no longer match the "
                    "saved patterns", len(skipped), slug)
    return {"removed": removed, "games": to_remove, "skipped": skipped,
            "failed": failed}


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
    content = await read_upload_capped(file, _MAX_ICON_BYTES, what="Icon")

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
            raise HTTPException(status_code=500, detail=safe_detail(e, request, what="Could not create folder"))

    user = getattr(request.state, "user", None)
    lib = await library_registry_handler.create_user_library(
        name=name, slug=slug, kind="collections" if body.is_collection else "custom_lib",
        color=body.color, icon=body.icon,
        storage_folder=storage_folder, created_by=getattr(user, "id", None),
        # A store is a plugin's to create, never a hand-made shelf: it lists a
        # catalogue of what could be added and is fed by a plugin's sync. So the
        # request's is_store is ignored here - the only path to a store is
        # ensure_store_library, called from a catalogue sync.
        is_store=False,
        adds_to_default_library=body.adds_to_default_library,
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


async def _assert_may_see_game(request, game) -> None:
    """Whether this account may be told about this game at all.

    These routes name the shelves a game sits on, which is a fact about a game
    in a library, and they answered for games in libraries the caller may not
    see. Answered as a 404 so neither the title nor the id leaks.

    One function for both of them. The read grew this check and the WRITE beside
    it did not, so an account refused the answer could still send the change -
    and with an empty body that change takes the shortest path through the
    route: no collections wanted, so the game is forced back into the default
    library and every membership row it had is deleted. One request to move a
    game out of a restricted or a switched-off library into the public one.
    """
    from handler.library.visibility import membership_map, visibility_for

    vis = await visibility_for(request.state.user)
    if not vis.allows(game, (await membership_map([game.id])).get(game.id)):
        raise HTTPException(status_code=404, detail="Game not found")


@protected_route(router.get, "/membership/{game_id}", scopes=[Scopes.LIBRARY_READ])
async def get_game_membership(request: Request, game_id: int) -> dict:
    """A game's default-library flag and the collection slugs it belongs to."""
    async with async_session_factory() as s:
        game = await s.get(LibraryGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    await _assert_may_see_game(request, game)
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

    # Invariant: never leave a game homeless. Unchecking the default library while
    # selecting no custom library would orphan it (is_active=1, no membership), so
    # re-home it to the default library instead.
    in_default = body.in_default_library or not wanted_ids

    async with async_session_factory() as s:
        async with s.begin():
            game = await s.get(LibraryGame, game_id)
            if game is None:
                raise HTTPException(status_code=404, detail="Game not found")
            # The same question the read asks, and asked before anything moves.
            await _assert_may_see_game(request, game)
            # Inside the transaction, before the write: the shelves a game sits
            # on are part of what the editor's Save changes, so a lock that let
            # them through would look broken to the first person to try it.
            assert_unlocked(request, game)
            game.in_default_library = in_default

    await library_registry_handler.set_memberships(game_id, wanted_ids)
    return {"ok": True, "in_default_library": in_default, "collections": list(slug_to_id.keys() & set(body.collections))}


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
