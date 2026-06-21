"""Database handler for Collections (admin-curated game groupings)."""

from __future__ import annotations

from sqlalchemy import delete as _delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.collection import Collection, CollectionMembership
from models.library_game import LibraryGame


class CollectionHandler(DBBaseHandler):
    model = Collection

    # ── Collections CRUD ────────────────────────────────────────────────────────

    @begin_session
    async def get_all(self, *, session: AsyncSession = None) -> list[Collection]:
        result = await session.execute(
            select(Collection).order_by(Collection.sort_order, Collection.id)
        )
        return list(result.scalars().all())

    @begin_session
    async def get_for_library(self, library_id: int, *, session: AsyncSession = None) -> list[Collection]:
        """Collections inside one container library."""
        result = await session.execute(
            select(Collection).where(Collection.library_id == library_id)
            .order_by(Collection.sort_order, Collection.id)
        )
        return list(result.scalars().all())

    @begin_session
    async def get_by_slug(self, slug: str, *, session: AsyncSession = None) -> Collection | None:
        result = await session.execute(select(Collection).where(Collection.slug == slug))
        return result.scalars().first()

    @begin_session
    async def any_exists(self, *, session: AsyncSession = None) -> bool:
        """True when at least one collection exists."""
        row = (await session.execute(select(Collection.id).limit(1))).first()
        return row is not None

    @begin_session
    async def create(
        self, *, name: str, slug: str, library_id: int, description: str | None = None,
        created_by: int | None = None, session: AsyncSession = None,
    ) -> Collection:
        max_order = (await session.execute(select(func.max(Collection.sort_order)))).scalar() or 0
        coll = Collection(
            slug=slug, name=name, description=description, library_id=library_id,
            sort_order=int(max_order) + 10, created_by=created_by,
        )
        session.add(coll)
        await session.flush()
        await session.refresh(coll)
        return coll

    @begin_session
    async def update(self, slug: str, *, session: AsyncSession = None, **fields) -> Collection | None:
        """Update editable fields. Pass only the keys to change; a key mapped to
        None clears that override (e.g. rating=None -> auto average)."""
        coll = (await session.execute(
            select(Collection).where(Collection.slug == slug)
        )).scalars().first()
        if coll is None:
            return None
        for key in ("name", "description", "description_short", "cover_path",
                    "hero_path", "logo_path",
                    "start_year", "end_year", "rating", "hltb_main_s", "hltb_complete_s", "sort_order"):
            if key in fields:
                setattr(coll, key, fields[key])
        return coll

    @begin_session
    async def delete(self, slug: str, *, session: AsyncSession = None) -> bool:
        coll = (await session.execute(
            select(Collection).where(Collection.slug == slug)
        )).scalars().first()
        if coll is None:
            return False
        await session.delete(coll)  # membership rows cascade
        return True

    # ── Membership ──────────────────────────────────────────────────────────────

    @begin_session
    async def get_members(self, collection_id: int, *, session: AsyncSession = None) -> list[LibraryGame]:
        """Full member LibraryGames (files eager-loaded) for the detail view."""
        rows = (await session.execute(
            select(LibraryGame)
            .join(CollectionMembership, CollectionMembership.library_game_id == LibraryGame.id)
            .where(CollectionMembership.collection_id == collection_id, LibraryGame.is_active.is_(True))
            .order_by(LibraryGame.title)
        )).scalars().all()
        return list(rows)

    @begin_session
    async def grid_rows(self, library_id: int | None = None, *, session: AsyncSession = None) -> list[tuple]:
        """Lightweight per-membership row (collection_id, id, title, cover,
        background, rating, release_date, source, gog_game_id, developer,
        publisher, os_windows, os_mac, os_linux) - feeds the grid (counts, cover
        stacks, hero art, rating, year range, aggregated quickfacts) without
        loading game files. Scoped to one container library when given."""
        stmt = (
            select(
                CollectionMembership.collection_id,
                LibraryGame.id, LibraryGame.title, LibraryGame.cover_path,
                LibraryGame.background_path,
                LibraryGame.rating, LibraryGame.release_date,
                LibraryGame.source, LibraryGame.gog_game_id,
                LibraryGame.developer, LibraryGame.publisher,
                LibraryGame.os_windows, LibraryGame.os_mac, LibraryGame.os_linux,
            )
            .join(LibraryGame, LibraryGame.id == CollectionMembership.library_game_id)
            .where(LibraryGame.is_active.is_(True))
        )
        if library_id is not None:
            stmt = stmt.join(Collection, Collection.id == CollectionMembership.collection_id).where(
                Collection.library_id == library_id
            )
        rows = (await session.execute(stmt)).all()
        return list(rows)

    @begin_session
    async def get_collection_ids_for_game(self, game_id: int, *, session: AsyncSession = None) -> list[int]:
        rows = (await session.execute(
            select(CollectionMembership.collection_id)
            .where(CollectionMembership.library_game_id == game_id)
        )).all()
        return [r[0] for r in rows]

    @begin_session
    async def get_collections_for_game(self, game_id: int, *, session: AsyncSession = None) -> list[Collection]:
        """Collections a game belongs to (for the membership editor + detail row)."""
        rows = (await session.execute(
            select(Collection)
            .join(CollectionMembership, CollectionMembership.collection_id == Collection.id)
            .where(CollectionMembership.library_game_id == game_id)
            .order_by(Collection.name)
        )).scalars().all()
        return list(rows)

    @begin_session
    async def set_collections_for_game(
        self, game_id: int, collection_ids: list[int], *, session: AsyncSession = None,
    ) -> None:
        """Replace the set of collections a game belongs to."""
        await session.execute(
            _delete(CollectionMembership).where(CollectionMembership.library_game_id == game_id)
        )
        for cid in dict.fromkeys(collection_ids):  # de-dup, preserve order
            session.add(CollectionMembership(collection_id=cid, library_game_id=game_id))


collection_handler = CollectionHandler()
