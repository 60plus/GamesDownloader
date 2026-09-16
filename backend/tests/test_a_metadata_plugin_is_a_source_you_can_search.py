"""A metadata plugin, offered as a source and then never asked.

Reported by the owner on 2026-09-11 with a screenshot of the ROM metadata editor
and a ring drawn round the row of source chips: "jesli plugin jest zainstalowany
to nie widac go w edit metadata". TheGamesDB was installed, enabled and loaded.

Measured before anything was changed, on his own install:

  * the plugin answers. `metadata_get_covers("Crash Bandicoot")` came back with
    five covers, `metadata_get_heroes` with six, `metadata_get_logos` with one,
    and `metadata_search_game` with five games. So "it does not find it" was not
    what was happening.
  * `/roms/search` asks four sources by name - ScreenScraper, IGDB, LaunchBox,
    SteamGridDB - and nothing else. `metadata_search_game` is not among them, so
    no plugin can appear in that list however well it answers. The counts on the
    screenshot add up to exactly that: 8 + 6 + 8 + 6 = 28.
  * and the header above that row already draws every metadata plugin's logo
    beside the built-in ones. The screen was promising a source the route never
    asked.

>>> WHAT THIS MUST NOT COST. `metadata_search_game` is one request for
TheGamesDB and the answer is remembered for two minutes. `metadata_get_game` is
one request PER CANDIDATE, and the free allowance is about a thousand a month -
the plugin had already burned a month of it in two days by asking eighteen times
per game. So the candidates are built from the search answer alone; the year and
the cover come from fields that answer already carries. A route that reached for
the detail hook to fill a thumbnail would undo that work, which is why it is
asserted here rather than left to memory.

>>> AND A PLUGIN MUST NOT BE ABLE TO EMPTY THE LIST. Plugin code is third-party
code running in-process. One that raises, or hangs, must cost its own results
and nothing else: the four built-in sources are what the editor is for.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
PANEL = FRONTEND / "src" / "views" / "emulation" / "EmulationRomMetadataPanel.vue"


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="u"), scopes={Scope.ROMS_READ}))


class _Hook:
    """Pluggy's hook relay, as this route meets it: one list per plugin."""

    def __init__(self, per_plugin, on_get_game=None):
        self._per_plugin = per_plugin
        self._on_get_game = on_get_game
        self.get_game_calls = 0

    def metadata_search_game(self, query):
        out = []
        for res in self._per_plugin:
            out.append(res(query) if callable(res) else res)
        return out

    def metadata_get_game(self, provider_game_id):
        self.get_game_calls += 1
        return [] if self._on_get_game is None else self._on_get_game

    def metadata_get_cover_url(self, provider_game_id):
        self.get_game_calls += 1
        return []


@pytest.fixture
def route(monkeypatch):
    """The route with every built-in source switched off.

    Not to make the test easier: with no credentials configured the four
    built-in sources return nothing, so anything that comes back came from a
    plugin and the assertion cannot pass for the wrong reason.
    """
    from endpoints.roms import roms_router
    from handler.config.config_handler import config_handler
    from handler.metadata import launchbox_handler

    async def _no_config(key, *a, **k):
        return ""

    #: One built-in result, so "the plugin did not empty the list" is a question
    #: with an answer. With every source silent the assertion would pass on an
    #: empty list and prove nothing.
    lb = [{"launchbox_id": "LB1", "name": "Crash Bandicoot",
           "release_year": 1996, "developer": "Naughty Dog"}]

    async def _lb(*a, **k):
        return lb

    monkeypatch.setattr(config_handler, "get", _no_config)
    monkeypatch.setattr(launchbox_handler, "search_candidates", _lb)
    monkeypatch.setattr(launchbox_handler, "_db_ready", False, raising=False)

    def _with_plugins(per_plugin, on_get_game=None):
        import plugins.manager as pm_mod
        hook = _Hook(per_plugin, on_get_game)
        # The manager as the route meets it: the hook relay AND the pairing of
        # an instance back to the directory it was loaded from, which is where
        # a plugin's logo is served from.
        monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
            hook=hook,
            get_plugin_instances=lambda: [],
            id_for_instance=lambda inst: None,
        ))
        return hook

    return SimpleNamespace(fn=roms_router.search_roms_metadata, with_plugins=_with_plugins)


def _tgdb(query):
    return [{
        "provider_id": "thegamesdb",
        "provider_game_id": "1006",
        "name": "Crash Bandicoot",
        "snippet": "A bandicoot.",
        "year": "1996",
        "cover_url": "https://cdn.thegamesdb.net/images/thumb/boxart/front/1006-1.jpg",
    }]


def _ppe(query):
    return [{
        "provider_id": "ppe",
        "provider_game_id": "https://www.ppe.pl/gry/Crash/8878",
        "name": "Crash Bandicoot N. Sane Trilogy",
    }]


# ── The plugin reaches the list ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_plugins_games_come_back_from_the_search(route):
    """The owner's actual complaint, as a question to the route."""
    route.with_plugins([_tgdb])

    out = await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")

    nasze = [r for r in out if r.get("provider_id") == "thegamesdb"]
    assert nasze, (
        "wtyczka nic nie wniosla do listy zrodel - trasa nadal pyta tylko cztery "
        "wbudowane, a ekran rysuje jej logo nad ta lista: %r" % (out,)
    )
    assert nasze[0]["name"] == "Crash Bandicoot"


@pytest.mark.asyncio
async def test_each_plugin_can_be_told_from_the_others_and_from_the_built_ins(route):
    """The chips are per source, so a result has to say whose it is. Three
    metadata plugins answer on the owner's install - thegamesdb, ppe and
    protondb - and "plugin" alone would collapse them into one chip."""
    route.with_plugins([_tgdb, _ppe])

    out = await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")

    wtyczkowe = [r for r in out if r.get("source") == "plugin"]
    assert len(wtyczkowe) == 2, f"{len(wtyczkowe)} wynikow z wtyczek zamiast dwoch"
    assert {r["provider_id"] for r in wtyczkowe} == {"thegamesdb", "ppe"}
    for r in wtyczkowe:
        assert r.get("_sourceIcon"), f"wynik bez logo, chip nie ma czym sie oznaczyc: {r}"


@pytest.mark.asyncio
async def test_a_plugin_candidate_looks_like_every_other_candidate(route):
    """The grid reads the same keys for every row. A result missing them renders
    as a blank tile with no name under it."""
    route.with_plugins([_tgdb])

    out = await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")
    r = next(x for x in out if x.get("provider_id") == "thegamesdb")

    for key in ("source", "name", "year", "cover_url", "regions",
                "ss_id", "igdb_id"):
        assert key in r, f"brakuje klucza {key!r}, siatka czyta go dla kazdego wiersza"
    assert r["ss_id"] is None and r["igdb_id"] is None, (
        "wynik z wtyczki udaje ScreenScraper albo IGDB, wiec 'Scrape this "
        "version' zgrałoby cudza gre"
    )
    assert r["year"] == "1996"
    assert r["cover_url"], "brak miniatury, a odpowiedz wyszukiwania ja niesie"


# ── What it must not cost, and what it must not break ────────────────────────

@pytest.mark.asyncio
async def test_building_the_list_never_asks_for_one_game_at_a_time(route):
    """>>> THE ALLOWANCE IS THE THING THAT RUNS OUT. metadata_get_game is one
    request per candidate. Calling it here to fill in a year or a thumbnail
    would put back exactly the cost that was just taken out of this plugin."""
    hook = route.with_plugins([_tgdb, _ppe])

    await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")

    assert hook.get_game_calls == 0, (
        "trasa dopytala o pojedyncze gry %d razy - to %d zapytan z limitu na "
        "jedno wyszukiwanie" % (hook.get_game_calls, hook.get_game_calls)
    )


@pytest.mark.asyncio
async def test_a_plugin_that_throws_does_not_take_the_built_in_sources_with_it(route):
    """>>> THE LEGAL CASE. Third-party code runs in this process. The four
    built-in sources are what this editor is for, and a plugin that raises must
    cost plugin results and nothing else.

    Plugin results and not "its own": pluggy's relay aborts on the first
    implementation that raises, so the answers already collected from the others
    are lost with it. That is the behaviour everywhere this hook is called in
    this codebase, and pretending otherwise here would be a test passing for a
    reason the product does not have.
    """
    def _zly(query):
        raise RuntimeError("wtyczka padla")

    route.with_plugins([_zly, _tgdb])

    out = await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")

    assert [r for r in out if r.get("source") == "launchbox"], (
        "padajaca wtyczka zabrala wyniki wbudowanych zrodel - albo wysadzila cala trase"
    )


@pytest.mark.asyncio
async def test_a_plugin_answering_nonsense_is_left_out_rather_than_rendered(route):
    """A row with no id cannot be selected and a row with no name renders as an
    unlabelled tile. Neither belongs in the grid."""
    def _bzdury(query):
        return [{"name": "bez id"}, {"provider_id": "x"}, "nie slownik", None]

    route.with_plugins([_bzdury])

    out = await route.fn(_request(), query="Crash Bandicoot", platform_slug="psx")

    assert [r for r in out if r.get("source") == "plugin"] == [], (
        "niekompletne wiersze trafily do siatki: %r"
        % ([r for r in out if r.get("source") == "plugin"],)
    )


# ── Whose logo goes on the chip ──────────────────────────────────────────────

def _fake_manager(provider_id, plugin_dir):
    class _P:
        def metadata_provider_id(self):
            return provider_id
    inst = _P()
    return SimpleNamespace(
        get_plugin_instances=lambda: [inst],
        id_for_instance=lambda i: plugin_dir if i is inst else None,
    )


def test_a_provider_whose_id_names_no_directory_still_gets_its_logo(monkeypatch):
    """The logo is served from the plugin's DIRECTORY, and a provider names
    itself: protondb's plugin sits in `steam-deck-compatibility`, which no
    suffix in the guess list turns it into. The URL built by guessing answers
    404, so the chip the owner asked for would arrive with no icon on it.

    The plugin itself knows the answer, and the manager can pair an instance
    back to the id it was registered under.
    """
    import plugins.manager as pm_mod
    from endpoints.roms.roms_router import _plugin_dir_for_provider

    monkeypatch.setattr(pm_mod, "plugin_manager",
                        _fake_manager("protondb", "steam-deck-compatibility"))

    assert _plugin_dir_for_provider("protondb") == "steam-deck-compatibility", (
        "nadal zgadujemy katalog po przyrostku, a /api/plugins/protondb/logo "
        "odpowiada 404"
    )


@pytest.mark.asyncio
async def test_the_editors_header_icons_resolve_the_same_way(monkeypatch):
    """>>> AND THE CHIP READS ITS LOGO FROM HERE, NOT FROM THE SEARCH RESULT.

    The panel looks a provider's logo up in the list this route returns and only
    falls back to a URL built from the id. So the same guess lived in two files,
    and fixing the search alone would have left the chip without its icon
    anyway. One answer, in one place, or the screen shows the older of the two.
    """
    import plugins.manager as pm_mod
    from endpoints.settings import plugins_router as pr_mod
    from endpoints.settings.plugins_router import plugin_metadata_providers

    class _P:
        def metadata_provider_id(self):
            return "protondb"

        def metadata_provider_name(self):
            return "ProtonDB"

    inst = _P()
    fake = SimpleNamespace(
        get_plugin_instances=lambda: [inst],
        id_for_instance=lambda i: "steam-deck-compatibility" if i is inst else None,
    )
    # The router bound the singleton by name at import; the shared resolver
    # reads it from its own module. Both, or the test measures half of it.
    monkeypatch.setattr(pm_mod, "plugin_manager", fake)
    monkeypatch.setattr(pr_mod, "plugin_manager", fake)

    req = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="u"), scopes={Scope.PLUGINS_READ}))
    out = await plugin_metadata_providers(req)

    assert out and out[0]["logo_url"] == "/api/plugins/steam-deck-compatibility/logo", (
        "lista dostawcow nadal podaje %r" % (out[0]["logo_url"] if out else None,)
    )


def test_an_unknown_provider_is_not_an_error(monkeypatch):
    """THE LEGAL CASE. A provider nobody registered, or a plugin that answers
    the id hook with a throw, must leave a usable URL rather than an exception
    inside a search."""
    import plugins.manager as pm_mod
    from endpoints.roms.roms_router import _plugin_dir_for_provider

    class _Zly:
        def metadata_provider_id(self):
            raise RuntimeError("nie dzis")

    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        get_plugin_instances=lambda: [_Zly()],
        id_for_instance=lambda i: "cokolwiek",
    ))

    assert _plugin_dir_for_provider("thegamesdb") == "thegamesdb"


def test_a_providers_display_name_resolves_to_the_same_directory(monkeypatch):
    """>>> THE ART HOOKS LABEL THEIR ROWS WITH THE NAME, NOT THE ID.

    `metadata_get_covers` and its two siblings return rows carrying `_source`,
    which is the provider's DISPLAY name. Four places took that, lowered it,
    stripped the spaces and looked for a directory of that shape:

        "TheGamesDB" -> "thegamesdb"   happens to be the directory
        "PPE.pl"     -> "ppe.pl"       is not a directory, and never will be

    It has not bitten yet only because TheGamesDB is the one plugin on the
    owner's install that implements the art hooks (measured). The next one to
    do it gets a 404 for its logo, and nobody would know why.
    """
    import plugins.manager as pm_mod
    from plugins.manager import plugin_dir_for_provider

    class _P:
        def metadata_provider_id(self):
            return "ppe"

        def metadata_provider_name(self):
            return "PPE.pl"

    inst = _P()
    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        get_plugin_instances=lambda: [inst],
        id_for_instance=lambda i: "ppe-metadata" if i is inst else None,
    ))

    for jak_pyta in ("ppe", "PPE.pl", "ppe.pl"):
        assert plugin_dir_for_provider(jak_pyta) == "ppe-metadata", (
            "%r nie trafia w katalog wtyczki" % jak_pyta
        )


def test_an_id_is_not_outvoted_by_another_plugins_name(monkeypatch):
    """THE LEGAL CASE for accepting both. Two plugins, and one's display name
    normalises to the other's id. The id is the exact thing being asked about,
    so it wins - otherwise adding a plugin would silently move another's logo.
    """
    import plugins.manager as pm_mod
    from plugins.manager import plugin_dir_for_provider

    class _Nazwa:
        def metadata_provider_id(self):
            return "inny"

        def metadata_provider_name(self):
            return "TheGamesDB"

    class _Id:
        def metadata_provider_id(self):
            return "thegamesdb"

        def metadata_provider_name(self):
            return "TheGamesDB (stary)"

    po_nazwie, po_id = _Nazwa(), _Id()
    dirs = {po_nazwie: "inny-metadata", po_id: "thegamesdb"}
    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        get_plugin_instances=lambda: [po_nazwie, po_id],
        id_for_instance=dirs.get,
    ))

    assert plugin_dir_for_provider("thegamesdb") == "thegamesdb", (
        "cudza nazwa wyswietlana przebila dokladne id"
    )


@pytest.mark.asyncio
async def test_art_from_a_plugin_carries_a_logo_that_exists(monkeypatch):
    """The library, GOG, catalogue and collection editors all reach plugin art
    through here, and this is where the display name was being mangled."""
    import plugins.manager as pm_mod
    from handler.metadata.external_art import search_cover_options

    class _P:
        def metadata_provider_id(self):
            return "ppe"

        def metadata_provider_name(self):
            return "PPE.pl"

    inst = _P()
    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        hook=SimpleNamespace(metadata_get_covers=lambda query: [[
            {"url": "http://x/1.jpg", "thumb": "http://x/1.jpg", "_source": "PPE.pl"},
        ]]),
        get_plugin_instances=lambda: [inst],
        id_for_instance=lambda i: "ppe-metadata" if i is inst else None,
    ))

    out = await search_cover_options("plugins", "Crash Bandicoot", asset_type="grids")

    assert out, "sztuka z wtyczki w ogole nie wrocila"
    assert out[0]["_sourceIcon"] == "/api/plugins/ppe-metadata/logo", (
        "ikona to %r - zbudowana z nazwy wyswietlanej, wiec 404"
        % out[0].get("_sourceIcon")
    )


def test_the_directory_guess_lives_in_exactly_one_place():
    """Six copies of the same guess existed, and they did not agree: two keyed
    on the display name, three on the provider id, and none of them could reach
    `steam-deck-compatibility`. A rule written six times is a rule that is wrong
    in at least one place, and the wrong one was the copy that is on screen.
    """
    backend = pathlib.Path(__file__).resolve().parent.parent
    kopie = []
    for f in sorted(backend.rglob("*.py")):
        if "tests" in f.parts:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if "-scraper" in line and "-plugin" in line and "-metadata" in line:
                kopie.append(f"{f.relative_to(backend)}:{n}")

    assert len(kopie) == 1 and kopie[0].startswith("plugins/manager.py:"), (
        "zgadywanie katalogu wtyczki zyje w %d miejscach zamiast w jednym:\n  %s"
        % (len(kopie), "\n  ".join(kopie) or "(w zadnym - kto teraz odpowiada?)")
    )


# ── The screen ───────────────────────────────────────────────────────────────

@pytest.mark.skipif(not PANEL.exists(), reason="panel .vue poza kontenerem")
def test_the_chips_are_built_from_what_came_back_not_from_a_list_of_four():
    """The filter row was a closed list of four keys. A fifth source could not
    appear in it however well the route answered, which is the half of this the
    owner could actually see."""
    src = PANEL.read_text(encoding="utf-8")

    start = src.index("const searchFilters = computed(")
    fn = src[start:start + 2000]

    assert "provider_id" in fn, (
        "lista chipow nadal nie patrzy na provider_id, wiec kazda wtyczka "
        "wpada do tego samego chipa albo do zadnego"
    )
    assert "'plugin'" in fn or '"plugin"' in fn, (
        "lista chipow nie rozpoznaje wynikow z wtyczek"
    )


@pytest.mark.skipif(not PANEL.exists(), reason="panel .vue poza kontenerem")
def test_choosing_a_plugin_result_opens_the_art_sections():
    """Covers, backgrounds, screenshots, description and details are each drawn
    only once a game has been picked, and every one of those five conditions
    listed the same three kinds of id. A plugin result would have loaded its
    media into a panel that draws none of it.

    Asked as "is there a gate left that still knows only those three", because
    five separate conditions is exactly the shape where one gets missed.
    """
    src = PANEL.read_text(encoding="utf-8")

    assert "selectedPlugin" in src, (
        "nie ma stanu dla wybranego wyniku z wtyczki, wiec po jego klknieciu "
        "sekcje sztuki pozostaja schowane"
    )
    for stara in ("selectedSsId || selectedIgdbId || selectedLaunchboxId",
                  "!selectedSsId && !selectedIgdbId && !selectedLaunchboxId"):
        assert stara not in src, (
            "zostala bramka, ktora zna tylko SS, IGDB i LaunchBox: %r" % stara
        )
    brama = src[src.index("const hasPickedGame"):][:300]
    assert "selectedPlugin" in brama, (
        "wspolna bramka nie liczy wyboru z wtyczki: %r" % brama.split("\n")[1:3]
    )


@pytest.mark.skipif(not PANEL.exists(), reason="panel .vue poza kontenerem")
def test_picking_a_plugin_result_cannot_start_a_scrape_of_somebody_elses_game():
    """>>> THE LEGAL CASE FOR THE SELECTION. "Scrape this version" reads
    selectedSsId and selectedLaunchboxId. Filling either of them from a plugin
    result to make the sections open would scrape a ScreenScraper id this
    provider never gave, against the ROM the reader is editing."""
    src = PANEL.read_text(encoding="utf-8")

    start = src.index("async function selectResult(")
    fn = src[start:src.index("async function scrapeThisVersion(")]
    galaz = fn[fn.index("if (result.source === 'plugin')"):]
    galaz = galaz[:galaz.index("} else if")]

    for zakazane in ("selectedSsId.value        = result",
                     "selectedIgdbId.value      = result",
                     "selectedLaunchboxId.value = result"):
        assert zakazane not in galaz, (
            "wybor z wtyczki ustawia %r, a to karmi 'Scrape this version'" % zakazane
        )
    assert "selectedPlugin.value" in galaz, "wybor z wtyczki nigdzie sie nie zapisuje"
