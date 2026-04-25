"""Invite code model - used when registration_mode = 'invite_only'."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class InviteCode(Base):
    __tablename__ = "invite_codes"

    code:        Mapped[str]            = mapped_column(String(64),  unique=True, index=True)
    created_by:  Mapped[str | None]     = mapped_column(String(64),  nullable=True)
    note:        Mapped[str | None]     = mapped_column(String(255), nullable=True)
    max_uses:    Mapped[int]            = mapped_column(Integer,     default=1)
    use_count:   Mapped[int]            = mapped_column(Integer,     default=0)
    expires_at:  Mapped[datetime | None]= mapped_column(DateTime,    nullable=True)
    is_active:   Mapped[bool]           = mapped_column(Boolean,     default=True)
