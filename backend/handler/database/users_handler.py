"""User database handler."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.user import User


class UsersHandler(DBBaseHandler):
    model = User

    @begin_session
    async def get_by_username(self, username: str, *, session: AsyncSession = None) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, obj: User, data: dict[str, Any]) -> User:  # type: ignore[override]
        """Update wrapper that invalidates the auth cache after the write.

        Bypassing the parent class's @begin_session would be a refactor.
        Instead we delegate to the base implementation and then drop both
        the old and new username keys from the cache so the next request
        sees the fresh row regardless of whether `username` itself changed.
        """
        old_username = getattr(obj, "username", None)
        fresh = await DBBaseHandler.update(self, obj, data)
        try:
            from handler.auth.user_cache import invalidate_user_cache
            await invalidate_user_cache(old_username)
            new_username = getattr(fresh, "username", None)
            if new_username and new_username != old_username:
                await invalidate_user_cache(new_username)
        except Exception:
            pass  # cache miss-on-stale is acceptable, never block the write
        return fresh

    async def delete(self, obj: User) -> None:  # type: ignore[override]
        username = getattr(obj, "username", None)
        await DBBaseHandler.delete(self, obj)
        try:
            from handler.auth.user_cache import invalidate_user_cache
            await invalidate_user_cache(username)
        except Exception:
            pass

    @begin_session
    async def get_by_email(self, email: str, *, session: AsyncSession = None) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @begin_session
    async def count(self, *, session: AsyncSession = None) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(User)
        result = await session.execute(stmt)
        return result.scalar_one()

    @begin_session
    async def update_first_user_avatar(
        self, avatar_path: str, *, session: AsyncSession = None
    ) -> bool:
        """Set avatar_path on the first user - all in a single session to avoid detached-instance issues."""
        stmt = select(User).limit(1)
        result = await session.execute(stmt)
        user = result.scalars().first()
        if not user:
            return False
        user.avatar_path = avatar_path
        # Drop the cached snapshot so the next request sees the new avatar.
        try:
            from handler.auth.user_cache import invalidate_user_cache
            await invalidate_user_cache(user.username)
        except Exception:
            pass
        return True
