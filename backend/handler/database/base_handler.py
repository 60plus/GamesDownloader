"""Base class for all database handlers.

Provides async session management via the @begin_session decorator.
Subclasses implement domain-specific queries.
"""

from __future__ import annotations

from typing import Any, Sequence, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from models.base import Base

T = TypeVar("T", bound=Base)


class DBBaseHandler:
    """Shared CRUD operations for any model extending Base."""

    model: type[T]

    @begin_session
    async def get_by_id(self, id: int, *, session: AsyncSession = None) -> T | None:
        return await session.get(self.model, id)

    @begin_session
    async def get_all(
        self, *, limit: int = 100, offset: int = 0, session: AsyncSession = None
    ) -> Sequence[T]:
        stmt = select(self.model).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return result.scalars().all()

    @begin_session
    async def create(self, obj: T, *, session: AsyncSession = None) -> T:
        session.add(obj)
        await session.flush()
        await session.refresh(obj)
        return obj

    @begin_session
    async def update(self, obj: T, data: dict[str, Any], *, session: AsyncSession = None) -> T:
        # Re-fetch by primary key so the object is bound to *this* session.
        # The caller's obj may come from a different (already-closed) session
        # (e.g. request.state.user from auth middleware), which would cause
        # SQLAlchemy's "instance is not persistent" error on flush/refresh.
        fresh = await session.get(self.model, obj.id)
        if fresh is None:
            raise ValueError(f"{self.model.__name__} id={obj.id} not found")
        for key, value in data.items():
            if hasattr(fresh, key):
                setattr(fresh, key, value)
        await session.flush()
        await session.refresh(fresh)
        return fresh

    @begin_session
    async def delete(self, obj: T, *, session: AsyncSession = None) -> None:
        # Re-fetch by primary key so the object belongs to this session
        fresh = await session.get(self.model, obj.id)
        if fresh is not None:
            await session.delete(fresh)
