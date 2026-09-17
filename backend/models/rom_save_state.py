"""ROM emulator save data models.

RomSaveState    - full emulator savestate (snapshot at any moment, .state file)
RomSave         - battery save / SRAM (.srm file, tied to in-game save slots)
RomSaveConflict - a second battery save for the same person and game, set aside
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RomSaveState(Base):
    """Full emulator savestate - capture of the entire emulator state.

    One row per (user, rom, slot): saving to a slot replaces whatever was there,
    exactly like a console memory card. `slot` is NULL only on legacy rows that
    predate slot support.
    """

    __tablename__ = "rom_save_states"

    rom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, index=True)

    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))     # directory on disk
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    emulator_core: Mapped[str | None] = mapped_column(String(50), nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Screenshot bytes are billed to the user's quota like any other file. Kept
    # as its own column because the thumbnail outlives its state's rewrites and
    # the quota is summed in SQL, with no disk access.
    screenshot_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    slot: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RomSave(Base):
    """Battery save file - the cartridge SRAM (.srm).

    One row per (user, rom), overwritten in place. The .srm is a single opaque
    blob holding the WHOLE SRAM chip, so the game's own in-game slots (Resident
    Evil typewriters, Zelda files) all live inside this one file - keeping
    several rows would only store copies of it from different moments.

    The uniqueness is enforced by the DB, not just by application logic: the
    player uploads SRAM from two places at once (EJS_onSaveSave and the 60s
    auto-sync), and a read-then-insert lets both racers insert.
    """

    __tablename__ = "rom_saves"
    __table_args__ = (
        UniqueConstraint("user_id", "rom_id", name="ux_save_user_rom"),
    )

    rom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, index=True)

    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    emulator_core: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)  # MD5 for dedup


class RomSaveConflict(Base):
    """A second memory card for one person and one game, waiting for them to choose.

    `rom_saves` holds one card per (user, rom), and a rename can bring two
    together: the file is renamed, a scan makes a new row for it, the player
    saves against that row before the scan pairs it with the old one - which
    already had a card. Keeping the old row's card and dropping the new one, or
    the other way round, would delete a save nobody was asked about.

    So the merge keeps the card already on the surviving row in use and sets the
    other one aside here: the file stays where it was written, this row says
    whose it is and where it lies, and its owner picks which one to keep. Only
    that person is told, and only they can see it.
    """

    __tablename__ = "rom_save_conflicts"

    rom_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("roms.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, index=True)

    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)

    emulator_core: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # When the set-aside card itself was last written, which is what the person
    # compares. `created_at` is only when the merge set it aside.
    card_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
