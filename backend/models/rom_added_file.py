"""RomAddedFile - a file an account put beside a ROM game, in its extras/ or mods/.

The files beside a game are read off the disk (handler/roms/game_extras.py):
they are put there over FTP as often as through the page, and a list that asked
the database would miss the first kind. What the disk cannot say is who brought
a file in, and that is what the upload quota sums by - a LibraryFile carries it
for a game's files, a Rom row for a ROM. A file added to a ROM's folder through
the page (the owner, 2026-09-18: "Add file" on a ROM, for administrators and
uploaders alike) gets a row here, so it counts against the account that added
it and that account may take it away again.

A file put there over FTP has no row: it counts against nobody, and only an
administrator removes it on its own.

`rel_path` is relative to the game's folder ("extras/Maps/World.png"), and the
folder is the ROM's own `fs_path`. Relative, like a ROM's `manual_path`, so a
folder renamed after the game's title takes its rows along without anybody
rewriting them. The row hangs off the ROM the page was showing and goes with
it: a ROM deleted with its files takes its extras too (decision D).
"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RomAddedFile(Base):
    __tablename__ = "rom_added_files"

    rom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roms.id", ondelete="CASCADE"), index=True,
    )
    rel_path: Mapped[str] = mapped_column(String(1024))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
