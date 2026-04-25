"""TorrentDownload - tracks admin-initiated torrent downloads to server.

Status lifecycle:
  downloading → complete  (percentDone == 1.0)
  downloading → error     (Transmission error)
  * → removed             (admin deleted before complete)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class TorrentDownload(Base):
    __tablename__ = "torrent_downloads"

    game_id:         Mapped[int | None] = mapped_column(ForeignKey("library_games.id", ondelete="SET NULL"), nullable=True)
    transmission_id: Mapped[int | None]
    info_hash:       Mapped[str | None] = mapped_column(String(64), index=True)
    status:          Mapped[str]        = mapped_column(String(16), default="downloading", index=True)
    # "downloading" | "complete" | "error" | "removed"
    title:           Mapped[str]        = mapped_column(String(512))
    os:              Mapped[str]        = mapped_column(String(16), default="windows")
    download_dir:    Mapped[str]        = mapped_column(String(1024))
    percent_done:    Mapped[float]      = mapped_column(Float, default=0.0)
    total_size:      Mapped[int]        = mapped_column(BigInteger, default=0)
    rate_download:   Mapped[int]        = mapped_column(BigInteger, default=0)
    eta:             Mapped[int]        = mapped_column(default=-1)
    error_msg:       Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by:      Mapped[str]        = mapped_column(String(64))
    completed_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
