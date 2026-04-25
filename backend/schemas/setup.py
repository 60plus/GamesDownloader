"""Pydantic schemas for setup / configuration endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SetupStatus(BaseModel):
    is_setup_complete: bool = False
    has_admin: bool = False
    has_db: bool = False


class ApiKeysRequest(BaseModel):
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    steamgriddb_api_key: str = ""
    rawg_api_key: str = ""
    screenscraper_user: str = ""
    screenscraper_password: str = ""
    ra_api_key: str = ""


class SmtpConfigRequest(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_address: str = ""
    use_tls: bool = True


class WebhookConfigRequest(BaseModel):
    enabled: bool = False
    url: str = ""
    events: list[str] = Field(default_factory=list)


class TorrentConfigRequest(BaseModel):
    client: str = "qbittorrent"  # or "transmission"
    host: str = "localhost"
    port: int = 8080
    username: str = ""
    password: str = ""
    download_path: str = "/data/downloads"


class SecurityConfigRequest(BaseModel):
    session_duration_days: int = 7
    remember_me_days: int = 30
    oidc_enabled: bool = False
    oidc_provider_url: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""


class AppSettingsRequest(BaseModel):
    app_name: str = "GamesDownloaderV3"
    default_theme: str = "default"
    default_skin: str = "purple"
    enable_registrations: bool = False
    enable_game_requests: bool = True
