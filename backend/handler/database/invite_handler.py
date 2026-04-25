"""Invite code CRUD handler."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select

from handler.database.session import async_session_factory
from models.invite_code import InviteCode


class InviteHandler:
    # ── Create ──────────────────────────────────────────────────────────────────

    async def create(
        self,
        created_by: str,
        max_uses: int = 1,
        expires_at: datetime | None = None,
        note: str | None = None,
    ) -> InviteCode:
        code = secrets.token_urlsafe(16)
        async with async_session_factory() as session:
            entry = InviteCode(
                code=code,
                created_by=created_by,
                max_uses=max(1, max_uses),
                expires_at=expires_at,
                note=note,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    # ── Read ─────────────────────────────────────────────────────────────────────

    async def get(self, code: str) -> InviteCode | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(InviteCode).where(InviteCode.code == code)
            )
            return result.scalar_one_or_none()

    async def get_all(self) -> list[InviteCode]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(InviteCode).order_by(InviteCode.id.desc())
            )
            return list(result.scalars().all())

    # ── Use ──────────────────────────────────────────────────────────────────────

    async def validate_and_use(self, code: str) -> bool:
        """
        Validate the invite code and increment its use counter atomically.
        Returns False if the code is invalid, inactive, exhausted, or expired.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                select(InviteCode)
                .where(InviteCode.code == code)
                .with_for_update()
            )
            entry = result.scalar_one_or_none()
            if not entry or not entry.is_active:
                return False
            if entry.use_count >= entry.max_uses:
                return False
            if entry.expires_at is not None:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                if entry.expires_at < now:
                    entry.is_active = False
                    await session.commit()
                    return False
            entry.use_count += 1
            if entry.use_count >= entry.max_uses:
                entry.is_active = False
            await session.commit()
            return True

    # ── Delete ───────────────────────────────────────────────────────────────────

    async def delete(self, invite_id: int) -> None:
        async with async_session_factory() as session:
            await session.execute(
                delete(InviteCode).where(InviteCode.id == invite_id)
            )
            await session.commit()


invite_handler = InviteHandler()
