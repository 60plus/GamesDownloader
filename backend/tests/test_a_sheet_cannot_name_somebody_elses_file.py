"""A deletion may not take a file just because a sheet says its name.

Deleting a ROM with its files also removes data files that a sheet NAMES but
which never became rows of their own - a Dreamcast .gdi beside track02.raw, for
instance. Nothing else points at those bytes once the sheet goes, so leaving
them would strand them for ever.

The list is built by reading the sheet's own text, and the only thing standing
between that and somebody else's file was a database check on the FILE NAME.
Files that are not ROM extensions never have rows, so that check never protects
them - and it is exactly those files the exception exists for.

So: upload `evil.cue` whose text reads FILE "Victim (Disc 1).sbi", let it be
scanned in (a .cue IS a ROM extension, so it gets a row and an owner), then
delete it with delete_files=true. The .sbi has no row, no other sheet names it,
and it goes. The same reaches an .m3u a playlist route wrote and the .raw tracks
of a neighbouring rip.

The fix asks about the STEM as well as the name. A file called `Victim (Disc 1)
.sbi` sits beside `Victim (Disc 1).cue`, which IS somebody's row - so the file
belongs to that disc, and a sheet from another set does not get to name it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


def _rom(name, path, rom_id=1, platform_id=1):
    return SimpleNamespace(id=rom_id, fs_name=name, fs_path=str(path),
                           platform_id=platform_id,
                           fs_name_no_ext=Path(name).stem)


@pytest.fixture
def shelf(tmp_path):
    """One platform directory holding two unrelated titles."""
    (tmp_path / "Victim (Disc 1).cue").write_text('FILE "Victim (Disc 1).bin" BINARY\n')
    (tmp_path / "Victim (Disc 1).bin").write_bytes(b"x")
    (tmp_path / "Victim (Disc 1).sbi").write_bytes(b"x")      # no row, ever
    (tmp_path / "evil.cue").write_text('FILE "Victim (Disc 1).sbi" BINARY\n')
    return tmp_path


def test_the_attack_is_what_this_test_thinks_it_is(shelf):
    """Without this, the assertions below could pass because the sheet reader
    never found the file at all."""
    from handler.filesystem.rom_scanner import tracks_referenced_by

    named = tracks_referenced_by(shelf / "evil.cue")
    assert "victim (disc 1).sbi" in {n.lower() for n in named}


@pytest.mark.asyncio
async def test_a_sheet_cannot_take_a_file_that_belongs_to_another_disc(shelf, monkeypatch):
    from endpoints.roms import roms_router as R

    async def names_with_rows(_platform_id, names):
        # `.sbi` is not a ROM extension, so it never has a row of its own.
        return {n.lower() for n in names if n.lower().endswith(".cue")}

    async def stems_with_rows(_platform_id, stems, exclude_ids=()):
        # ...but the disc it belongs to does.
        return {s.lower() for s in stems if s.lower() == "victim (disc 1)"}

    monkeypatch.setattr(R.rom_handler, "fs_names_with_rows", names_with_rows)
    monkeypatch.setattr(R.rom_handler, "stems_with_rows", stems_with_rows)

    taken = await R.removable_tracks([_rom("evil.cue", shelf, rom_id=9)])

    assert [p.name for p in taken] == [], (
        "podlozony arkusz zabiera plik nalezacy do cudzej plyty"
    )


@pytest.mark.asyncio
async def test_a_set_still_takes_its_own_orphaned_tracks(shelf, monkeypatch):
    """The caution that makes this worth doing carefully: the feature has to go
    on working for the case it was written for."""
    from endpoints.roms import roms_router as R

    # A .cue rather than a .gdi: the .gdi grammar carries track numbers and
    # sector sizes, and a bare file name in one parses to nothing - which would
    # make this test pass over an empty list for the wrong reason.
    (shelf / "Rip.cue").write_text('FILE "track02.raw" BINARY\n')
    (shelf / "track02.raw").write_bytes(b"x")

    async def names_with_rows(_platform_id, names):
        return {n.lower() for n in names if n.lower().endswith((".cue", ".gdi"))}

    async def stems_with_rows(_platform_id, stems, exclude_ids=()):
        return {s.lower() for s in stems if s.lower() in ("victim (disc 1)",)}

    monkeypatch.setattr(R.rom_handler, "fs_names_with_rows", names_with_rows)
    monkeypatch.setattr(R.rom_handler, "stems_with_rows", stems_with_rows)

    taken = await R.removable_tracks([_rom("Rip.cue", shelf, rom_id=3)])

    from handler.filesystem.rom_scanner import tracks_referenced_by
    assert "track02.raw" in {n.lower() for n in tracks_referenced_by(shelf / "Rip.cue")}, (
        "test nie odtwarza tego, co mysli - arkusz nie nazywa tej sciezki"
    )
    assert [p.name for p in taken] == ["track02.raw"], (
        "komplet przestal zabierac wlasne osierocone sciezki"
    )


@pytest.mark.asyncio
async def test_a_files_own_set_does_not_protect_it_from_itself(shelf, monkeypatch):
    """The stem of a track file often matches nothing; the stem of a subchannel
    file matches the disc BEING deleted. That disc is in this set, so it must
    not count as "somebody else's" - or a legitimate deletion would leave the
    .sbi behind for ever."""
    from endpoints.roms import roms_router as R

    seen: dict = {}

    async def names_with_rows(_platform_id, names):
        return set()

    async def stems_with_rows(platform_id, stems, exclude_ids=()):
        seen["exclude_ids"] = tuple(exclude_ids)
        return set()

    monkeypatch.setattr(R.rom_handler, "fs_names_with_rows", names_with_rows)
    monkeypatch.setattr(R.rom_handler, "stems_with_rows", stems_with_rows)

    await R.removable_tracks([_rom("Victim (Disc 1).cue", shelf, rom_id=5)])

    assert seen.get("exclude_ids") == (5,), (
        "pytanie o rdzenie nie wyklucza wierszy z kasowanego kompletu, wiec "
        "plyta chroni wlasny plik podkanalu przed usunieciem razem z nia"
    )


# ── The handler behind it ────────────────────────────────────────────────────

def test_the_handler_offers_the_question():
    from handler.database.rom_handler import RomHandler

    assert hasattr(RomHandler, "stems_with_rows"), (
        "brak zapytania o rdzenie nazw, wiec `removable_tracks` nie ma jak "
        "odroznic cudzego pliku od osieroconej sciezki"
    )


# ── The query itself, against a database ─────────────────────────────────────
#
# Every test above hands `removable_tracks` a stub, which is right for testing
# the caller and useless for testing the answer. The stubs agree with what the
# fixture writes, and the fixture wrote `fs_name_no_ext=Path(name).stem` - the
# raw stem. The SCANNER does not: it writes `_strip_tags(stem)`, so the row for
# `Victim (Disc 1).cue` carries `Victim`, not `Victim (Disc 1)`.
#
# That is the whole protection: the stem asked about comes from a file on disk
# and still has its brackets, the stem stored has had them removed, and the two
# can never be equal for any name in the Redump or No-Intro style. Which is to
# say: for every disc that has a .sbi at all, since a subchannel file exists
# because a disc is a regional release with LibCrypt.

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def rows():
    """Two discs, written BOTH ways a real library writes them.

    Measured on the live install: of 48 rows, 26 carried `fs_name_no_ext` with
    the tags stripped and 6 carried the full stem. A fixture that models only
    one of those agrees with whichever half of the code it was written beside -
    which is how the first version of this fix passed its tests and failed on
    the first real disc it met.
    """
    from handler.filesystem.rom_scanner import _strip_tags
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    def _row(rid, fs_name, *, stripped: bool):
        stem = Path(fs_name).stem
        return Rom(
            id=rid, platform_id=1, fs_name=fs_name,
            fs_name_no_ext=_strip_tags(stem) if stripped else stem,
            fs_extension=Path(fs_name).suffix.lstrip("."),
            fs_path="/roms/psx", name=stem,
            slug=stem.lower(), missing_from_fs=False,
            fs_size_bytes=10,
        )

    async with maker() as session:
        session.add(RomPlatform(id=1, slug="psx", name="PlayStation", fs_slug="psx"))
        # The scanner's own expression...
        session.add(_row(1, "Victim (Disc 1).cue", stripped=True))
        session.add(_row(2, "Evil (Europe).cue", stripped=True))
        # ...and the shape the multi-disc rows on the live install actually
        # carry: the whole stem, tags and all.
        session.add(_row(3, "Final Fantasy IX (Europe) (Disc 3).chd", stripped=False))
        await session.commit()
    yield maker, engine
    await engine.dispose()


def test_the_fixture_reproduces_what_the_scanner_stores(rows):
    """Without this the test below could pass or fail for the wrong reason."""
    from handler.filesystem.rom_scanner import _strip_tags

    assert _strip_tags("Victim (Disc 1)") == "Victim", (
        "skaner nie obcina tagow, wiec ten test nie odtwarza stanu bazy"
    )


@pytest.mark.asyncio
async def test_a_disc_whose_row_kept_the_whole_stem_is_protected_too(rows):
    """The half my own fix broke, found by measuring the live library rather
    than by reading the scanner: multi-disc rows there carry the full stem in
    `fs_name_no_ext`, so asking only for the stripped form found nothing."""
    maker, _engine = rows
    from handler.database.rom_handler import RomHandler

    stem = "Final Fantasy IX (Europe) (Disc 3)"
    async with maker() as session:
        got = await RomHandler().stems_with_rows(1, [stem], session=session)

    assert got == {stem.lower()}, (
        "plyta, ktorej wiersz trzyma PELNY rdzen, nie broni swojego pliku "
        "podkanalu - kolumna ma na zywej instalacji oba warianty naraz"
    )


@pytest.mark.asyncio
async def test_a_tagged_disc_still_protects_its_subchannel_file(rows):
    """`Victim (Disc 1).sbi` belongs to `Victim (Disc 1).cue`, and the query has
    to say so. Asking the stored column instead compares `Victim (Disc 1)` with
    `Victim` and answers "nobody's", which is how somebody else's LibCrypt patch
    was removed by a sheet that merely named it."""
    maker, _engine = rows
    from handler.database.rom_handler import RomHandler

    async with maker() as session:
        spoken_for = await RomHandler().stems_with_rows(
            1, ["Victim (Disc 1)"], session=session)

    assert spoken_for == {"victim (disc 1)"}, (
        "plyta z tagiem w nazwie nie broni swojego pliku podkanalu - a wlasnie "
        "plyty z tagami regionu maja LibCrypt, wiec ochrona nie dziala dla "
        "zadnej plyty, dla ktorej powstala"
    )


@pytest.mark.asyncio
async def test_a_stem_nobody_holds_is_still_nobody_s(rows):
    """The other half of the pair. Widening the match until everything looks
    spoken for would leave every orphaned track file on the shelf for ever."""
    maker, _engine = rows
    from handler.database.rom_handler import RomHandler

    async with maker() as session:
        assert await RomHandler().stems_with_rows(
            1, ["track02"], session=session) == set()
        # Not a prefix match either: `Victim` alone is nobody's file here.
        assert await RomHandler().stems_with_rows(
            1, ["Victim"], session=session) == set(), (
            "dopasowanie po obcietym rdzeniu uznaje ZA CUDZY kazdy plik o "
            "nazwie bazowej plyty, wiec komplet nie zabralby wlasnych sciezek"
        )


@pytest.mark.asyncio
async def test_the_set_being_deleted_does_not_protect_its_own(rows):
    maker, _engine = rows
    from handler.database.rom_handler import RomHandler

    async with maker() as session:
        assert await RomHandler().stems_with_rows(
            1, ["Victim (Disc 1)"], exclude_ids=[1], session=session) == set()
