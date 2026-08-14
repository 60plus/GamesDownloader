"""Database handler for ROM platforms and ROMs."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.rom import Rom
from models.rom_platform import RomPlatform


class RomPlatformHandler(DBBaseHandler):
    model = RomPlatform

    # ── Query ──────────────────────────────────────────────────────────────────

    @begin_session
    async def get_by_fs_slug(self, fs_slug: str, *, session: AsyncSession = None) -> RomPlatform | None:
        result = await session.execute(
            select(RomPlatform).where(RomPlatform.fs_slug == fs_slug)
        )
        return result.scalars().first()

    @begin_session
    async def get_by_slug(self, slug: str, *, session: AsyncSession = None) -> RomPlatform | None:
        result = await session.execute(
            select(RomPlatform).where(RomPlatform.slug == slug)
        )
        return result.scalars().first()

    @begin_session
    async def get_all_simple(self, *, session: AsyncSession = None) -> list[RomPlatform]:
        """Return all platform rows (no join, no filter)."""
        result = await session.execute(select(RomPlatform))
        return list(result.scalars().all())

    @begin_session
    async def get_all_with_counts(self, *, session: AsyncSession = None) -> list[dict]:
        """Return platforms that have at least one non-missing ROM."""
        rom_count_col = func.count(Rom.id)
        stmt = (
            select(RomPlatform, rom_count_col.label("rom_count"))
            .outerjoin(Rom, (Rom.platform_id == RomPlatform.id) & (~Rom.missing_from_fs))
            .group_by(RomPlatform.id)
            .having(rom_count_col > 0)
            .order_by(RomPlatform.name)
        )
        result = await session.execute(stmt)
        rows = result.all()
        out = []
        for platform, count in rows:
            out.append({
                "id":            platform.id,
                "slug":          platform.slug,
                "fs_slug":       platform.fs_slug,
                "name":          platform.custom_name or platform.name,
                "cover_path":    platform.cover_path,
                "is_identified": platform.is_identified,
                "rom_count":     count,
            })
        return out

    @begin_session
    async def upsert(self, fs_slug: str, slug: str, name: str, *, session: AsyncSession = None) -> RomPlatform:
        """Create or update a platform by fs_slug.

        Falls back to lookup by slug - several filesystem directories may
        alias to the same canonical slug (e.g. `atari2600/` and `atari-2600/`
        both map to slug `atari-2600`).  When that happens we reuse the
        existing row instead of trying to INSERT a duplicate (which would
        raise IntegrityError on the ix_rom_platforms_slug unique index).
        """
        existing = await session.execute(
            select(RomPlatform).where(RomPlatform.fs_slug == fs_slug)
        )
        platform = existing.scalars().first()
        if platform is None:
            # Alias case: another fs_slug already claimed this slug
            existing_by_slug = await session.execute(
                select(RomPlatform).where(RomPlatform.slug == slug)
            )
            platform = existing_by_slug.scalars().first()
        if platform is None:
            platform = RomPlatform(fs_slug=fs_slug, slug=slug, name=name)
            session.add(platform)
            await session.flush()
            await session.refresh(platform)
        return platform

    @begin_session
    async def set_cover(self, platform_id: int, cover_path: str, *, session: AsyncSession = None) -> None:
        await session.execute(
            update(RomPlatform)
            .where(RomPlatform.id == platform_id)
            .values(cover_path=cover_path)
        )

    @begin_session
    async def total_roms(self, *, session: AsyncSession = None) -> int:
        result = await session.execute(
            select(func.count(Rom.id)).where(~Rom.missing_from_fs)
        )
        return result.scalar_one()

    @begin_session
    async def sample_rom_with_cover(self, *, session: AsyncSession = None) -> Rom | None:
        """Return one ROM that has a cover (for home card display)."""
        result = await session.execute(
            select(Rom)
            .where(Rom.cover_path.isnot(None), ~Rom.missing_from_fs)
            .order_by(func.rand())
            .limit(1)
        )
        return result.scalars().first()

    @begin_session
    async def sample_platform_with_hero(
        self, *, session: AsyncSession = None
    ) -> dict | None:
        """Return a random platform that has a ROM with a background/hero image.

        Returns dict with keys: fs_slug, hero_path (background or cover fallback).
        Used by the home-page Emulation Library card.
        """
        result = await session.execute(
            select(RomPlatform.fs_slug, Rom.background_path, Rom.cover_path)
            .join(Rom, Rom.platform_id == RomPlatform.id)
            .where(
                ~Rom.missing_from_fs,
                (Rom.background_path.isnot(None)) | (Rom.cover_path.isnot(None)),
            )
            .order_by(func.rand())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        fs_slug, bg, cover = row
        return {"fs_slug": fs_slug, "hero_path": bg or cover}


# Fields that the metadata-update endpoint is allowed to set.
# Never includes identity/filesystem columns (id, platform_id, fs_*, missing_from_fs)
# so a malformed or malicious request cannot corrupt the ROM record.
_METADATA_FIELDS: frozenset[str] = frozenset({
    "name", "slug", "summary", "developer", "publisher",
    "release_year", "genres", "regions", "languages", "tags",
    "rating", "ss_score", "igdb_rating", "lb_rating", "plugin_ratings", "player_count", "alternative_names", "franchises",
    "cover_path", "cover_url", "cover_type", "cover_aspect", "background_path", "screenshots",
    "support_path", "wheel_path", "bezel_path", "steamgrid_path", "video_path", "picto_path",
    "ss_id", "igdb_id", "launchbox_id", "ss_metadata", "igdb_metadata",
    "developer_ss_id", "publisher_ss_id",
    "hltb_id", "hltb_main_s", "hltb_extra_s", "hltb_complete_s",
    "is_identified",
})


class RomHandler(DBBaseHandler):
    model = Rom

    # ── Query ──────────────────────────────────────────────────────────────────

    @begin_session
    async def get_with_platform(self, rom_id: int, *, session: AsyncSession = None) -> Rom | None:
        result = await session.execute(
            select(Rom)
            .options(selectinload(Rom.platform))
            .where(Rom.id == rom_id)
        )
        return result.scalars().first()

    @begin_session
    async def get_by_ids(
        self, rom_ids: list[int], *, session: AsyncSession = None
    ) -> dict[int, Rom]:
        """Bulk fetch keyed by id - one query instead of N when a list of rows
        (e.g. savestates) needs its ROMs' names and covers."""
        if not rom_ids:
            return {}
        result = await session.execute(
            select(Rom)
            .options(selectinload(Rom.platform))
            .where(Rom.id.in_(set(rom_ids)))
        )
        return {r.id: r for r in result.scalars().all()}

    @begin_session
    async def get_recent(self, limit: int = 24, *, session: AsyncSession = None) -> list[Rom]:
        """Return the most recently added non-missing ROMs (newest id first)."""
        result = await session.execute(
            select(Rom)
            .options(selectinload(Rom.platform))
            .where(~Rom.missing_from_fs)
            .order_by(Rom.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @begin_session
    async def get_rated(self, *, session: AsyncSession = None) -> list[Rom]:
        """Every non-missing ROM that carries at least one rating source."""
        result = await session.execute(
            select(Rom)
            .options(selectinload(Rom.platform))
            .where(
                ~Rom.missing_from_fs,
                or_(
                    Rom.ss_score.is_not(None),
                    Rom.igdb_rating.is_not(None),
                    Rom.lb_rating.is_not(None),
                    Rom.plugin_ratings.is_not(None),
                ),
            )
        )
        return list(result.scalars().all())

    @begin_session
    async def list_for_platform(
        self,
        platform_id: int,
        *,
        search: str = "",
        sort: str = "name_asc",
        limit: int = 48,
        offset: int = 0,
        session: AsyncSession = None,
    ) -> tuple[list[Rom], int]:
        base = (
            select(Rom)
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs)
        )
        if search:
            term = f"%{search}%"
            base = base.where(
                Rom.name.ilike(term) | Rom.fs_name_no_ext.ilike(term)
            )
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_stmt)).scalar_one()
        _sort_map = {
            "name_asc":   (Rom.name.asc(),  Rom.fs_name_no_ext.asc()),
            "name_desc":  (Rom.name.desc(), Rom.fs_name_no_ext.desc()),
            "year_asc":   (Rom.release_year.asc(),  Rom.name.asc()),
            "year_desc":  (Rom.release_year.desc(), Rom.name.asc()),
        }
        order_cols = _sort_map.get(sort, _sort_map["name_asc"])
        items_stmt = (
            base
            .order_by(*order_cols)
            .limit(limit)
            .offset(offset)
        )
        result = await session.execute(items_stmt)
        return list(result.scalars().all()), total

    @begin_session
    async def find_for_import(
        self,
        *,
        sha1: str | None = None,
        fs_name: str | None = None,
        name: str | None = None,
        platform_id: int | None = None,
        session: AsyncSession = None,
    ) -> Rom | None:
        """Find the ROM a restored save belongs to, strongest evidence first.

        The archive was written on another install, so ids mean nothing here.
        The hash identifies the dump exactly; the filename survives a re-scan;
        the title is the last resort and only within the right platform, since
        the same title exists on several.
        """
        # platform is eager-loaded: the caller writes the save under the
        # platform's folder, and by then this session is closed - a lazy load
        # would raise DetachedInstanceError mid-import.
        base = select(Rom).options(selectinload(Rom.platform))
        if sha1:
            hit = (await session.execute(
                base.where(Rom.sha1_hash == sha1)
            )).scalars().first()
            if hit:
                return hit
        if platform_id is None:
            return None
        if fs_name:
            hit = (await session.execute(
                base.where(Rom.platform_id == platform_id, Rom.fs_name == fs_name)
            )).scalars().first()
            if hit:
                return hit
        if name:
            return (await session.execute(
                base.where(
                    Rom.platform_id == platform_id,
                    or_(Rom.name == name, Rom.fs_name_no_ext == name),
                )
            )).scalars().first()
        return None

    @begin_session
    async def get_by_fs_name(
        self,
        platform_id: int,
        fs_name: str,
        *,
        session: AsyncSession = None,
    ) -> Rom | None:
        result = await session.execute(
            select(Rom).where(
                Rom.platform_id == platform_id,
                Rom.fs_name == fs_name,
            )
        )
        return result.scalars().first()

    @begin_session
    async def count_for_platform(self, platform_id: int, *, session: AsyncSession = None) -> int:
        """Count non-missing ROMs for a platform."""
        result = await session.execute(
            select(func.count(Rom.id))
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs)
        )
        return result.scalar_one()

    @begin_session
    async def owned_signatures(
        self,
        platform_id: int,
        *,
        crcs: set[str] | None = None,
        md5s: set[str] | None = None,
        sha1s: set[str] | None = None,
        fs_names: set[str] | None = None,
        session: AsyncSession = None,
    ) -> dict[str, set[str]]:
        """Which of the given signatures already exist (non-missing) for a
        platform, in one query bounded by the caller's page.

        Used to mark a ROM-source listing entry "owned" before any download: a
        hash identifies the exact dump regardless of filename; the filename is
        the cheap fallback. Returns sets under keys crc / md5 / sha1 / fs_name,
        holding only the values actually present.
        """
        found: dict[str, set[str]] = {"crc": set(), "md5": set(), "sha1": set(), "fs_name": set()}
        crcs = {c.lower() for c in (crcs or set()) if c}
        md5s = {c.lower() for c in (md5s or set()) if c}
        sha1s = {c.lower() for c in (sha1s or set()) if c}
        fs_names = {c for c in (fs_names or set()) if c}
        conds = []
        if crcs:
            conds.append(func.lower(Rom.crc_hash).in_(crcs))
        if md5s:
            conds.append(func.lower(Rom.md5_hash).in_(md5s))
        if sha1s:
            conds.append(func.lower(Rom.sha1_hash).in_(sha1s))
        if fs_names:
            conds.append(Rom.fs_name.in_(fs_names))
        if not conds:
            return found
        stmt = (
            select(Rom.crc_hash, Rom.md5_hash, Rom.sha1_hash, Rom.fs_name)
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs, or_(*conds))
        )
        for crc, md5, sha1, fs_name in (await session.execute(stmt)).all():
            if crc:
                found["crc"].add(crc.lower())
            if md5:
                found["md5"].add(md5.lower())
            if sha1:
                found["sha1"].add(sha1.lower())
            if fs_name:
                found["fs_name"].add(fs_name)
        return found

    @begin_session
    async def mark_all_missing(self, platform_id: int, *, session: AsyncSession = None) -> None:
        """Set missing_from_fs=True for all ROMs of a platform before re-scan."""
        await session.execute(
            update(Rom)
            .where(Rom.platform_id == platform_id)
            .values(missing_from_fs=True)
        )

    @begin_session
    async def mark_present(self, rom_id: int, *, session: AsyncSession = None) -> None:
        await session.execute(
            update(Rom).where(Rom.id == rom_id).values(missing_from_fs=False)
        )

    @begin_session
    async def upsert(
        self,
        platform_id: int,
        fs_name: str,
        fs_name_no_ext: str,
        fs_extension: str,
        fs_path: str,
        fs_size_bytes: int,
        crc_hash: str = "",
        md5_hash: str = "",
        sha1_hash: str = "",
        *,
        session: AsyncSession = None,
    ) -> Rom:
        existing = await session.execute(
            select(Rom).where(
                Rom.platform_id == platform_id,
                Rom.fs_name == fs_name,
            )
        )
        rom = existing.scalars().first()
        if rom is None:
            rom = Rom(
                platform_id=platform_id,
                fs_name=fs_name,
                fs_name_no_ext=fs_name_no_ext,
                fs_extension=fs_extension,
                fs_path=fs_path,
                fs_size_bytes=fs_size_bytes,
                crc_hash=crc_hash or None,
                md5_hash=md5_hash or None,
                sha1_hash=sha1_hash or None,
                missing_from_fs=False,
            )
            session.add(rom)
            await session.flush()
            await session.refresh(rom)
        else:
            rom.fs_size_bytes = fs_size_bytes
            rom.fs_path = fs_path
            rom.missing_from_fs = False
            if crc_hash:
                rom.crc_hash = crc_hash
            if md5_hash:
                rom.md5_hash = md5_hash
            if sha1_hash:
                rom.sha1_hash = sha1_hash
            await session.flush()
        return rom

    @begin_session
    async def update_metadata(
        self,
        rom_id: int,
        data: dict,
        *,
        session: AsyncSession = None,
    ) -> Rom | None:
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return None
        for k, v in data.items():
            if k in _METADATA_FIELDS:
                setattr(rom, k, v)
        await session.flush()
        await session.refresh(rom)
        return rom


    @begin_session
    async def clear_metadata(self, rom_id: int, *, session: AsyncSession = None) -> Rom | None:
        """Reset all scraped metadata to NULL, keep filesystem fields and hashes."""
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return None
        _CLEAR = [
            "name", "slug", "summary", "developer", "publisher",
            "release_year", "genres", "regions", "languages", "tags",
            "rating", "ss_score", "igdb_rating", "lb_rating", "plugin_ratings", "player_count", "alternative_names", "franchises",
            "cover_path", "cover_url", "cover_type", "cover_aspect", "background_path", "screenshots",
            "support_path", "wheel_path", "bezel_path", "steamgrid_path", "video_path", "picto_path",
            "ss_id", "igdb_id", "launchbox_id", "ss_metadata", "igdb_metadata",
        ]
        for field in _CLEAR:
            if hasattr(rom, field):
                setattr(rom, field, None)
        rom.is_identified = False
        await session.flush()
        await session.refresh(rom)
        return rom

    @begin_session
    async def clear_all_metadata(self, *, session: AsyncSession = None) -> int:
        """Clear metadata for ALL ROMs across all platforms."""
        from sqlalchemy import select
        roms = (await session.execute(select(Rom))).scalars().all()
        count = 0
        for rom in roms:
            _CLEAR = [
                "name", "slug", "summary", "developer", "publisher",
                "release_year", "genres", "regions", "languages", "tags",
                "rating", "ss_score", "igdb_rating", "lb_rating", "plugin_ratings", "player_count", "alternative_names", "franchises",
                "cover_path", "cover_url", "cover_type", "cover_aspect", "background_path", "screenshots",
                "support_path", "wheel_path", "bezel_path", "steamgrid_path", "video_path", "picto_path",
                "ss_id", "igdb_id", "launchbox_id", "ss_metadata", "igdb_metadata",
            ]
            for field in _CLEAR:
                if hasattr(rom, field):
                    setattr(rom, field, None)
            rom.is_identified = False
            count += 1
        await session.flush()
        return count


rom_platform_handler = RomPlatformHandler()
rom_handler = RomHandler()
