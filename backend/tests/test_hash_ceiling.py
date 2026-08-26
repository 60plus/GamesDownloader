"""Hashing a ROM means reading all of it, and that has to be declinable.

A scan computes CRC, MD5 and SHA-1 for every file it has not seen before, so
the first sight of a forty gigabyte disc image costs forty gigabytes of reads
before anything shows up in the library, and there was no setting anywhere that
said otherwise.

RomM's answer is one boolean in a YAML file, all or nothing, plus a hard-coded
list of platforms it never hashes. A size ceiling is the better shape: a
cartridge dump is hashed for free and stays identified, and only the files that
actually cost something are skipped - and those can be asked for by hand.
"""

from __future__ import annotations



import pytest

from handler.filesystem import rom_scanner
from handler.filesystem.rom_scanner import (
    hash_ceiling_bytes,
    hashing_reads_whole_file,
    skip_hashing,
)

GIB = 1024 ** 3


# ── the decision ─────────────────────────────────────────────────────────────

def test_no_ceiling_means_hash_everything():
    """The default. A hash is how a ROM gets identified, so nothing is skipped
    until somebody says so."""
    assert skip_hashing(500 * GIB, "iso", 0) is False
    assert skip_hashing(500 * GIB, "iso", -1) is False


def test_a_file_over_the_ceiling_is_skipped():
    assert skip_hashing(41 * GIB, "iso", 8 * GIB) is True


def test_a_file_under_the_ceiling_is_hashed():
    assert skip_hashing(2 * GIB, "iso", 8 * GIB) is False
    assert skip_hashing(8 * GIB, "iso", 8 * GIB) is False, "the ceiling itself is allowed"


def test_a_chd_is_never_skipped_however_large():
    """Its source hash sits in its own header, 124 bytes in. A ceiling that
    skipped CHDs would stop identifying exactly the files it was aimed at while
    saving nothing at all."""
    assert skip_hashing(60 * GIB, "chd", 8 * GIB) is False
    assert skip_hashing(60 * GIB, ".CHD", 8 * GIB) is False
    assert hashing_reads_whole_file("chd") is False
    assert hashing_reads_whole_file("iso") is True
    assert hashing_reads_whole_file("") is True


def test_a_file_of_unknown_size_is_hashed():
    assert skip_hashing(0, "iso", 8 * GIB) is False


# ── the scan itself ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_real_scan_skips_the_large_file_and_hashes_the_small_one(
    tmp_path, monkeypatch
):
    """The seam the tests above cannot reach: whether the walk actually asks.

    The decision function can be perfect while the loop ignores it, and every
    test in this file would still pass. So this runs the real scan over a real
    directory, with only the database calls stubbed, and looks at what was
    written for each file.
    """
    import hashlib

    from handler.filesystem import rom_scanner as scanner

    library = tmp_path / "roms" / "psx"
    library.mkdir(parents=True)
    small = b"a cartridge sized rom"
    (library / "small.iso").write_bytes(small)
    (library / "huge.iso").write_bytes(b"x" * 4096)

    _write_settings(tmp_path, monkeypatch, {"hash_max_bytes": 1024})

    class _Platform:
        id = 1
        slug = "psx"
        fs_slug = "psx"

    written: dict[str, dict] = {}

    async def _nothing(*a, **k):
        return None

    async def _no_platforms(*a, **k):
        return []

    async def _upsert_platform(*a, **k):
        return _Platform()

    async def _upsert_rom(**kwargs):
        written[kwargs["fs_name"]] = kwargs

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _no_platforms)
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert", _upsert_platform)
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "apply_disk_groups", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "clear_container_hashes", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "upsert", _upsert_rom)

    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert written["small.iso"]["md5_hash"] == hashlib.md5(small).hexdigest()
    assert written["huge.iso"]["md5_hash"] == ""
    assert written["huge.iso"]["crc_hash"] == ""
    assert written["huge.iso"]["sha1_hash"] == ""
    # It is still in the library, just not identified by hash.
    assert written["huge.iso"]["fs_size_bytes"] == 4096


# ── the setting behind it ────────────────────────────────────────────────────

def _write_settings(tmp_path, monkeypatch, roms_section):
    import yaml

    from config import config_manager

    settings = tmp_path / "settings.yaml"
    settings.write_text(yaml.dump({"roms": roms_section}), encoding="utf-8")
    monkeypatch.setattr(config_manager, "_CONFIG_FILE", settings)


def test_the_ceiling_is_read_from_the_rom_settings(tmp_path, monkeypatch):
    _write_settings(tmp_path, monkeypatch, {"hash_max_bytes": 8 * GIB})
    assert hash_ceiling_bytes() == 8 * GIB


def test_an_unset_ceiling_reads_as_none(tmp_path, monkeypatch):
    _write_settings(tmp_path, monkeypatch, {"library_path": "/data/games/roms"})
    assert hash_ceiling_bytes() == 0


@pytest.mark.parametrize("bad", ["", None, "eight gigabytes", -5, {}])
def test_a_value_that_is_not_a_size_reads_as_no_ceiling(tmp_path, monkeypatch, bad):
    """Anything unusable has to mean "hash everything". Reading it as a small
    number would silently stop hashing an entire library."""
    _write_settings(tmp_path, monkeypatch, {"hash_max_bytes": bad})
    assert hash_ceiling_bytes() == 0


def test_the_settings_screen_reports_the_ceiling_that_is_actually_obeyed(
    tmp_path, monkeypatch
):
    """Same rule the download ceiling on that screen already follows: show the
    number the scan uses, not the raw stored key."""
    import asyncio

    from endpoints.settings import roms_settings_router

    _write_settings(tmp_path, monkeypatch, {"hash_max_bytes": 4 * GIB})
    out = asyncio.run(roms_settings_router.get_rom_settings.__wrapped__(None))
    assert out["hash_max_bytes"] == 4 * GIB


# ── asking for the hashes of one file anyway ─────────────────────────────────

@pytest.mark.asyncio
async def test_asking_for_a_skipped_file_hashes_it_and_stores_the_result(
    tmp_path, monkeypatch
):
    """The other half of the ceiling. Without it a skipped file stays
    unidentified until somebody edits a setting and rescans the library."""
    import hashlib
    import zlib

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    body = b"a rom that was too large to hash on the way in" * 32
    library = tmp_path / "roms"
    rom_dir = library / "psx"
    rom_dir.mkdir(parents=True)
    (rom_dir / "game.iso").write_bytes(body)

    async def _roms_path():
        return str(library)

    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            session.add(RomPlatform(id=1, slug="psx", fs_slug="psx", name="PlayStation"))
            session.add(Rom(
                id=7, platform_id=1, fs_name="game.iso", fs_name_no_ext="game",
                fs_extension="iso", fs_path=str(rom_dir), fs_size_bytes=len(body),
            ))
            await session.commit()

            async def _get(rom_id):
                return (await session.execute(
                    select(Rom).where(Rom.id == rom_id))).scalar_one_or_none()

            monkeypatch.setattr(rom_handler, "get_with_platform", _get)
            # begin_session passes a supplied session straight through, so the
            # real writer runs against this table rather than the app's.
            writer = rom_handler.set_hashes
            monkeypatch.setattr(
                rom_handler, "set_hashes",
                lambda *a, **k: writer(*a, session=session, **k),
            )

            out = await roms_router.compute_rom_hashes.__wrapped__(None, 7)
            assert out["has_hashes"] is True

            row = await _get(7)
            assert row.md5_hash == hashlib.md5(body).hexdigest()
            assert row.sha1_hash == hashlib.sha1(body).hexdigest()
            assert row.crc_hash == format(zlib.crc32(body) & 0xFFFFFFFF, "08X")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_asking_about_a_file_that_is_not_there_says_so(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    class _Row:
        fs_path = str(tmp_path)
        fs_name = "gone.iso"

    async def _get(rom_id):
        return _Row() if rom_id == 7 else None

    monkeypatch.setattr(rom_handler, "get_with_platform", _get)

    with pytest.raises(HTTPException) as missing_row:
        await roms_router.compute_rom_hashes.__wrapped__(None, 8)
    assert missing_row.value.status_code == 404

    with pytest.raises(HTTPException) as missing_file:
        await roms_router.compute_rom_hashes.__wrapped__(None, 7)
    assert missing_file.value.status_code == 404


@pytest.mark.asyncio
async def test_a_file_outside_the_rom_directory_is_refused(tmp_path, monkeypatch):
    """Same guard the download route applies two functions above. `fs_path` is
    a stored string, and a row can point outside the library through a symlink
    or after the library path was changed under it. Reading such a file and
    publishing its digest to a scraper is not a smaller thing than serving it."""
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    (library / "psx").mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "secrets.iso").write_bytes(b"not a rom")

    class _Row:
        fs_path = str(outside)
        fs_name = "secrets.iso"

    async def _get(rom_id):
        return _Row()

    async def _roms_path():
        return str(library)

    monkeypatch.setattr(rom_handler, "get_with_platform", _get)
    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)

    with pytest.raises(HTTPException) as refused:
        await roms_router.compute_rom_hashes.__wrapped__(None, 7)
    assert refused.value.status_code == 403


@pytest.mark.asyncio
async def test_a_file_that_yields_nothing_says_so_and_keeps_the_row(
    tmp_path, monkeypatch
):
    """`_compute_hashes` answers ('', '', '') both for a read that failed and
    for a format with no usable digest. Writing that as NULL would null good
    values on a transient error, and answering 200 left the button reappearing
    with nothing said."""
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    rom_dir = library / "psx"
    rom_dir.mkdir(parents=True)
    (rom_dir / "game.iso").write_bytes(b"x")

    class _Row:
        fs_path = str(rom_dir)
        fs_name = "game.iso"

    wrote: list = []

    async def _get(rom_id):
        return _Row()

    async def _roms_path():
        return str(library)

    monkeypatch.setattr(rom_handler, "get_with_platform", _get)
    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)
    monkeypatch.setattr(rom_handler, "set_hashes",
                        lambda *a, **k: wrote.append(a))
    monkeypatch.setattr(rom_scanner, "_compute_hashes", lambda *a, **k: ("", "", ""))

    with pytest.raises(HTTPException) as refused:
        await roms_router.compute_rom_hashes.__wrapped__(None, 7)
    assert refused.value.status_code == 422
    assert wrote == [], "a failed read overwrote the row"


@pytest.mark.asyncio
async def test_the_same_file_is_not_read_twice_at_once(tmp_path, monkeypatch):
    """Each read holds a thread from the pool the scanner also uses."""
    from fastapi import HTTPException

    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler

    library = tmp_path / "roms"
    rom_dir = library / "psx"
    rom_dir.mkdir(parents=True)
    (rom_dir / "game.iso").write_bytes(b"x")

    class _Row:
        fs_path = str(rom_dir)
        fs_name = "game.iso"

    async def _get(rom_id):
        return _Row()

    async def _roms_path():
        return str(library)

    monkeypatch.setattr(rom_handler, "get_with_platform", _get)
    monkeypatch.setattr(roms_router, "_get_roms_path", _roms_path)

    roms_router._hashing_roms.add(7)
    try:
        with pytest.raises(HTTPException) as busy:
            await roms_router.compute_rom_hashes.__wrapped__(None, 7)
        assert busy.value.status_code == 409
    finally:
        roms_router._hashing_roms.discard(7)


# ── a file that changed while it was over the ceiling ────────────────────────

@pytest.mark.asyncio
async def test_a_file_that_grew_past_the_ceiling_loses_its_old_checksums(
    tmp_path, monkeypatch
):
    """The worst of the three: keeping them is worse than having none.

    The scraper stops matching on filename the moment a hash exists, so the ROM
    would be confidently identified as whatever used to sit under that name.
    And nothing would ever repair it, because the size test that noticed the
    change fires once and the row is about to be written with the new size."""
    from handler.filesystem import rom_scanner as scanner

    library = tmp_path / "roms" / "psx"
    library.mkdir(parents=True)
    (library / "game.iso").write_bytes(b"x" * 4096)

    _write_settings(tmp_path, monkeypatch, {"hash_max_bytes": 1024})

    class _Platform:
        id = 1
        slug = "psx"
        fs_slug = "psx"

    class _Existing:
        fs_size_bytes = 300            # what the row remembers
        crc_hash = "DEADBEEF"
        md5_hash = "b" * 32
        sha1_hash = "a" * 40
        extra_disk = False

    written: dict = {}
    cleared: list = []

    async def _nothing(*a, **k):
        return None

    async def _no_platforms(*a, **k):
        return []

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _no_platforms)
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert",
                        lambda *a, **k: _as_awaitable(_Platform()))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name",
                        lambda *a, **k: _as_awaitable(_Existing()))
    monkeypatch.setattr(scanner.rom_handler, "apply_disk_groups", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "clear_container_hashes",
                        lambda *a, **k: _as_awaitable(cleared.append(k) or None))
    monkeypatch.setattr(scanner.rom_handler, "upsert",
                        lambda **k: _as_awaitable(written.update({k["fs_name"]: k})))

    await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert written["game.iso"]["crc_hash"] == ""
    assert written["game.iso"]["md5_hash"] == ""
    assert cleared and cleared[0].get("drop_sha1") is True


async def _as_awaitable(value):
    return value


def test_the_operator_ceiling_reaches_inside_an_archive(tmp_path):
    """The ceiling measured the file on disk, which for an archive is the
    COMPRESSED size - so a PlayStation 2 set in .7z sailed under a 2 GiB
    ceiling and was then read, and extracted, at four and a half."""
    import zipfile as _zipfile

    from handler.filesystem.rom_scanner import _compute_hashes

    member = b"i" * 200_000
    archive = tmp_path / "game.zip"
    with _zipfile.ZipFile(archive, "w", _zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("game.iso", member)

    assert archive.stat().st_size < 100_000, "the test needs it to compress well"

    # No operator ceiling: hashed as before.
    assert _compute_hashes(archive)[1] != ""
    # A ceiling under the member's real size turns it away, even though the
    # file on disk is comfortably below it.
    assert _compute_hashes(archive, 100_000) == ("", "", "")


# ── what the page is told ────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("hashes, expected", [
    ({}, False),
    ({"crc_hash": "DEADBEEF"}, True),
    ({"sha1_hash": "a" * 40}, True),
    ({"md5_hash": "b" * 32}, True),
])
async def test_the_rom_page_learns_whether_the_file_is_identified_by_hash(
    monkeypatch, hashes, expected
):
    """The button to compute them only makes sense for a file that has none, so
    the payload carries that - and only that. The digests themselves are of no
    use to a browser and are not sent."""
    from endpoints.roms import roms_router
    from handler.database.rom_handler import rom_handler
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    rom = Rom(id=7, platform_id=1, fs_name="game.iso", fs_name_no_ext="game",
              fs_extension="iso", fs_path="/roms/psx", fs_size_bytes=1, **hashes)
    rom.platform = RomPlatform(id=1, slug="psx", fs_slug="psx", name="PlayStation")

    async def _get(rom_id):
        return rom

    monkeypatch.setattr(rom_handler, "get_with_platform", _get)

    out = await roms_router.get_rom.__wrapped__(None, 7)
    assert out["has_hashes"] is expected
    # The digests travel with it now: they are listed among the file's facts,
    # so that asking for them has a visible answer rather than a button that
    # quietly goes away. The flag still decides whether the button is offered.
    for key in ("crc_hash", "md5_hash", "sha1_hash"):
        assert key in out
        assert out[key] == hashes.get(key)
