"""Library database handler - LibraryGame, LibraryFile, DownloadStat, UserGameAccess."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.download_stat import DownloadStat
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.user_game_access import UserGameAccess


class LibraryHandler(DBBaseHandler):
    model = LibraryGame

    # ── Games ─────────────────────────────────────────────────────────────────

    @begin_session
    async def get_by_slug(self, slug: str, *, session: AsyncSession = None) -> LibraryGame | None:
        stmt = select(LibraryGame).where(LibraryGame.slug == slug)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @begin_session
    async def get_by_gog_game_id(self, gog_game_id: int, *, session: AsyncSession = None) -> LibraryGame | None:
        stmt = select(LibraryGame).where(LibraryGame.gog_game_id == gog_game_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _active_filters(self, stmt, search, in_default_only, library_id):
        stmt = stmt.where(LibraryGame.is_active == True)  # noqa: E712
        if search:
            stmt = stmt.where(LibraryGame.title.ilike(f"%{search}%"))
        if in_default_only:
            stmt = stmt.where(LibraryGame.in_default_library == True)  # noqa: E712
        if library_id is not None:
            from models.library import LibraryMembership
            stmt = stmt.where(LibraryGame.id.in_(
                select(LibraryMembership.library_game_id)
                .where(LibraryMembership.library_id == library_id)
            ))
        return stmt

    @staticmethod
    def _apply_sort(stmt, sort: str):
        """Server-side sort. MariaDB has no NULLS LAST, so nullable sort keys
        order by IS NULL first to push the unrated / undated rows to the end."""
        if sort == "title_desc":
            return stmt.order_by(LibraryGame.title.desc())
        if sort == "rating_desc":
            return stmt.order_by(LibraryGame.rating.is_(None),
                                 LibraryGame.rating.desc(), LibraryGame.title)
        if sort == "release_desc":
            return stmt.order_by(LibraryGame.release_date.is_(None),
                                 LibraryGame.release_date.desc(), LibraryGame.title)
        if sort == "created_desc":
            return stmt.order_by(LibraryGame.id.desc())
        return stmt.order_by(LibraryGame.title)

    @begin_session
    async def get_all_active(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
        in_default_only: bool = False,
        library_id: int | None = None,
        sort: str = "title_asc",
        session: AsyncSession = None,
    ) -> Sequence[LibraryGame]:
        stmt = self._active_filters(select(LibraryGame), search, in_default_only, library_id)
        stmt = self._apply_sort(stmt, sort).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return result.scalars().all()

    @begin_session
    async def get_by_ids(
        self, ids: list[int], *, session: AsyncSession = None
    ) -> Sequence[LibraryGame]:
        """Full rows for an explicit id list, returned in the given order -
        lets callers rank games on the slim home-meta rows (e.g. by the
        aggregate rating) and then load only the winners."""
        if not ids:
            return []
        stmt = select(LibraryGame).where(LibraryGame.id.in_(ids))
        rows = (await session.execute(stmt)).scalars().all()
        order = {gid: i for i, gid in enumerate(ids)}
        return sorted(rows, key=lambda g: order.get(g.id, len(order)))

    @begin_session
    async def get_popular(
        self, limit: int = 12, *, session: AsyncSession = None
    ) -> list[tuple[LibraryGame, int]]:
        """Active default-library games ordered by all-time download count.
        Returns (game, download_count) pairs - the storefront 'popular' rail."""
        counts = (
            select(
                DownloadStat.library_game_id.label("gid"),
                func.count().label("dl"),
            )
            .group_by(DownloadStat.library_game_id)
            .subquery()
        )
        stmt = (
            select(LibraryGame, counts.c.dl)
            .join(counts, LibraryGame.id == counts.c.gid)
            .where(
                LibraryGame.is_active == True,  # noqa: E712
                LibraryGame.in_default_library == True,  # noqa: E712
            )
            .order_by(counts.c.dl.desc(), LibraryGame.title)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    @begin_session
    async def count_active(
        self,
        search: str | None = None,
        *,
        in_default_only: bool = False,
        library_id: int | None = None,
        session: AsyncSession = None,
    ) -> int:
        stmt = self._active_filters(select(func.count()).select_from(LibraryGame),
                                    search, in_default_only, library_id)
        result = await session.execute(stmt)
        return result.scalar_one()

    @begin_session
    async def get_home_meta(self, *, session: AsyncSession = None) -> list:
        """Slim per-game metadata rows for the WHOLE default library - feeds
        the home aggregations (genre tiles, trailer pool) without loading the
        files relationship or the heavy media columns of every game."""
        stmt = select(
            LibraryGame.id,
            LibraryGame.gog_game_id,
            LibraryGame.source,
            LibraryGame.title,
            LibraryGame.description_short,
            LibraryGame.cover_path,
            LibraryGame.background_path,
            LibraryGame.genres,
            LibraryGame.rating,
            LibraryGame.meta_ratings,
            LibraryGame.hltb_main_s,
            LibraryGame.video_path,
            LibraryGame.videos,
        ).where(
            LibraryGame.is_active == True,  # noqa: E712
            LibraryGame.in_default_library == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        return list(result.all())

    # ── Files ─────────────────────────────────────────────────────────────────

    @begin_session
    async def get_file_by_id(self, file_id: int, *, session: AsyncSession = None) -> LibraryFile | None:
        return await session.get(LibraryFile, file_id)

    @begin_session
    async def get_files_for_game(
        self, game_id: int, *, session: AsyncSession = None
    ) -> Sequence[LibraryFile]:
        stmt = select(LibraryFile).where(LibraryFile.library_game_id == game_id)
        result = await session.execute(stmt)
        return result.scalars().all()

    @begin_session
    async def create_file(self, file: LibraryFile, *, session: AsyncSession = None) -> LibraryFile:
        session.add(file)
        await session.flush()
        await session.refresh(file)
        return file

    @begin_session
    async def update_file(
        self, file: LibraryFile, data: dict[str, Any], *, session: AsyncSession = None
    ) -> LibraryFile:
        fresh = await session.get(LibraryFile, file.id)
        if fresh is None:
            raise ValueError(f"LibraryFile id={file.id} not found")
        for key, value in data.items():
            if hasattr(fresh, key):
                setattr(fresh, key, value)
        await session.flush()
        await session.refresh(fresh)
        return fresh

    @begin_session
    async def delete_file(self, file: LibraryFile, *, session: AsyncSession = None) -> None:
        fresh = await session.get(LibraryFile, file.id)
        if fresh is not None:
            await session.delete(fresh)

    # ── Per-game access control ────────────────────────────────────────────────

    @begin_session
    async def get_game_access(
        self, user_id: int, game_id: int, *, session: AsyncSession = None
    ) -> UserGameAccess | None:
        stmt = select(UserGameAccess).where(
            UserGameAccess.user_id == user_id,
            UserGameAccess.library_game_id == game_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @begin_session
    async def set_game_access(
        self, user_id: int, game_id: int, access: str, *, session: AsyncSession = None
    ) -> UserGameAccess:
        existing = await session.execute(
            select(UserGameAccess).where(
                UserGameAccess.user_id == user_id,
                UserGameAccess.library_game_id == game_id,
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.access = access
            await session.flush()
            await session.refresh(row)
            return row
        entry = UserGameAccess(user_id=user_id, library_game_id=game_id, access=access)
        session.add(entry)
        await session.flush()
        await session.refresh(entry)
        return entry

    @begin_session
    async def delete_game_access(
        self, user_id: int, game_id: int, *, session: AsyncSession = None
    ) -> None:
        await session.execute(
            delete(UserGameAccess).where(
                UserGameAccess.user_id == user_id,
                UserGameAccess.library_game_id == game_id,
            )
        )

    @begin_session
    async def get_denied_game_ids_for_user(
        self, user_id: int, *, session: AsyncSession = None
    ) -> set[int]:
        stmt = select(UserGameAccess.library_game_id).where(
            UserGameAccess.user_id == user_id,
            UserGameAccess.access == "deny",
        )
        result = await session.execute(stmt)
        return set(result.scalars().all())

    # ── Download statistics ────────────────────────────────────────────────────

    @begin_session
    async def record_download(
        self,
        user_id: int | None,
        game_id: int,
        file_id: int,
        filename: str,
        bytes_transferred: int | None = None,
        *,
        session: AsyncSession = None,
    ) -> DownloadStat:
        stat = DownloadStat(
            user_id=user_id,
            library_game_id=game_id,
            library_file_id=file_id,
            filename=filename,
            bytes_transferred=bytes_transferred,
        )
        session.add(stat)
        await session.flush()
        await session.refresh(stat)
        return stat

    @begin_session
    async def get_global_stats(self, *, session: AsyncSession = None) -> dict:
        """Total downloads, total bytes, top 10 games by download count."""
        total_dl = await session.execute(
            select(func.count()).select_from(DownloadStat)
        )
        total_bytes = await session.execute(
            select(func.sum(DownloadStat.bytes_transferred))
        )
        top_games_q = (
            select(
                DownloadStat.library_game_id,
                func.count().label("count"),
            )
            .group_by(DownloadStat.library_game_id)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_games_result = await session.execute(top_games_q)
        top_games = [
            {"game_id": row.library_game_id, "count": row.count}
            for row in top_games_result
        ]
        return {
            "total_downloads": total_dl.scalar_one() or 0,
            "total_bytes":     total_bytes.scalar_one() or 0,
            "top_games":       top_games,
        }

    @begin_session
    async def get_game_stats(self, game_id: int, *, session: AsyncSession = None) -> dict:
        """Per-game: total downloads, total bytes, top files."""
        total_dl = await session.execute(
            select(func.count()).select_from(DownloadStat)
            .where(DownloadStat.library_game_id == game_id)
        )
        total_bytes = await session.execute(
            select(func.sum(DownloadStat.bytes_transferred))
            .where(DownloadStat.library_game_id == game_id)
        )
        top_files_q = (
            select(
                DownloadStat.library_file_id,
                DownloadStat.filename,
                func.count().label("count"),
            )
            .where(DownloadStat.library_game_id == game_id)
            .group_by(DownloadStat.library_file_id, DownloadStat.filename)
            .order_by(func.count().desc())
            .limit(20)
        )
        top_files_result = await session.execute(top_files_q)
        top_files = [
            {"file_id": row.library_file_id, "filename": row.filename, "count": row.count}
            for row in top_files_result
        ]
        return {
            "total_downloads": total_dl.scalar_one() or 0,
            "total_bytes":     total_bytes.scalar_one() or 0,
            "top_files":       top_files,
        }
