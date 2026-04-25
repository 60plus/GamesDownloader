"""
GOG library sync - fetches owned games from GOG and stores them in DB.

Endpoint used: embed.gog.com/account/getFilteredProducts
(paginated, returns up to 50 games per page with metadata)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from handler.gog.gog_auth_handler import _HDRS, gog_auth_handler
from models.gog_game import GogGame

logger = logging.getLogger(__name__)

GOG_PRODUCTS_URL = (
    "https://embed.gog.com/account/getFilteredProducts"
    "?mediaType=1&sortBy=title&page={page}"
)


class GogSyncHandler(DBBaseHandler):
    model = GogGame

    @begin_session
    async def sync_library(
        self,
        user_id: int | None = None,
        progress_cb: Callable[[int, int, str], Awaitable[None]] | None = None,
        *,
        session: AsyncSession = None,
    ) -> dict:
        """Fetch all owned GOG games and upsert into DB. Returns summary dict.

        user_id: when set, syncs a specific user's GOG library.
                 When None, syncs the admin's library.
        """
        access_token = await gog_auth_handler.get_access_token(user_id=user_id)
        if not access_token:
            return {"ok": False, "error": "GOG account not connected", "synced": 0}

        headers = {**_HDRS, "Authorization": f"Bearer {access_token}"}

        total_pages = 1
        page = 1
        total_products = 0
        synced = 0

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30) as client:
            while page <= total_pages:
                try:
                    resp = await client.get(GOG_PRODUCTS_URL.format(page=page))
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    logger.error(f"GOG sync page {page} failed: {e}")
                    break

                total_pages = data.get("totalPages", 1)
                products    = data.get("products", [])
                if not total_products:
                    total_products = total_pages * len(products)  # rough estimate

                for product in products:
                    synced += 1
                    if progress_cb:
                        await progress_cb(synced, total_products, product.get("title", ""))
                    await self._upsert_game(product, owner_user_id=user_id, session=session)

                page += 1

        logger.info(f"GOG sync complete: {synced} games")
        return {"ok": True, "synced": synced}

    @begin_session
    async def _upsert_game(self, product: dict, owner_user_id: int | None = None, *, session: AsyncSession = None) -> None:
        gog_id = int(product.get("id", 0))
        if not gog_id:
            return

        # Query by gog_id AND owner to support per-user libraries
        stmt = select(GogGame).where(GogGame.gog_id == gog_id)
        if owner_user_id is not None:
            stmt = stmt.where(GogGame.owner_user_id == owner_user_id)
        else:
            stmt = stmt.where(GogGame.owner_user_id.is_(None))
        result = await session.execute(stmt)
        game = result.scalars().first()

        # Normalize fields
        title      = product.get("title", "")
        slug       = product.get("slug") or product.get("url", "").split("/")[-1] or str(gog_id)

        # ── Cover URL ─────────────────────────────────────────────────────────
        # GOG embed returns image as "//images.gog-statics.com/{hash}" (no extension).
        # The portrait product-card cover is obtained by appending "_product_card.jpg".
        image = product.get("image", "") or ""
        if image:
            if image.startswith("//"):
                image = "https:" + image
            elif not image.startswith("http") and image.startswith("/"):
                image = "https://images.gog.com" + image
            # Append .jpg when no file extension present
            # NOTE: GOG CDN no longer supports formatter suffixes like _product_card.jpg -
            # plain {hash}.jpg (200 OK) must be used instead.
            if not any(image.endswith(ext) for ext in (".jpg", ".png", ".webp", ".gif", ".ico")):
                image += ".jpg"
        cover_url = image

        # ── Release date ──────────────────────────────────────────────────────
        raw_date = product.get("globalReleaseDate") or product.get("releaseDate") or ""
        if isinstance(raw_date, (int, float)) and raw_date > 0:
            release_date = datetime.fromtimestamp(raw_date, tz=timezone.utc).strftime("%Y-%m-%d")
        elif isinstance(raw_date, str) and raw_date:
            release_date = raw_date[:10]
        else:
            release_date = ""

        developer  = product.get("developer") or product.get("brand", "")
        publisher  = product.get("publisher", "")
        genres     = product.get("genres") or []
        tags       = product.get("tags") or []
        rating     = float(product.get("rating", 0) or 0) or None
        works_on   = product.get("worksOn") or {}

        if game:
            game.title       = title
            game.slug        = slug
            # Only update cover_url from embed API if the game hasn't been scraped yet
            # (once scraped, the scrape handler sets a better v2 boxArtImage URL - don't revert it)
            if not game.scraped and cover_url:
                game.cover_url = cover_url
            elif not game.cover_url and cover_url:
                game.cover_url = cover_url
            game.developer   = developer or game.developer
            game.publisher   = publisher or game.publisher
            game.release_date = release_date or game.release_date
            game.genres      = genres or game.genres
            game.tags        = tags or game.tags
            game.rating      = rating or game.rating
            game.os_windows  = bool(works_on.get("Windows"))
            game.os_mac      = bool(works_on.get("Mac"))
            game.os_linux    = bool(works_on.get("Linux"))
            # If previously "scraped" but has no description or cover_path,
            # reset so the next auto-scrape retries (e.g. API was unavailable)
            if game.scraped and not game.description and not game.cover_path:
                game.scraped = False
        else:
            session.add(GogGame(
                gog_id        = gog_id,
                owner_user_id = owner_user_id,
                slug          = slug,
                title         = title,
                cover_url     = cover_url,
                developer     = developer,
                publisher     = publisher,
                release_date  = release_date,
                genres        = genres,
                tags          = tags,
                rating        = rating,
                os_windows    = bool(works_on.get("Windows")),
                os_mac        = bool(works_on.get("Mac")),
                os_linux      = bool(works_on.get("Linux")),
            ))

    @begin_session
    async def get_by_id(self, game_id: int, *, session: AsyncSession = None) -> GogGame | None:
        result = await session.execute(select(GogGame).where(GogGame.id == game_id))
        return result.scalars().first()

    @begin_session
    async def update_fields(
        self, game_id: int, fields: dict, *, session: AsyncSession = None
    ) -> bool:
        """Update arbitrary fields on a GogGame by DB id. Returns True if found."""
        result = await session.execute(select(GogGame).where(GogGame.id == game_id))
        game = result.scalars().first()
        if not game:
            return False
        for key, value in fields.items():
            if hasattr(game, key):
                setattr(game, key, value)
        return True

    @begin_session
    async def get_all(self, *, session: AsyncSession = None) -> list[GogGame]:
        result = await session.execute(select(GogGame).order_by(GogGame.title))
        return list(result.scalars().all())

    @begin_session
    async def get_all_deduped(self, *, session: AsyncSession = None) -> list[GogGame]:
        """Return one row per gog_id, preferring admin copy (owner_user_id IS NULL)."""
        from sqlalchemy import func, case, literal_column
        subq = (
            select(
                GogGame.id,
                func.row_number().over(
                    partition_by=GogGame.gog_id,
                    order_by=case(
                        (GogGame.owner_user_id.is_(None), literal_column("0")),
                        else_=literal_column("1"),
                    ),
                ).label("rn"),
            ).subquery()
        )
        result = await session.execute(
            select(GogGame)
            .join(subq, GogGame.id == subq.c.id)
            .where(subq.c.rn == 1)
            .order_by(GogGame.title)
        )
        return list(result.scalars().all())

    @begin_session
    async def count(self, *, session: AsyncSession = None) -> int:
        from sqlalchemy import func
        result = await session.execute(
            select(func.count(GogGame.id))
        )
        return result.scalar() or 0


gog_sync_handler = GogSyncHandler()
