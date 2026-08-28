"""What the image installs, and what it has to say about it.

GamesDownloader is AGPL-3.0 and ships as a public Docker image built on
Debian. The image already runs ClamAV and Transmission, both GPL-2.0, as
separate programs, and NOTICE.md names them. chdman, which converts disc
images to CHD, is the fourth of those and belongs in the same list.

Two things here fail quietly rather than loudly, which is why they are pinned:

  * the image never carried LICENSE or NOTICE.md at all, while a comment in
    the Dockerfile sends the reader to NOTICE.md for the source link GPL-3.0
    requires. A pointer to a file nobody running this could open.
  * mame-tools without --no-install-recommends pulls in the whole of MAME and
    its ROM data, which is hundreds of megabytes rather than seventeen. The
    image would still work, so nothing would complain.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCKERFILE = ROOT / "Dockerfile"
NOTICE = ROOT / "NOTICE.md"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    if not DOCKERFILE.is_file():
        pytest.skip("Dockerfile nie jest obecny")
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def notice() -> str:
    if not NOTICE.is_file():
        pytest.skip("NOTICE.md nie jest obecny")
    return NOTICE.read_text(encoding="utf-8")


def test_the_image_carries_the_licences_it_points_at(dockerfile):
    """The Dockerfile itself tells the reader to see NOTICE.md. That is only
    true if the file is in there."""
    copied = re.search(r"^COPY\s+([^\n]*?)\s+/app/\s*$", dockerfile, re.M)
    assert copied, "brak COPY, ktory wnosi licencje do obrazu"
    carried = copied.group(1).split()
    for name in ("LICENSE", "NOTICE.md"):
        assert name in carried, f"{name} nie trafia do obrazu"


def test_mame_tools_comes_in_without_its_recommendations(dockerfile):
    """The package that provides chdman recommends the emulator itself, plus
    its ROM data and a Qt interface. That is hundreds of megabytes arriving in
    a public image to run one command line tool."""
    install = next(
        (block for block in dockerfile.split("RUN ") if "mame-tools" in block
         and "apt-get install" in block),
        None,
    )
    assert install, "mame-tools nie jest instalowany przez apt"
    assert "--no-install-recommends" in install, (
        "bez --no-install-recommends wchodzi cale MAME z danymi"
    )


def test_only_the_tool_that_is_used_stays_in_the_image(dockerfile):
    """mame-tools installs nine programs and GD runs one. The other eight are
    emulator-side tooling for cassettes, floppies and cartridge images."""
    assert "rm -f castool" in dockerfile, "reszta pakietu zostaje w obrazie"
    for extra in ("floptool", "imgtool", "jedutil", "ldresample",
                  "ldverify", "romcmp", "unidasm"):
        assert extra in dockerfile, f"{extra} nie jest usuwany"
    assert "command -v chdman" in dockerfile, (
        "nic nie sprawdza, czy po sprzataniu chdman wciaz jest"
    )


def test_the_notice_names_the_tool_and_where_its_source_is(notice):
    """GPL asks for the source of what is distributed, and the honest answer
    for a Debian package is the package and the command that fetches it."""
    assert "chdman" in notice, "brak chdman w NOTICE.md"
    assert "mame-tools" in notice, "brak nazwy pakietu, z ktorego pochodzi"
    assert "apt-get source mame" in notice, "brak drogi do zrodel"
    assert "github.com/mamedev/mame" in notice, "brak adresu projektu"


def test_the_notice_still_names_the_other_bundled_programs(notice):
    """Pinned so the chdman entry cannot be added by replacing the list. These
    three carry the same kind of obligation and were there first."""
    for name in ("ClamAV", "Transmission", "EmulatorJS"):
        assert name in notice, f"{name} zniknal z NOTICE.md"
