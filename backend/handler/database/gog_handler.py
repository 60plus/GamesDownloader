"""GOG games database handler."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.gog_game import GogGame


class GogDbHandler(DBBaseHandler):
    model = GogGame

    @begin_session
    async def get_by_gog_id(self, gog_id: int, *, session: AsyncSession = None) -> GogGame | None:
        stmt = select(GogGame).where(GogGame.gog_id == gog_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @begin_session
    async def search(
        self, query: str, *, limit: int = 50, session: AsyncSession = None
    ) -> Sequence[GogGame]:
        stmt = (
            select(GogGame)
            .where(GogGame.title.ilike(f"%{query}%"))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    @begin_session
    async def get_all_gog_ids(self, *, session: AsyncSession = None) -> set[int]:
        stmt = select(GogGame.gog_id)
        result = await session.execute(stmt)
        return set(result.scalars().all())

    @begin_session
    async def upsert(self, gog_id: int, data: dict, *, session: AsyncSession = None) -> GogGame:
        existing = await session.execute(
            select(GogGame).where(GogGame.gog_id == gog_id)
        )
        game = existing.scalar_one_or_none()
        if game:
            for key, value in data.items():
                if hasattr(game, key):
                    setattr(game, key, value)
        else:
            game = GogGame(gog_id=gog_id, **data)
            session.add(game)
        await session.flush()
        await session.refresh(game)
        return game

    @begin_session
    async def count(self, *, session: AsyncSession = None) -> int:
        stmt = select(func.count()).select_from(GogGame)
        result = await session.execute(stmt)
        return result.scalar_one()
