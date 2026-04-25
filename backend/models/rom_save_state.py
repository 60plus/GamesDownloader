"""ROM emulator save data models.

RomSaveState - full emulator savestate (snapshot at any moment, .state file)
RomSave      - battery save / SRAM (.srm file, tied to in-game save slots)
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class RomSaveState(Base):
    """Full emulator savestate - capture of the entire emulator state."""

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


class RomSave(Base):
    """Battery save file - in-game SRAM (.srm) tied to game save slots."""

    __tablename__ = "rom_saves"

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
