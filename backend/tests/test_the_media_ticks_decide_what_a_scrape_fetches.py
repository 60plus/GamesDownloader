"""The Additional media ticks on a platform's Scrape Preset decide what is fetched.

Found in 2026-08 and confirmed by the 1.0.34 audit: the ticks were saved and
never read. The scrape built a list of URLs from them and threw it away, then
fetched screenshots, background, wheel, support, bezel, Steam Grid, video and
picto whatever was ticked, and a manual, maps, a box texture, a title screen or
a marquee never, having nowhere to keep them. Two of the names were not even
ScreenScraper's: the screen saved `ss-titre` and `marquee` where the API says
`sstitle` and `screenmarquee`, so choosing either as a cover gave a box instead.

THE OWNER DECIDED THIS (2026-09-17), as RomM does it: each tick lets its media
in, the default is small - the cover, which is the preset's own field, and
gameplay screenshots - and everything else is asked for. The ticks with nowhere
to go leave the screen until ROMs get folders of their own; wheel, Steam Grid
and picto, fetched until now with no tick at all, get one.

A preset saved before any of this was not a choice about downloads: the screen
started every platform with nothing ticked, and saving a cover type saved that
empty list with it. Such a list takes the default. One somebody filled in is
kept, since that is what they asked for.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SETTINGS_VUE = BACKEND.parent / "frontend" / "src" / "views" / "settings" / "SettingsRoms.vue"

_EVERY_TYPE = (
    "box-2D", "fanart", "background", "ss", "sstitle",
    "support-2D", "support-texture", "wheel-hd", "screenmarquee",
    "bezel-16-9", "bezel-4-3", "steamgrid", "video", "video-normalized",
    "pictoliste",
)


# ── Reading a preset ─────────────────────────────────────────────────────────

def test_a_platform_with_no_preset_gets_the_small_default():
    from handler.metadata.scrape_presets import wanted_media

    assert wanted_media(None) == {"ss"}
    assert wanted_media({}) == {"ss"}
    assert wanted_media({"cover_type": "box-3D"}) == {"ss"}


def test_an_empty_list_saved_before_the_ticks_worked_takes_the_default():
    from handler.metadata.scrape_presets import wanted_media

    assert wanted_media({"cover_type": "box-2D", "region": "wor", "extras": []}) == {"ss"}, (
        "stary preset z pusta lista (nikt niczego nie wybieral) traci zrzuty ekranu"
    )


def test_a_list_somebody_filled_in_before_is_kept_under_the_right_names():
    from handler.metadata.scrape_presets import wanted_media

    got = wanted_media({"extras": ["bezel-16-9", "marquee", "ss-titre", "video"]})
    assert got == {"bezel-16-9", "screenmarquee", "sstitle", "video"}


def test_an_empty_list_saved_now_means_nothing_but_the_cover():
    from handler.metadata.scrape_presets import PRESET_VERSION, wanted_media

    assert wanted_media({"extras": [], "version": PRESET_VERSION}) == set(), (
        "administrator odznaczyl wszystko, a skan i tak pobiera zrzuty"
    )


def test_an_old_cover_name_reaches_screenscraper_under_its_real_name():
    from handler.metadata.scrape_presets import cover_type

    assert cover_type({"cover_type": "ss-titre"}) == "sstitle"
    assert cover_type({"cover_type": "marquee"}) == "screenmarquee"
    assert cover_type({"cover_type": "box-3D"}) == "box-3D"
    assert cover_type({}) == "box-2D"


# ── Picking the background ───────────────────────────────────────────────────

def _game(*types):
    return {"id": 1, "medias": [{"type": t, "url": f"http://ss/{t}.jpg", "region": "wor"}
                                for t in types]}


def test_a_background_is_picked_from_the_types_asked_for():
    from handler.metadata.screenscraper_handler import extract_metadata

    game = _game("fanart", "background", "ss")

    assert extract_metadata(game)["background_url"].endswith("/fanart.jpg"), (
        "bez listy typow tlo nie jest juz fanartem, jak bylo dotad"
    )
    assert extract_metadata(game, background_types=("background",))["background_url"].endswith(
        "/background.jpg")


def test_no_background_asked_for_is_no_background_not_a_screenshot():
    from handler.metadata.screenscraper_handler import extract_metadata

    assert extract_metadata(_game("ss"), background_types=())["background_url"] is None
    # Asked for and missing, a screenshot still stands in, as it always has.
    assert extract_metadata(_game("ss"), background_types=("fanart",))["background_url"].endswith(
        "/ss.jpg")


# ── The scrape obeys it ──────────────────────────────────────────────────────

@pytest.fixture
def scrape(monkeypatch, tmp_path):
    """scrape_rom against a ScreenScraper answer carrying every kind of media.

    `.preset` is the platform's saved preset; `.fetched` is every URL the scrape
    downloaded; `.sgdb` is every SteamGridDB request."""
    from handler.metadata import rom_scrape_handler as h
    from plugins.manager import plugin_manager

    state = SimpleNamespace(preset=None, fetched=[], sgdb=[])

    settings = {
        "screenscraper_username": "u", "screenscraper_password": "p",
        "steamgriddb_api_key": "key",
    }
    # What LaunchBox answers, or None to leave it switched off.
    state.launchbox = None

    async def _get(key, *_a, **_k):
        if key == "launchbox_enabled":
            return "true" if state.launchbox else "false"
        return settings.get(key, "")

    async def _launchbox(*_a, **_k):
        return state.launchbox

    async def _get_bool(_key, default=False):
        return False

    state.types = list(_EVERY_TYPE)
    # Media the answer carries on top of one of each type, for a test that needs
    # several of a kind or one in another region.
    state.more = []

    async def _search(*_a, **_k):
        return {
            "id": 42,
            "noms": [{"region": "wor", "text": "Game"}],
            "medias": [{"type": t, "url": f"http://ss/{t}.jpg", "region": "wor"}
                       for t in state.types] + list(state.more),
        }

    async def _nothing(*_a, **_k):
        return None

    async def _no_plugins(*_a, **_k):
        return []

    async def _download(url, dest, *, replace=False):
        state.fetched.append(url)
        return dest

    def _sections(name):
        if name == "rom_scrape_presets":
            return {} if state.preset is None else {"snes": state.preset}
        return {}

    class _Answer:
        status_code = 404

        @staticmethod
        def json():
            return {}

    class _Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        async def get(self, url, **_k):
            state.sgdb.append(url)
            return _Answer()

    monkeypatch.setattr(h.config_handler, "get", _get)
    monkeypatch.setattr(h.config_handler, "get_bool", _get_bool)
    monkeypatch.setattr(h.config_manager, "get_section", _sections)
    monkeypatch.setattr(h.screenscraper_handler, "search_game", _search)
    monkeypatch.setattr(h.hltb_handler, "search_game", _nothing)
    monkeypatch.setattr(h.launchbox_handler, "search_game", _launchbox)
    monkeypatch.setattr(plugin_manager, "call_each", _no_plugins)
    monkeypatch.setattr(h, "_download_image", _download)
    monkeypatch.setattr(h, "_detect_cover_aspect", lambda _p: None)
    monkeypatch.setattr(h, "_rom_media_dir", lambda *_a: tmp_path)
    monkeypatch.setattr(h.httpx, "AsyncClient", _Client)

    rom = SimpleNamespace(
        id=5, fs_name="Game.sfc", fs_name_no_ext="Game", fs_size_bytes=1,
        crc_hash="", md5_hash="", sha1_hash="", media_source=None, cover_source=None,
        cover_path=None, background_path=None, screenshots=None, support_path=None,
        wheel_path=None, bezel_path=None, steamgrid_path=None, video_path=None,
        picto_path=None,
    )
    platform = SimpleNamespace(slug="snes", fs_slug="snes")
    state.rom = rom

    async def _run():
        state.fetched.clear()
        state.sgdb.clear()
        state.result = await h.scrape_rom(rom, platform)
        return {u.rsplit("/", 1)[-1].rsplit(".", 1)[0] for u in state.fetched}

    state.run = _run
    return state


@pytest.mark.asyncio
async def test_with_no_preset_a_scrape_fetches_the_cover_and_screenshots(scrape):
    got = await scrape.run()

    assert got == {"box-2D", "ss"}, (
        f"bez presetu skan pobiera wiecej niz okladke i zrzuty: {sorted(got)}"
    )
    assert not scrape.sgdb, "bez zaznaczonego Steam Grid ani tla skan pyta SteamGridDB"


@pytest.mark.asyncio
async def test_each_tick_lets_in_its_own_media_and_nothing_else(scrape):
    from handler.metadata.scrape_presets import PRESET_VERSION

    cases = {
        "support-2D": {"support-2D"},
        "support-texture": {"support-texture"},
        "bezel-16-9": {"bezel-16-9"},
        "bezel-4-3": {"bezel-4-3"},
        "video": {"video"},
        "video-normalized": {"video-normalized"},
        "steamgrid": {"steamgrid"},
        "pictoliste": {"pictoliste"},
        "wheel": {"wheel-hd"},
        "fanart": {"fanart"},
        "background": {"background"},
        "sstitle": {"sstitle"},
    }
    for tick, expected in cases.items():
        scrape.preset = {"cover_type": "box-2D", "region": "wor",
                         "extras": [tick], "version": PRESET_VERSION}
        got = await scrape.run()
        assert got == {"box-2D"} | expected, (
            f"zaznaczenie {tick!r} pobiera {sorted(got - {'box-2D'})} "
            f"zamiast {sorted(expected)}"
        )


@pytest.mark.asyncio
async def test_an_unticked_background_is_not_fetched_from_another_provider_either(scrape):
    """ScreenScraper is told which backgrounds are wanted; LaunchBox and IGDB
    are not, and their background arrives in the same merged answer."""
    scrape.types = [t for t in _EVERY_TYPE if t not in ("fanart", "background")]
    scrape.launchbox = {"background_url": "http://lb/launchbox-fanart.jpg"}

    got = await scrape.run()

    assert "launchbox-fanart" not in got, "odznaczone tlo i tak przychodzi z LaunchBoxa"


@pytest.mark.asyncio
async def test_nothing_ticked_is_the_cover_alone(scrape):
    from handler.metadata.scrape_presets import PRESET_VERSION

    scrape.preset = {"cover_type": "box-2D", "region": "wor", "extras": [],
                     "version": PRESET_VERSION}

    assert await scrape.run() == {"box-2D"}
    assert not scrape.sgdb


@pytest.mark.asyncio
async def test_a_background_that_is_wanted_may_still_come_from_steamgriddb(scrape):
    """The fallback is not dropped, only asked first: ticked, it runs as before."""
    from handler.metadata.scrape_presets import PRESET_VERSION

    scrape.preset = {"cover_type": "box-2D", "region": "wor",
                     "extras": ["steamgrid", "background"], "version": PRESET_VERSION}
    # ScreenScraper has neither, which is when the fallback is asked.
    scrape.types = [t for t in _EVERY_TYPE if t not in ("steamgrid", "fanart", "background")]
    await scrape.run()

    assert scrape.sgdb, "zaznaczony Steam Grid nie siega juz po SteamGridDB"


@pytest.mark.asyncio
async def test_a_title_screen_chosen_as_the_cover_is_the_title_screen(scrape):
    scrape.preset = {"cover_type": "ss-titre", "region": "wor", "extras": []}

    got = await scrape.run()

    assert "sstitle" in got and "box-2D" not in got, (
        f"okladka 'ekran tytulowy' pobiera pudelko: {sorted(got)}"
    )


# ── The title screen ends the gallery ───────────────────────────────────────
#
# Its own tick, off by default like everything past the cover and the gameplay
# screenshots. It goes LAST and on top of the six (the owner's call, 2026-09-18):
# a video's thumbnail in Modern, the hover preview in Vapor and Couch's stand-in
# background all take the first picture as the game's own, and those should go
# on showing the game being played.

_SHOTS = "/resources/roms/snes/5/"


def _title_preset(*ticks):
    from handler.metadata.scrape_presets import PRESET_VERSION

    return {"cover_type": "box-2D", "region": "wor", "extras": list(ticks),
            "version": PRESET_VERSION}


@pytest.mark.asyncio
async def test_the_title_screen_comes_after_the_gameplay(scrape):
    scrape.preset = _title_preset("ss", "sstitle")

    await scrape.run()

    assert scrape.result["screenshots"] == [
        _SHOTS + "screenshot_0.jpg", _SHOTS + "title_screen.jpg",
    ], "ekran tytulowy nie stoi na koncu galerii, za rozgrywka"


@pytest.mark.asyncio
async def test_the_title_screen_takes_no_gameplay_place(scrape):
    scrape.preset = _title_preset("ss", "sstitle")
    scrape.more = [{"type": "ss", "url": f"http://ss/ss-{n}.jpg", "region": "wor"}
                   for n in range(1, 8)]

    await scrape.run()

    shots = scrape.result["screenshots"]
    assert len(shots) == 7 and shots[-1] == _SHOTS + "title_screen.jpg", (
        f"ekran tytulowy zabral miejsce zrzutowi rozgrywki: {shots}"
    )


@pytest.mark.asyncio
async def test_ticked_alone_it_joins_the_gallery_already_there(scrape):
    """An unticked kind is not fetched, which is not the same as deleted: with
    gameplay unticked, the gameplay pictures already there stay."""
    scrape.preset = _title_preset("sstitle")
    scrape.rom.screenshots = [_SHOTS + "screenshot_0.png", _SHOTS + "screenshot_1.png"]
    scrape.rom.media_source = {"screenshots": "scrape"}

    got = await scrape.run()

    assert "ss" not in got
    assert scrape.result["screenshots"] == [
        _SHOTS + "screenshot_0.png", _SHOTS + "screenshot_1.png", _SHOTS + "title_screen.jpg",
    ]


@pytest.mark.asyncio
async def test_a_new_title_screen_replaces_the_old_one(scrape):
    scrape.preset = _title_preset("sstitle")
    scrape.rom.screenshots = [_SHOTS + "screenshot_0.png", _SHOTS + "title_screen.png"]
    scrape.rom.media_source = {"screenshots": "scrape"}

    await scrape.run()

    assert scrape.result["screenshots"] == [
        _SHOTS + "screenshot_0.png", _SHOTS + "title_screen.jpg",
    ], "stary ekran tytulowy zostal w galerii obok nowego"


@pytest.mark.asyncio
async def test_a_gallery_somebody_put_together_gets_no_title_screen(scrape):
    scrape.preset = _title_preset("ss", "sstitle")
    scrape.rom.screenshots = [_SHOTS + "mine.png"]
    scrape.rom.media_source = {"screenshots": "manual"}

    got = await scrape.run()

    assert "sstitle" not in got, "skan dopisuje do galerii ulozonej recznie"
    assert "screenshots" not in scrape.result


@pytest.mark.asyncio
async def test_a_game_with_no_title_screen_leaves_the_gallery_alone(scrape):
    scrape.preset = _title_preset("sstitle")
    scrape.types = [t for t in _EVERY_TYPE if t != "sstitle"]
    scrape.rom.screenshots = [_SHOTS + "screenshot_0.png"]
    scrape.rom.media_source = {"screenshots": "scrape"}

    await scrape.run()

    assert "screenshots" not in scrape.result


@pytest.mark.asyncio
async def test_the_manual_tick_brings_the_manual_and_the_rest_of_the_scrape(
        scrape, monkeypatch, tmp_path):
    """Found on 2026-09-18, while writing the wiki: with the tick on, the scrape
    asked keep_existing_media about a column it had never been told of, which
    raises - so every scrape of a platform with Manual ticked failed as a
    whole, cover and title with it. The manual had only source-reading tests,
    and the manuals on the test server had been fetched by a script."""
    import handler.filesystem.rom_paths as rom_paths
    from handler.metadata import manuals

    library = tmp_path / "library"
    scrape.rom.fs_path = str(library / "snes" / "Game")
    scrape.rom.name = "Game"
    scrape.rom.regions = ["eu"]
    scrape.rom.manual_path = None
    scrape.more = [{"type": "manuel", "url": "http://ss/manuel.pdf", "region": "eu",
                    "format": "pdf"}]
    scrape.preset = _title_preset("manuel")
    fetched = []

    async def _fetch(url, dest):
        fetched.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"%PDF-1.4")
        return dest

    # The game alone in its folder (manuals.manual_home asks the library).
    from handler.database.rom_handler import rom_handler

    async def _its_set(_rom_id, **_k):
        return [scrape.rom]

    async def _nobody(*_a, **_k):
        return None

    async def _unclaimed(*_a, **_k):
        return False

    monkeypatch.setattr(rom_handler, "disk_set", _its_set)
    monkeypatch.setattr(rom_handler, "another_in_folder", _nobody)
    monkeypatch.setattr(rom_handler, "manual_claimed", _unclaimed)
    monkeypatch.setattr(manuals, "fetch_manual", _fetch)
    monkeypatch.setattr(rom_paths, "roms_library_path", lambda: str(library))

    await scrape.run()

    assert fetched == ["http://ss/manuel.pdf"]
    assert scrape.result.get("manual_path") == "extras/Manual.pdf"
    assert scrape.result.get("cover_path"), "okladka przepadla razem z calym scrapem"


def test_the_title_screen_is_the_presets_region_first():
    from handler.metadata.screenscraper_handler import pick_title_screen

    game = {"medias": [
        {"type": "sstitle", "url": "http://ss/title-jp.png", "region": "jp"},
        {"type": "sstitle", "url": "http://ss/title-eu.png", "region": "eu"},
        {"type": "ss", "url": "http://ss/gameplay-eu.png", "region": "eu"},
    ]}

    assert pick_title_screen(game, "eu") == "http://ss/title-eu.png"
    assert pick_title_screen(game, "jp") == "http://ss/title-jp.png"
    assert pick_title_screen({"medias": [
        {"type": "ss", "url": "http://ss/gameplay.png", "region": "wor"},
    ]}, "wor") is None


# ── The screen says the same ─────────────────────────────────────────────────

def _vue() -> str:
    return io.open(SETTINGS_VUE, encoding="utf-8").read()


def _extras_values(source: str) -> list[str]:
    block = source[source.index("const EXTRAS_GROUPS"):]
    block = block[:block.index("\n]")]
    return re.findall(r"value:\s*'([^']+)'", block)


def test_the_screen_offers_only_ticks_the_scrape_obeys():
    from handler.metadata.scrape_presets import TICKS

    offered = _extras_values(_vue())
    assert sorted(offered) == sorted(TICKS), (
        f"ekran i skan nie zgadzaja sie co do zaznaczen: ekran {sorted(offered)}, "
        f"skan {sorted(TICKS)}"
    )


def test_the_screen_starts_a_platform_with_the_servers_default():
    from handler.metadata.scrape_presets import DEFAULT_MEDIA

    source = _vue()
    default = re.search(r"const DEFAULT_PRESET: ScrapePreset = \{[^}]*extras:\s*\[([^\]]*)\]", source)
    assert default, "nie znalazlem DEFAULT_PRESET"
    assert re.findall(r"'([^']+)'", default.group(1)) == list(DEFAULT_MEDIA)
    # And every place that builds a fresh entry uses it rather than an empty list.
    assert "extras: []" not in source, "nowa platforma dostaje pusta liste zamiast domyslnej"


def test_the_screen_names_covers_the_way_screenscraper_does():
    source = _vue()
    block = source[source.index("const COVER_TYPES"):]
    block = block[:block.index("\n]")]
    values = re.findall(r"value:\s*'([^']+)'", block)
    assert "ss-titre" not in values and "marquee" not in values
    assert "sstitle" in values and "screenmarquee" in values


# ── The routes hand back what the scrape will do ─────────────────────────────

def _route(fn):
    return getattr(fn, "__wrapped__", fn)


@pytest.mark.asyncio
async def test_the_presets_route_shows_the_default_an_old_empty_list_takes(monkeypatch):
    """The platform page saves every preset back when a cover type changes. If
    the route handed back the stored empty list, that save would turn an old
    'nobody chose' into a new 'nothing at all' for every platform at once."""
    from endpoints.settings import roms_settings_router as r

    stored = {"snes": {"cover_type": "marquee", "region": "wor", "extras": []}}
    monkeypatch.setattr(r.config_manager, "get_section", lambda _n: stored)

    shown = await _route(r.get_scrape_presets)(SimpleNamespace())

    assert shown["snes"]["extras"] == ["ss"]
    assert shown["snes"]["cover_type"] == "screenmarquee"


@pytest.mark.asyncio
async def test_saving_marks_the_preset_as_a_real_choice(monkeypatch):
    from endpoints.settings import roms_settings_router as r
    from handler.metadata.scrape_presets import PRESET_VERSION, wanted_media

    saved = {}
    monkeypatch.setattr(r.config_manager, "save_section",
                        lambda name, data: saved.update({name: data}))

    body = r.ScrapePresetsBody(presets={
        "snes": {"cover_type": "box-2D", "region": "wor", "extras": []},
        # What the platform page posts for a platform with no preset yet.
        "nes": {"cover_type": "box-3D"},
    })
    await _route(r.save_scrape_presets)(SimpleNamespace(), body)

    presets = saved["rom_scrape_presets"]
    assert presets["snes"]["version"] == PRESET_VERSION
    assert wanted_media(presets["snes"]) == set(), "swiadome odznaczenie wszystkiego przepadlo"
    assert wanted_media(presets["nes"]) == {"ss"}, (
        "zmiana typu okladki na stronie platformy zabiera jej zrzuty ekranu"
    )


@pytest.mark.asyncio
async def test_one_platforms_preset_comes_back_with_the_default(monkeypatch):
    from endpoints.settings import roms_settings_router as r

    monkeypatch.setattr(r.config_manager, "get_section", lambda _n: {})

    shown = await _route(r.get_platform_preset)(SimpleNamespace(), "snes")

    assert shown == {"cover_type": "box-2D", "region": "wor", "extras": ["ss"]}
