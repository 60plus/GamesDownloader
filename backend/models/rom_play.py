"""Per-user ROM play history - powers the dashboard "Recently played" section.

One row per (user, rom). It is touched when the in-browser player launches a ROM
(last_played_at + play_count) and when the session ends (seconds_played). Unlike
a savestate, a row here just means the game was *launched* - so "Recently played"
lists everything the user played, while "Continue playing" stays save-based.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RomPlay(Base):
    __tablename__ = "rom_plays"
    __table_args__ = (
        UniqueConstraint("user_id", "rom_id", name="uq_rom_play_user_rom"),
    )

    rom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, index=True)

    last_played_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    seconds_played: Mapped[int] = mapped_column(BigInteger, default=0)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
