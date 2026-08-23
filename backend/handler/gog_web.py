"""GOG's wire format: the headers we send, and the shapes it sends back.

Eleven copies of the two header dictionaries were spread over six files, seven
of them written out again inside a function body, and the URL helper existed
twice and was imported across modules by its underscore name from whichever
file happened to hold it. They are collected here exactly as they were - the
bytes that go over the wire are unchanged, and the headers that genuinely
differ (the browser identity used for fetching images, the plainer ones used
for Wikipedia and for the media proxy) stay where they are, because they are
not these.
"""

from __future__ import annotations

# The short identity, used for GOG's JSON endpoints.
GOG_JSON_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 GOGGalaxy/2.0",
    "Accept": "application/json",
}

# The fuller one, used where GOG is asked to behave like the desktop client:
# signing in, and scraping a product page.
GOG_GALAXY_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def gog_image_url(url: str) -> str:
    """Make a GOG image address absolute.

    GOG hands back three shapes: a full address, one that starts at the root
    of the image host, and a protocol-relative one that would resolve against
    whatever page it came from.
    """
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://images.gog.com" + url
    return url
