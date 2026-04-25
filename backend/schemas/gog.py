"""Pydantic schemas for GOG endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class GogGameResponse(BaseModel):
    id: int
    gog_id: int
    slug: str
    title: str
    summary: str | None = None
    genres: list[str] | None = None
    tags: list[str] | None = None
    release_date: str | None = None
    developer: str | None = None
    publisher: str | None = None
    rating: float | None = None
    os_windows: bool = False
    os_mac: bool = False
    os_linux: bool = False
    cover_url: str | None = None
    background_url: str | None = None
    icon_url: str | None = None
    screenshots: list[str] | None = None
    version: str | None = None
    is_downloaded: bool = False
    file_size: int | None = None

    model_config = {"from_attributes": True}


class GogGameDetail(GogGameResponse):
    installers: dict | None = None
    extras: dict | None = None
    dlcs: list | None = None
    changelog: str | None = None
    download_path: str | None = None


class GogSyncStatus(BaseModel):
    total: int = 0
    synced: int = 0
    in_progress: bool = False


class GogAuthStatus(BaseModel):
    authenticated: bool = False
    username: str | None = None
    avatar_url: str | None = None
