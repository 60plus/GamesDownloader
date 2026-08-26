"""Reading what a No-Intro style filename says about a ROM.

These lived inside the remote-source browser, which is the only place that ever
called them, and so the local library never got the benefit: a ROM the scraper
did not recognise ended up with no region at all, even when the region was
written in its filename all along.

They are here so both callers can reach them without the scanner having to
import the source browser, which pulls in most of the download machinery.
"""

from __future__ import annotations

import re

# Region tags parsed from a No-Intro filename, kept out of the displayed title.
REGION_TAGS = {
    "usa": "USA", "us": "USA", "u": "USA",
    "europe": "Europe", "eu": "Europe", "e": "Europe",
    "japan": "Japan", "jp": "Japan", "jpn": "Japan", "j": "Japan",
    "world": "World", "w": "World",
    "korea": "Korea", "china": "China", "brazil": "Brazil",
    "australia": "Australia", "spain": "Spain", "france": "France",
    "germany": "Germany", "italy": "Italy",
}

PAREN_TAG = re.compile(r"\s*\(([^()]*)\)")


def region_from_name(filename: str) -> str | None:
    """Best-effort region parsed from a No-Intro filename's parenthesised tags."""
    for tag in PAREN_TAG.findall(filename or ""):
        for part in re.split(r"[,/]", tag):
            key = part.strip().lower()
            if key in REGION_TAGS:
                return REGION_TAGS[key]
    return None


def is_region_part(part: str) -> bool:
    """Whether one comma-separated part of a tag is nothing but region names."""
    bits = [b.strip().lower() for b in part.split("/") if b.strip()]
    return bool(bits) and all(b in REGION_TAGS for b in bits)


def strip_region_from_title(title: str) -> str:
    """Drop region tags from a display title, keep the name and everything else.

    Only the region parts of a tag go, not the whole parenthesis: an arcade set
    is described as "DoDonPachi II - Bee Storm (World, ver. 102)", where the
    region belongs in its own column but the version is the only thing telling
    that row apart from its siblings. Dropping the lot collapsed a dozen sets
    into a dozen identical rows.
    """
    def _keep(m: re.Match) -> str:
        rest = [p.strip() for p in m.group(1).split(",")
                if p.strip() and not is_region_part(p)]
        return f" ({', '.join(rest)})" if rest else ""
    cleaned = PAREN_TAG.sub(_keep, title or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip() or (title or "")
