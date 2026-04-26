"""Pydantic schemas for user endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from models.user import Role


class UserCreate(BaseModel):
    username:    str       = Field(..., min_length=3, max_length=64)
    password:    str       = Field(..., min_length=8)
    email:       str       = Field(..., min_length=3, max_length=255)
    role:        Role      = Role.USER
    invite_code: str | None = None   # required when registration_mode = "invite_only"


class UserUpdate(BaseModel):
    email: str | None = None
    role: Role | None = None
    enabled: bool | None = None
    permissions: dict[str, Any] | None = None


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None
    role: Role
    enabled: bool
    avatar_path: str | None
    permissions: dict[str, Any] | None
    preferences: dict[str, Any] | None
    created_at: datetime
    totp_enabled: bool = False

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Response shape for /auth/login.

    When the user has TOTP enabled, the server does NOT issue access / refresh
    tokens immediately. Instead it returns a short-lived `challenge_token` and
    expects the client to call /auth/login-totp with that token plus a valid
    6-digit code (or a recovery code) to complete the login.
    """
    requires_totp:    bool = False
    challenge_token:  str | None = None
    access_token:     str | None = None
    refresh_token:    str | None = None
    token_type:       str = "bearer"


class LoginTotpRequest(BaseModel):
    challenge_token: str
    code:            str   # 6-digit TOTP or formatted recovery code (XXXXX-XXXXX)


class Enable2FAStartResponse(BaseModel):
    secret:            str   # base32 manual entry key (hidden behind QR)
    provisioning_uri:  str   # otpauth:// URI for QR rendering
    qr_svg:            str   # self-contained SVG of the URI for inline embedding


class Enable2FAVerifyRequest(BaseModel):
    code: str


class Enable2FAVerifyResponse(BaseModel):
    enabled:          bool
    recovery_codes:   list[str]   # plaintext, shown once


class Disable2FARequest(BaseModel):
    password: str
    code:     str   # current TOTP or recovery code, to prove possession


class TotpStatusResponse(BaseModel):
    enabled:                bool
    recovery_codes_left:    int


class TokenPayload(BaseModel):
    sub: str
    scopes: list[str] = []
