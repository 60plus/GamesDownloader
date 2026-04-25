"""Download token CRUD handler."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from handler.database.session import async_session_factory
from models.download_token import DownloadToken


class DownloadTokenHandler:

    async def create(
        self,
        file_id:       int,
        file_name:     str,
        game_title:    str | None,
        created_by:    str,
        expires_at:    datetime | None = None,
        max_downloads: int | None = None,
        password_hash: str | None = None,
        note:          str | None = None,
    ) -> DownloadToken:
        token = secrets.token_urlsafe(32)
        async with async_session_factory() as session:
            entry = DownloadToken(
                token=token,
                file_id=file_id,
                file_name=file_name,
                game_title=game_title,
                created_by=created_by,
                expires_at=expires_at,
                max_downloads=max_downloads,
                download_count=0,
                password_hash=password_hash,
                note=note,
                is_active=True,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def get_by_token(self, token: str) -> DownloadToken | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DownloadToken).where(DownloadToken.token == token)
            )
            return result.scalar_one_or_none()

    async def get_all(self) -> list[DownloadToken]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DownloadToken).order_by(DownloadToken.id.desc())
            )
            return list(result.scalars().all())

    async def revoke(self, token_id: int) -> None:
        async with async_session_factory() as session:
            await session.execute(
                update(DownloadToken)
                .where(DownloadToken.id == token_id)
                .values(is_active=False)
            )
            await session.commit()

    async def delete(self, token_id: int) -> None:
        async with async_session_factory() as session:
            await session.execute(
                delete(DownloadToken).where(DownloadToken.id == token_id)
            )
            await session.commit()

    async def increment_count(self, token_id: int) -> None:
        """Atomically increment download_count and deactivate if max reached."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(DownloadToken)
                .where(DownloadToken.id == token_id)
                .with_for_update()
            )
            entry = result.scalar_one_or_none()
            if not entry:
                return
            entry.download_count += 1
            if entry.max_downloads is not None and entry.download_count >= entry.max_downloads:
                entry.is_active = False
            await session.commit()

    def is_valid(self, token: DownloadToken) -> bool:
        """Check if a token is currently usable (active, not expired, not exhausted)."""
        if not token.is_active:
            return False
        if token.expires_at is not None:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if token.expires_at < now:
                return False
        if token.max_downloads is not None and token.download_count >= token.max_downloads:
            return False
        return True


download_token_handler = DownloadTokenHandler()
