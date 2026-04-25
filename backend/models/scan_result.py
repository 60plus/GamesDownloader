"""ClamAV scan result - one row per scan run."""
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Text, Integer

from models.base import Base


class ScanResult(Base):
    __tablename__ = "scan_results"

    # "manual" | "auto_upload" | "auto_download"
    scan_type:      Mapped[str]        = mapped_column(String(32), default="manual")
    # Comma-separated list of top-level paths that were scanned
    paths:          Mapped[str | None] = mapped_column(Text, nullable=True)
    # "running" | "complete" | "error" | "cancelled"
    status:         Mapped[str]        = mapped_column(String(16), default="running")
    total_files:    Mapped[int]        = mapped_column(Integer, default=0)
    infected_count: Mapped[int]        = mapped_column(Integer, default=0)
    clean_count:    Mapped[int]        = mapped_column(Integer, default=0)
    error_count:    Mapped[int]        = mapped_column(Integer, default=0)
    # JSON array of {"path": "...", "threat": "..."} objects for infected files
    infected_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Error or cancellation message
    error_message:  Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by:   Mapped[str | None] = mapped_column(String(128), nullable=True)
