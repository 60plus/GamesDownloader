"""Quarantine database handler."""
from __future__ import annotations

import logging

from sqlalchemy import select, desc

from handler.database.session import async_session_factory
from models.quarantine_entry import QuarantineEntry

logger = logging.getLogger(__name__)


class QuarantineHandler:

    async def create(
        self,
        original_path: str,
        quarantine_path: str,
        threat: str,
        filename: str,
        file_size: int | None = None,
        scan_id: int | None = None,
        triggered_by: str | None = None,
    ) -> QuarantineEntry:
        entry = QuarantineEntry(
            original_path=original_path,
            quarantine_path=quarantine_path,
            threat=threat,
            filename=filename,
            file_size=file_size,
            scan_id=scan_id,
            triggered_by=triggered_by,
        )
        async with async_session_factory() as session:
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def get(self, entry_id: int) -> QuarantineEntry | None:
        async with async_session_factory() as session:
            return await session.get(QuarantineEntry, entry_id)

    async def get_all(self) -> list[QuarantineEntry]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(QuarantineEntry).order_by(desc(QuarantineEntry.created_at))
            )
            return list(result.scalars().all())

    async def delete(self, entry_id: int) -> bool:
        async with async_session_factory() as session:
            entry = await session.get(QuarantineEntry, entry_id)
            if not entry:
                return False
            await session.delete(entry)
            await session.commit()
            return True


quarantine_handler = QuarantineHandler()
