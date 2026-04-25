"""DownloadToken - shareable, time-limited, optionally password-protected download link."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class DownloadToken(Base):
    __tablename__ = "download_tokens"

    token:          Mapped[str]            = mapped_column(String(64),   unique=True, index=True)
    file_id:        Mapped[int]            = mapped_column(Integer)              # no FK - survives file deletion
    file_name:      Mapped[str]            = mapped_column(String(512))          # denormalized
    game_title:     Mapped[str | None]     = mapped_column(String(512),  nullable=True)
    created_by:     Mapped[str]            = mapped_column(String(128))
    expires_at:     Mapped[datetime | None]= mapped_column(DateTime,     nullable=True)
    max_downloads:  Mapped[int | None]     = mapped_column(Integer,      nullable=True)  # None = unlimited
    download_count: Mapped[int]            = mapped_column(Integer,      default=0)
    password_hash:  Mapped[str | None]     = mapped_column(String(256),  nullable=True)
    note:           Mapped[str | None]     = mapped_column(String(256),  nullable=True)
    is_active:      Mapped[bool]           = mapped_column(Boolean,      default=True)
