"""Content fetched onto the server is charged to whoever fetched it.

Reported: "dla uploadera gry pobrane z Pluginow storefront/RomDownloader nie
zaliczaja sie do limitu miejsca na gry. pobralem jako gdtest gre na amige i nie
zostala zaliczona."

Two different failures wore one symptom.

The storefront one is a missing field. That path builds a real LibraryGame with
real LibraryFile rows carrying real sizes, and even asks the quota for a per-file
ceiling on the way in, but leaves published_by NULL. The quota sums by owner, so
an account whose games all arrived this way reads as using nothing, forever, and
the ceiling it asks for therefore never tightens.

The ROM one is deeper: a unit mismatch. The quota's unit is "library games owned
by an account", and a ROM is not a library game. A ROM fetched through a rom
source plugin creates a row in `roms` and nothing else - no LibraryGame, no
LibraryFile. The account behind the request was collected as a username string,
parked on an in-memory job object, and read exactly once to decorate a log line.
It never reached the database, and there was no column for it to reach.

So the fix is in two halves that must both hold: a ROM gains an owner, and the
sum learns to look at both domains. Either alone leaves the report true.

WHAT IS DELIBERATELY NOT HERE:
- No backfill for ROMs. Nothing ever recorded who downloaded what - the job
  registry is process memory - so every existing ROM keeps a NULL owner and
  counts against nobody. Guessing would put real uploaders over quota on the
  first boot after an upgrade, which is the shape of an incident already on
  record here. NULL is the honest answer for a file that was already there.
- The scanner stays owner-blind. It re-walks the whole tree, so attributing what
  it finds to whoever triggered the scan would hand one account every ROM on the
  disk. Attribution belongs at the download, not at the discovery.
"""
from __future__ import annotations

import io
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parent.parent
QUOTA = BACKEND / "handler" / "library" / "quota.py"
ROM_SOURCES = BACKEND / "endpoints" / "roms" / "rom_sources_router.py"
ROM_HANDLER = BACKEND / "handler" / "roms" / "rom_source_handler.py"
CATALOG = BACKEND / "handler" / "library" / "catalog_sync_handler.py"
PLUGINS = BACKEND / "endpoints" / "settings" / "plugins_router.py"
SCANNER = BACKEND / "handler" / "filesystem" / "rom_scanner.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


# ── The storefront half: a missing field ─────────────────────────────────────

def test_a_catalogue_download_records_who_asked_for_it():
    """The game is built here, so this is where the owner has to be set."""
    source = _source(CATALOG)
    start = source.index("async def _ensure_game_for_entry")
    body = source[start:source.index("\nasync def ", start + 10)]
    assert "published_by" in body, "gra ze sklepu powstaje bez wlasciciela"
    assert "uploaded_by" in body, "gra ze sklepu nie zapamietuje, kto ja przyniosl"


def test_the_account_reaches_the_handler_that_builds_the_game():
    """The router had the user and passed only their name. A name cannot be
    summed against a quota."""
    source = _source(CATALOG)
    for fn in ("async def queue_entry_downloads", "async def _queue_entry_downloads_locked"):
        start = source.index(fn)
        signature = source[start:source.index(")", source.index("(", start))]
        assert "user_id" in signature, f"{fn} nie przyjmuje konta"


def test_the_router_passes_the_id_and_not_only_the_name():
    source = _source(PLUGINS)
    start = source.index("await queue_entry_downloads(")
    call = source[start:source.index(")", source.index("max_bytes", start))]
    assert "user_id" in call, "router nie przekazuje konta"


# ── The ROM half: a unit mismatch ────────────────────────────────────────────

def test_a_rom_can_belong_to_somebody():
    from models.rom import Rom

    for column in ("published_by", "uploaded_by"):
        assert column in Rom.__table__.columns, f"roms nie ma kolumny {column}"


def test_the_columns_are_created_on_an_existing_install():
    # The list is column-aligned with runs of spaces, so compare on the names
    # rather than on the spacing that happens to sit between them.
    source = re.sub(r"\s+", " ", _source(BACKEND / "main.py"))
    for column in ("published_by", "uploaded_by"):
        assert f'"roms", "{column}"' in source, f"brak migracji dla roms.{column}"


def test_nothing_guesses_an_owner_for_roms_already_here():
    """The one thing that would turn this fix into an incident. Nothing ever
    recorded who downloaded what, so any backfill here is a guess, and a guess
    puts real uploaders over quota the moment the sum starts counting."""
    source = _source(BACKEND / "main.py")
    for forbidden in ("UPDATE `roms` SET `published_by`", "UPDATE `roms` SET `uploaded_by`"):
        assert forbidden not in source, "uzupelnianie wstecz zgaduje wlasciciela ROM-ow"


def test_the_download_carries_the_account_not_a_display_name():
    """actor was a username string that died in a log line. The id has to travel
    the same road and reach the row."""
    source = _source(ROM_HANDLER)
    start = source.index("class _RomJob")
    body = source[start:source.index("\n@", start) if "\n@" in source[start:start + 3000]
                  else start + 3000]
    assert "actor_id" in body, "zadanie pobrania nie niesie konta"


def test_both_rom_source_routes_pass_the_account():
    """Downloading and importing are the same act by two doors. The hole comes
    back through whichever one is forgotten."""
    source = _source(ROM_SOURCES)
    assert source.count("actor_id=") >= 2, "nie obie trasy przekazuja konto"


def test_the_downloaded_rom_row_gets_the_owner():
    source = _source(ROM_HANDLER)
    import re as _re

    # The whole function, not a fixed window: a window of characters goes quiet
    # as soon as somebody writes a comment above the line it was looking for.
    start = source.index("async def _register_and_scrape")
    nxt = _re.search(r"\n(async )?def ", source[start + 10:])
    body = source[start:start + 10 + nxt.start()] if nxt else source[start:]
    assert "published_by" in body, "pobrany ROM nie dostaje wlasciciela"


def test_the_scanner_never_attributes_what_it_merely_finds():
    """It re-walks the entire tree. Stamping there would hand one account every
    ROM on the disk the first time somebody pressed Scan."""
    source = _source(SCANNER)
    for forbidden in ("published_by", "uploaded_by", "actor_id"):
        assert forbidden not in source, f"skaner przypisuje wlasciciela ({forbidden})"


# ── The sum has to look at both domains ──────────────────────────────────────

def test_the_total_includes_roms():
    source = _source(QUOTA)
    assert "Rom.published_by" in source, "suma nie liczy ROM-ow"
    assert "fs_size_bytes" in source, "suma nie zna rozmiaru ROM-u"


def test_a_rom_that_is_gone_from_the_disk_stops_counting():
    """The scanner marks a vanished file rather than deleting the row, so
    counting them would charge an account for files that are not there."""
    source = _source(QUOTA)
    assert "missing_from_fs" in source, "suma liczy ROM-y, ktorych juz nie ma"


def test_the_listing_agrees_with_the_bar():
    """The figure and the rows underneath it come from one rule, or somebody is
    looking at a total they cannot account for."""
    source = _source(QUOTA)
    start = source.index("async def owned_games")
    body = source[start:source.index("\nasync def ", start + 10)]
    assert "_owned_roms" in body, "lista wgran nie pokazuje ROM-ow, a suma je liczy"
    assert '"kind"' in body, "wiersze nie mowia, czy to gra czy ROM"
    # And a ROM row is shaped like a game row, or every caller has to special
    # case half of its own list.
    roms = source[source.index("async def _owned_roms"):]
    for field in ('"kind": "rom"', '"size_bytes"', '"library"', '"title"'):
        assert field in roms, f"wiersz ROM-u nie ma {field}"


def test_gog_is_still_left_out():
    """Tens of gigabytes nobody uploaded. The reason is in the module header and
    it has not changed."""
    source = _source(QUOTA)
    assert '!= "gog"' in source


# ── And the guard that should have caught all of this ────────────────────────

def test_the_old_guard_test_no_longer_passes_on_a_substring():
    """test_upload_quota.py asserted that the text "quota." appeared in three
    files. It would have stayed green through every hole above."""
    source = _source(BACKEND / "tests" / "test_upload_quota.py")
    match = re.search(r'assert\s+"quota\."\s+in\s+\w+', source)
    assert not match, "straznik nadal sprawdza obecnosc napisu zamiast zachowania"
