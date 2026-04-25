"""User model with role-based access."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Role(str, enum.Enum):
    ADMIN    = "admin"
    UPLOADER = "uploader"
    EDITOR   = "editor"
    USER     = "user"


class User(Base):
    __tablename__ = "users"

    username:        Mapped[str]            = mapped_column(String(64),  unique=True, index=True)
    email:           Mapped[str | None]     = mapped_column(String(255), unique=True, nullable=True)
    hashed_password: Mapped[str]            = mapped_column(String(255))
    role:            Mapped[Role]           = mapped_column(default=Role.USER)
    enabled:         Mapped[bool]           = mapped_column(default=True)
    avatar_path:     Mapped[str | None]     = mapped_column(String(512), nullable=True)

    # Optional JSON overrides - absent key = role default applies.
    # Supported keys:
    #   access_gamesdownloader: bool
    #   access_emulation: bool
    #   edit_metadata: bool
    #   upload: bool
    permissions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Per-user UI appearance preferences (theme, skin, card effects, etc.)
    preferences: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
