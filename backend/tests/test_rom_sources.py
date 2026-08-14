"""ROM source framework - the security-critical, pure pieces.

Downloads land in roms/<fs_slug>/<filename>, so the filename and slug that a
plugin (untrusted external code) hands back are the thing to pin: no traversal,
no absolute path, only a recognized ROM extension, only a known platform, and
no SSRF target. Region parsing/stripping is display logic but is exercised here
too so a title never silently keeps or loses the wrong tag.
"""
from __future__ import annotations

import asyncio

import pytest

import handler.roms.rom_source_handler as h
from utils.net_guard import UnsafeURLError


# ── Filename safety ────────────────────────────────────────────────────────────

def test_safe_filename_keeps_a_no_intro_name():
    # Spaces and parentheses are legitimate No-Intro punctuation, kept as-is.
    assert h._safe_rom_filename("Ace of Aces (USA).zip") == "Ace of Aces (USA).zip"


@pytest.mark.parametrize("raw, expected", [
    ("../../etc/passwd.zip", "passwd.zip"),   # traversal collapses to a basename
    ("foo/bar.nes", "bar.nes"),               # a separator never survives
    ("/data/plugins/evil.zip", "evil.zip"),   # absolute path -> basename only
    ("a<b>c.zip", "a_b_c.zip"),               # shell/FS-hostile chars neutralised
])
def test_safe_filename_neutralises_paths_and_bad_chars(raw, expected):
    assert h._safe_rom_filename(raw) == expected


@pytest.mark.parametrize("raw", [
    "",                       # nothing
    "..",                     # traversal token
    "readme.txt",             # not a ROM extension
    "installer.exe",          # not a ROM extension
    "cover.png",              # not a ROM extension
    "noextension",            # no extension at all
])
def test_safe_filename_rejects_unusable(raw):
    assert h._safe_rom_filename(raw) == ""


def test_safe_filename_accepts_common_rom_containers():
    for name in ("Game (Europe).zip", "Game.7z", "Game.nes", "Game.n64"):
        assert h._safe_rom_filename(name) == name


# ── Region parsing and title stripping ─────────────────────────────────────────

@pytest.mark.parametrize("filename, region", [
    ("Super Mario World (USA).zip", "USA"),
    ("Chrono Trigger (Japan).zip", "Japan"),
    ("Sonic (Europe).zip", "Europe"),
    ("Tetris (World).zip", "World"),
    ("Zelda (USA, Europe).zip", "USA"),        # first recognised tag wins
    ("Homebrew (Unl).zip", None),              # no region tag present
])
def test_region_parsed_from_filename(filename, region):
    assert h._region_from_name(filename) == region


def test_title_strips_region_tag_only():
    # The region tag goes; a non-region qualifier (Rev A) stays.
    assert h._strip_region_from_title("Super Mario World (USA)") == "Super Mario World"
    assert h._strip_region_from_title("Street Fighter II (USA) (Rev A)") == "Street Fighter II (Rev A)"


def test_title_never_becomes_empty():
    # A pathological all-tag title falls back to the original rather than "".
    assert h._strip_region_from_title("(USA)") == "(USA)"


def test_title_keeps_the_non_region_half_of_a_mixed_tag():
    # An arcade description carries the region and the revision in one tag. The
    # region belongs in its own column, but dropping the whole tag would collapse
    # a dozen distinct sets into a dozen identical rows.
    assert (h._strip_region_from_title("DoDonPachi II - Bee Storm (World, ver. 102)")
            == "DoDonPachi II - Bee Storm (ver. 102)")
    assert (h._strip_region_from_title("FixEight (Japan, Taito license)")
            == "FixEight (Taito license)")
    # A version built out of slashes is not a region list and survives intact.
    assert (h._strip_region_from_title("Sailor Moon (Ver. 95/03/22B, Europe)")
            == "Sailor Moon (Ver. 95/03/22B)")


def test_title_drops_a_tag_that_is_only_regions():
    assert h._strip_region_from_title("Sonic (USA/Europe)") == "Sonic"
    assert h._strip_region_from_title("Sonic (Japan, USA)") == "Sonic"


def test_listing_names_an_untitled_row_without_its_extension(monkeypatch):
    # The container already has its own column, so it does not belong in the
    # title too - but a title the source DID send is left exactly as sent.
    def _list(self, fs_slug, page, page_size, query, region, sort, collection):
        return {
            "items": [
                {"id": "a", "filename": "Meteos (USA).zip"},
                {"id": "b", "filename": "mslug.zip", "title": "Metal Slug"},
            ],
            "total": 2,
        }

    _listing_source(_list, monkeypatch)
    out = asyncio.run(h.list_roms("s1", "nds", 1, 60, None, None, None, None))

    assert [i["title"] for i in out["items"]] == ["Meteos", "Metal Slug"]
    # The file itself is untouched: it is what lands on disk.
    assert [i["filename"] for i in out["items"]] == ["Meteos (USA).zip", "mslug.zip"]
    assert [i["format"] for i in out["items"]] == ["zip", "zip"]


# ── resolve_download validation (the download security gate) ───────────────────

def _fake_source(spec):
    class _Src:
        def rom_source_resolve_download(self, entry_id):
            return spec
    return _Src()


def test_resolve_accepts_a_clean_entry(monkeypatch):
    monkeypatch.setattr(h, "assert_fetch_allowed", lambda *a, **k: None)
    out = h._resolve_entry(
        _fake_source({
            "url": "https://archive.org/download/x/y.zip/Ace%20(USA).zip",
            "filename": "Ace (USA).zip",
            "fs_slug": "snes",
            "headers": {"Authorization": "LOW access:secret"},
            "cookies": {"logged-in-user": "u"},
        }),
        "e1",
    )
    assert out is not None
    assert out["filename"] == "Ace (USA).zip"
    assert out["fs_slug"] == "snes"
    assert out["headers"] == {"Authorization": "LOW access:secret"}
    assert out["cookies"] == {"logged-in-user": "u"}


def test_resolve_folds_a_cookie_header_into_the_jar(monkeypatch):
    # httpx drops a Cookie *header* on redirects, so the core moves it into the
    # cookie jar (which survives redirects). Header goes, cookies gain the pairs.
    monkeypatch.setattr(h, "assert_fetch_allowed", lambda *a, **k: None)
    out = h._resolve_entry(
        _fake_source({
            "url": "https://x/y.zip",
            "filename": "g.zip",
            "fs_slug": "snes",
            "headers": {"Cookie": "logged-in-user=u; logged-in-sig=s"},
        }),
        "e1",
    )
    assert out is not None
    assert out["headers"] is None
    assert out["cookies"] == {"logged-in-user": "u", "logged-in-sig": "s"}


@pytest.mark.parametrize("spec", [
    {"url": "https://x/y", "filename": "x.exe", "fs_slug": "snes"},   # non-ROM ext
    {"url": "https://x/y", "filename": "x.zip", "fs_slug": "not-a-platform"},  # unmapped slug
    {"url": "", "filename": "x.zip", "fs_slug": "snes"},              # no URL
    {"url": "https://x/y", "filename": "../../evil", "fs_slug": "snes"},  # no ROM ext after basename
])
def test_resolve_rejects_bad_entries(monkeypatch, spec):
    monkeypatch.setattr(h, "assert_fetch_allowed", lambda *a, **k: None)
    assert h._resolve_entry(_fake_source(spec), "e1") is None


def test_resolve_rejects_ssrf_target(monkeypatch):
    def _blocked(*a, **k):
        raise UnsafeURLError("blocked")
    monkeypatch.setattr(h, "assert_fetch_allowed", _blocked)
    spec = {"url": "http://169.254.169.254/latest/meta-data/", "filename": "x.zip", "fs_slug": "snes"}
    assert h._resolve_entry(_fake_source(spec), "e1") is None


def test_resolve_survives_a_raising_plugin(monkeypatch):
    monkeypatch.setattr(h, "assert_fetch_allowed", lambda *a, **k: None)

    class _Boom:
        def rom_source_resolve_download(self, entry_id):
            raise RuntimeError("plugin blew up")

    assert h._resolve_entry(_Boom(), "e1") is None


@pytest.mark.parametrize(
    "returned",
    ["https://archive.org/download/item/rom.zip", ["url"], 42, object()],
)
def test_resolve_refuses_a_plugin_that_answers_with_something_other_than_a_dict(
    monkeypatch, returned,
):
    """Returning the URL bare instead of the documented dict is a plausible
    mistake. Reading .get() off it used to raise past the guard, which stranded
    the entry's in-flight reservation for the life of the process and dropped
    every entry queued behind it."""
    monkeypatch.setattr(h, "assert_fetch_allowed", lambda *a, **k: None)

    class _Sloppy:
        def rom_source_resolve_download(self, entry_id):
            return returned

    assert h._resolve_entry(_Sloppy(), "e1") is None


# ── Source presentation (what a theme heads the page with) ─────────────────────

class _FakePluginManager:
    def __init__(self, inst, plugin_id, manifest):
        self._inst, self._pid, self._manifest = inst, plugin_id, manifest

    def get_plugin_instances(self):
        return [self._inst]

    def id_for_instance(self, inst):
        return self._pid

    def manifest_for(self, plugin_id):
        return self._manifest if plugin_id == self._pid else None


def test_source_icon_prefers_the_declared_asset():
    assert h._source_icon("p1", {"icon_asset": "art/icon.png"}) == "/api/plugins/p1/assets/art/icon.png"


def test_source_icon_refuses_a_traversing_asset(tmp_path, monkeypatch):
    # A plugin naming ../.. never turns into an assets URL that climbs out.
    monkeypatch.setattr(h, "PLUGINS_PATH", str(tmp_path))
    assert h._source_icon("p1", {"icon_asset": "../../etc/passwd"}) is None


def test_source_icon_falls_back_to_the_plugin_logo(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "PLUGINS_PATH", str(tmp_path))
    (tmp_path / "p1").mkdir()
    (tmp_path / "p1" / "logo.png").write_bytes(b"x")
    assert h._source_icon("p1", {}) == "/api/plugins/p1/logo"


def test_source_icon_is_none_without_any_art(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "PLUGINS_PATH", str(tmp_path))
    assert h._source_icon("p1", {}) is None


def test_source_listing_carries_the_owning_plugin(tmp_path, monkeypatch):
    class _Src:
        def rom_source_id(self):
            return "archive-x"

        def rom_source_name(self):
            return "Internet Archive - 1G1R"

        def rom_source_meta(self):
            return {"tile_asset": "tlo.png", "requires_auth": True, "configured": False}

    monkeypatch.setattr(h, "PLUGINS_PATH", str(tmp_path))
    (tmp_path / "gd3-x").mkdir()
    (tmp_path / "gd3-x" / "logo.png").write_bytes(b"x")
    monkeypatch.setattr(h, "plugin_manager", _FakePluginManager(_Src(), "gd3-x", {"name": "RomDownloader"}))

    [src] = h.list_rom_sources()
    # The catalogue keeps its own name; the plugin identity rides alongside it,
    # so a theme can head the page with the feature and not the catalogue.
    assert src["name"] == "Internet Archive - 1G1R"
    assert src["plugin_name"] == "RomDownloader"
    assert src["icon"] == "/api/plugins/gd3-x/logo"
    assert src["tile_bg"] == "/api/plugins/gd3-x/assets/tlo.png"
    assert src["configured"] is False


# ── Merged catalogues (the collection field) ───────────────────────────────────

def _listing_source(fn, monkeypatch):
    """Stand a fake source up in front of list_roms, with owned-state disabled."""
    class _Src:
        rom_source_list = fn

    inst = _Src()
    monkeypatch.setattr(h, "_source_instance_for", lambda sid: inst)
    monkeypatch.setattr(h, "_source_meta", lambda i: {})

    async def _none_owned(fs_slug, items):
        return {"crc": set(), "md5": set(), "sha1": set(), "fs_name": set()}

    monkeypatch.setattr(h, "_owned_lookup", _none_owned)
    return inst


def test_listing_passes_the_filter_and_stamps_the_collection(monkeypatch):
    seen: dict = {}

    def _list(self, fs_slug, page, page_size, query, region, sort, collection):
        seen["collection"] = collection
        return {
            "items": [{
                "id": "e1", "title": "Game (USA)", "filename": "Game (USA).zip",
                "collection": "Set A",
            }],
            "total": 1,
            "collections": ["Set A", "Set B", ""],
        }

    _listing_source(_list, monkeypatch)
    out = asyncio.run(h.list_roms("s1", "snes", 1, 60, None, None, None, "Set A"))

    assert seen["collection"] == "Set A"
    # Blank labels are dropped, so a theme never renders an empty filter option.
    assert out["collections"] == ["Set A", "Set B"]
    assert out["items"][0]["collection"] == "Set A"
    assert out["items"][0]["title"] == "Game"      # region tag still stripped


def test_listing_passes_the_release_type_filter(monkeypatch):
    seen: dict = {}

    def _list(self, fs_slug, page, page_size, query, region, sort, collection, fmt, kind):
        seen["kind"] = kind
        return {
            "items": [{"id": "e1", "filename": "Game (USA) (Proto).zip", "kind": "Prototype"}],
            "total": 1,
            "kinds": ["Retail", "prototype"],
        }

    _listing_source(_list, monkeypatch)
    out = asyncio.run(h.list_roms("s1", "snes", 1, 60, None, None, None, None, None,
                                  "prototype"))

    assert seen["kind"] == "prototype"
    # Lower-cased on the way out, so a theme can key its labels off the value.
    assert out["kinds"] == ["retail", "prototype"]
    assert out["items"][0]["kind"] == "prototype"


def test_listing_still_works_for_a_pre_collection_plugin(monkeypatch):
    calls: list = []

    def _old_list(self, fs_slug, page, page_size, query, region, sort):
        calls.append((fs_slug, page))
        return {"items": [], "total": 0}

    _listing_source(_old_list, monkeypatch)
    out = asyncio.run(h.list_roms("s1", "snes", 1, 60, None, None, None, "Set A"))

    assert calls == [("snes", 1)]                  # called, not blown up
    assert out["items"] == [] and out["collections"] == []


def test_entry_without_a_collection_reports_none(monkeypatch):
    def _list(self, fs_slug, page, page_size, query, region, sort, collection):
        return {"items": [{"id": "e1", "title": "Game", "filename": "Game.zip"}], "total": 1}

    _listing_source(_list, monkeypatch)
    out = asyncio.run(h.list_roms("s1", "snes", 1, 60, None, None, None, None))
    assert out["items"][0]["collection"] is None
