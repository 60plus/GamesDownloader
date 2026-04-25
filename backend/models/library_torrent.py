"""LibraryTorrent - tracks .torrent seeds generated for user downloads.

One record per generated seed torrent. Status lifecycle:
  seeding → expired   (after one full upload detected by seed_monitor)
  seeding → error     (Transmission lost the torrent)
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class LibraryTorrent(Base):
    __tablename__ = "library_torrents"

    file_id:         Mapped[int]        = mapped_column(ForeignKey("library_files.id", ondelete="CASCADE"), index=True)
    transmission_id: Mapped[int | None]
    info_hash:       Mapped[str | None] = mapped_column(String(64), index=True)
    torrent_path:    Mapped[str | None] = mapped_column(String(1024))
    status:          Mapped[str]        = mapped_column(String(16), default="seeding", index=True)
    # "seeding" | "expired" | "error"
    file_size:       Mapped[int | None] = mapped_column(BigInteger)
    created_by:      Mapped[str]        = mapped_column(String(64))
