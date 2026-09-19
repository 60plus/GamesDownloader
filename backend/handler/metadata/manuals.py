"""A game's manual: which of ScreenScraper's copies to take, and taking it.

ScreenScraper usually holds several manuals for one game - Japanese, American,
European, a French and a German one - all PDFs. Measured on the owner's library
it had one for 45 of 54 games, 147 files in all, typically three megabytes and
none over fifteen.

Which one is the owner's choice: the ROM's own region first, so the manual
matches the text on the screen; then Europe, America and the world release;
then any other language; Japan last, since for most people it cannot be read.
A Japanese manual is still taken when it is the only one - it is the game's.
"""
from __future__ import annotations

import logging
from pathlib import Path

from utils.http import fetch_media_bytes

logger = logging.getLogger(__name__)

# How a ROM's region, as the library spells it, reads in ScreenScraper's codes.
# Spain is `sp` there, not `es` - measured, ten Spanish manuals on one shelf.
_REGION_CODES: dict[str, tuple[str, ...]] = {
    "europe": ("eu", "uk"),
    "usa": ("us",),
    "japan": ("jp",),
    "world": ("wor", "ss"),
    "france": ("fr",),
    "germany": ("de",),
    "spain": ("sp",),
    "italy": ("it",),
    "australia": ("au", "eu"),
    "brazil": ("br",),
    "korea": ("kr",),
    "china": ("cn",),
}

# After the ROM's own region. Canada sits with America because its manuals are
# the American ones in two languages; the other European languages go before
# Japanese, which is last on purpose.
_AFTERWARDS = ("eu", "uk", "us", "ca", "wor", "ss", "fr", "de", "sp", "it", "cus")

# What every PDF opens with. An error page, a "no media" answer or a body cut off
# by the connection does not, and is refused rather than saved as a manual.
_PDF_MAGIC = b"%PDF-"


def pick_manual(medias, rom_regions) -> dict | None:
    """The manual to fetch for a ROM of *rom_regions*, or None if there is none."""
    candidates = [
        m for m in (medias or [])
        if isinstance(m, dict) and m.get("type") == "manuel"
        and (m.get("format") or "pdf").lower() == "pdf" and m.get("url")
    ]
    if not candidates:
        return None
    order: list[str] = []
    for region in rom_regions or []:
        order.extend(_REGION_CODES.get(str(region).lower(), ()))
    order.extend(_AFTERWARDS)
    order.append("jp")
    for code in order:
        for manual in candidates:
            if (manual.get("region") or "").lower() == code:
                return manual
    return candidates[0]


def is_pdf(content: bytes) -> bool:
    return content[:len(_PDF_MAGIC)] == _PDF_MAGIC


# ── Where it lives ──────────────────────────────────────────────────────────
#
# Beside the game, under extras/, where it can be seen over FTP and travels with
# the game when the folder is copied (the owner's decision, 2026-09-18). Not in
# the media store with the covers: that is the application's, this is the game's.

MANUAL_NAME = "Manual.pdf"


def manual_dest(rom_folder: Path, shelf: Path, title: str | None, fs_name: str, *,
                shared: bool = False) -> Path:
    """Where this ROM's manual is written.

    A game with a folder of its own keeps a plain Manual.pdf in its extras. A
    ROM still lying flat on the shelf - the platform folder, or `roms/` inside
    it, the other shape a platform may keep - shares extras/ with every other
    flat game there, so in that case the name carries the game's. So does a
    folder several games live in (*shared*): a Zelda/ holding three regions
    gave one region's booklet to all three (1.0.36 audit).
    """
    from utils.game_folders import game_folder_name, shelves_of

    extras = Path(rom_folder) / "extras"
    # Every shelf of the platform, the console's other names included.
    if Path(rom_folder) not in shelves_of(shelf) and not shared:
        return extras / MANUAL_NAME

    return extras / f"{game_folder_name(title=title, fs_name=fs_name)} - {MANUAL_NAME}"


async def manual_home(rom, title: str | None, shelf: Path, *, session=None) -> Path:
    """Where this ROM's manual goes, beside whichever other games share its place.

    manual_dest, told whether other games live in the folder. And when the name
    it gives is already another game's manual - two regions of one title want
    the same name, in one folder or loose on one shelf - this one is named
    after its own file instead, rather than taking the other game's booklet as
    its own (1.0.36 audit).
    """
    from handler.database.rom_handler import rom_handler

    shared_session = {} if session is None else {"session": session}
    members = await rom_handler.disk_set(rom.id, **shared_session)
    ids = [m.id for m in members] or [rom.id]
    folder = Path(rom.fs_path)
    others = await rom_handler.another_in_folder(str(folder), ids, **shared_session)
    dest = manual_dest(folder, shelf, title, rom.fs_name, shared=others is not None)
    # Asked whether or not the file is there: a manual deleted over FTP leaves
    # its row naming it, and a booklet fetched into that name would open on the
    # other game's page (1.0.36 audit, round 2).
    if await rom_handler.manual_claimed(
            str(folder), stored_path(dest, folder), ids, **shared_session):
        dest = manual_dest(folder, shelf, None, rom.fs_name, shared=True)
    return dest


def stored_path(dest: Path, rom_folder: Path) -> str:
    """What the row keeps: the manual's path relative to the ROM's folder.

    Relative so a folder renamed after the title takes the manual with it and
    the row still finds it, without anybody rewriting the column.
    """
    return Path(dest).relative_to(Path(rom_folder)).as_posix()


def resolve_manual(rom, library_root: str) -> Path | None:
    """The file this ROM's manual is, or None.

    Only inside the ROM library. The column is written by the scraper, but a
    restored metadata backup writes rows too, and a path that climbs out of the
    library must not become something the manual route hands a browser.
    """
    relative = (getattr(rom, "manual_path", None) or "").strip()
    folder = getattr(rom, "fs_path", None)
    if not relative or not folder:
        return None
    try:
        candidate = (Path(folder) / relative).resolve()
        root = Path(library_root).resolve()
    except OSError:
        return None
    if root != candidate and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None


async def fetch_manual(url: str, dest: Path) -> Path | None:
    """Download a manual to *dest*, or return None and leave *dest* alone.

    The whole body is read and checked before anything is written, so a failure
    of any kind - a timeout, a refusal, an answer that is not a PDF - costs the
    manual already on the disk nothing. Written beside the old one first and
    moved over it, so a reader never catches half a file.
    """
    if not url:
        return None
    try:
        content, _ctype = await fetch_media_bytes(
            url, headers={"User-Agent": "GamesDownloader/3.0"}, timeout=60)
    except Exception as exc:  # noqa: BLE001 - one manual must not end a scrape
        logger.warning("Could not fetch a manual: %s", type(exc).__name__)
        return None
    if not is_pdf(content):
        logger.warning("A manual came back as something other than a PDF; not kept")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    partial.write_bytes(content)
    partial.replace(dest)
    return dest
