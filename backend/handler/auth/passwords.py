"""Password hashing utilities using bcrypt directly, and the one strength rule."""

from __future__ import annotations

import bcrypt

MIN_PASSWORD_LENGTH = 8


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def password_problem(plain: str) -> str | None:
    """What is wrong with this password, or None when nothing is.

    The rule used to be stated in six places and they did not agree: the reset
    link and the first-run wizard demanded a letter and a digit, while the
    registration that created the account, the profile page and both admin
    routes asked only for length. Resetting a password was therefore harder
    than choosing one in the first place. This is now the only statement of it.
    """
    if len(plain) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
    if not any(c.isalpha() for c in plain):
        return "Password must contain at least one letter"
    if not any(c.isdigit() for c in plain):
        return "Password must contain at least one digit"
    return None


def ensure_password_ok(plain: str) -> None:
    """Reject a weak password the way every other handler rejects bad input.

    Deliberately a 400 with a plain string rather than a Pydantic constraint:
    a schema rejection is a 422 whose `detail` is a LIST of validation objects,
    and every caller in the frontend renders `detail` straight into the error
    line. One shape in, one shape out.
    """
    from fastapi import HTTPException

    problem = password_problem(plain)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
