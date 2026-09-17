"""What a ROM scrape fetches for a platform, read from its Scrape Preset.

The Additional media ticks on Settings > ROMs were saved and never read. Every
scrape fetched screenshots, background, wheel, support, bezel, Steam Grid, video
and picto whatever was ticked, and never a manual, maps, a box texture, a title
screen or a marquee, which had nowhere to be kept (1.0.34 audit).

Each tick now lets its media in, and the default is small, as in RomM: the
cover, which is the preset's own field and always fetched, and gameplay
screenshots. Everything else is asked for (the owner's decision, 2026-09-17).
The ticks with nowhere to go are off the screen until ROMs get folders of their
own; wheel, Steam Grid and picto, fetched until now with no tick at all, got one.
"""

from __future__ import annotations

#: Stamped on every preset saved from here on. A preset without it was saved
#: while the ticks did nothing, which `wanted_media` has to know.
PRESET_VERSION = 2

#: Ticked for a platform nobody has chosen for.
DEFAULT_MEDIA: tuple[str, ...] = ("ss",)

#: Both fill the one background slot. Either ticked means a background is wanted.
BACKGROUND_TYPES: tuple[str, ...] = ("fanart", "background")

# Names an older screen saved. ScreenScraper calls them something else, so a
# cover or a tick carrying one of these never matched anything.
_RENAMED = {"ss-titre": "sstitle", "marquee": "screenmarquee"}

# A tick, and the ScreenScraper types it lets into its slot. The wheel keeps the
# whole family it was picked from before, marquee included, so a game whose only
# logo is a marquee still gets one.
_LETS_IN: dict[str, tuple[str, ...]] = {
    "support-2D":       ("support-2D",),
    "support-texture":  ("support-texture",),
    "bezel-16-9":       ("bezel-16-9",),
    "bezel-4-3":        ("bezel-4-3",),
    "video":            ("video",),
    "video-normalized": ("video-normalized",),
    "steamgrid":        ("steamgrid",),
    "pictoliste":       ("pictoliste", "pictocouleur", "pictomonochrome"),
    "wheel":            ("wheel-hd", "wheel", "wheel-carbon", "wheel-steel",
                         "screenmarquee", "screenmarqueesmall"),
}

#: Every tick the settings screen offers, and the scrape obeys.
TICKS: tuple[str, ...] = ("ss", *BACKGROUND_TYPES, *_LETS_IN)


def _renamed(name: str) -> str:
    return _RENAMED.get(name, name)


def cover_type(preset: dict | None) -> str:
    """The cover this platform asked for, under ScreenScraper's name for it."""
    return _renamed((preset or {}).get("cover_type") or "box-2D")


def wanted_media(preset: dict | None) -> frozenset[str]:
    """The ticks this platform's scrape obeys.

    A preset saved before the ticks did anything is not a choice about
    downloads: the screen started every platform with none ticked, and saving a
    cover type saved that empty list with it. Such a list takes the default. One
    somebody filled in is kept, since that is what they asked for.
    """
    preset = preset or {}
    extras = preset.get("extras")
    if not isinstance(extras, list):
        return frozenset(DEFAULT_MEDIA)
    if not extras and (preset.get("version") or 1) < PRESET_VERSION:
        return frozenset(DEFAULT_MEDIA)
    return frozenset(_renamed(e) for e in extras if isinstance(e, str))


def lets_in(wanted: frozenset[str], ss_type: str) -> bool:
    """Whether a ScreenScraper media of *ss_type* may fill its slot."""
    return any(ss_type in _LETS_IN.get(tick, ()) for tick in wanted)


def as_shown(preset: dict | None, *, region: str = "wor") -> dict:
    """A preset as the screens read it: what the scrape will actually do.

    The platform page saves every preset back when one cover type changes, so
    handing back an old stored empty list would turn "nobody chose" into
    "nothing at all" for every platform at once.
    """
    preset = preset or {}
    return {
        "cover_type": cover_type(preset),
        "region": preset.get("region") or region,
        "extras": sorted(wanted_media(preset)),
    }


def as_saved(preset: dict) -> dict:
    """A preset as it is written: real names, and marked as a real choice."""
    return {
        "cover_type": cover_type(preset),
        "region": preset.get("region") or "wor",
        "extras": sorted({_renamed(e) for e in preset.get("extras") or [] if isinstance(e, str)}),
        "version": PRESET_VERSION,
    }
