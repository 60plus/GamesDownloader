"""
ConfigHandler - read/write AppConfig with optional Fernet encryption.

Encryption key is derived from AUTH_SECRET_KEY via PBKDF2 so no
extra env var is needed.  Fernet is symmetric AES-128-CBC + HMAC-SHA256.
"""

from __future__ import annotations

import base64
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from models.app_config import AppConfig
from handler.database.base_handler import DBBaseHandler
from decorators.database import begin_session

# ── Derive a stable Fernet key from the app's auth secret ─────────────────────
_SALT = b"gd3-config-salt-v1"   # static salt is fine - key material comes from secret


def _get_fernet() -> Fernet:
    from config import AUTH_SECRET_KEY
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(AUTH_SECRET_KEY.encode()))
    return Fernet(key)


def _encrypt(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def _decrypt(token: str) -> str:
    return _get_fernet().decrypt(token.encode()).decode()


class ConfigHandler(DBBaseHandler):
    model = AppConfig

    @begin_session
    async def get(self, key: str, *, session: AsyncSession = None) -> str | None:
        result = await session.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalars().first()
        if row is None:
            return None
        if row.is_sensitive and row.value:
            try:
                return _decrypt(row.value)
            except Exception:
                return None
        return row.value

    @begin_session
    async def set(self, key: str, value: str, *, sensitive: bool = False, session: AsyncSession = None) -> None:
        result = await session.execute(select(AppConfig).where(AppConfig.key == key))
        row = result.scalars().first()
        stored = _encrypt(value) if sensitive else value
        if row:
            row.value = stored
            row.is_sensitive = sensitive
        else:
            session.add(AppConfig(key=key, value=stored, is_sensitive=sensitive))

    @begin_session
    async def set_many(self, data: dict[str, tuple[str, bool]], *, session: AsyncSession = None) -> None:
        """data = {key: (value, is_sensitive)}"""
        for key, (value, sensitive) in data.items():
            await self.set(key, value, sensitive=sensitive, session=session)

    @begin_session
    async def get_bool(self, key: str, default: bool = False, *, session: AsyncSession = None) -> bool:
        val = await self.get(key, session=session)
        if val is None:
            return default
        return val.lower() in ("true", "1", "yes")

    @begin_session
    async def is_setup_complete(self, *, session: AsyncSession = None) -> bool:
        return await self.get_bool("setup_complete", default=False, session=session)

    @begin_session
    async def mark_setup_complete(self, *, session: AsyncSession = None) -> None:
        await self.set("setup_complete", "true", session=session)


config_handler = ConfigHandler()
