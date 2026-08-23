"""Text helpers for values that arrive from outside and land in a column."""

from __future__ import annotations

_ELLIPSIS = "…"
# How far back from the cut a space may sit and still be worth breaking on.
# Beyond this the string is effectively unbroken (a URL, a CJK sentence) and a
# word break would throw away a useful chunk of it.
_WORD_BREAK_WINDOW = 40


def clamp_text(value, limit: int | None):
    """Return *value* trimmed to fit a column of *limit* characters.

    Metadata providers do not promise a length. GOG's `lead`, IGDB's `summary`
    and a Wikipedia opening paragraph are all offered as the game's tagline and
    any of them can run past five hundred characters, while the column holding
    it is a VARCHAR(512). MySQL answers an oversized value with error 1406 and
    rejects the entire statement - so one long tagline once discarded the
    cover, the artwork, the genres, the ratings and the screenshots that
    travelled in the same UPDATE.

    Trimming loses the tail of a tagline. Not trimming loses everything.
    """
    if not limit or not isinstance(value, str) or len(value) <= limit:
        return value
    cut = value[: limit - 1]
    space = cut.rfind(" ")
    # `space > 0` matters: rfind returns -1 when there is no space at all, and
    # on a narrow column (limit at or under the window) -1 would satisfy the
    # distance test below and then cut[:-1] would quietly drop a character that
    # did fit. A space at position 0 is no use either.
    if space > 0 and space >= limit - 1 - _WORD_BREAK_WINDOW:
        cut = cut[:space]
    return cut.rstrip() + _ELLIPSIS
