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

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _expired(entry: InviteCode, now: datetime) -> bool:
        return entry.expires_at is not None and entry.expires_at < now

    @classmethod
    def _usable(cls, entry: InviteCode | None, now: datetime) -> bool:
        """Whether a code may still be redeemed. Pure: no writes, no commit.

        The single statement of what makes a code good, so the look and the
        redemption can never come to different answers.
        """
        if not entry or not entry.is_active:
            return False
        if entry.use_count >= entry.max_uses:
            return False
        return not cls._expired(entry, now)

    async def check(self, code: str) -> bool:
        """Whether this code would be accepted, WITHOUT spending it.

        Used to decide whether a registration form is worth showing. It must
        not consume a use, or merely opening the invite link would burn it.
        """
        if not code:
            return False
        async with async_session_factory() as session:
            result = await session.execute(
                select(InviteCode).where(InviteCode.code == code)
            )
            return self._usable(result.scalar_one_or_none(), self._now())

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
            now = self._now()
            if not self._usable(entry, now):
                # Retire a code the clock has run out on, so it stops being
                # offered as active in the admin list.
                if entry is not None and entry.is_active and self._expired(entry, now):
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
