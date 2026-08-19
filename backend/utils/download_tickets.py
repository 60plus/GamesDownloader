"""Short-lived signed links for downloading a ROM file.

A download is started by navigating the browser to a URL - that is what makes
the file land in the download folder rather than in a tab, and what lets a
multi-gigabyte image stream to disk instead of into a JavaScript buffer. But a
navigation carries no Authorization header, which is the only thing
AuthMiddleware reads, so the authenticated route answers it with 401. Nobody
could download a ROM from the interface at all.

Savestate thumbnails solved the same problem with a signature over the server
secret, and this follows that shape - with two differences, because a ROM is not
a thumbnail:

  * the ticket expires. A thumbnail URL may be shared forever by design; a link
    to somebody's whole game library should stop working shortly after it was
    handed out.
  * the ticket names the user it was issued to, so it cannot be passed to
    somebody the library would not have served.

The ticket is minted by an authenticated request, which is where access is
decided; this module only decides whether a ticket presented later is genuine
and still valid.
"""

from __future__ import annotations

import hmac
import time
from hashlib import sha256

from config import AUTH_SECRET_KEY

# Long enough to survive a slow page and a click, short enough that a link
# pasted into a chat has stopped working by the time anyone reads it.
TICKET_TTL_S = 300

_SIG_LEN = 32


def _sign(rom_id: int, user_id: int, expires_at: int, kind: str) -> str:
    return hmac.new(
        AUTH_SECRET_KEY.encode(),
        f"dl:{rom_id}:{user_id}:{expires_at}:{kind}".encode(),
        sha256,
    ).hexdigest()[:_SIG_LEN]


def issue(rom_id: int, user_id: int, ttl_s: int = TICKET_TTL_S, kind: str = "one") -> tuple[int, str]:
    """A (expires_at, signature) pair for one ROM and one user.

    *kind* separates a single file from the whole set of disks a title was
    split across, so a ticket for one cannot be presented for the other.
    """
    expires_at = int(time.time()) + ttl_s
    return expires_at, _sign(rom_id, user_id, expires_at, kind)


def valid(rom_id: int, user_id: int, expires_at: int, sig: str, kind: str = "one") -> bool:
    """True when the ticket is genuine, for this ROM and user, and not expired.

    Expiry is checked first and separately from the signature: a stale ticket is
    refused even if it was perfectly signed, which is the entire point of
    putting a deadline in it.
    """
    if expires_at < int(time.time()):
        return False
    return hmac.compare_digest(_sign(rom_id, user_id, expires_at, kind), sig or "")
