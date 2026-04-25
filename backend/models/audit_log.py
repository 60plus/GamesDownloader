"""Audit log - records security-relevant events."""
from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Index, String, Text

from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
    )

    action:     Mapped[str]        = mapped_column(String(64))
    username:   Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64),  nullable=True)
    details:    Mapped[str | None] = mapped_column(Text,         nullable=True)
    status:     Mapped[str]        = mapped_column(String(16), default="ok")
