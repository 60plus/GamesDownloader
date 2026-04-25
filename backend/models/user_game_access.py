"""UserGameAccess - per-game access overrides (allow / deny) per user."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class UserGameAccess(Base):
    __tablename__ = "user_game_access"
    __table_args__ = (
        UniqueConstraint("user_id", "library_game_id", name="uq_user_game"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )
    # "deny"  → block user from this game regardless of library access
    # "allow" → explicitly allow even if library access is revoked (future use)
    access: Mapped[str] = mapped_column(String(8), default="deny")
