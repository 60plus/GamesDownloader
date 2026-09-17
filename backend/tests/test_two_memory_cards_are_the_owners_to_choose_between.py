"""Two memory cards for one game are the owner's to choose between, and only theirs.

A rename merge that meets a card on both rows keeps the surviving row's card in
use and sets the other aside (`rom_save_conflicts`). These are the routes the
owner uses to see both, download either, and keep one:

  GET  /api/savestates/conflicts                  mine, with both cards described
  GET  /api/savestates/conflicts/{id}/export      the set-aside card, as a backup
  POST /api/savestates/conflicts/{id}/resolve     keep "current" or "set_aside"

Nobody else sees them, an administrator included: a memory card is private.
Deleting the game takes a set-aside card with the others, or its file would be
left on disk with nothing able to name it.

A real database and real files throughout.
"""
from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.rom import Rom
from models.rom_platform import RomPlatform
from models.rom_save_state import RomSave, RomSaveConflict, RomSaveState

GAME = 1
ME, SOMEBODY_ELSE = 7, 9
BEFORE, DURING = b"PRZED ZMIANA NAZWY", b"W TRAKCIE SKANU, DLUZSZA"


def _request(user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="gdtest", permissions={}), scopes=set()))


@pytest_asyncio.fixture
async def world(tmp_path, monkeypatch):
    import decorators.database as D
    from endpoints.roms import savestate_router as R
    from utils import save_paths

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for model in (RomPlatform, Rom, RomSaveState, RomSave, RomSaveConflict):
            await conn.run_sync(model.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(D, "async_session_factory", maker)

    root = tmp_path / "saves"
    monkeypatch.setattr(save_paths, "_root_cache", root)
    monkeypatch.setattr(R, "_saves_dir",
                        lambda slug, rom_id, user_id: root / slug / str(rom_id) / "saves" / str(user_id))

    current_dir = root / "snes" / str(GAME) / "saves" / str(ME)
    aside_dir = root / "snes" / "2" / "saves" / str(ME)
    theirs_dir = root / "snes" / "2" / "saves" / str(SOMEBODY_ELSE)
    for directory in (current_dir, aside_dir, theirs_dir):
        directory.mkdir(parents=True)
    (current_dir / "Zelda.srm").write_bytes(BEFORE)
    (aside_dir / "Zelda.srm").write_bytes(DURING)
    (theirs_dir / "Zelda.srm").write_bytes(b"ICH")

    async with maker() as db:
        db.add(RomPlatform(id=1, fs_slug="snes", slug="snes", name="SNES"))
        db.add(Rom(id=GAME, platform_id=1, fs_name="Zelda (USA).sfc", fs_name_no_ext="Zelda (USA)",
                   fs_extension="sfc", fs_path="/roms/snes", name="Zelda", fs_size_bytes=10))
        db.add(RomSave(id=1, rom_id=GAME, user_id=ME, file_name="Zelda.srm",
                       file_path=str(current_dir), file_size_bytes=len(BEFORE),
                       content_hash=hashlib.md5(BEFORE).hexdigest(), emulator_core="snes9x",
                       updated_at=datetime(2026, 1, 1, 12, 0, 0)))
        db.add(RomSaveConflict(id=5, rom_id=GAME, user_id=ME, file_name="Zelda.srm",
                               file_path=str(aside_dir), file_size_bytes=len(DURING),
                               content_hash=hashlib.md5(DURING).hexdigest(), emulator_core="snes9x",
                               card_updated_at=datetime(2026, 9, 6, 21, 10, 0)))
        db.add(RomSaveConflict(id=6, rom_id=GAME, user_id=SOMEBODY_ELSE, file_name="Zelda.srm",
                               file_path=str(theirs_dir), file_size_bytes=3))
        await db.commit()

    yield SimpleNamespace(R=R, maker=maker, current=current_dir / "Zelda.srm",
                          aside=aside_dir / "Zelda.srm", theirs=theirs_dir / "Zelda.srm")
    await engine.dispose()


async def _rows(maker, model):
    async with maker() as db:
        return (await db.execute(select(model))).scalars().all()


@pytest.mark.asyncio
async def test_the_owner_sees_both_cards_and_nobody_else_s(world):
    listed = await world.R.list_save_conflicts.__wrapped__(_request())

    assert [c["id"] for c in listed] == [5], f"lista pokazuje cudze albo zadne karty: {listed}"
    card = listed[0]
    assert card["rom_id"] == GAME and card["rom_name"] == "Zelda"
    assert card["set_aside"]["file_size_bytes"] == len(DURING)
    assert card["set_aside"]["updated_at"].startswith("2026-09-06T21:10"), (
        "nie widac, kiedy odlozona karta byla zapisana - nie ma jak wybrac"
    )
    assert card["set_aside"]["export_url"] == "/api/savestates/conflicts/5/export"
    assert card["current"]["id"] == 1 and card["current"]["file_size_bytes"] == len(BEFORE)


@pytest.mark.asyncio
async def test_keeping_the_current_card_throws_the_other_one_away(world):
    await world.R.resolve_save_conflict.__wrapped__(
        _request(), 5, world.R.SaveConflictChoice(keep="current"))

    assert world.current.read_bytes() == BEFORE, "biezaca karta zostala ruszona"
    assert not world.aside.exists(), "plik odlozonej karty zostal na dysku"
    assert [c.id for c in await _rows(world.maker, RomSaveConflict)] == [6]


@pytest.mark.asyncio
async def test_keeping_the_set_aside_card_puts_it_in_use(world):
    result = await world.R.resolve_save_conflict.__wrapped__(
        _request(), 5, world.R.SaveConflictChoice(keep="set_aside"))

    cards = await _rows(world.maker, RomSave)
    assert len(cards) == 1, "zamiast podmienic karte powstala druga"
    card = cards[0]
    in_use = Path(card.file_path) / card.file_name
    assert in_use.read_bytes() == DURING, "w uzyciu nadal jest poprzednia karta"
    assert card.content_hash == hashlib.md5(DURING).hexdigest(), (
        "hasz karty nie zgadza sie z trescia - odtwarzacz nie pozna, ze karta sie zmienila"
    )
    assert card.file_size_bytes == len(DURING)
    assert result["save"]["content_hash"] == card.content_hash
    assert not world.aside.exists(), "plik odlozonej karty zostal na dysku obok"
    assert [c.id for c in await _rows(world.maker, RomSaveConflict)] == [6]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["resolve", "export"])
async def test_somebody_else_s_card_is_not_found(world, route):
    with pytest.raises(HTTPException) as refused:
        if route == "resolve":
            await world.R.resolve_save_conflict.__wrapped__(
                _request(), 6, world.R.SaveConflictChoice(keep="current"))
        else:
            await world.R.export_save_conflict.__wrapped__(_request(), 6)

    assert refused.value.status_code == 404
    assert world.theirs.exists() and len(await _rows(world.maker, RomSaveConflict)) == 2


@pytest.mark.asyncio
async def test_a_set_aside_card_whose_file_is_gone_cannot_be_kept(world):
    """Keeping it would write an empty card over a real one. The choice stays
    open, so the current card can still be kept."""
    world.aside.unlink()

    with pytest.raises(HTTPException) as refused:
        await world.R.resolve_save_conflict.__wrapped__(
            _request(), 5, world.R.SaveConflictChoice(keep="set_aside"))

    assert refused.value.status_code == 409
    assert world.current.read_bytes() == BEFORE
    assert 5 in [c.id for c in await _rows(world.maker, RomSaveConflict)]


@pytest.mark.asyncio
async def test_the_set_aside_card_can_be_downloaded_first(world):
    response = await world.R.export_save_conflict.__wrapped__(_request(), 5)
    try:
        with zipfile.ZipFile(response.path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
    finally:
        Path(response.path).unlink(missing_ok=True)

    assert DURING in members.values(), f"archiwum nie zawiera odlozonej karty: {list(members)}"


@pytest.mark.asyncio
async def test_deleting_the_game_takes_a_set_aside_card_too(world):
    """The deletion routes collect every save through `list_saves_for_rom`.
    A set-aside card left out of that would stay on disk with nothing able to
    name it once the row cascades away."""
    from handler.database.save_state_handler import save_state_handler

    listed = await save_state_handler.list_saves_for_rom(GAME)

    paths = {str(Path(s.file_path) / s.file_name) for s in listed}
    assert str(world.aside) in paths and str(world.theirs) in paths, (
        "usuniecie gry nie zabierze odlozonych kart"
    )
    assert str(world.current) in paths


def test_the_routes_are_declared_where_a_rom_id_cannot_swallow_them():
    """`/{rom_id}/saves` and friends take the first segment as a number; these
    routes are registered by the same router and must be reachable."""
    from endpoints.roms import savestate_router as R

    paths = {getattr(r, "path", "") for r in R.router.routes}
    for path in ("/api/savestates/conflicts",
                 "/api/savestates/conflicts/{conflict_id}/export",
                 "/api/savestates/conflicts/{conflict_id}/resolve"):
        assert path in paths, f"brak trasy {path}"
