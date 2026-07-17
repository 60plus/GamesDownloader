"""Blended ROM rating.

`roms.rating` is NOT a user-facing score - it is the ScreenScraper note divided
by 20, i.e. a 0-1 fraction, which renders as a nonsense "0.8" star. The score to
show is this blend of every source the ROM actually carries, on the same 0-5
scale as the library's `aggregate_rating()`.

Lives in utils so both the endpoints and the dashboard handler can reach it
without a handler having to import from endpoints.
"""

from __future__ import annotations


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
