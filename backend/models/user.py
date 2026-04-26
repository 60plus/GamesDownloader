"""User model with role-based access."""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import JSON, Boolean, String
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

    # ── Two-factor authentication (TOTP - RFC 6238) ──────────────────────────
    # totp_secret holds the base32-encoded shared secret only when 2FA is
    # actively enabled. During enrollment the secret is staged in Redis
    # (auth:totp_pending:<user_id>) and only persisted here once the user
    # proves possession of the authenticator by submitting a valid 6-digit
    # code. Disabling 2FA wipes the column.
    totp_secret:          Mapped[str | None]       = mapped_column(String(64),  nullable=True)
    totp_enabled:         Mapped[bool]             = mapped_column(Boolean,     default=False)
    # Recovery codes are stored as bcrypt hashes, never plaintext. List is
    # consumed: each code can be used exactly once, after which it is removed.
    totp_recovery_codes:  Mapped[list[str] | None] = mapped_column(JSON,        nullable=True)
