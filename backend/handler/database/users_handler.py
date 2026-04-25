"""User database handler."""

from __future__ import annotations

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
        return True
