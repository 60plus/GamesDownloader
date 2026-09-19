"""The About window offers a way to say thank you, and it does it as a link.

Buy Me a Coffee hands out a ready-made button as a <script> from their CDN.
Dropping that tag into the page would not work here and should not: script-src
is 'self' with no host exceptions, so the browser refuses the file, and even if
it did load, every user who opened About would be announced to a third party.
So the button is what the Discord button already is - an anchor we style
ourselves - and these tests hold that shape, because the tempting fix when the
button "does not look official" is to paste the vendor snippet back in.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"
DIALOG = FRONTEND / "src" / "components" / "common" / "AboutDialog.vue"
ENGLISH = FRONTEND / "src" / "i18n" / "en.json"
TRANSLATIONS = FRONTEND / "public" / "i18n"
LANGUAGES = ("de", "es", "fr", "it", "pl", "pt", "ru")

PROFILE = "https://buymeacoffee.com/gamesdownloader"


def _text(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dialog() -> str:
    return _text(DIALOG)


@pytest.fixture(scope="module")
def support_anchor(dialog: str) -> str:
    match = re.search(r"<a\b[^>]*buymeacoffee[^>]*>", dialog)
    assert match, "okno About nie ma odnosnika do Buy Me a Coffee"
    return match.group(0)


def test_the_window_points_at_the_authors_page(support_anchor: str) -> None:
    assert PROFILE in support_anchor, f"odnosnik nie prowadzi do {PROFILE}"


def test_the_page_opens_beside_the_app_and_cannot_reach_back(support_anchor: str) -> None:
    # Same pair the Discord link uses: a new tab, and no window.opener handed
    # to a page we do not control.
    assert 'target="_blank"' in support_anchor
    assert "noopener" in support_anchor


def test_it_stands_next_to_discord(dialog: str) -> None:
    discord = dialog.index("discord.gg")
    support = dialog.index("buymeacoffee")
    assert discord < support, "przycisk ma stac obok Discorda, nie przed nim"
    between = dialog[discord:support]
    assert "about-sep" not in between, "przycisk wypadl pod kreske, do stopki"


def test_no_vendor_script_was_pasted_in() -> None:
    # The whole reason the link is hand-built. A file that loads their button
    # script (or anything else off-origin) is blocked by the CSP at runtime,
    # which is a blank space in the window rather than an error anyone sees.
    roots = [FRONTEND / "src", FRONTEND / "public", FRONTEND / "index.html"]
    offenders = []
    for root in roots:
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix not in (".vue", ".ts", ".js", ".html"):
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            if "cdnjs.buymeacoffee.com" in body or "bmc-button" in body:
                offenders.append(path.name)
    assert not offenders, f"skrypt dostawcy wrocil do: {offenders}"


def test_the_icon_is_a_file_of_ours(dialog: str, support_anchor: str) -> None:
    # It started as the beer emoji, which is a glyph drawn by whatever font the
    # viewer's system has - colour on Windows and phones, an empty box on a
    # machine with no emoji font installed. An image we serve looks the same to
    # everyone, and img-src is 'self' plus https:, so a CDN would load but
    # would also tell a stranger who opened this window.
    tail = dialog[dialog.index(support_anchor) + len(support_anchor):]
    icon = re.search(r'<img\s+src="([^"]+)"', tail)
    assert icon, "przycisk nie ma ikony"
    src = icon.group(1)
    assert src.startswith("/"), f"ikona spoza naszego serwera: {src}"
    assert (FRONTEND / "public" / src.lstrip("/")).is_file(), f"brak pliku {src}"


def test_the_label_is_translated_everywhere(dialog: str, support_anchor: str) -> None:
    tail = dialog[dialog.index(support_anchor) + len(support_anchor):]
    key = re.search(r"t\(\s*'([^']+)'\s*\)", tail)
    assert key, "napis na przycisku nie idzie przez tlumaczenia"
    name = key.group(1)
    english = json.loads(_text(ENGLISH))
    assert name in english, f"{name} nie ma w en.json"
    for code in LANGUAGES:
        other = json.loads(_text(TRANSLATIONS / f"{code}.json"))
        assert name in other, f"{name} nie ma w {code}.json"
        assert other[name].strip(), f"{name} jest puste w {code}.json"
