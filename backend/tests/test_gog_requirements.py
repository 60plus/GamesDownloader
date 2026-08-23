"""The GOG expand that takes the whole payload down with it.

`system_requirements` used to be a valid expand on the v1 product API. GOG went
from ignoring an unknown expand to rejecting the entire request with a 400, and
that request is where the description, the screenshots and the videos come
from - so asking for the one field it will not give costs the three it would.

The GOG scraper was fixed when that happened. The library scraper was not, and
had been receiving nothing at all ever since, quietly, because the failure is
caught and the log line sits at a level nobody runs at. This is the guard that
keeps either of them from asking again.

Requirements themselves are not in v1 any more in any form. GOG v2 carries them
under _embedded.supportedOperatingSystems[].systemRequirements, which nothing
reads; what a game displays today was written by RAWG or Steam through the
metadata editor.
"""
from __future__ import annotations


def test_neither_scraper_asks_gog_for_system_requirements():
    from handler.gog import gog_scrape_handler
    from handler.library import library_scrape_handler

    for modul in (gog_scrape_handler, library_scrape_handler):
        assert "system_requirements" not in modul._GOG_V1, (
            f"{modul.__name__} asks for an expand that makes GOG refuse the call")


def test_the_v1_expand_still_asks_for_what_it_needs():
    """Dropping the bad field must not have taken a good one with it."""
    from handler.gog import gog_scrape_handler
    from handler.library import library_scrape_handler

    for modul, wanted in (
        (gog_scrape_handler, ("description", "screenshots", "videos", "downloads")),
        (library_scrape_handler, ("description", "screenshots", "videos")),
    ):
        for field in wanted:
            assert field in modul._GOG_V1, f"{modul.__name__} stopped asking for {field}"
