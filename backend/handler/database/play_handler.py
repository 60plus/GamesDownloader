"""Database handler for per-user ROM play history (dashboard "Recently played").

record_start / record_end use MySQL INSERT ... ON DUPLICATE KEY UPDATE so the
one-row-per-(user, rom) upsert is atomic - no read-modify-write race even if two
play events for the same ROM arrive back to back.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.rom_play import RomPlay


class PlayHandler(DBBaseHandler):
    model = RomPlay

    @begin_session
    async def record_start(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> None:
        """A ROM was launched: bump last_played_at + play_count (insert or update)."""
        now = datetime.utcnow()
        stmt = mysql_insert(RomPlay).values(
            user_id=user_id, rom_id=rom_id,
            last_played_at=now, play_count=1, seconds_played=0,
        )
        stmt = stmt.on_duplicate_key_update(
            last_played_at=now,
            play_count=RomPlay.play_count + 1,
        )
        await session.execute(stmt)

    @begin_session
    async def record_end(
        self, user_id: int, rom_id: int, seconds: int, *, session: AsyncSession = None
    ) -> None:
        """A play session ended: add elapsed seconds. Tolerates a missing start row
        (e.g. the play/start POST was lost) by inserting one."""
        secs = max(0, int(seconds or 0))
        if secs == 0:
            return
        now = datetime.utcnow()
        stmt = mysql_insert(RomPlay).values(
            user_id=user_id, rom_id=rom_id,
            last_played_at=now, play_count=1, seconds_played=secs,
        )
        stmt = stmt.on_duplicate_key_update(
            seconds_played=RomPlay.seconds_played + secs,
        )
        await session.execute(stmt)

    @begin_session
    async def get_play(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> RomPlay | None:
        return (await session.execute(
            select(RomPlay).where(RomPlay.user_id == user_id, RomPlay.rom_id == rom_id)
        )).scalar_one_or_none()


play_handler = PlayHandler()
