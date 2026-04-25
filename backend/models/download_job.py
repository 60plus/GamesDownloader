"""DownloadJob model - tracks individual file download tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    # Which game this download belongs to
    gog_id: Mapped[int] = mapped_column(BigInteger, index=True)
    game_title: Mapped[str] = mapped_column(String(512))

    # What is being downloaded
    file_name: Mapped[str] = mapped_column(String(512))       # e.g. "setup_game_1.0.exe"
    file_type: Mapped[str] = mapped_column(String(32), default="installer")  # installer | bonus | patch
    os_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)   # windows | mac | linux
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)       # en | pl | de ...
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # GOG API identifiers (for resolving download URL)
    installer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    downlink_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Destination
    dest_dir: Mapped[str | None] = mapped_column(String(1024), nullable=True)    # /data/games/GOG/Title/
    dest_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)   # full path incl filename

    # Progress
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # statuses: pending | queued | downloading | paused | completed | failed | cancelled
    total_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)       # bytes
    downloaded_size: Mapped[int] = mapped_column(BigInteger, default=0)             # bytes
    speed_bps: Mapped[int] = mapped_column(BigInteger, default=0)                   # bytes/sec
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)                 # 0.0–100.0
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Checksum verification (MD5 provided by GOG API)
    verify_checksum: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)   # expected MD5
    # checksum_status: None | "pending" | "ok" | "failed" | "skipped"
    checksum_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
