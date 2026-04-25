"""ClamAV quarantine - one row per quarantined file."""
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Integer

from models.base import Base


class QuarantineEntry(Base):
    __tablename__ = "quarantine_entries"

    # Where the file originally lived (for restore)
    original_path:   Mapped[str]        = mapped_column(Text)
    # Where the file is now (inside /data/clamav/quarantine/)
    quarantine_path: Mapped[str]        = mapped_column(Text)
    # Threat name reported by ClamAV
    threat:          Mapped[str]        = mapped_column(String(256))
    # Original filename (display only)
    filename:        Mapped[str]        = mapped_column(String(512))
    # File size in bytes at time of quarantine
    file_size:       Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which scan triggered this (nullable - could be auto-scan)
    scan_id:         Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Who triggered the scan
    triggered_by:    Mapped[str | None] = mapped_column(String(128), nullable=True)
