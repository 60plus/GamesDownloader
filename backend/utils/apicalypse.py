"""Search terms bound for IGDB's Apicalypse query language.

Apicalypse ends a statement with `;` and delimits a string with `"`, so a term
carrying either escapes the field it was meant to fill. Terms reach us from the
`q` query parameter and from stored game titles, neither of which we control.

One implementation on purpose: this used to exist as four separate copies, two
of them written out by hand at the call site, which is how three call sites
ended up sending the term through with no cleaning at all.
"""
from __future__ import annotations

_MAX_TERM = 128


def sanitize_search(term: str | None) -> str:
    """A term safe to place inside `search "..."`.

    Drops the quote and semicolon that would break out of the string, flattens
    newlines that would split the query into further statements, and caps the
    length so an over-long term cannot push the rest of the query out.
    """
    cleaned = (term or "").replace('"', "").replace("'", "").replace(";", "")
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    return cleaned.strip()[:_MAX_TERM]
