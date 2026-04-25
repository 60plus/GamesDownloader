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

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    scopes: list[str] = []
