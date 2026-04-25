"""Pydantic schemas for plugin endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PluginInfo(BaseModel):
    """Response model for a single plugin."""

    plugin_id: str
    name: str
    version: str
    author: str
    description: str | None = None
    plugin_type: str
    enabled: bool
    has_logo: bool = False
    installed_at: datetime | None = None
    config: dict[str, Any] | None = None
    config_schema: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class PluginConfigUpdate(BaseModel):
    """Request body for updating plugin configuration.
    Accepts the config dict directly (no wrapper key)."""

    model_config = {"extra": "allow"}

    # The config is sent as the root object directly, e.g. {"enabled": true}
    # We accept any keys via extra="allow" and extract them in the endpoint.
