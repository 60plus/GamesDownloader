"""LibraryFile - a downloadable file attached to a LibraryGame."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class LibraryFile(Base):
    __tablename__ = "library_files"

    library_game_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library_games.id", ondelete="CASCADE"), index=True,
    )

    # ── File info ─────────────────────────────────────────────────────────────
    filename:     Mapped[str]       = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Classification ────────────────────────────────────────────────────────
    file_type: Mapped[str]       = mapped_column(String(16),  default="game")  # game|extra|dlc
    os:        Mapped[str]       = mapped_column(String(16),  default="all")   # windows|mac|linux|all
    language:  Mapped[str | None] = mapped_column(String(8),  nullable=True)
    version:   Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Storage ───────────────────────────────────────────────────────────────
    size_bytes:   Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Relative to GD_BASE_PATH - e.g. "games/GOG/Witcher 3/windows/setup.exe"
    file_path:    Mapped[str]        = mapped_column(String(1024))
    checksum_md5: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # ── Source ────────────────────────────────────────────────────────────────
    source:       Mapped[str]  = mapped_column(String(16), default="custom")  # gog|custom
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    game: Mapped[LibraryGame] = relationship("LibraryGame", back_populates="files")


# Avoid circular import - resolve forward ref
from models.library_game import LibraryGame  # noqa: E402
