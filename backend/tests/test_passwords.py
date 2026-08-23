"""Unit tests for password hashing and the strength rule (handler.auth.passwords)."""
from __future__ import annotations

import pytest

from handler.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    ensure_password_ok,
    hash_password,
    password_problem,
    verify_password,
)


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


# ── Strength rule ────────────────────────────────────────────────────────────
# The rule used to be written out in six places that did not agree: the reset
# link and the first-run wizard wanted a letter and a digit, while registration,
# the profile page and both admin routes asked only for length. Nothing in the
# suite touched any of them, so the disagreement went unnoticed for as long as
# it existed. These pin the single rule down.

def test_rejects_shorter_than_minimum():
    assert password_problem("abcdef1") is not None
    assert str(MIN_PASSWORD_LENGTH) in password_problem("abcdef1")


def test_rejects_the_four_characters_the_reset_form_used_to_allow():
    # ResetPassword.vue accepted 4 while the server demanded 8 plus a letter
    # plus a digit, so the reader was told "too short" only after a round trip,
    # in English, whatever their language.
    assert password_problem("abc1") is not None


def test_rejects_letters_only():
    assert password_problem("abcdefgh") is not None


def test_rejects_digits_only():
    assert password_problem("12345678") is not None


def test_accepts_minimum_length_with_a_letter_and_a_digit():
    assert password_problem("abcdefg1") is None


def test_ensure_raises_a_400_whose_detail_is_a_sentence():
    # Deliberately not a Pydantic constraint: a schema rejection is a 422 whose
    # detail is a LIST of validation objects, and every caller in the frontend
    # renders detail straight into the error line.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        ensure_password_ok("short")
    assert caught.value.status_code == 400
    assert isinstance(caught.value.detail, str)


def test_ensure_passes_a_good_password_silently():
    assert ensure_password_ok("abcdefg1") is None
