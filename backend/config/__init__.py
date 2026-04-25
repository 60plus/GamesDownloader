"""GamesDownloaderV3 - centralised configuration.

All settings come from environment variables with typed defaults.
Runtime-mutable settings (API keys, SMTP, etc.) live in ConfigManager (YAML).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int = 0) -> int:
    return int(os.environ.get(key, str(default)))


def _env_bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("1", "true", "yes")


# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_PATH: Final[str] = _env("GD_BASE_PATH", "/data")
CONFIG_PATH: Final[Path] = Path(BASE_PATH) / "config"
RESOURCES_PATH: Final[str] = str(Path(BASE_PATH) / "resources")
ROMS_PATH: Final[str] = _env("GD_ROMS_PATH", str(Path(BASE_PATH) / "games" / "roms"))
GAMES_PATH: Final[str] = _env("GD_GAMES_PATH", str(Path(BASE_PATH) / "games"))
DOWNLOADS_PATH: Final[str] = _env("GD_DOWNLOADS_PATH", str(Path(BASE_PATH) / "downloads"))
PLUGINS_PATH: Final[str] = _env("GD_PLUGINS_PATH", str(Path(BASE_PATH) / "plugins"))

# ── Database ──────────────────────────────────────────────────────────────────
DB_HOST: Final[str] = _env("DB_HOST", "localhost")
DB_PORT: Final[int] = _env_int("DB_PORT", 3306)
DB_NAME: Final[str] = _env("DB_NAME", "gamesdownloader")
DB_USER: Final[str] = _env("DB_USER", "gd")
DB_PASSWD: Final[str] = _env("DB_PASSWD", "gd")
DB_DRIVER: Final[str] = _env("DB_DRIVER", "aiomysql")

DATABASE_URL: Final[str] = (
    f"mysql+{DB_DRIVER}://{DB_USER}:{DB_PASSWD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
SYNC_DATABASE_URL: Final[str] = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_HOST: Final[str] = _env("REDIS_HOST", "localhost")
REDIS_PORT: Final[int] = _env_int("REDIS_PORT", 6379)
REDIS_PASSWORD: Final[str] = _env("REDIS_PASSWORD", "")
REDIS_URL: Final[str] = (
    f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
    if REDIS_PASSWORD
    else f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
)

# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_SECRET_KEY: Final[str] = _env("GD_AUTH_SECRET_KEY", "change-me-in-production")
AUTH_ALGORITHM: Final[str] = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = _env_int("GD_TOKEN_EXPIRE_MIN", 60)
REFRESH_TOKEN_EXPIRE_DAYS: Final[int] = _env_int("GD_REFRESH_EXPIRE_DAYS", 7)

# ── Server ────────────────────────────────────────────────────────────────────
DEV_HOST: Final[str] = _env("GD_DEV_HOST", "0.0.0.0")
DEV_PORT: Final[int] = _env_int("GD_DEV_PORT", 8080)
DEBUG: Final[bool] = _env_bool("GD_DEBUG", False)

# ── Task queue ────────────────────────────────────────────────────────────────
TASK_TIMEOUT: Final[int] = _env_int("GD_TASK_TIMEOUT", 3600)  # seconds
