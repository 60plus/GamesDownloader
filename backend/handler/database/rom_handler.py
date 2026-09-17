"""Database handler for ROM platforms and ROMs."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.rom import Rom
from models.rom_platform import RomPlatform

# Everything a scraper writes onto a ROM, and nothing the filesystem scan owns:
# path, size, hashes and disk-set membership have to survive a metadata reset.
# This list used to exist twice, verbatim, in the two functions that clear it.
SCRAPED_METADATA_FIELDS = (
    "name", "slug", "summary",
    "developer", "developer_ss_id", "publisher", "publisher_ss_id",
    "release_year", "genres", "regions", "languages", "tags",
    "rating", "ss_score", "igdb_rating", "lb_rating", "plugin_ratings",
    "player_count", "alternative_names", "franchises",
    "cover_path", "cover_url", "cover_type", "cover_aspect", "cover_source",
    # Where every other picture came from. Cleared with the rest, which is
    # the way back for somebody who wants a scrape to replace what they
    # chose: the paths go with it, so the next pass fetches and records.
    "media_source",
    "background_path", "screenshots",
    "support_path", "wheel_path", "bezel_path", "steamgrid_path",
    "video_path", "picto_path",
    "ss_id", "igdb_id", "launchbox_id",
    "ss_metadata", "igdb_metadata", "launchbox_metadata",
    "hltb_id", "hltb_main_s", "hltb_extra_s", "hltb_complete_s",
)


def cleared_metadata_values() -> dict:
    """The column-to-value map that represents "never scraped"."""
    values: dict = {f: None for f in SCRAPED_METADATA_FIELDS if hasattr(Rom, f)}
    values["is_identified"] = False
    return values


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
    async def rom_counts_by_fs_slug(self, *, session: AsyncSession = None) -> dict[str, int]:
        """How many ROM rows each platform holds, keyed by its folder name.

        One query for the whole tree, asked once before the walk. A scan touches
        a platform only when there is something to do, and "is there anything in
        the database for this folder" is the half of that question the disk
        cannot answer. Asking it per platform would trade a hundred pointless
        writes for a hundred pointless reads.

        Keyed by `fs_slug` because that is what a directory on disk is called;
        several alias folders can map to one platform row, and each of them
        needs the same answer.
        """
        rows = (await session.execute(
            select(RomPlatform.fs_slug, func.count(Rom.id))
            .select_from(RomPlatform)
            .outerjoin(Rom, Rom.platform_id == RomPlatform.id)
            .group_by(RomPlatform.fs_slug)
        )).all()
        return {fs_slug: int(n or 0) for fs_slug, n in rows}

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
            .outerjoin(Rom, (Rom.platform_id == RomPlatform.id) & (~Rom.missing_from_fs) & (~Rom.extra_disk))
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
            select(func.count(Rom.id)).where(~Rom.missing_from_fs, ~Rom.extra_disk)
        )
        return result.scalar_one()

    @begin_session
    async def sample_rom_with_cover(self, *, session: AsyncSession = None) -> Rom | None:
        """Return one ROM that has a cover (for home card display)."""
        result = await session.execute(
            select(Rom)
            .where(Rom.cover_path.isnot(None), ~Rom.missing_from_fs, ~Rom.extra_disk)
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
                ~Rom.missing_from_fs, ~Rom.extra_disk,
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
    "cover_path", "cover_url", "cover_type", "cover_aspect", "cover_source",
    # Where every other picture came from. Cleared with the rest, which is
    # the way back for somebody who wants a scrape to replace what they
    # chose: the paths go with it, so the next pass fetches and records.
    "media_source",
    "background_path", "screenshots",
    "support_path", "wheel_path", "bezel_path", "steamgrid_path", "video_path", "picto_path",
    "ss_id", "igdb_id", "launchbox_id", "ss_metadata", "igdb_metadata",
    "developer_ss_id", "publisher_ss_id",
    "hltb_id", "hltb_main_s", "hltb_extra_s", "hltb_complete_s",
    "is_identified",
    # Typed by hand rather than scraped - an Amiga title asks for its save disk
    # by name, and no source knows that name. Deliberately absent from the clear
    # list below: a re-scrape replaces what a scraper found, not what a player
    # told GD.
    "save_disk_name",
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
            .where(~Rom.missing_from_fs, ~Rom.extra_disk)
            .order_by(Rom.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @begin_session
    async def get_rated(self, *, session: AsyncSession = None) -> list[Rom]:
        """Every non-missing ROM that carries at least one rating source.

        Unbounded by design - the blended ranking has to see the whole library,
        because a SQL sample ordered by one column would miss a game rated only
        by one provider. What it does not need is the raw provider payloads:
        `ss_metadata` holds the entire ScreenScraper `jeu` object including its
        full media array, and on a few thousand rated ROMs those three columns
        are the overwhelming majority of the bytes moved and deserialised for a
        rail of twenty-four tiles.

        `plugin_ratings` is deliberately NOT deferred - the blended rating
        reads it, and steam-deck-compatibility writes it.
        """
        result = await session.execute(
            select(Rom)
            .options(
                selectinload(Rom.platform),
                defer(Rom.ss_metadata),
                defer(Rom.igdb_metadata),
                defer(Rom.launchbox_metadata),
            )
            .where(
                ~Rom.missing_from_fs, ~Rom.extra_disk,
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
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs, ~Rom.extra_disk)
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
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs, ~Rom.extra_disk)
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
            .where(Rom.platform_id == platform_id, ~Rom.missing_from_fs, ~Rom.extra_disk, or_(*conds))
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
    async def mark_all_missing(self, platform_id: int | None = None, *,
                               session: AsyncSession = None) -> None:
        """Set missing_from_fs=True before a re-scan un-sets what it finds.

        Without a platform this is the whole table, which is what the pre-pass
        of a scan wants: it used to run this once per platform, and GD makes a
        folder for every platform it knows, so a real install issued a hundred
        statements to say a thing that is one statement. Every ROM belongs to a
        platform, so "every platform's rows" and "every row" are the same set.

        With a platform it is one platform, which is what the cleanup for a
        folder that has disappeared wants, and that one must not touch the rest
        of the library.
        """
        stmt = update(Rom).values(missing_from_fs=True)
        if platform_id is not None:
            stmt = stmt.where(Rom.platform_id == platform_id)
        await session.execute(stmt)

    @begin_session
    async def clear_container_hashes(self, platform_id: int, fs_name: str, *,
                                     drop_sha1: bool = False,
                                     session: AsyncSession = None) -> None:
        """Null the CRC and MD5 on a row whose format has no container hash worth keeping.

        `upsert` only writes a hash when it has one, which is the right guard
        everywhere else: a re-hash that failed must not wipe good values. It
        also means an empty result cannot clear a stale one, and for a CHD that
        matters. A CHD hashed under the old scheme carries digests of its
        compressed container, and leaving them in place is worse than having
        none - the scraper is handed all three, and a CRC that belongs to a
        container can still collide with some other entry.

        *drop_sha1* is for the case where nothing replaces them: a CHD older
        than v5 carries no source hash at all, so its stored SHA-1 is a digest
        of the container too and has to go with the rest.
        """
        values: dict = {"crc_hash": None, "md5_hash": None}
        if drop_sha1:
            values["sha1_hash"] = None
        await session.execute(
            update(Rom)
            .where(Rom.platform_id == platform_id, Rom.fs_name == fs_name)
            .values(**values)
        )

    @begin_session
    async def set_hashes(self, rom_id: int, crc: str, md5: str, sha1: str, *,
                         session: AsyncSession = None) -> None:
        """Write the three digests of one ROM, computed on request.

        Unlike `upsert`, this writes an empty value as NULL: it is called when
        somebody asked for the hashes of a specific file, so "nothing came
        back" is an answer worth recording rather than a partial result that
        must not overwrite good values.
        """
        await session.execute(
            update(Rom).where(Rom.id == rom_id).values(
                crc_hash=crc or None, md5_hash=md5 or None, sha1_hash=sha1 or None
            )
        )

    @begin_session
    async def adopt_converted_file(
        self, rom_id: int, fs_name: str, size_bytes: int, sha1: str, *,
        session: AsyncSession = None,
    ) -> None:
        """Point an existing row at the file a conversion produced.

        The file changes and the game does not. Savestates, battery saves and
        play history all key on this row's id, so writing a new row for the
        new filename would leave a shelf that looks identical and has lost
        every hour anybody put into the game. Everything scraped stays, and so
        does the disc's place in its set: losing disk_group would break a four
        disc title into four separate games.

        Only the SHA-1 is kept. A CHD is identified by the digest written into
        its own header and by nothing else, and the CRC and MD5 that are there
        now describe a file that is about to stop existing - left in place they
        would also tell the scan this row had already been hashed correctly.

        A sheet's tracks stop being rows, because after this there is no sheet
        and no track, only one file. Matched on this row's own former name, so
        the identically shaped rows belonging to the game next door in the same
        folder are not touched.
        """
        rom = await session.get(Rom, rom_id)
        if rom is None:
            raise HTTPException(status_code=404, detail="ROM not found")

        old_name = rom.fs_name
        name = Path(fs_name).name
        await session.execute(
            update(Rom).where(Rom.id == rom_id).values(
                fs_name=name,
                fs_name_no_ext=Path(name).stem,
                fs_extension=Path(name).suffix.lstrip(".").lower(),
                fs_size_bytes=int(size_bytes or 0),
                crc_hash=None,
                md5_hash=None,
                sha1_hash=sha1 or None,
                missing_from_fs=False,
            )
        )
        if old_name:
            await session.execute(
                delete(Rom).where(
                    Rom.platform_id == rom.platform_id,
                    Rom.track_of == old_name,
                )
            )

    @begin_session
    async def mark_present(self, rom_id: int, *, session: AsyncSession = None) -> None:
        await session.execute(
            update(Rom).where(Rom.id == rom_id).values(missing_from_fs=False)
        )

    @begin_session
    async def get_disk_set(
        self, platform_id: int, disk_group: str, *, session: AsyncSession = None
    ) -> list[Rom]:
        """Every disk of one title, in insertion order.

        Deliberately ignores extra_disk: this is the one place that wants the
        disks the listings hide, so the game's own page can offer them.
        """
        result = await session.execute(
            select(Rom)
            .where(
                Rom.platform_id == platform_id,
                Rom.disk_group == disk_group,
                ~Rom.missing_from_fs,
            )
            .order_by(Rom.disk_number)
        )
        return list(result.scalars().all())

    @begin_session
    async def apply_disk_groups(
        self,
        platform_id: int,
        assignments: dict[str, tuple[str | None, int | None, bool, str | None]],
        *,
        session: AsyncSession = None,
    ) -> None:
        """Record which ROMs belong with which, for a whole platform.

        Written after the directory walk rather than during it, because whether
        a file is one of a set depends on what else is beside it: the first disk
        of a pair only becomes part of a set when the second one turns up.

        Every ROM found on disk gets an entry, including the ones that belong to
        no set - clearing their fields is what lets a title stop being a set
        when its other disks are deleted.
        """
        for fs_name, (group, number, extra, track_of) in assignments.items():
            await session.execute(
                update(Rom)
                .where(Rom.platform_id == platform_id, Rom.fs_name == fs_name)
                .values(disk_group=group, disk_number=number, extra_disk=extra,
                        track_of=track_of)
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
        region_hint: str | None = None,
        *,
        session: AsyncSession = None,
    ) -> Rom:
        """Create or update a ROM row from what the filesystem says about it.

        `region_hint` is what the filename claims, and it is only ever written
        into an empty column. Anything already there came from a scraper or from
        somebody editing it by hand, and a guess read off a filename has no
        business overruling either.
        """
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
                regions=[region_hint] if region_hint else None,
                missing_from_fs=False,
            )
            session.add(rom)
            await session.flush()
            await session.refresh(rom)
        else:
            if region_hint and not rom.regions:
                rom.regions = [region_hint]
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
    async def max_rom_id(self, *, session: AsyncSession = None) -> int:
        """The highest ROM id so far, or 0 for an empty library.

        Ids only grow, so a row with a higher id than this was made after the
        question was asked. That is how an upload or a download tells a row it
        brought into being from an old one the scanner carried a renamed file
        onto - the carried-over row keeps its id, because saves key on it.
        """
        from sqlalchemy import func

        return int((await session.execute(select(func.max(Rom.id)))).scalar() or 0)

    @begin_session
    async def set_owner(
        self, rom_id: int, user_id: int, *, session: AsyncSession = None,
    ) -> None:
        """Record who brought this ROM in, once.

        Owner and uploader start out the same; only a claim parts them. Written
        only onto a row that has none, so a re-download cannot move a ROM from
        one account to another, and cannot undo an admin taking it over.
        """
        rom = await session.get(Rom, rom_id)
        if rom is None or rom.published_by is not None:
            return
        rom.published_by = user_id
        rom.uploaded_by = user_id
        await session.flush()

    @begin_session
    async def set_published_by(
        self, rom_id: int, user_id: int, *, session: AsyncSession = None,
    ) -> None:
        """Move ownership, and only ownership.

        Unlike set_owner this overwrites what is there - that is the whole
        point of a claim - but it still never touches uploaded_by, so the
        account that fetched the ROM keeps its name on it.
        """
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return
        rom.published_by = user_id
        await session.flush()

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


    async def _sheet_of(self, rom: Rom, session: AsyncSession) -> Rom:
        """The row a track belongs to, or the row itself.

        Acting on a track file means acting on its disc. Nothing in the
        interface offers a track, but an id is an id and a route reached with
        one should do the sensible thing rather than delete half a disc.
        """
        if not rom.track_of:
            return rom
        found = await session.execute(
            select(Rom).where(
                Rom.platform_id == rom.platform_id, Rom.fs_name == rom.track_of
            )
        )
        return found.scalars().first() or rom

    @begin_session
    async def fs_names_with_rows(
        self, platform_id: int, fs_names, *, session: AsyncSession = None
    ) -> set[str]:
        """Which of *fs_names* are library entries of this platform, lowercased.

        Asked before a delete takes a data file it believes nothing points at.
        The set being deleted knows its own members and nothing else, so a file
        that is somebody else's entry looks exactly like an orphan from there.
        """
        names = [n for n in fs_names if n]
        if not names:
            return set()
        result = await session.execute(
            select(Rom.fs_name).where(Rom.platform_id == platform_id, Rom.fs_name.in_(names))
        )
        return {name.lower() for name in result.scalars().all()}

    @begin_session
    async def stems_with_rows(
        self, platform_id: int, stems, *, exclude_ids=(), session: AsyncSession = None
    ) -> set[str]:
        """Which of *stems* name an entry of this platform, lowercased.

        The sibling above asks about whole file names, which is enough for a
        data file that could have been a row. It is not enough for the files
        that never can be: a .sbi is not a ROM extension, so it has no row and
        never will, and a name check therefore never protects it.

        What protects it is the disc it sits beside. `Victim (Disc 1).sbi`
        shares a stem with `Victim (Disc 1).cue`, and that IS somebody's entry -
        so the file belongs to that disc and a sheet from another set does not
        get to name it. Without this, uploading a .cue whose text names somebody
        else's subchannel file and then deleting it was enough to remove theirs.

        *exclude_ids* is the set being deleted. Its own discs must not count, or
        a disc would protect its own .sbi from going with it.

        THE COLUMN IS NOT THE STEM, AND IT IS NOT ONE THING EITHER.

        The stems asked about come from files on a shelf, brackets and all.
        `fs_name_no_ext` holds something else, and MEASURED ON A LIVE LIBRARY it
        holds two different things: of 48 rows, 26 carried the name with its
        tags stripped (`MediEvil (USA).chd` -> `MediEvil`) and 6 carried the
        full stem (`Final Fantasy IX (Europe) (Disc 3).chd` -> the whole thing).
        The scanner strips; something on the multi-disc path does not.

        So neither comparison is right on its own. Asking for the raw stem
        missed every stripped row - which is what the audit found - and asking
        for the stripped stem misses every raw one, which is what I broke by
        fixing it that way and only the measurement caught.

        The column can therefore only NARROW the query, in both spellings at
        once, and the FILE NAME settles it: that is the one value with a single
        meaning, and it is what the caller asked about.
        """
        from pathlib import Path

        # A private name from the scanner on purpose. Writing the rule out a
        # second time here is how the two spellings drifted apart to begin with.
        from handler.filesystem.rom_scanner import _strip_tags

        wanted = [s for s in stems if s]
        if not wanted:
            return set()
        keys: set[str] = set()
        for stem in wanted:
            keys.add(stem)
            keys.add(_strip_tags(stem))
        query = select(Rom.fs_name).where(
            Rom.platform_id == platform_id,
            Rom.fs_name_no_ext.in_(sorted(k for k in keys if k)),
        )
        if exclude_ids:
            query = query.where(Rom.id.notin_(list(exclude_ids)))
        result = await session.execute(query)
        asked = {s.lower() for s in wanted}
        return {
            Path(fs_name).stem.lower()
            for fs_name in result.scalars().all()
            if fs_name and Path(fs_name).stem.lower() in asked
        }

    async def _tracks_of(self, platform_id: int, fs_names, session: AsyncSession) -> list[Rom]:
        if not fs_names:
            return []
        result = await session.execute(
            select(Rom)
            .where(Rom.platform_id == platform_id, Rom.track_of.in_(list(fs_names)))
            .order_by(Rom.fs_name)
        )
        return list(result.scalars().all())

    @begin_session
    async def disk_set(self, rom_id: int, *, session: AsyncSession = None) -> list[Rom]:
        """Every ROM belonging to the same title, disks first and in order.

        A title that arrived on several floppies is several rows, and they only
        mean anything together: one of them alone cannot be started and cannot
        be grouped back. Callers that act on a ROM act on this list.

        The track files of any disc kept as a sheet come after the disks. They
        are not disks and no caller should offer them as one, which is what
        `track_of` says - but deleting a sheet and leaving its data behind is
        how a library ends up with orphaned gigabytes nothing can reach.

        A ROM that is a title on its own answers with itself, so the caller has
        one shape to handle rather than two.
        """
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return []
        rom = await self._sheet_of(rom, session)
        if rom.disk_group:
            result = await session.execute(
                select(Rom)
                .where(Rom.platform_id == rom.platform_id, Rom.disk_group == rom.disk_group)
                .order_by(Rom.disk_number, Rom.fs_name)
            )
            disks = list(result.scalars().all())
        else:
            disks = [rom]
        return disks + await self._tracks_of(
            rom.platform_id, [d.fs_name for d in disks], session
        )

    @begin_session
    async def rom_with_tracks(self, rom_id: int, *, session: AsyncSession = None) -> list[Rom]:
        """One ROM and the track files it is the sheet for.

        Narrower than `disk_set` on purpose. Asking for disc 3 of a title means
        disc 3, not the whole box - but disc 3 as a sheet alone is two
        kilobytes of text naming files the download would not include.
        """
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return []
        rom = await self._sheet_of(rom, session)
        return [rom] + await self._tracks_of(rom.platform_id, [rom.fs_name], session)

    @begin_session
    async def all_for_platform(
        self, platform_id: int, *, session: AsyncSession = None,
    ) -> list[dict]:
        """Every row of this platform, unpaginated and unfiltered.

        `list_for_platform` next door is for a screen: it pages, and it hides
        missing rows and extra discs. Deciding what a set of exclusion patterns
        covers has to see all of them - a stray file that ended up marked as an
        extra disc, or one whose file has since gone, is exactly the kind of
        thing somebody writes a pattern to be rid of.
        """
        rows = (await session.execute(
            select(Rom.id, Rom.fs_name, Rom.fs_path, Rom.name, Rom.fs_size_bytes)
            .where(Rom.platform_id == platform_id)
        )).all()
        return [
            {"id": r.id, "fs_name": r.fs_name, "fs_path": r.fs_path,
             "name": r.name, "size_bytes": r.fs_size_bytes}
            for r in rows
        ]

    @begin_session
    async def restore_present(self, ids, *, session: AsyncSession = None) -> None:
        """Put these rows back to present, in one statement.

        For a scan that was stopped partway. A scan marks everything missing on
        the way in and un-marks what the walk finds, so abandoning it halfway
        would leave every platform it had not reached looking empty. A scan that
        did not finish makes no claim about what is missing: this puts back
        exactly the snapshot it took before it started, and the next complete
        scan decides.

        One statement, because the set is potentially every row in the library
        and putting them back one at a time is the mistake the pre-pass made.
        """
        wanted = list(ids)
        if not wanted:
            return
        await session.execute(
            update(Rom).where(Rom.id.in_(wanted)).values(missing_from_fs=False)
        )

    @begin_session
    async def all_missing(self, *, session: AsyncSession = None) -> list[dict]:
        """Every row whose file is gone, with the platform it belongs to.

        Nothing else in the application returns these: every listing, count and
        search filters them out, so a row pointing into empty space is not just
        unimportant, it is unreachable. This is the query behind the one screen
        that shows them.

        The platform comes back with the row because the screen groups by it,
        and asking per row would be one query per orphan on a library that has
        just lost a drive.
        """
        rows = (await session.execute(
            select(Rom.id, Rom.name, Rom.fs_name, Rom.fs_path, Rom.fs_size_bytes,
                   RomPlatform.slug, RomPlatform.name, RomPlatform.custom_name)
            .select_from(Rom)
            .join(RomPlatform, RomPlatform.id == Rom.platform_id)
            .where(Rom.missing_from_fs.is_(True))
            .order_by(RomPlatform.name, Rom.fs_name)
        )).all()
        return [
            {"id": r[0], "name": r[1], "fs_name": r[2], "fs_path": r[3],
             "size_bytes": r[4], "platform_slug": r[5],
             "platform_name": r[7] or r[6]}
            for r in rows
        ]

    @begin_session
    async def present_ids(
        self, platform_id: int | None = None, *, session: AsyncSession = None,
    ) -> list[int]:
        """Rows whose file was there a moment ago. One platform, or all of them.

        Read immediately before a scan marks everything missing, which is the
        only moment the answer exists. It is what lets "gone" mean "gone during
        this scan" rather than "gone at some point since March": a row that was
        already missing is not evidence of a rename, and treating it as one lets
        a file deleted months ago donate its history to an unrelated newcomer.

        Without a platform it is the whole table, which is what that pre-pass
        wants and what stops it issuing one query per platform folder.
        """
        stmt = select(Rom.id).where(Rom.missing_from_fs.is_(False))
        if platform_id is not None:
            stmt = stmt.where(Rom.platform_id == platform_id)
        rows = (await session.execute(stmt)).all()
        return [r.id for r in rows]

    @begin_session
    async def missing_with_hashes(
        self, platform_ids, *, session: AsyncSession = None,
    ) -> list[dict]:
        """Rows whose file was not found in this scan, and that carry a digest.

        The donor side of a rename. Only what the matcher needs, as plain dicts,
        so the rule that decides a rename can be a pure function with no session
        in it - it is the part worth testing exhaustively.
        """
        if not platform_ids:
            return []
        rows = (await session.execute(
            select(Rom.id, Rom.platform_id, Rom.sha1_hash, Rom.fs_size_bytes,
                   Rom.fs_extension, Rom.track_of)
            .where(
                Rom.platform_id.in_(list(platform_ids)),
                Rom.missing_from_fs.is_(True),
                Rom.sha1_hash.is_not(None),
            )
        )).all()
        return [
            {"id": r.id, "platform_id": r.platform_id, "sha1": r.sha1_hash,
             "size": r.fs_size_bytes, "ext": r.fs_extension, "track_of": r.track_of}
            for r in rows
        ]

    @begin_session
    async def rows_for_matching(
        self, rom_ids, *, session: AsyncSession = None,
    ) -> list[dict]:
        """The same shape as missing_with_hashes, for rows named by id.

        Read back rather than remembered: the disc grouping runs after the rows
        are written, so whether one of them turned out to be a track of a sheet
        is not knowable at the moment it is created.
        """
        if not rom_ids:
            return []
        rows = (await session.execute(
            select(Rom.id, Rom.platform_id, Rom.sha1_hash, Rom.fs_size_bytes,
                   Rom.fs_extension, Rom.track_of)
            .where(Rom.id.in_(list(rom_ids)))
        )).all()
        return [
            {"id": r.id, "platform_id": r.platform_id, "sha1": r.sha1_hash,
             "size": r.fs_size_bytes, "ext": r.fs_extension, "track_of": r.track_of}
            for r in rows
        ]

    @begin_session
    async def adopt_renamed(
        self, old_id: int, new_id: int, *, session: AsyncSession = None,
    ) -> bool:
        """Move a renamed file onto the row that already knew the game.

        The OLD row survives and the new one goes. That direction is the whole
        point: saves, play history and collection membership all key on the rom
        id, so keeping the new row would preserve the cover and lose everything
        somebody actually accumulated.

        What crosses over is only what describes the file - its name, where it
        sits, how big it is, and the disc facts the grouping pass worked out
        from the filenames earlier in this scan. The metadata stays exactly as
        it was on the old row, because that is what is being rescued.
        """
        old = await session.get(Rom, old_id)
        new = await session.get(Rom, new_id)
        if old is None or new is None or old.id == new.id:
            return False

        for field in ("fs_name", "fs_name_no_ext", "fs_extension", "fs_path",
                      "fs_size_bytes", "disk_group", "disk_number", "extra_disk",
                      "save_disk_name", "track_of"):
            setattr(old, field, getattr(new, field))
        # Only ever filled in. The two agreed on sha1 to get here; crc and md5
        # may be present on one side and not the other.
        for field in ("crc_hash", "md5_hash", "sha1_hash"):
            value = getattr(new, field, None)
            if value and not getattr(old, field, None):
                setattr(old, field, value)
        old.missing_from_fs = False

        await session.delete(new)
        await session.flush()
        return True

    @begin_session
    async def move_player_data(
        self, from_rom_id: int, to_rom_id: int, *, session: AsyncSession = None,
    ) -> list[int]:
        """Carry saves, savestates and play history from one ROM row to another.

        For the merge at the end of a scan: a renamed file arrives as a new row
        and is folded into the row it was renamed from, which is then the one
        that survives. The new row is deleted by that merge and everything here
        hangs off it by `ondelete="CASCADE"`, so anything a player did against
        it while the scan was running has to come across first.

        The alternative, and what this replaces, was to abandon the merge when
        the new row had been touched. That protected one session and gave up
        every save from before the rename: the old row keeps `missing_from_fs`,
        which every listing filters out, no later scan can pair it again because
        the new name is by then already in the database, and it lands on the
        missing-entries screen where one click removes the save FILES too.

        Returns the accounts that now have a memory card set aside, so they can
        be told. Three tables, three rules, each forced by what the schema
        allows:

          rom_plays        one row per (user, rom), and it is an aggregate -
                           launches, seconds, a last-played stamp. Two rows for
                           one game are the same game played twice, so they add.
          rom_save_states  one row per (user, rom, slot), and a slot is a
                           number. A colliding state takes the first free one
                           rather than displacing what is already there.
          rom_saves        ONE memory card per (user, rom). Two cards cannot
                           become one and choosing between them would delete a
                           save nobody was asked about. The card already on the
                           surviving row stays in use and the other is set aside
                           in `rom_save_conflicts`, file and all, for its owner
                           to choose. This used to refuse the whole move, which
                           kept the merge from happening and left the old row
                           missing - the very state described above, for the one
                           person with the most at stake.
        """
        from models.rom_play import RomPlay
        from models.rom_save_state import RomSave, RomSaveConflict, RomSaveState

        if from_rom_id == to_rom_id:
            return []

        cards = (await session.execute(
            select(RomSave).where(RomSave.rom_id == from_rom_id)
        )).scalars().all()
        held = {
            int(user_id) for (user_id,) in await session.execute(
                select(RomSave.user_id).where(RomSave.rom_id == to_rom_id))
        }
        set_aside: list[int] = []
        for card in cards:
            if int(card.user_id) not in held:
                card.rom_id = to_rom_id
                continue
            # The row goes, the file stays where it was written: nothing here
            # deletes save files, and the set-aside row is what points at it.
            session.add(RomSaveConflict(
                rom_id=to_rom_id,
                user_id=card.user_id,
                file_name=card.file_name,
                file_path=card.file_path,
                file_size_bytes=card.file_size_bytes or 0,
                emulator_core=card.emulator_core,
                slot=card.slot,
                content_hash=card.content_hash,
                card_updated_at=card.updated_at or card.created_at,
            ))
            await session.delete(card)
            set_aside.append(int(card.user_id))

        # Savestates. Slots are per person, so somebody else's slot 0 is not in
        # the way of mine.
        taken: dict[int, set] = {}
        for user_id, slot in await session.execute(
                select(RomSaveState.user_id, RomSaveState.slot)
                .where(RomSaveState.rom_id == to_rom_id)):
            taken.setdefault(int(user_id), set()).add(slot)
        states = (await session.execute(
            select(RomSaveState).where(RomSaveState.rom_id == from_rom_id)
        )).scalars().all()
        for state in states:
            slots = taken.setdefault(int(state.user_id), set())
            if state.slot in slots:
                # Also the path a legacy row with no slot at all takes when the
                # destination already has one: it gets a number rather than
                # sitting on top of something.
                free = 0
                while free in slots:
                    free += 1
                state.slot = free
            slots.add(state.slot)
            state.rom_id = to_rom_id

        # Play history, which merges by arithmetic.
        mine = {
            int(row.user_id): row for row in (await session.execute(
                select(RomPlay).where(RomPlay.rom_id == to_rom_id))).scalars().all()
        }
        for play in (await session.execute(
                select(RomPlay).where(RomPlay.rom_id == from_rom_id))).scalars().all():
            kept = mine.get(int(play.user_id))
            if kept is None:
                play.rom_id = to_rom_id
                continue
            kept.play_count = (kept.play_count or 0) + (play.play_count or 0)
            kept.seconds_played = (kept.seconds_played or 0) + (play.seconds_played or 0)
            if play.last_played_at and (
                    kept.last_played_at is None
                    or play.last_played_at > kept.last_played_at):
                kept.last_played_at = play.last_played_at
            await session.delete(play)

        await session.flush()
        return set_aside

    @begin_session
    async def ids_with_player_data(
        self, rom_ids, *, session: AsyncSession = None,
    ) -> set[int]:
        """Of these rows, the ones somebody has already played or saved against.

        Deleting a ROM row takes its savestates, memory cards and play history
        with it by cascade, and those are the one thing here that cannot be
        rebuilt from the disk. So anything that undoes its own work has to ask
        this first: a row a person has touched is no longer an untouched
        addition, whatever created it.

        One query per table rather than one per row - a stopped scan can be
        asking about thousands.
        """
        ids = [int(i) for i in rom_ids]
        if not ids:
            return set()
        from models.rom_play import RomPlay
        from models.rom_save_state import RomSave, RomSaveState

        touched: set[int] = set()
        for model in (RomSaveState, RomSave, RomPlay):
            rows = await session.execute(
                select(model.rom_id).where(model.rom_id.in_(ids)).distinct()
            )
            touched.update(int(r[0]) for r in rows.all() if r[0] is not None)
        return touched

    @begin_session
    async def delete(self, rom_id: int, *, session: AsyncSession = None) -> bool:
        """Drop one ROM row. Saves and play history follow it by cascade."""
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return False
        await session.delete(rom)
        await session.flush()
        return True

    @begin_session
    async def delete_many(self, rom_ids, *, session: AsyncSession = None) -> int:
        """Drop these ROM rows in one statement. Returns how many went.

        For a scan leaving by the shutdown door, where a delete per row, each in
        its own transaction, does not fit the few seconds the process is given.
        Saves and play history cascade in the database as they do for `delete`,
        so callers hand in only rows nobody has played or saved against.
        """
        ids = [int(i) for i in rom_ids]
        if not ids:
            return 0
        result = await session.execute(delete(Rom).where(Rom.id.in_(ids)))
        return result.rowcount or 0

    @begin_session
    async def clear_metadata(self, rom_id: int, *, session: AsyncSession = None) -> Rom | None:
        """Reset all scraped metadata to NULL, keep filesystem fields and hashes."""
        rom = await session.get(Rom, rom_id)
        if rom is None:
            return None
        for field, value in cleared_metadata_values().items():
            setattr(rom, field, value)
        await session.flush()
        await session.refresh(rom)
        return rom

    @begin_session
    async def clear_metadata_for_platform(
        self, platform_id: int, *, session: AsyncSession = None,
    ) -> int:
        """Clear scraped metadata for every ROM on a platform, in one statement.

        The route used to page the platform with `list_for_platform(limit=9999)`
        and then call `clear_metadata` once per row, which went wrong in four
        ways on a large set. It stopped at ten thousand and reported that number
        as though it were the whole job. It skipped every `extra_disk` and
        `missing_from_fs` ROM, because that listing query filters those out for
        the shelf - so the extra disks of a multi-disk title kept the metadata
        the operator had just asked to be rid of. It opened one transaction per
        ROM. And because clearing sets `name` to NULL while the default sort is
        `name_asc`, and MariaDB orders NULLs first, a second click walked the
        same already-cleared rows again and never reached the rest.
        """
        result = await session.execute(
            update(Rom)
            .where(Rom.platform_id == platform_id)
            .values(**cleared_metadata_values())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount

    @begin_session
    async def clear_all_metadata(self, *, session: AsyncSession = None) -> int:
        """Clear metadata for ALL ROMs across all platforms."""
        result = await session.execute(
            update(Rom)
            .values(**cleared_metadata_values())
            .execution_options(synchronize_session=False)
        )
        return result.rowcount


rom_platform_handler = RomPlatformHandler()
rom_handler = RomHandler()
