"""TOTP (RFC 6238) helpers for two-factor authentication.

Why a dedicated helper module:
- pyotp imports lazily so the rest of the app keeps working if the dependency
  is somehow unavailable on a partial install.
- Recovery codes are stored as bcrypt hashes (same scheme as passwords) so a
  database leak does not give an attacker working backup keys.
- A separate "pending enrollment" buffer in Redis holds the candidate secret
  until the user proves they configured the authenticator correctly. We never
  persist a TOTP secret to the users table without that proof.
"""

from __future__ import annotations

import logging
import secrets
from typing import Iterable

logger = logging.getLogger(__name__)

# Provisioning issuer name shown inside Google Authenticator / Authy / 1Password
ISSUER = "GamesDownloader"

# Length of recovery codes once formatted with the dash separator (10 chars + dash)
_RECOVERY_GROUPS = 2  # "ABCDE-FGHIJ"
_RECOVERY_GROUP_SIZE = 5
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # I/O/0/1 dropped to avoid confusion


# ── Secret + provisioning URI ─────────────────────────────────────────────────

def generate_secret() -> str:
    """Return a freshly generated base32 secret (160 bits)."""
    import pyotp
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, username: str) -> str:
    """Build the otpauth:// URI an authenticator app can scan as a QR code."""
    import pyotp
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=ISSUER)


def render_qr_svg(data: str) -> str:
    """Render `data` as a self-contained SVG QR code for inline embedding.

    Returns an SVG string ready to be inlined into a data URL or rendered as
    `v-html`. We avoid Pillow / PNG so the response stays text-only and the
    image survives any future strict CSP that bans data:image/png.
    """
    try:
        import qrcode
        import qrcode.image.svg
        factory = qrcode.image.svg.SvgImage
        img = qrcode.make(data, image_factory=factory, box_size=8, border=2)
        from io import BytesIO
        buf = BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception as exc:
        logger.warning("QR rendering failed: %s", exc)
        return ""


def verify_code(secret: str, code: str, *, window: int = 1) -> bool:
    """Return True when `code` is a valid TOTP for `secret`.

    `window=1` accepts the previous and next 30s step to absorb clock drift,
    matching the recommendation in RFC 6238 section 5.2.
    """
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) not in (6, 8):
        return False
    try:
        import pyotp
        return pyotp.totp.TOTP(secret).verify(code, valid_window=window)
    except Exception:
        return False


# ── Recovery codes ────────────────────────────────────────────────────────────

def generate_recovery_codes(n: int = 10) -> list[str]:
    """Generate `n` human-friendly one-time recovery codes."""
    out: list[str] = []
    for _ in range(n):
        groups = []
        for _g in range(_RECOVERY_GROUPS):
            groups.append("".join(secrets.choice(_RECOVERY_ALPHABET)
                                  for _c in range(_RECOVERY_GROUP_SIZE)))
        out.append("-".join(groups))
    return out


def hash_recovery_codes(codes: Iterable[str]) -> list[str]:
    """Return bcrypt hashes for storage. Plaintext codes are shown to the user
    once and never persisted."""
    from handler.auth.passwords import hash_password
    return [hash_password(_normalise(c)) for c in codes]


def consume_recovery_code(stored_hashes: list[str] | None, code: str) -> tuple[bool, list[str]]:
    """Try to spend a recovery code. Returns (matched, remaining_hashes).

    The matched hash is removed from the returned list; callers must persist
    that list back to the database to make codes one-shot.
    """
    if not stored_hashes:
        return False, list(stored_hashes or [])
    from handler.auth.passwords import verify_password
    target = _normalise(code)
    remaining: list[str] = []
    consumed = False
    for h in stored_hashes:
        if (not consumed) and verify_password(target, h):
            consumed = True
            continue
        remaining.append(h)
    return consumed, remaining


def _normalise(code: str) -> str:
    """Strip spaces, dashes, and uppercase so users do not have to type the
    code with the exact same dash placement they were shown."""
    return "".join(code.split()).replace("-", "").upper()


# ── Pending-enrollment Redis storage ─────────────────────────────────────────

_PENDING_PREFIX = "auth:totp_pending:"
_PENDING_TTL = 600  # 10 minutes for the user to scan + verify


async def stash_pending_secret(user_id: int, secret: str) -> None:
    try:
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        await r.set(f"{_PENDING_PREFIX}{user_id}", secret, ex=_PENDING_TTL)
    except Exception:
        logger.warning("Could not stash pending TOTP secret (Redis unavailable)")


async def pop_pending_secret(user_id: int) -> str | None:
    try:
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        key = f"{_PENDING_PREFIX}{user_id}"
        val = await r.get(key)
        if val is None:
            return None
        await r.delete(key)
        # Redis client is configured with decode_responses=True, so this is already str
        return val if isinstance(val, str) else val.decode("utf-8")
    except Exception:
        return None
