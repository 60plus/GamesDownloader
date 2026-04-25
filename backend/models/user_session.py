"""User session model - tracks active JWT sessions for revocation and visibility."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    username:    Mapped[str]            = mapped_column(String(64),  index=True)
    access_jti:  Mapped[str]            = mapped_column(String(64),  unique=True, index=True)
    refresh_jti: Mapped[str]            = mapped_column(String(64),  unique=True, index=True)
    ip_address:  Mapped[str | None]     = mapped_column(String(64),  nullable=True)
    user_agent:  Mapped[str | None]     = mapped_column(String(512), nullable=True)
    last_used:   Mapped[datetime | None] = mapped_column(nullable=True)
    is_active:   Mapped[bool]           = mapped_column(default=True)
