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
        """Record one completed download of a link that has no limit.

        Exhaustion is not decided here. It used to set is_active to False, which
        reads as "somebody revoked this" everywhere the status is worked out -
        so an exhausted link never showed as exhausted, and the branch that says
        so could not be reached. A link that has run out of uses says that
        through its count, which is what is_valid reads.
        """
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
            await session.commit()

    async def reserve_use(self, token_id: int) -> bool:
        """Take one use of a limited link before serving it, or refuse.

        Counting on the way out cannot hold a limit. The check and the increment
        were at opposite ends of a transfer that runs for minutes, so three
        requests arriving together all passed a check that said nought of one
        used, and all three were served - a link limited to a single download
        handing out three copies.

        The condition and the increment are one statement here, so the database
        decides who gets the last use. Returns False when there was none left,
        and the caller turns the request away.
        """
        async with async_session_factory() as session:
            result = await session.execute(
                update(DownloadToken)
                .where(
                    DownloadToken.id == token_id,
                    DownloadToken.is_active.is_(True),
                    DownloadToken.max_downloads.isnot(None),
                    DownloadToken.download_count < DownloadToken.max_downloads,
                )
                .values(download_count=DownloadToken.download_count + 1)
            )
            await session.commit()
            return bool(result.rowcount)

    async def release_use(self, token_id: int) -> None:
        """Hand back a use the transfer did not spend.

        A link limited to one download must not be spent by a request that
        dropped at four percent. The use is taken up front because that is the
        only place a limit can be enforced, and given back here when the file
        did not go over in full.
        """
        async with async_session_factory() as session:
            await session.execute(
                update(DownloadToken)
                .where(DownloadToken.id == token_id, DownloadToken.download_count > 0)
                .values(download_count=DownloadToken.download_count - 1)
            )
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
