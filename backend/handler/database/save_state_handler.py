"""Database handler for ROM savestates and battery saves."""

from __future__ import annotations

from sqlalchemy import func, select
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

    @begin_session
    async def list_states(
        self, user_id: int, rom_id: int, *, session: AsyncSession = None
    ) -> list[RomSaveState]:
        result = await session.execute(
            select(RomSaveState)
            .where(RomSaveState.user_id == user_id, RomSaveState.rom_id == rom_id)
            .order_by(RomSaveState.created_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def list_all_states_for_user(
        self, user_id: int, *, session: AsyncSession = None
    ) -> list[RomSaveState]:
        result = await session.execute(
            select(RomSaveState)
            .where(RomSaveState.user_id == user_id)
            .order_by(RomSaveState.created_at.desc())
        )
        return list(result.scalars().all())

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
    async def delete_state(
        self, state_id: int, user_id: int, *, session: AsyncSession = None
    ) -> bool:
        state = await session.get(RomSaveState, state_id)
        if state is None or state.user_id != user_id:
            return False
        await session.delete(state)
        return True

    # ── Battery Saves ─────────────────────────────────────────────────────────

    @begin_session
    async def create_save(
        self, save: RomSave, *, session: AsyncSession = None
    ) -> RomSave:
        session.add(save)
        await session.flush()
        await session.refresh(save)
        return save

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
    async def get_save_by_hash(
        self,
        user_id: int,
        rom_id: int,
        content_hash: str,
        *,
        session: AsyncSession = None,
    ) -> RomSave | None:
        result = await session.execute(
            select(RomSave).where(
                RomSave.user_id == user_id,
                RomSave.rom_id == rom_id,
                RomSave.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

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
        """Total bytes used by all states + saves for this user."""
        state_bytes = await session.scalar(
            select(func.coalesce(func.sum(RomSaveState.file_size_bytes), 0))
            .where(RomSaveState.user_id == user_id)
        ) or 0
        save_bytes = await session.scalar(
            select(func.coalesce(func.sum(RomSave.file_size_bytes), 0))
            .where(RomSave.user_id == user_id)
        ) or 0
        return int(state_bytes) + int(save_bytes)


save_state_handler = SaveStateHandler()
