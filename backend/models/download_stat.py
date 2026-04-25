"""DownloadStat - records each file download for statistics."""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class DownloadStat(Base):
    __tablename__ = "download_stats"

    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )
    library_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_files.id", ondelete="CASCADE"), index=True,
    )

    bytes_transferred: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    filename:          Mapped[str | None] = mapped_column(String(512), nullable=True)
