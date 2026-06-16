"""Unit tests for bcrypt password hashing (handler.auth.passwords)."""
from __future__ import annotations

from handler.auth.passwords import hash_password, verify_password


def test_hash_is_not_plaintext():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert h.startswith("$2")  # bcrypt hash prefix


def test_verify_accepts_correct_password():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("hunter3", h) is False


def test_same_password_hashes_differently():
    # Random per-hash salt: two hashes of the same password differ, both verify.
    a = hash_password("same")
    b = hash_password("same")
    assert a != b
    assert verify_password("same", a)
    assert verify_password("same", b)
