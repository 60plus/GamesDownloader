"""Unit tests for JWT creation/validation (handler.auth.tokens).

Guards the python-jose -> PyJWT migration: tokens must round-trip, carry the
right claims, and decode_token must return None (not raise) for expired,
tampered, or malformed tokens.
"""
from __future__ import annotations

from datetime import timedelta

import jwt

from config import AUTH_ALGORITHM
from handler.auth.scopes import Scope
from handler.auth.tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_access_token_roundtrip_carries_claims():
    token = create_access_token("alice", scopes=[Scope.LIBRARY_READ, Scope.LIBRARY_DOWNLOAD])
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "alice"
    assert payload["type"] == "access"
    assert set(payload["scopes"]) == {"library.read", "library.download"}
    assert len(payload["jti"]) == 32  # secrets.token_hex(16) -> 32 hex chars


def test_refresh_token_has_refresh_type():
    payload = decode_token(create_refresh_token("bob"))
    assert payload is not None
    assert payload["type"] == "refresh"
    assert payload["sub"] == "bob"


def test_access_token_without_scopes_defaults_empty():
    payload = decode_token(create_access_token("carol"))
    assert payload is not None
    assert payload["scopes"] == []


def test_expired_token_returns_none():
    expired = create_access_token("dave", expires_delta=timedelta(seconds=-10))
    assert decode_token(expired) is None


def test_garbage_token_returns_none():
    assert decode_token("not.a.jwt") is None
    assert decode_token("") is None


def test_token_signed_with_other_key_returns_none():
    forged = jwt.encode(
        {"sub": "mallory", "type": "access"},
        "a-completely-different-secret-key-0123456789",
        algorithm=AUTH_ALGORITHM,
    )
    assert decode_token(forged) is None


def test_jti_is_unique_per_token():
    t1 = decode_token(create_access_token("alice"))
    t2 = decode_token(create_access_token("alice"))
    assert t1["jti"] != t2["jti"]
