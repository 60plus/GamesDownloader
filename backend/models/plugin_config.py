"""PluginConfig model - tracks installed plugin state and configuration."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class PluginConfig(Base):
    __tablename__ = "plugin_configs"

    plugin_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="0.0.0")
    author: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    plugin_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="library"
    )
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class PluginStoreSource(Base):
    __tablename__ = "plugin_store_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
