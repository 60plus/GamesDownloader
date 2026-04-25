"""Audit log database handler."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select, desc

from handler.database.session import async_session_factory
from models.audit_log import AuditLog

logger = logging.getLogger(__name__)
_MAX_LOGS = 10_000   # rolling maximum kept in DB


class AuditHandler:
    async def log(
        self,
        action: str,
        username: str | None = None,
        ip_address: str | None = None,
        details: dict | str | None = None,
        status: str = "ok",
    ) -> None:
        detail_str = None
        if isinstance(details, dict):
            detail_str = json.dumps(details, ensure_ascii=False)
        elif isinstance(details, str):
            detail_str = details

        entry = AuditLog(
            action=action,
            username=username,
            ip_address=ip_address,
            details=detail_str,
            status=status,
        )
        try:
            async with async_session_factory() as session:
                session.add(entry)
                await session.commit()
        except Exception:
            logger.exception("Failed to write audit log entry")
            return
        # Rolling trim runs in its own session so it doesn't reuse the
        # already-committed (and closed) session above.
        try:
            await self._trim()
        except Exception:
            logger.warning("Audit log trim failed - non-critical")

    async def _trim(self) -> None:
        from sqlalchemy import func, delete
        async with async_session_factory() as session:
            count_result = await session.execute(
                select(func.count()).select_from(AuditLog)
            )
            count = count_result.scalar_one()
            if count > _MAX_LOGS:
                cutoff_result = await session.execute(
                    select(AuditLog.id).order_by(desc(AuditLog.created_at)).offset(_MAX_LOGS - 1).limit(1)
                )
                cutoff_id = cutoff_result.scalar_one_or_none()
                if cutoff_id:
                    await session.execute(delete(AuditLog).where(AuditLog.id < cutoff_id))
                    await session.commit()

    async def get_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        action_filter: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        async with async_session_factory() as session:
            from sqlalchemy import func
            stmt = select(AuditLog).order_by(desc(AuditLog.created_at))
            count_stmt = select(func.count()).select_from(AuditLog)
            if action_filter:
                stmt = stmt.where(AuditLog.action.ilike(f"%{action_filter}%"))
                count_stmt = count_stmt.where(AuditLog.action.ilike(f"%{action_filter}%"))
            total = (await session.execute(count_stmt)).scalar_one()
            result = await session.execute(stmt.offset(offset).limit(limit))
            return result.scalars().all(), total

    async def get_known_ips(self, username: str, limit: int = 200) -> set[str]:
        """Return IPs from previous successful logins for a user (for new-IP detection)."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(AuditLog.ip_address)
                .where(
                    AuditLog.username == username,
                    AuditLog.action == "login_ok",
                    AuditLog.ip_address.isnot(None),
                )
                .order_by(desc(AuditLog.created_at))
                .limit(limit)
            )
            return {r for r in result.scalars().all() if r}

    async def clear_all(self) -> None:
        async with async_session_factory() as session:
            from sqlalchemy import delete
            await session.execute(delete(AuditLog))
            await session.commit()


audit_handler = AuditHandler()
