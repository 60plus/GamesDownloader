"""Database handler for the library registry (libraries + membership)."""

from __future__ import annotations

from sqlalchemy import delete as _delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.library import Library, LibraryMembership, UserLibraryAccess  # noqa: F401

# Libraries that may be restricted per-user (decision: collections/custom/GOG).
# Emulation/couch stay governed purely by the roms.read scope.
ACL_KINDS = frozenset({"gog", "custom", "collection"})

# Built-in libraries seeded on first startup. Order/visuals mirror the previous
# hard-coded home cards so the UI looks identical until an admin changes things.
_BUILTINS = [
    {"slug": "gog",       "name": "GOG",       "kind": "gog",       "icon": "/icons/gog.ico",
     "color": "#7c3aed", "sort_order": 10, "is_builtin": True, "storage_folder": "GOG"},
    {"slug": "games",     "name": "Games",     "kind": "custom",    "icon": "/GDLOGO.png",
     "color": "#14b8a6", "sort_order": 20, "is_builtin": True, "storage_folder": "CUSTOM"},
    {"slug": "emulation", "name": "Emulation", "kind": "emulation", "icon": "/icons/gamepad.svg",
     "color": "#14b8a6", "sort_order": 30, "is_builtin": True, "storage_folder": None},
    # Couch Mode is a controller-first VIEW of the emulation library, not a
    # browsable library. It lives in the registry so the same admin toggle /
    # ordering applies; the frontend only shows it when emulation is also on.
    {"slug": "couch",     "name": "Couch Mode", "kind": "couch",    "icon": "/icons/gamepad.svg",
     "color": "#f59e0b", "sort_order": 40, "is_builtin": True, "storage_folder": None},
]


class LibraryRegistryHandler(DBBaseHandler):
    model = Library

    @begin_session
    async def get_all(self, *, session: AsyncSession = None) -> list[Library]:
        result = await session.execute(
            select(Library).order_by(Library.sort_order, Library.id)
        )
        return list(result.scalars().all())

    @begin_session
    async def get_by_slug(self, slug: str, *, session: AsyncSession = None) -> Library | None:
        result = await session.execute(select(Library).where(Library.slug == slug))
        return result.scalars().first()

    @begin_session
    async def update(
        self, slug: str, *, enabled: bool | None = None,
        sort_order: int | None = None, name: str | None = None,
        color: str | None = None, icon: str | None = None,
        session: AsyncSession = None,
    ) -> Library | None:
        lib = (await session.execute(
            select(Library).where(Library.slug == slug)
        )).scalars().first()
        if lib is None:
            return None
        if enabled is not None:
            lib.enabled = enabled
        if sort_order is not None:
            lib.sort_order = sort_order
        if name is not None:
            lib.name = name
        if color is not None:
            lib.color = color
        if icon is not None:
            lib.icon = icon
        return lib

    @begin_session
    async def create_collection(
        self, *, name: str, slug: str, color: str | None = None,
        icon: str | None = None, storage_folder: str | None = None,
        created_by: int | None = None, session: AsyncSession = None,
    ) -> Library:
        max_order = (await session.execute(select(func.max(Library.sort_order)))).scalar() or 0
        lib = Library(
            slug=slug, name=name, kind="collection", color=color, icon=icon,
            enabled=True, sort_order=int(max_order) + 10, is_builtin=False,
            storage_folder=storage_folder, created_by=created_by,
        )
        session.add(lib)
        await session.flush()
        await session.refresh(lib)
        return lib

    @begin_session
    async def delete_collection(self, slug: str, *, session: AsyncSession = None) -> bool:
        lib = (await session.execute(select(Library).where(Library.slug == slug))).scalars().first()
        if lib is None or lib.is_builtin:
            return False
        await session.delete(lib)  # membership rows cascade
        return True

    # ── Per-game collection membership ──────────────────────────────────────────

    @begin_session
    async def get_member_library_ids(self, game_id: int, *, session: AsyncSession = None) -> list[int]:
        rows = (await session.execute(
            select(LibraryMembership.library_id)
            .where(LibraryMembership.library_game_id == game_id)
        )).all()
        return [r[0] for r in rows]

    @begin_session
    async def set_memberships(self, game_id: int, library_ids: list[int], *, session: AsyncSession = None) -> None:
        await session.execute(
            _delete(LibraryMembership).where(LibraryMembership.library_game_id == game_id)
        )
        for lid in library_ids:
            session.add(LibraryMembership(library_id=lid, library_game_id=game_id))

    # ── Per-user access control (restricted libraries) ──────────────────────────

    @begin_session
    async def get_access(self, slug: str, *, session: AsyncSession = None) -> dict | None:
        """Visibility + allowlisted user ids for a library, or None if missing."""
        lib = (await session.execute(select(Library).where(Library.slug == slug))).scalars().first()
        if lib is None:
            return None
        rows = (await session.execute(
            select(UserLibraryAccess.user_id).where(UserLibraryAccess.library_id == lib.id)
        )).all()
        return {"visibility": lib.visibility or "public", "user_ids": [r[0] for r in rows]}

    @begin_session
    async def set_access(
        self, slug: str, visibility: str, user_ids: list[int], *, session: AsyncSession = None,
    ) -> Library | None:
        """Set a library's visibility and replace its allowlist (restricted only)."""
        lib = (await session.execute(select(Library).where(Library.slug == slug))).scalars().first()
        if lib is None:
            return None
        lib.visibility = "restricted" if visibility == "restricted" else "public"
        await session.execute(
            _delete(UserLibraryAccess).where(UserLibraryAccess.library_id == lib.id)
        )
        if lib.visibility == "restricted":
            for uid in {int(u) for u in user_ids}:
                session.add(UserLibraryAccess(library_id=lib.id, user_id=uid))
        return lib

    @begin_session
    async def get_user_access_ids(self, user_id: int, *, session: AsyncSession = None) -> set[int]:
        """All library ids this user is explicitly allowlisted for."""
        rows = (await session.execute(
            select(UserLibraryAccess.library_id).where(UserLibraryAccess.user_id == user_id)
        )).all()
        return {r[0] for r in rows}

    @begin_session
    async def user_can_access(self, user, lib: Library | None, *, session: AsyncSession = None) -> bool:
        """True when `user` may see/browse `lib`. Admins bypass; public libs are
        open; restricted libs require an allowlist row. `lib` already loaded."""
        from models.user import Role
        if lib is None:
            return True
        if getattr(user, "role", None) == Role.ADMIN:
            return True
        if (lib.visibility or "public") != "restricted":
            return True
        row = (await session.execute(
            select(UserLibraryAccess.id).where(
                UserLibraryAccess.library_id == lib.id,
                UserLibraryAccess.user_id == getattr(user, "id", None),
            ).limit(1)
        )).first()
        return row is not None

    @begin_session
    async def ensure_builtins(self, *, session: AsyncSession = None) -> None:
        """Insert any missing built-in library rows. Idempotent (runs every boot)."""
        existing = {s for (s,) in (await session.execute(select(Library.slug))).all()}
        for b in _BUILTINS:
            if b["slug"] not in existing:
                session.add(Library(**b))


library_registry_handler = LibraryRegistryHandler()
