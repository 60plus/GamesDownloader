"""The region written on a ROM's filename is now read by the library scan.

The parser was already here, already tested, and already correct. It just lived
inside the remote-source browser and nothing else called it, so a ROM the
scraper failed to recognise ended up with an empty region column while the
answer sat in its filename the whole time.

Moving it also meant the source browser had to keep working, so the first test
holds the shape of that move rather than the behaviour.
"""
from __future__ import annotations

from utils.rom_names import region_from_name, strip_region_from_title


def test_the_source_browser_still_reaches_these():
    """The move must not break the caller that already had them.

    The browser addresses them under their old private names, and so do its
    tests, so they stay bound there.
    """
    from handler.roms import rom_source_handler as h

    assert h._region_from_name is region_from_name
    assert h._strip_region_from_title is strip_region_from_title


def test_the_common_no_intro_tags():
    assert region_from_name("Chrono Trigger (USA).sfc") == "USA"
    assert region_from_name("Metal Slug (Japan).zip") == "Japan"
    assert region_from_name("Sonic (Europe).md") == "Europe"
    assert region_from_name("Tetris (World).gb") == "World"


def test_the_short_forms():
    assert region_from_name("Zelda (U) [!].nes") == "USA"
    assert region_from_name("Zelda (J).nes") == "Japan"
    assert region_from_name("Zelda (E).nes") == "Europe"


def test_the_first_region_of_a_combined_tag():
    assert region_from_name("Sonic (USA/Europe).md") == "USA"
    assert region_from_name("Sonic (Japan, USA).md") == "Japan"


def test_a_region_hiding_among_other_tags():
    # An arcade set writes the region beside the version.
    assert region_from_name("DoDonPachi II - Bee Storm (World, ver. 102).zip") == "World"
    assert region_from_name("Sailor Moon (Ver. 95/03/22B, Europe).zip") == "Europe"


def test_a_filename_saying_nothing_about_region():
    assert region_from_name("Some Homebrew.nes") is None
    assert region_from_name("Game (Rev A).sfc") is None
    assert region_from_name("") is None
    assert region_from_name("Game (Proto).bin") is None
