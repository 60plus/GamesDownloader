"""User session CRUD - create, list, revoke JWT sessions."""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis
from sqlalchemy import select, update

from config import ACCESS_TOKEN_EXPIRE_MINUTES, REDIS_URL
from handler.database.session import async_session_factory
from models.user_session import UserSession

_REVOKED_PREFIX = "revoked_jti:"


def _redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True)


class SessionHandler:
    async def create(
        self,
        username:    str,
        access_jti:  str,
        refresh_jti: str,
        ip_address:  str | None = None,
        user_agent:  str | None = None,
    ) -> UserSession:
        async with async_session_factory() as db:
            session = UserSession(
                username=username,
                access_jti=access_jti,
                refresh_jti=refresh_jti,
                ip_address=ip_address,
                user_agent=user_agent,
                last_used=datetime.now(timezone.utc),
                is_active=True,
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return session

    async def get_active_for_user(self, username: str) -> list[UserSession]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession)
                .where(UserSession.username == username, UserSession.is_active == True)
                .order_by(UserSession.id.desc())
            )
            return list(result.scalars().all())

    async def get_all_active(self) -> list[UserSession]:
        """Admin: list all active sessions across all users."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession)
                .where(UserSession.is_active == True)
                .order_by(UserSession.id.desc())
            )
            return list(result.scalars().all())

    async def get_by_refresh_jti(self, refresh_jti: str) -> UserSession | None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession).where(UserSession.refresh_jti == refresh_jti)
            )
            return result.scalar_one_or_none()

    async def get_by_access_jti(self, access_jti: str) -> UserSession | None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession).where(UserSession.access_jti == access_jti)
            )
            return result.scalar_one_or_none()

    async def get_by_id(self, session_id: int) -> UserSession | None:
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession).where(UserSession.id == session_id)
            )
            return result.scalar_one_or_none()

    async def revoke(self, session_id: int) -> bool:
        async with async_session_factory() as db:
            # Fetch access_jti before revoking so we can blocklist it in Redis
            row = await db.execute(
                select(UserSession.access_jti)
                .where(UserSession.id == session_id, UserSession.is_active == True)
            )
            access_jti = row.scalar_one_or_none()

            result = await db.execute(
                update(UserSession)
                .where(UserSession.id == session_id, UserSession.is_active == True)
                .values(is_active=False)
            )
            await db.commit()

        if access_jti and result.rowcount > 0:
            await self._blocklist_jti(access_jti)

        return result.rowcount > 0

    async def revoke_all_for_user(self, username: str) -> int:
        async with async_session_factory() as db:
            # Fetch all active access_jtis before revoking
            rows = await db.execute(
                select(UserSession.access_jti)
                .where(UserSession.username == username, UserSession.is_active == True)
            )
            jtis = [r for r in rows.scalars().all() if r]

            result = await db.execute(
                update(UserSession)
                .where(UserSession.username == username, UserSession.is_active == True)
                .values(is_active=False)
            )
            await db.commit()

        for jti in jtis:
            await self._blocklist_jti(jti)

        return result.rowcount

    async def _blocklist_jti(self, access_jti: str) -> None:
        """Add access JTI to Redis blocklist with TTL = access token lifetime."""
        ttl = ACCESS_TOKEN_EXPIRE_MINUTES * 60
        async with _redis() as r:
            await r.setex(f"{_REVOKED_PREFIX}{access_jti}", ttl, "1")

    async def update_access_jti(self, refresh_jti: str, new_access_jti: str) -> None:
        """Called on token refresh - update access_jti and last_used."""
        async with async_session_factory() as db:
            await db.execute(
                update(UserSession)
                .where(UserSession.refresh_jti == refresh_jti)
                .values(access_jti=new_access_jti, last_used=datetime.now(timezone.utc))
            )
            await db.commit()

    async def touch(self, access_jti: str) -> None:
        """Update last_used timestamp for the session (called from middleware)."""
        async with async_session_factory() as db:
            await db.execute(
                update(UserSession)
                .where(UserSession.access_jti == access_jti, UserSession.is_active == True)
                .values(last_used=datetime.now(timezone.utc))
            )
            await db.commit()

    async def is_revoked(self, refresh_jti: str) -> bool:
        """Check if a refresh token's session has been revoked."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(UserSession.is_active)
                .where(UserSession.refresh_jti == refresh_jti)
            )
            val = result.scalar_one_or_none()
            if val is None:
                return False  # unknown jti - allow (legacy tokens before session tracking)
            return not val


session_handler = SessionHandler()
