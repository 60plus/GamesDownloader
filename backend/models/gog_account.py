"""GogAccount model - stores GOG OAuth tokens (encrypted) and profile info."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class GogAccount(Base):
    __tablename__ = "gog_account"

    # Per-user GOG account: NULL = legacy admin account, INT = user's account
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    gog_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    gog_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    gog_created_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    games_count: Mapped[int | None] = mapped_column(nullable=True)
    movies_count: Mapped[int | None] = mapped_column(nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)   # stored encrypted
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)  # stored encrypted
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
