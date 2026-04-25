"""ClamAV scan result database handler."""
from __future__ import annotations

import logging

from sqlalchemy import select, desc

from handler.database.session import async_session_factory
from models.scan_result import ScanResult

logger = logging.getLogger(__name__)
_MAX_SCANS = 200  # keep last N scan records


class ScanHandler:

    async def create(
        self,
        scan_type: str = "manual",
        paths: str | None = None,
        triggered_by: str | None = None,
    ) -> ScanResult:
        """Create a new scan record in 'running' state and return it."""
        entry = ScanResult(
            scan_type=scan_type,
            paths=paths,
            status="running",
            triggered_by=triggered_by,
        )
        async with async_session_factory() as session:
            session.add(entry)
            await session.commit()
            await session.refresh(entry)
            return entry

    async def update(self, scan_id: int, **kwargs) -> None:
        """Update fields on an existing scan record."""
        async with async_session_factory() as session:
            entry = await session.get(ScanResult, scan_id)
            if entry:
                for k, v in kwargs.items():
                    setattr(entry, k, v)
                await session.commit()

    async def get(self, scan_id: int) -> ScanResult | None:
        async with async_session_factory() as session:
            return await session.get(ScanResult, scan_id)

    async def get_recent(self, limit: int = 50) -> list[ScanResult]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(ScanResult).order_by(desc(ScanResult.created_at)).limit(limit)
            )
            return list(result.scalars().all())

    async def _trim(self) -> None:
        """Keep only the newest _MAX_SCANS records."""
        from sqlalchemy import func, delete
        async with async_session_factory() as session:
            count = (await session.execute(
                select(func.count()).select_from(ScanResult)
            )).scalar_one()
            if count > _MAX_SCANS:
                cutoff_row = (await session.execute(
                    select(ScanResult.id)
                    .order_by(desc(ScanResult.created_at))
                    .offset(_MAX_SCANS - 1)
                    .limit(1)
                )).scalar_one_or_none()
                if cutoff_row:
                    await session.execute(
                        delete(ScanResult).where(ScanResult.id < cutoff_row)
                    )
                    await session.commit()


scan_handler = ScanHandler()
