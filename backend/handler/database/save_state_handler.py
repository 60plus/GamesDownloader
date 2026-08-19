"""Database handler for ROM savestates and battery saves."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.rom_save_state import RomSave, RomSaveState


class SaveStateHandler(DBBaseHandler):
    model = RomSaveState   # default for DBBaseHandler helpers

    # ── Savestates ────────────────────────────────────────────────────────────

    @begin_session
    async def create_state(
        self, state: RomSaveState, *, session: AsyncSession = None
    ) -> RomSaveState:
        session.add(state)
        await session.flush()
        await session.refresh(state)
        return state

    # Ordered by updated_at, NOT created_at: a slot keeps its original created_at
    # when re-saved, so "newest first" by creation would rank a freshly written
    # slot behind a stale one - and resume-from-newest would load the wrong save.
    @begin_session
    async def list_states(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> list[RomSaveState]:
        result = await session.execute(
            select(RomSaveState)
            .where(RomSaveState.user_id == user_id, RomSaveState.rom_id == rom_id)
            .order_by(RomSaveState.updated_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def list_states_for_rom(
        self, rom_id: int, *, session: AsyncSession = None
    ) -> list[RomSaveState]:
        """Every player's savestates for one ROM.

        Not scoped to a user, unlike everything around it, because the caller
        is removing the ROM itself: what has to be found is every file that
        would otherwise be left behind, whoever it belongs to.
        """
        result = await session.execute(
            select(RomSaveState).where(RomSaveState.rom_id == rom_id)
        )
        return list(result.scalars().all())

    @begin_session
    async def list_saves_for_rom(
        self, rom_id: int, *, session: AsyncSession = None
    ) -> list[RomSave]:
        """Every player's battery saves for one ROM. See list_states_for_rom."""
        result = await session.execute(
            select(RomSave).where(RomSave.rom_id == rom_id)
        )
        return list(result.scalars().all())

    @begin_session
    async def list_all_states_for_user(
        self, user_id: int, *, session: AsyncSession = None
    ) -> list[RomSaveState]:
        result = await session.execute(
            select(RomSaveState)
            .where(RomSaveState.user_id == user_id)
            .order_by(RomSaveState.updated_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def get_state_by_slot(
        self, user_id: int, rom_id: int, slot: int, *, session: AsyncSession = None
    ) -> RomSaveState | None:
        """The savestate currently occupying `slot` - the row an upload replaces."""
        result = await session.execute(
            select(RomSaveState).where(
                RomSaveState.user_id == user_id,
                RomSaveState.rom_id == rom_id,
                RomSaveState.slot == slot,
            )
        )
        return result.scalar_one_or_none()

    @begin_session
    async def update_state(
        self, state_id: int, data: dict, *, session: AsyncSession = None
    ) -> RomSaveState | None:
        state = await session.get(RomSaveState, state_id)
        if state is None:
            return None
        for k, v in data.items():
            setattr(state, k, v)
        await session.flush()
        await session.refresh(state)
        return state

    @begin_session
    async def get_state(
        self, state_id: int, user_id: int, *, session: AsyncSession = None
    ) -> RomSaveState | None:
        result = await session.execute(
            select(RomSaveState).where(
                RomSaveState.id == state_id,
                RomSaveState.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @begin_session
    async def get_state_any(
        self, state_id: int, *, session: AsyncSession = None
    ) -> RomSaveState | None:
        """A savestate row without an ownership check.

        Only for the signed thumbnail route, where the URL signature is the
        authorisation. Everything else must use get_state(state_id, user_id).
        """
        return await session.get(RomSaveState, state_id)

    @begin_session
    async def delete_state(
        self, state_id: int, user_id: int, *, session: AsyncSession = None
    ) -> bool:
        state = await session.get(RomSaveState, state_id)
        if state is None or state.user_id != user_id:
            return False
        await session.delete(state)
        return True

    # ── Battery Saves ─────────────────────────────────────────────────────────
    # Writes go through upsert_save only - a plain insert would race.

    @begin_session
    async def list_saves(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> list[RomSave]:
        result = await session.execute(
            select(RomSave)
            .where(RomSave.user_id == user_id, RomSave.rom_id == rom_id)
            .order_by(RomSave.updated_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def list_all_saves_for_user(
        self, user_id: int, *, session: AsyncSession = None
    ) -> list[RomSave]:
        result = await session.execute(
            select(RomSave)
            .where(RomSave.user_id == user_id)
            .order_by(RomSave.updated_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def get_save(
        self, save_id: int, user_id: int, *, session: AsyncSession = None
    ) -> RomSave | None:
        result = await session.execute(
            select(RomSave).where(
                RomSave.id == save_id,
                RomSave.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @begin_session
    async def get_save_for_rom(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> RomSave | None:
        """The single battery save this user holds for a ROM.

        The .srm is the whole SRAM chip, so there is only ever one current one;
        an upload overwrites it rather than piling up copies.
        """
        result = await session.execute(
            select(RomSave)
            .where(RomSave.user_id == user_id, RomSave.rom_id == rom_id)
            .order_by(RomSave.updated_at.desc())
        )
        return result.scalars().first()

    @begin_session
    async def upsert_save(
        self, user_id: int, rom_id: int, values: dict, *, session: AsyncSession = None
    ) -> RomSave | None:
        """Insert-or-update the ROM's battery save in ONE statement.

        Atomic on purpose: the player uploads SRAM from two places that can fire
        together (EJS_onSaveSave and the 60s auto-sync), and a read-then-insert
        let both racers insert - which is exactly how a game with one in-game
        save ended up with two identical battery rows.
        """
        stmt = mysql_insert(RomSave).values(user_id=user_id, rom_id=rom_id, **values)
        stmt = stmt.on_duplicate_key_update(**values)
        await session.execute(stmt)
        return (await session.execute(
            select(RomSave).where(RomSave.user_id == user_id, RomSave.rom_id == rom_id)
        )).scalars().first()

    @begin_session
    async def update_save(
        self, save_id: int, data: dict, *, session: AsyncSession = None
    ) -> RomSave | None:
        save = await session.get(RomSave, save_id)
        if save is None:
            return None
        for k, v in data.items():
            setattr(save, k, v)
        await session.flush()
        await session.refresh(save)
        return save

    @begin_session
    async def delete_save(
        self, save_id: int, user_id: int, *, session: AsyncSession = None
    ) -> bool:
        save = await session.get(RomSave, save_id)
        if save is None or save.user_id != user_id:
            return False
        await session.delete(save)
        return True

    # ── Quota ─────────────────────────────────────────────────────────────────

    @begin_session
    async def get_user_total_size(
        self, user_id: int, *, session: AsyncSession = None
    ) -> int:
        """Total bytes used by all states + saves for this user.

        Screenshots count. They are written to disk next to the state and are
        the larger half of a slot more often than not; leaving them out let an
        import park unlimited image bytes on the host while the quota read back
        a few kilobytes.
        """
        state_bytes = await session.scalar(
            select(func.coalesce(func.sum(RomSaveState.file_size_bytes), 0)
                   + func.coalesce(func.sum(RomSaveState.screenshot_size_bytes), 0))
            .where(RomSaveState.user_id == user_id)
        ) or 0
        save_bytes = await session.scalar(
            select(func.coalesce(func.sum(RomSave.file_size_bytes), 0))
            .where(RomSave.user_id == user_id)
        ) or 0
        return int(state_bytes) + int(save_bytes)


save_state_handler = SaveStateHandler()
