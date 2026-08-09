"""Database handler for the library registry (libraries + membership)."""

from __future__ import annotations

from sqlalchemy import delete as _delete, func, select, update as _update
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.library import Library, LibraryMembership, UserLibraryAccess  # noqa: F401

# Libraries that may be restricted per-user (decision: user libraries/custom/GOG).
# Emulation/couch stay governed purely by the roms.read scope.
# NOTE: kind "custom_lib" = user-created separate libraries (e.g. "Kids games").
# kind "collections" = a user-created container holding Collections (game
# groupings - models/collection.py). Both are user content and restrictable.
ACL_KINDS = frozenset({"gog", "custom", "custom_lib", "collections"})

# Built-in libraries seeded on first startup. Order/visuals mirror the previous
# hard-coded home cards so the UI looks identical until an admin changes things.
_BUILTINS = [
    # GOG is a storefront: it lists everything the account owns, most of which is
    # not on this server yet. Upgrades get the same flag from a one-shot backfill
    # in main.py, keyed on the column being new.
    {"slug": "gog",       "name": "GOG",       "kind": "gog",       "icon": "/icons/gog.ico",
     "color": "#7c3aed", "sort_order": 10, "is_builtin": True, "storage_folder": "GOG",
     "is_store": True},
    {"slug": "games",     "name": "Games",     "kind": "custom",    "icon": "/GDLOGO.png",
     "color": "#14b8a6", "sort_order": 20, "is_builtin": True, "storage_folder": "CUSTOM"},
    {"slug": "emulation", "name": "Emulation", "kind": "emulation", "icon": "/icons/gamepad.svg",
     "color": "#14b8a6", "sort_order": 30, "is_builtin": True, "storage_folder": None},
    # Couch Mode is a controller-first VIEW of the emulation library, not a
    # browsable library. It lives in the registry so the same admin toggle /
    # ordering applies; the frontend only shows it when emulation is also on.
    {"slug": "couch",     "name": "Couch Mode", "kind": "couch",    "icon": "/icons/gamepad.svg",
     "color": "#f59e0b", "sort_order": 40, "is_builtin": True, "storage_folder": None},
    # Collection containers (kind "collections") are NOT seeded - they are
    # user-created in Settings > Libraries ("This library will be a Collection")
    # and fully deletable. There is no permanent built-in collections library.
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
        is_store: bool | None = None,
        adds_to_default_library: bool | None = None,
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
        if is_store is not None:
            lib.is_store = is_store
        if adds_to_default_library is not None:
            lib.adds_to_default_library = adds_to_default_library
        return lib

    @begin_session
    async def apply_default_library_flag(
        self, library_id: int, value: bool, *, session: AsyncSession = None,
    ) -> int:
        """Push a library's "also in Games" choice onto the games already in it.

        Only games whose sole home is this library are touched. A game that also
        sits in another library may be in the default one for a reason that has
        nothing to do with this switch, and silently yanking it out of the home
        rails because an unrelated shelf was reconfigured would be worse than
        doing nothing. Returns how many rows changed.
        """
        from models.library_game import LibraryGame

        in_this_library = select(LibraryMembership.library_game_id).where(
            LibraryMembership.library_id == library_id
        ).scalar_subquery()
        only_here = (
            select(LibraryMembership.library_game_id)
            .where(LibraryMembership.library_game_id.in_(in_this_library))
            .group_by(LibraryMembership.library_game_id)
            .having(func.count(LibraryMembership.id) == 1)
        ).scalar_subquery()

        result = await session.execute(
            _update(LibraryGame)
            .where(
                LibraryGame.id.in_(only_here),
                LibraryGame.in_default_library != value,
            )
            .values(in_default_library=value)
        )
        return int(result.rowcount or 0)

    @begin_session
    async def create_user_library(
        self, *, name: str, slug: str, kind: str = "custom_lib",
        color: str | None = None, icon: str | None = None,
        storage_folder: str | None = None, is_store: bool = False,
        adds_to_default_library: bool = False,
        created_by: int | None = None, session: AsyncSession = None,
    ) -> Library:
        # kind "custom_lib" = a user-created separate library (e.g. "Kids games").
        # kind "collections" = a user-created container that holds Collections.
        max_order = (await session.execute(select(func.max(Library.sort_order)))).scalar() or 0
        lib = Library(
            slug=slug, name=name, kind=kind, color=color, icon=icon,
            enabled=True, sort_order=int(max_order) + 10, is_builtin=False,
            storage_folder=storage_folder, created_by=created_by,
            is_store=is_store, adds_to_default_library=adds_to_default_library,
        )
        session.add(lib)
        await session.flush()
        await session.refresh(lib)
        return lib

    @begin_session
    async def ensure_store_library(
        self, catalog_id: str, *, slug: str, name: str,
        color: str | None = None, icon: str | None = None,
        storage_folder: str | None = None, plugin_id: str | None = None,
        session: AsyncSession = None,
    ) -> Library:
        """Create or update the store library a plugin catalogue lives in.

        A store is a plugin's to create, never an admin's, so this is the only
        path that turns on is_store for a plugin catalogue. Idempotent, keyed on
        catalog_id: it will adopt an existing library that already carries the
        slug (the demo shelf made by hand), and it never stamps over a name or
        colour an admin has since changed. plugin_id records the owner so the
        store can be removed with the plugin later without a live instance.
        """
        lib = (await session.execute(
            select(Library).where(Library.catalog_id == catalog_id)
        )).scalars().first()
        if lib is None:
            lib = (await session.execute(
                select(Library).where(Library.slug == slug)
            )).scalars().first()

        if lib is None:
            max_order = (await session.execute(select(func.max(Library.sort_order)))).scalar() or 0
            lib = Library(
                slug=slug, name=name, kind="custom_lib", color=color, icon=icon,
                enabled=True, sort_order=int(max_order) + 10, is_builtin=False,
                storage_folder=storage_folder or name, is_store=True,
                catalog_id=catalog_id, plugin_id=plugin_id,
                # Hidden from users by default - a storefront of things not yet on
                # the server is an admin surface. The admin opens it with the same
                # visibility toggle every other library has.
                visibility="restricted",
            )
            session.add(lib)
            await session.flush()
            await session.refresh(lib)
            return lib

        # Adopt / confirm: a store fed by this catalogue. Fill the on-disk folder
        # only if it has none, so an admin's choice stands. Keep the owner current
        # so a store made before the column, or by hand, learns who feeds it.
        lib.is_store = True
        lib.catalog_id = catalog_id
        if plugin_id:
            lib.plugin_id = plugin_id
        if not lib.storage_folder:
            lib.storage_folder = storage_folder or name
        await session.flush()
        return lib

    @begin_session
    async def delete_user_library(self, slug: str, *, session: AsyncSession = None) -> bool:
        from models.library_game import LibraryGame
        lib = (await session.execute(select(Library).where(Library.slug == slug))).scalars().first()
        if lib is None or lib.is_builtin:
            return False
        # A plugin store is the plugin's to own: it comes and goes with the
        # plugin, never by hand. Deleting it here would orphan the catalogue and
        # a re-sync would just recreate it.
        if lib.catalog_id:
            return False
        # Games that belong to this library, captured BEFORE its membership rows
        # cascade away, so we can rescue any that would be left with no home.
        member_ids = [r[0] for r in (await session.execute(
            select(LibraryMembership.library_game_id).where(LibraryMembership.library_id == lib.id)
        )).all()]
        # A collections container also owns its Collections. Delete them first so
        # their membership rows cascade (the library_id FK is not enforced on the
        # pre-existing table, so we cannot rely on ON DELETE CASCADE there).
        if lib.kind == "collections":
            from models.collection import Collection
            colls = (await session.execute(
                select(Collection).where(Collection.library_id == lib.id)
            )).scalars().all()
            for c in colls:
                await session.delete(c)  # collection_membership rows cascade
        await session.delete(lib)  # library_membership rows cascade
        await session.flush()       # apply the cascade before checking what is left
        # Re-home any game whose ONLY library was this one: with no membership and
        # outside the default library it would be an unreachable orphan
        # (is_active=1, no membership). Move it into the default library instead.
        if member_ids:
            still = {r[0] for r in (await session.execute(
                select(LibraryMembership.library_game_id)
                .where(LibraryMembership.library_game_id.in_(member_ids))
            )).all()}
            stranded = [gid for gid in member_ids if gid not in still]
            if stranded:
                await session.execute(
                    _update(LibraryGame)
                    .where(LibraryGame.id.in_(stranded),
                           LibraryGame.in_default_library.is_(False))
                    .values(in_default_library=True)
                )
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
        # Invariant: a game must always have a home. If it now belongs to no custom
        # library and is not in the default library, re-home it there so it can
        # never become an unreachable orphan (is_active=1, no membership row).
        if not library_ids:
            from models.library_game import LibraryGame
            game = await session.get(LibraryGame, game_id)
            if game is not None and not game.in_default_library:
                game.in_default_library = True

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
        # A plugin store follows the same visibility rules as any other library:
        # it is created restricted (so it is admin-only until an admin opens it),
        # but the admin governs that with the normal toggle rather than a special
        # case here. GOG's store is public and untouched.
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
