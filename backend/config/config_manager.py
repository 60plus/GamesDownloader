"""Runtime-mutable configuration stored as YAML on disk.

Handles API keys, SMTP, webhooks, torrent client settings, etc.
Thread-safe singleton - reads on demand, writes atomically.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml

from config import CONFIG_PATH

_CONFIG_FILE = CONFIG_PATH / "settings.yaml"
_lock = threading.Lock()


def _ensure_dir() -> None:
    _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _read_raw() -> dict[str, Any]:
    """Read config file (caller must hold _lock)."""
    _ensure_dir()
    if not _CONFIG_FILE.exists():
        return {}
    return yaml.safe_load(_CONFIG_FILE.read_text(encoding="utf-8")) or {}


def _write_atomic(data: dict[str, Any]) -> None:
    """Write config atomically via a temp file + rename (caller must hold _lock)."""
    _ensure_dir()
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=_CONFIG_FILE.parent, prefix=".settings_", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        # os.replace is atomic on POSIX; on Windows it may raise if dest is locked
        os.replace(tmp_path, _CONFIG_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_all() -> dict[str, Any]:
    with _lock:
        return _read_raw()


def save_all(data: dict[str, Any]) -> None:
    with _lock:
        _write_atomic(data)


def get_section(section: str) -> dict[str, Any]:
    with _lock:
        return _read_raw().get(section, {})


def save_section(section: str, values: dict[str, Any]) -> None:
    """Read-modify-write under a single lock to prevent TOCTOU races."""
    with _lock:
        data = _read_raw()
        data[section] = values
        _write_atomic(data)


# ── Convenience accessors ────────────────────────────────────────────────────

def get_api_keys() -> dict[str, str]:
    return get_section("api_keys")


def save_api_keys(keys: dict[str, str]) -> None:
    save_section("api_keys", keys)


def get_smtp_config() -> dict[str, Any]:
    return get_section("smtp")


def save_smtp_config(cfg: dict[str, Any]) -> None:
    save_section("smtp", cfg)


def get_webhook_config() -> dict[str, Any]:
    return get_section("webhooks")


def save_webhook_config(cfg: dict[str, Any]) -> None:
    save_section("webhooks", cfg)


def get_torrent_config() -> dict[str, Any]:
    return get_section("torrent")


def save_torrent_config(cfg: dict[str, Any]) -> None:
    save_section("torrent", cfg)


def get_security_config() -> dict[str, Any]:
    return get_section("security")


def save_security_config(cfg: dict[str, Any]) -> None:
    save_section("security", cfg)
