"""Blended ROM rating.

`roms.rating` is NOT a user-facing score - it is the ScreenScraper note divided
by 20, i.e. a 0-1 fraction, which renders as a nonsense "0.8" star. The score to
show is this blend of every source the ROM actually carries, on the same 0-5
scale as the library's `aggregate_rating()`.

Lives in utils so both the endpoints and the dashboard handler can reach it
without a handler having to import from endpoints.
"""

from __future__ import annotations


def normalize_star_5(value) -> float | None:
    """Coerce any rating onto the 0-5 star scale `library_games.rating` holds.

    The column is a 0-5 star, but more than one writer reaches it and they do
    not all speak that scale: the metadata-search apply hands RAWG back on a
    0-10 scale (rawg*2), a scrape can carry an IGDB 0-100 total, an admin can
    paste a Metacritic 0-10. A value already in 0-5 passes through; a 0-10 one
    is halved; a 0-100 one is divided by 20. This is the magnitude rule
    `aggregate_rating` uses for an unknown source, so the stored star and the
    blended one agree. Clamped to 0-5; None - and anything unparseable or not
    positive - stays None.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    if v > 10:
        v = v / 20.0
    elif v > 5:
        v = v / 2.0
    return round(min(5.0, v), 1)


def rom_rating_agg(
    ss_score: float | None,
    igdb_rating: float | None,
    lb_rating: float | None,
    plugin_ratings: dict | None,
) -> float | None:
    """Average the ROM's rating sources onto 0-5 (SS /20, IGDB /100, LaunchBox
    /10, plugin ratings /10). None when the ROM carries no rating at all."""
    vals: list[float] = []
    if ss_score is not None:
        vals.append(ss_score / 4)
    if igdb_rating is not None:
        vals.append(igdb_rating / 20)
    if lb_rating is not None:
        vals.append(lb_rating / 2)
    for entry in (plugin_ratings or {}).values():
        try:
            vals.append(float(entry.get("rating")) / 2)
        except (TypeError, ValueError, AttributeError):
            continue
    if not vals:
        return None
    return round(min(5.0, max(0.0, sum(vals) / len(vals))), 1)


def rom_rating_agg_of(rom) -> float | None:
    """`rom_rating_agg` for a Rom ORM row."""
    return rom_rating_agg(
        rom.ss_score, rom.igdb_rating, rom.lb_rating, rom.plugin_ratings
    )
