"""Game request + vote models - users propose games, others upvote."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class GameRequest(Base):
    __tablename__ = "game_requests"
    __table_args__ = (
        Index("ix_game_requests_status", "status"),
        Index("ix_game_requests_user_id", "user_id"),
    )

    title:        Mapped[str]       = mapped_column(String(255))
    description:  Mapped[str | None] = mapped_column(Text, nullable=True)
    link:         Mapped[str | None] = mapped_column(String(512), nullable=True)
    # 'games' | 'roms'
    platform:     Mapped[str]       = mapped_column(String(16), default="games")
    # for roms: fs_slug of the platform (e.g. 'snes')
    platform_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # cover from search suggestion
    cover_url:    Mapped[str | None] = mapped_column(String(512), nullable=True)
    # pending | approved | rejected | done
    status:       Mapped[str]       = mapped_column(String(16), default="pending")
    admin_note:   Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id:      Mapped[int]       = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # denormalized for display - avoids JOIN on every list fetch
    username:     Mapped[str | None] = mapped_column(String(128), nullable=True)


class GameRequestVote(Base):
    __tablename__ = "game_request_votes"
    __table_args__ = (
        UniqueConstraint("request_id", "user_id", name="uq_vote_user_request"),
        Index("ix_grv_request_id", "request_id"),
    )

    request_id: Mapped[int] = mapped_column(ForeignKey("game_requests.id", ondelete="CASCADE"))
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
