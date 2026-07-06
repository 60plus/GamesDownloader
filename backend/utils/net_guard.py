"""SSRF guard for server-side URL fetching.

Validates that a URL's host does not resolve to an internal/dangerous address
before the server fetches it, so an attacker cannot make the server reach
internal services (cloud metadata at 169.254.169.254, localhost admin ports,
LAN devices) through a user-supplied URL.

Policy:
  - loopback / link-local (incl. cloud metadata) / reserved / unspecified /
    multicast are ALWAYS rejected.
  - RFC-1918 private LAN is rejected too, UNLESS allow_private_lan=True - used
    by the URL-upload endpoint, where a self-hoster may legitimately pull a file
    from a NAS on their own LAN.

Note: this resolves the host and checks the result; it does not pin the IP, so a
determined DNS-rebinding attacker could still slip through (matches the existing
store-icon-proxy rigor). The endpoints using it are privileged (uploader/admin).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL host resolves to a disallowed address."""


def _check_ip(ip_str: str, allow_private_lan: bool) -> None:
    addr = ipaddress.ip_address(ip_str)
    if (
        addr.is_loopback or addr.is_link_local or addr.is_reserved
        or addr.is_unspecified or addr.is_multicast
    ):
        raise UnsafeURLError(f"URL resolves to a blocked address ({ip_str})")
    if addr.is_private and not allow_private_lan:
        raise UnsafeURLError(f"URL resolves to a private address ({ip_str})")


def assert_fetch_allowed(url: str, *, allow_private_lan: bool = False) -> None:
    """Raise UnsafeURLError if *url* is not safe for the server to fetch."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http(s) URLs may be fetched")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Cannot resolve host: {host}") from exc
    for _family, _type, _proto, _canon, sockaddr in infos:
        _check_ip(sockaddr[0], allow_private_lan)


def make_request_guard(allow_private_lan: bool = False):
    """Return an httpx 'request' event hook that re-validates every hop
    (including redirects) with assert_fetch_allowed, closing redirect-based
    SSRF bypasses on clients that follow redirects."""
    async def _guard(request) -> None:  # httpx.Request
        assert_fetch_allowed(str(request.url), allow_private_lan=allow_private_lan)
    return _guard
