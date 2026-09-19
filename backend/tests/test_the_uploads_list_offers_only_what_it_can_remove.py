"""A row that offers a bin has to be a row the bin can empty.

"My uploads" lists what an account is charged for and puts a delete beside each
line. For a ROM it wrote `can_delete: True` on every row without asking, and the
route behind the button asks a harder question: deleting a ROM takes its whole
disc set, so `can_delete_rom_set` refuses unless every disc of the title is this
account's.

A single-disc ROM is unaffected - its set is itself - so the flag was right for
the common case and wrong exactly where it mattered: an account that supplied
the one disc a set was missing sees a delete on it that can only answer 403.

Track files are the documented exception: a .bin behind an uploaded .cue carries
no owner of its own, and refusing over that would stop an uploader removing
their own upload. The flag has to make the same exception, or it goes wrong the
other way and hides a button that would have worked.

WHAT THE FIRST VERSION OF THIS FILE GOT WRONG, and why it is written down here.

The fixture built rows the scanner cannot produce: `disk_group` AND `track_of`
on the same row. There is exactly one writer of that column - `apply_adjust`,
fed by `plan_disk_assignments` - and it sets EITHER a group and a number for a
disc, OR a `track_of` and nothing else for a track. A single-disc title never
gets a group at all, because `group_disks` drops any title with fewer than two
members. So the branch the fixture was exercising is unreachable in production,
and the case that IS reachable was never tested.

The parity test then counted a set's members with a query of its own - by group,
like the flag - while the route counts them with `disk_set`, which walks UP from
a track to its sheet and DOWN from a sheet to its tracks. Two rules spelled two
ways, compared against each other, agreeing about a shape neither would meet.
It is the route's list or it is not parity, so this file asks the route's own
`disk_set` now.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from handler.library.ownership import can_delete_rom_set
from models.rom import Rom
from models.rom_platform import RomPlatform

ME = 3
SOMEBODY_ELSE = 7
UPLOADER = {Scope.LIBRARY_UPLOAD}


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
        from models.rom_added_file import RomAddedFile
        await conn.run_sync(RomAddedFile.__table__.create)
        # `owned_games` answers about BOTH kinds and attaches the shelf each
        # game sits on, so the game side has to exist even when this file only
        # asks about ROMs.
        from models.library import Library, LibraryMembership
        from models.library_file import LibraryFile
        from models.library_game import LibraryGame
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    from handler.library import quota
    monkeypatch.setattr(quota, "async_session_factory", maker, raising=False)

    def _rom(rid, fs_name, owner, **kw):
        """One ROM row, with the columns the model insists on filled in.

        `fs_extension` is NOT NULL, and forgetting it fails the whole fixture
        rather than the assertion - which reads as the feature being broken.
        """
        from pathlib import Path as _P
        return Rom(
            id=rid, platform_id=1, fs_name=fs_name,
            fs_name_no_ext=_P(fs_name).stem,
            fs_extension=_P(fs_name).suffix.lstrip("."),
            fs_path="/roms/psx", name=kw.pop("name", _P(fs_name).stem),
            slug=kw.pop("slug", _P(fs_name).stem.lower()),
            published_by=owner, missing_from_fs=False, fs_size_bytes=10, **kw)

    def _disc(rid, fs_name, owner, group, number, **kw):
        """A disc of a multi-disc title: a group and a number, never a track."""
        return _rom(rid, fs_name, owner, disk_group=group, disk_number=number,
                    extra_disk=number != 1, **kw)

    def _track(rid, fs_name, owner, sheet, **kw):
        """A data file behind a sheet.

        No group and no number, whatever the sheet has - that is the shape
        `plan_disk_assignments` writes, and it is why a track can never be found
        by asking for a group.
        """
        return _rom(rid, fs_name, owner, track_of=sheet, extra_disk=True, **kw)

    async with maker() as session:
        session.add(RomPlatform(id=1, slug="psx", name="PlayStation", fs_slug="psx"))
        # A single-disc ROM of mine: its set is itself.
        session.add(_rom(1, "Solo.chd", ME))
        # A two disc title where I supplied the second disc only.
        session.add(_disc(2, "Set (Disc 1).chd", SOMEBODY_ELSE, "set", 1,
                          name="Set", slug="set"))
        session.add(_disc(3, "Set (Disc 2).chd", ME, "set", 2,
                          name="Set", slug="set"))
        # A single-disc title of mine kept as a sheet, whose track file carries
        # no owner. NO disk_group on either row: one disc is not a set.
        session.add(_rom(4, "Mine.cue", ME, name="Mine", slug="mine"))
        session.add(_track(5, "Mine.bin", None, "Mine.cue",
                           name="Mine", slug="mine"))
        # My sheet over somebody else's data file. Reachable without anybody
        # doing anything strange: a .bin IS a ROM extension, so an account that
        # uploads one on its own gets a row and a stamp for it; a .cue naming
        # that file arrives later and the scanner marks the .bin as its track,
        # leaving the owner where it was.
        session.add(_rom(6, "Shared.cue", ME, name="Shared", slug="shared"))
        session.add(_track(7, "Shared.bin", SOMEBODY_ELSE, "Shared.cue",
                           name="Shared", slug="shared"))
        # The same thing the other way up: my data file under somebody else's
        # sheet. Acting on it acts on THEIR disc, which is what `_sheet_of` is
        # for and what a flag computed from the row alone cannot see.
        session.add(_rom(8, "Other.cue", SOMEBODY_ELSE, name="Other", slug="other"))
        session.add(_track(9, "Other.bin", ME, "Other.cue",
                           name="Other", slug="other"))
        await session.commit()
    yield maker
    await engine.dispose()


def _flag(rows, rom_id):
    return next(r["can_delete"] for r in rows if r["kind"] == "rom" and r["id"] == rom_id)


@pytest.mark.asyncio
async def test_the_fixture_holds_shapes_the_scanner_writes(db):
    """A guard on the test rather than on the code.

    The previous fixture gave a track file a `disk_group`, which no scan can
    produce, and the assertions passed over a state that cannot occur. If this
    ever fails, the rows below stopped describing the library.
    """
    from sqlalchemy import select as _select

    async with db() as session:
        rows = (await session.execute(_select(Rom))).scalars().all()

    both = [r.fs_name for r in rows if r.track_of and r.disk_group]
    assert not both, (
        f"wiersze z grupa I sciezka naraz: {both} - `plan_disk_assignments` "
        "zapisuje ALBO grupe, ALBO track_of, nigdy oba"
    )
    grouped = {r.disk_group for r in rows if r.disk_group}
    for group in grouped:
        members = [r for r in rows if r.disk_group == group]
        assert len(members) > 1, (
            f"grupa {group!r} ma jednego czlonka - `group_disks` odrzuca tytul "
            "jednoplytowy, wiec taki wiersz nie dostaje grupy"
        )


@pytest.mark.asyncio
async def test_a_single_disc_rom_still_offers_its_bin(db):
    from handler.library import quota

    assert _flag(await quota.owned_games(ME), 1) is True


@pytest.mark.asyncio
async def test_a_disc_from_a_set_i_do_not_wholly_own_offers_nothing(db):
    from handler.library import quota

    assert _flag(await quota.owned_games(ME), 3) is False, (
        "wiersz obiecuje kosz, a trasa za nim odmowi - komplet plyt nalezy "
        "do dwoch osob"
    )


@pytest.mark.asyncio
async def test_an_unowned_track_file_does_not_take_the_bin_away(db):
    """The documented exception. A .bin behind an uploaded .cue has no owner of
    its own, and reading that as somebody else's would hide a button that works."""
    from handler.library import quota

    assert _flag(await quota.owned_games(ME), 4) is True


@pytest.mark.asyncio
async def test_a_sheet_over_somebody_elses_data_file_offers_nothing(db):
    """The case the group-only question cannot see.

    `Shared.cue` is mine and has no group, so the flag answered "its set is
    itself, and it is mine" and stopped. The route does not stop there: it adds
    the tracks of the sheet, finds one carrying another account's name, and
    refuses. The bin was offered and could only answer 403.
    """
    from handler.library import quota

    assert _flag(await quota.owned_games(ME), 6) is False, (
        "kosz przy moim arkuszu, ktorego plik danych nalezy do kogos innego - "
        "trasa odmowi, bo sciezka Z WLASCICIELEM nie jest udokumentowanym "
        "wyjatkiem"
    )


@pytest.mark.asyncio
async def test_my_data_file_under_somebody_elses_sheet_offers_nothing(db):
    """The same divergence upside down, and it needs no track exception at all:
    acting on a track acts on its SHEET, and the sheet is not mine."""
    from handler.library import quota

    assert _flag(await quota.owned_games(ME), 9) is False, (
        "kosz przy moim pliku danych lezacym pod cudzym arkuszem - trasa "
        "przechodzi na arkusz i odmawia"
    )


@pytest.mark.asyncio
async def test_the_flag_agrees_with_the_rule_the_route_applies(db):
    """The pair. Whatever the list says, the route has to say the same, or one
    of them is offering something the other refuses.

    Asked with the ROUTE's own list of members - `rom_handler.disk_set`, the
    call `delete_rom` makes - and not with a second query that happens to be
    written here. A parity test that counts the set its own way is not a parity
    test; it is the same mistake twice, agreeing with itself.
    """
    from handler.database.rom_handler import RomHandler
    from handler.library import quota

    rom_handler = RomHandler()
    rows = [r for r in await quota.owned_games(ME) if r["kind"] == "rom"]
    assert rows, "lista nie zwrocila zadnego ROM-u - test nie sprawdza niczego"

    disagreed = []
    async with db() as session:
        for row in rows:
            named = await session.get(Rom, row["id"])
            members = await rom_handler.disk_set(row["id"], session=session)
            route = can_delete_rom_set(UPLOADER, ME, named, members)
            if row["can_delete"] != route:
                disagreed.append(
                    f"{named.fs_name}: lista={row['can_delete']} trasa={route}")
    assert not disagreed, "lista i trasa nie zgadzaja sie: " + "; ".join(disagreed)


@pytest.mark.asyncio
async def test_the_pair_is_asked_about_more_than_one_shape(db):
    """A guard on the test above.

    If the list ever stops returning the awkward rows - a disc of a shared set,
    a sheet over another account's file, a file under another account's sheet -
    the parity test still passes and stops meaning anything.
    """
    from handler.library import quota

    listed = {r["id"] for r in await quota.owned_games(ME) if r["kind"] == "rom"}
    assert {1, 3, 4, 6, 9} <= listed, (
        f"lista wgran nie zawiera juz wszystkich badanych ksztaltow: {listed}"
    )
