"""Who added which file beside a ROM game (models/rom_added_file.py).

A game's folder can hold several ROMs - the discs of a set, or two games put in
one folder over FTP - so the rows of a folder are asked for through every ROM
whose `fs_path` it is, not through one id. A row keeps the ROM it was added
from; a claim and "Remove my files" act on that ROM's rows, the way My uploads
lists them.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.rom import Rom
from models.rom_added_file import RomAddedFile


class RomAddedFileHandler(DBBaseHandler):
    model = RomAddedFile

    @begin_session
    async def in_folder(self, fs_path: str, *, session: AsyncSession = None) -> list[RomAddedFile]:
        """The rows of the files beside the game in this folder."""
        result = await session.execute(
            select(RomAddedFile)
            .join(Rom, Rom.id == RomAddedFile.rom_id)
            .where(Rom.fs_path == fs_path)
            .order_by(RomAddedFile.id)
        )
        return list(result.scalars().unique().all())

    @begin_session
    async def record(
        self, rom_id: int, fs_path: str, rel_path: str, size_bytes: int,
        published_by: int | None, *, session: AsyncSession = None,
    ) -> RomAddedFile:
        """Write down that this account brought this file in.

        One row per file of a folder: a file sent again under the same name
        replaces the bytes, so its row takes the new size and the account that
        sent them - the same as a game's file row (upload_router._finalize_upload).
        """
        found = (await session.execute(
            select(RomAddedFile)
            .join(Rom, Rom.id == RomAddedFile.rom_id)
            .where(Rom.fs_path == fs_path, RomAddedFile.rel_path == rel_path)
        )).scalars().first()
        if found is not None:
            found.size_bytes = int(size_bytes or 0)
            if published_by:
                found.published_by = published_by
            return found
        row = RomAddedFile(rom_id=rom_id, rel_path=rel_path,
                           size_bytes=int(size_bytes or 0), published_by=published_by)
        session.add(row)
        await session.flush()
        return row

    @begin_session
    async def forget(self, ids, *, session: AsyncSession = None) -> int:
        wanted = [i for i in ids if i]
        if not wanted:
            return 0
        result = await session.execute(delete(RomAddedFile).where(RomAddedFile.id.in_(wanted)))
        return int(result.rowcount or 0)

    @begin_session
    async def of_rom(self, rom_id: int, published_by: int | None = None, *,
                     session: AsyncSession = None) -> list[RomAddedFile]:
        """The rows added from this ROM, only one account's when given."""
        query = select(RomAddedFile).where(RomAddedFile.rom_id == rom_id)
        if published_by is not None:
            query = query.where(RomAddedFile.published_by == published_by)
        return list((await session.execute(query.order_by(RomAddedFile.id))).scalars().all())

    @begin_session
    async def hand_over(self, rom_id: int, from_user: int, to_user: int, *,
                        session: AsyncSession = None) -> int:
        """Move one account's files of this ROM to another, as a claim does."""
        result = await session.execute(
            update(RomAddedFile)
            .where(RomAddedFile.rom_id == rom_id, RomAddedFile.published_by == from_user)
            .values(published_by=to_user)
        )
        return int(result.rowcount or 0)

    @begin_session
    async def hand_to(self, rom_ids, to_rom_id: int, *, session: AsyncSession = None) -> int:
        """Attach these ROMs' rows to another ROM of the same folder.

        For a game leaving a folder another game stays in: the files stay with
        the folder, so their rows must not go with the leaving row (ON DELETE
        CASCADE) - they keep counting against, and belonging to, who added them.
        """
        wanted = [int(i) for i in rom_ids if i]
        if not wanted:
            return 0
        result = await session.execute(
            update(RomAddedFile).where(RomAddedFile.rom_id.in_(wanted)).values(rom_id=to_rom_id)
        )
        return int(result.rowcount or 0)

    @begin_session
    async def by_rom_of(self, user_id: int, *, session: AsyncSession = None) -> list[tuple[int, int, int]]:
        """(rom id, bytes, how many files) for each ROM this account added files to."""
        rows = (await session.execute(
            select(RomAddedFile.rom_id,
                   func.coalesce(func.sum(RomAddedFile.size_bytes), 0),
                   func.count(RomAddedFile.id))
            .where(RomAddedFile.published_by == user_id)
            .group_by(RomAddedFile.rom_id)
        )).all()
        return [(int(r), int(size or 0), int(n or 0)) for r, size, n in rows]


rom_added_file_handler = RomAddedFileHandler()
