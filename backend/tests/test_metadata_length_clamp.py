"""Over-long provider text must not throw away the rest of a metadata write.

`library_games.description_short` is a VARCHAR(512), and every metadata source
offers something for it that has no length promise: GOG's `lead`, IGDB's
`summary`, a Wikipedia opening paragraph. MySQL answers an oversized value with
error 1406 and rejects the *entire* statement, so applying metadata to Prince
of Persia discarded the cover, the background, the logo, the icon, the genres,
the ratings, seven screenshots and a trailer - all of which were valid and all
of which travelled in the same UPDATE as the one long tagline.

These pin the rule: trim the tagline, keep the write.
"""
from __future__ import annotations

import models.library_file  # noqa: F401 - configures the LibraryGame.files mapper
from models.gog_game import GogGame
from models.library_game import LibraryGame
from utils.text import clamp_text

# The shape of the value that caused it: one paragraph of plot, no line breaks.
LONG_TAGLINE = (
    "The game is set in ancient Persia. While the sultan is fighting a war in "
    "a foreign land, his vizier Jaffar, a wizard, seizes power. His only "
    "obstacle is the sultan's daughter, and he locks her in a tower. "
) * 4


# ── The rule ─────────────────────────────────────────────────────────────────

def test_a_value_that_fits_is_untouched():
    assert clamp_text("Prince of Persia", 512) == "Prince of Persia"
    assert clamp_text("x" * 512, 512) == "x" * 512


def test_nothing_to_clamp_passes_through():
    assert clamp_text(None, 512) is None
    assert clamp_text(7, 512) == 7
    assert clamp_text("anything", None) == "anything"


def test_an_oversized_value_is_trimmed_to_fit():
    out = clamp_text(LONG_TAGLINE, 512)
    assert len(out) <= 512
    assert out.endswith("…")
    assert LONG_TAGLINE.startswith(out[:200])


def test_the_trim_prefers_a_word_boundary():
    """A tagline cut mid-word reads like a bug; cut between words it reads
    like a tagline that ran long."""
    out = clamp_text(LONG_TAGLINE, 512)
    assert not out[:-1].endswith(" ")
    # The character before the ellipsis closes a word that appears intact in
    # the source text.
    assert out[:-1] in LONG_TAGLINE


def test_an_unbroken_string_is_still_trimmed():
    """No spaces to break on - a URL, or a language that does not use them.
    Length still wins; the column does not care how readable the value is."""
    out = clamp_text("x" * 900, 512)
    assert len(out) == 512
    assert out.endswith("…")


# ── The columns that take provider text ──────────────────────────────────────

def test_library_game_clamps_the_tagline_on_construction():
    """The catalogue push and the scrape both build the row this way."""
    assert len(LibraryGame(description_short=LONG_TAGLINE).description_short) <= 512


def test_library_game_clamps_the_tagline_on_assignment():
    """The editor PATCH - the path that actually failed - assigns after load."""
    game = LibraryGame(title="Prince of Persia")
    game.description_short = LONG_TAGLINE
    assert len(game.description_short) <= 512


def test_library_game_clamps_its_other_bounded_metadata():
    game = LibraryGame(
        title="T" * 400,
        subtitle="S" * 400,
        developer="D" * 400,
        publisher="P" * 400,
        catalog_external_id="E" * 400,
    )
    assert len(game.title) <= 255
    assert len(game.subtitle) <= 255
    assert len(game.developer) <= 255
    assert len(game.publisher) <= 255
    assert len(game.catalog_external_id) <= 255


def test_gog_game_clamps_the_fields_written_through_from_the_editor():
    """A source=gog edit writes developer/publisher to this row first, so an
    unclamped value here would half-apply the edit before the library row was
    even reached."""
    gog = GogGame(developer="D" * 400, publisher="P" * 400)
    assert len(gog.developer) <= 255
    assert len(gog.publisher) <= 255


# ── The regression ───────────────────────────────────────────────────────────

def test_the_rest_of_the_metadata_survives_a_long_tagline():
    """The whole point: everything else in the write is still there."""
    game = LibraryGame(
        title="Prince of Persia",
        description_short=LONG_TAGLINE,
        developer="Brøderbund Software",
        cover_path="/resources/library/124/cover/cover.png",
        genres=["Platform", "Puzzle", "Adventure"],
        meta_ratings={"steam": 8.2, "rawg": 4.07},
        screenshots=[f"/resources/library/124/shots/shot_{i:03}.jpg" for i in range(7)],
    )
    assert len(game.description_short) <= 512
    assert game.developer == "Brøderbund Software"
    assert game.cover_path == "/resources/library/124/cover/cover.png"
    assert game.genres == ["Platform", "Puzzle", "Adventure"]
    assert len(game.screenshots) == 7


def test_the_clamp_follows_the_column_and_is_not_a_copy_of_it():
    """Widening the column must widen the clamp; a hardcoded 512 here would
    silently keep trimming after a migration."""
    limit = LibraryGame.__table__.c["description_short"].type.length
    assert len(LibraryGame(description_short="z" * (limit + 200)).description_short) == limit


# ── The same guard on the ROM side ───────────────────────────────────────────
#
# The library fix left `Rom` without a single validator, and it is written from
# exactly the same kind of source: ScreenScraper returns a publisher list as
# one string and a descriptive `joueurs` rather than a number. Those land in
# VARCHAR columns, so one long value would throw away the cover, the artwork,
# the genres and everything else in the same UPDATE - the failure the library
# side hit for real.

def test_rom_clamps_the_fields_a_scraper_writes():
    from models.rom import Rom

    rom = Rom(
        name="N" * 900,
        slug="s" * 900,
        developer="D" * 400,
        publisher="P" * 400,
        player_count="one to four players, or two in the versus mode" * 4,
        cover_type="box-2D" * 20,
    )
    assert len(rom.name) <= 512
    assert len(rom.slug) <= 512
    assert len(rom.developer) <= 255
    assert len(rom.publisher) <= 255
    assert len(rom.player_count) <= 50
    assert len(rom.cover_type) <= 32


def test_rom_clamps_on_assignment_too():
    """The scrape apply sets attributes on a row it already loaded."""
    from models.rom import Rom

    rom = Rom(name="Prince of Persia")
    rom.publisher = "Brøderbund Software, " * 40
    assert len(rom.publisher) <= 255


def test_rom_leaves_the_filesystem_fields_alone():
    """fs_name is half of the ROM's identity key (platform_id, fs_name), so
    trimming it would sever the row from the file on disk. The scan owns these,
    not a provider, and the column is wide enough for any real filename."""
    from models.rom import Rom

    dlugie = "A Very Long Filename " * 30 + ".sfc"
    rom = Rom(fs_name=dlugie, fs_name_no_ext=dlugie, fs_path="/roms/snes")
    assert rom.fs_name == dlugie
    assert rom.fs_name_no_ext == dlugie


def test_the_rom_clamp_follows_its_columns():
    from models.rom import Rom

    for field in ("name", "slug", "developer", "publisher", "player_count", "cover_type"):
        limit = Rom.__table__.c[field].type.length
        assert len(getattr(Rom(**{field: "z" * (limit + 100)}), field)) == limit


def test_a_narrow_column_does_not_lose_a_character_it_could_have_kept():
    """rfind returns -1 when there is no space, and on a column no wider than
    the word-break window that -1 used to pass the distance test and cut one
    character off a value that fitted. cover_type (32) and cover_aspect (10)
    are both inside that window."""
    assert len(clamp_text("z" * 100, 32)) == 32
    assert len(clamp_text("z" * 100, 10)) == 10
    assert len(clamp_text("z" * 100, 4)) == 4
