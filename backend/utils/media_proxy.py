"""Serve scraper thumbnails without handing their credentialed URLs to a browser.

ScreenScraper builds every media URL with the server's account password in the
query string (ssid/sspassword/devid/devpassword). Those URLs are shown in <img>
tags all over the metadata editor and the game-request dialog; rendering them
directly would put the server's scraper password in every user's browser
history, DevTools, and any intermediary proxy - the same credential-leak class
the stored-cover fix (download_request_cover) already closed, but on the live
search/browse paths it did not cover.

Instead the server wraps such a URL into an opaque, Fernet-encrypted token and
hands out ``/api/media/proxy/<token>``. The token is unforgeable (encrypted with
the app secret, so a client can never mint one for an arbitrary URL) and reveals
nothing about the URL it stands for. The proxy route decrypts it, fetches the
bytes through the SSRF-guarded downloader, and streams them back - the password
never leaves the server.

A URL that carries no secret (public IGDB / RAWG / LaunchBox / SteamGridDB
thumbnails) is returned unchanged: there is nothing to hide and no reason to pay
for a proxy hop.

The predicate is shared with the persist path (recently_added._is_leaky_url) so
"what we refuse to store" and "what we refuse to show" can never drift apart.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROXY_PREFIX = "/api/media/proxy/"

# A namespace stamped inside the encrypted plaintext. The proxy token shares the
# app's Fernet with encrypted AppConfig secrets; requiring this tag means the
# open proxy will only ever act on a string WE wrapped as a media URL, never on
# some other ciphertext that merely happens to decrypt to an http(s) string.
_NS = "gdmp1|"


def is_leaky_url(url: str | None) -> bool:
    """True when the URL carries a scraper credential in its query string."""
    if not url or not isinstance(url, str):
        return False
    try:
        from handler.notifications.recently_added import _is_leaky_url
        return _is_leaky_url(url)
    except Exception:
        low = url.lower()
        return any(k in low for k in ("sspassword=", "devpassword=", "password=", "passwd=", "pwd="))


def proxy_url(url: str | None) -> str | None:
    """A client-safe URL for a media asset.

    Credentialed scraper URLs become ``/api/media/proxy/<token>``; everything
    else (local paths, public CDN thumbnails, None) is returned unchanged.
    """
    if not url or not isinstance(url, str) or not is_leaky_url(url):
        return url
    try:
        from handler.config.config_handler import _encrypt
        return PROXY_PREFIX + _encrypt(_NS + url)
    except Exception:
        # If we cannot encrypt it we must not leak it: drop the cover instead.
        logger.warning("media proxy: could not wrap a credentialed URL - dropping it")
        return None


def proxy_media_list(items: list, key: str = "url") -> list:
    """Rewrite ``item[key]`` through proxy_url for every dict in the list."""
    if not items:
        return items
    for it in items:
        if isinstance(it, dict) and it.get(key):
            it[key] = proxy_url(it[key])
    return items


def resolve_proxy_url(url: str | None) -> str | None:
    """Turn a ``/api/media/proxy/<token>`` URL back into the real scraper URL for
    a server-side download (the pick-back path, where a client hands the picked
    cover back to be stored). Non-proxy URLs pass through unchanged; a malformed
    or forged token yields None so the caller fetches nothing.
    """
    if not url or not isinstance(url, str):
        return url
    i = url.find(PROXY_PREFIX)
    if i < 0:
        return url
    token = url[i + len(PROXY_PREFIX):].split("?", 1)[0].split("#", 1)[0].strip("/")
    if not token:
        return None
    try:
        from handler.config.config_handler import _decrypt
        plain = _decrypt(token)
    except Exception:
        logger.warning("media proxy: undecodable token on a fetch")
        return None
    if not plain.startswith(_NS):
        # Decrypted to something that was not stamped as a media URL (e.g. an
        # unrelated config ciphertext) - refuse rather than fetch it.
        logger.warning("media proxy: token without the media namespace - refusing")
        return None
    return plain[len(_NS):]
