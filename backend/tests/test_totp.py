"""Unit tests for TOTP / recovery-code helpers (handler.auth.totp)."""
from __future__ import annotations

import pyotp

from handler.auth.totp import (
    consume_recovery_code,
    generate_recovery_codes,
    generate_secret,
    hash_recovery_codes,
    verify_code,
)

_BASE32 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


def test_generate_secret_is_base32_length_32():
    secret = generate_secret()
    assert len(secret) == 32
    assert set(secret) <= _BASE32


def test_verify_code_accepts_current_totp():
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_code(secret, code) is True


def test_verify_code_rejects_wrong_code():
    secret = generate_secret()
    real = pyotp.TOTP(secret).now()
    wrong = "000000" if real != "000000" else "111111"
    assert verify_code(secret, wrong) is False


def test_verify_code_rejects_malformed():
    secret = generate_secret()
    assert verify_code(secret, "12345") is False    # too short
    assert verify_code(secret, "abcdef") is False    # not digits
    assert verify_code(secret, "") is False
    assert verify_code("", "123456") is False


def test_recovery_codes_format_and_count():
    codes = generate_recovery_codes(5)
    assert len(codes) == 5
    for c in codes:
        a, b = c.split("-")
        assert len(a) == 5 and len(b) == 5


def test_consume_recovery_code_is_one_shot():
    codes = generate_recovery_codes(3)
    hashes = hash_recovery_codes(codes)
    ok, remaining = consume_recovery_code(hashes, codes[0])
    assert ok is True
    assert len(remaining) == 2
    # Spending the same code again fails and does not shrink the list further.
    ok2, remaining2 = consume_recovery_code(remaining, codes[0])
    assert ok2 is False
    assert len(remaining2) == 2


def test_consume_recovery_code_accepts_dashless_lowercase_input():
    codes = generate_recovery_codes(1)
    hashes = hash_recovery_codes(codes)
    dashless = codes[0].replace("-", "").lower()
    ok, _ = consume_recovery_code(hashes, dashless)
    assert ok is True
