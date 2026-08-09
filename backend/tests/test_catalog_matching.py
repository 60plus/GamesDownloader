"""Which real game a port's name refers to.

Every case here is one a live probe over the PC Ports catalogue actually got
wrong, or nearly did. The failure mode that matters is not "no result" - it is
a confident wrong result, because a filled-in description reads as data and
nobody re-checks it. So these pin the two rules that reject a plausible lie:
a match must share an identifying word, and a sequel must not outrank the game
it is a sequel to.
"""
from __future__ import annotations

import pytest

from handler.library.catalog_meta_handler import (
    distinctive,
    name_score,
    pick_match,
    platforms_for_category,
    tokens,
)

N64 = {"nintendo-64"}


def cand(name: str, *platforms: str) -> dict:
    return {"name": name, "slug": name.lower().replace(" ", "-"),
            "platforms": set(platforms)}


# ── The identifying-word rule ────────────────────────────────────────────────

def test_unrelated_game_on_the_same_console_is_rejected():
    """Goemon 64 matched Doom 64: one shared word, and it was the number.

    Both are "a word plus 64" on the N64, so overlap scoring liked it and the
    console agreed. Nothing but the distinctive-word rule rejects this.
    """
    assert pick_match("Goemon 64", [cand("Doom 64", "nintendo-64")], N64) is None


def test_a_shared_number_alone_is_not_a_match():
    assert distinctive(tokens("Goemon 64")) == {"goemon"}
    assert not (distinctive(tokens("Goemon 64")) & distinctive(tokens("Doom 64")))


def test_a_shared_word_is_not_enough_when_the_specific_one_is_missing():
    """Legend of Dragoon matched The Legend of Zelda on the word "legend".

    "legend" is a real identifying word, so no stopword list rejects this. What
    does is that the candidate drops "dragoon" and brings "zelda" instead: it
    neither accounts for the query nor stays silent about anything else.
    """
    assert pick_match(
        "Legend of Dragoon", [cand("The Legend of Zelda", "nintendo-64")], N64,
    ) is None


def test_a_variant_name_that_adds_nothing_is_kept():
    """Jak & Daxter Trilogy is Jak and Daxter Collection, scoring only 0.67.

    It drops a word rather than introducing one, which is what tells it apart
    from the two rejections above at exactly the same similarity score.
    """
    picked = pick_match(
        "Jak & Daxter Trilogy", [cand("Jak and Daxter Collection")], set(),
    )
    assert picked is not None
    assert picked[0]["name"] == "Jak and Daxter Collection"


# ── The sequel rule ──────────────────────────────────────────────────────────

def test_sequel_does_not_outrank_the_original():
    """Bomberman 64 matched "Bomberman 64: The Second Attack" - its sequel.

    The query sits inside that name, so plain containment scored it top. The
    added distinctive words are what tell the two apart.
    """
    picked = pick_match("Bomberman 64", [
        cand("Bomberman 64: The Second Attack", "nintendo-64"),
        cand("Bomberman 64", "nintendo-64"),
    ], N64)
    assert picked is not None
    assert picked[0]["name"] == "Bomberman 64"


def test_containment_with_extra_identifying_words_scores_below_exact():
    assert name_score("Bomberman 64", "Bomberman 64") == 1.0
    assert (name_score("Bomberman 64", "Bomberman 64: The Second Attack")
            < name_score("Bomberman 64", "Bomberman 64"))


def test_noise_words_in_a_longer_name_are_free():
    """A year or an edition marker is not a different game."""
    assert name_score("Star Fox 64", "Star Fox 64 (1997)") >= 0.75
    assert name_score("Mario Kart 64", "Mario Kart 64 Remastered Edition") >= 0.75


# ── The console as a tie-breaker ─────────────────────────────────────────────

def test_console_carries_a_half_match():
    """Banjo 64 is Banjo-Kazooie. Half the words match; the console decides."""
    picked = pick_match("Banjo 64", [cand("Banjo-Kazooie", "nintendo-64")], N64)
    assert picked is not None
    assert picked[0]["name"] == "Banjo-Kazooie"
    assert picked[1] == "low"


def test_a_strong_name_needs_no_console():
    picked = pick_match("Chameleon Twist", [cand("Chameleon Twist")], set())
    assert picked is not None
    assert picked[1] == "high"


def test_weak_name_without_console_agreement_is_refused():
    """SM64 Co-op DX is a mod - there is no original, so no match is correct."""
    assert pick_match(
        "SM64 Co-op DX", [cand("CO-OP: Decrypted", "pc")], N64,
    ) is None


def test_console_ranks_above_a_same_scoring_stranger():
    picked = pick_match("Perfect Dark", [
        cand("Perfect Dark", "xbox360"),
        cand("Perfect Dark", "nintendo-64"),
    ], N64)
    assert picked is not None
    assert "nintendo-64" in picked[0]["platforms"]


# ── Category to platform ─────────────────────────────────────────────────────

@pytest.mark.parametrize("category,expected", [
    ("N64 Ports",            {"nintendo-64"}),
    ("Nintendo 64",          {"nintendo-64"}),
    ("Gamecube / Wii Ports", {"gamecube"}),
    ("PlayStation Ports",    {"playstation1", "playstation2", "psp"}),
])
def test_category_maps_to_console(category, expected):
    assert platforms_for_category(category) == expected


def test_unknown_category_constrains_nothing():
    """"Other Ports" is a real heading. No constraint is the honest answer."""
    assert platforms_for_category("Other Ports") == set()
    assert platforms_for_category(None) == set()


def test_no_candidates_is_not_a_match():
    assert pick_match("Anything", [], N64) is None


# ── A same-named stranger on the wrong console ───────────────────────────────

def test_exact_name_on_the_wrong_console_is_only_low():
    """Dinosaur Planet matched a same-named mobile game, not Rare's N64 one.

    The name is exact, which scored it high, but it is not on the N64 the port
    came from. That mismatch is the one cue something is off, so it caps the
    confidence at low instead of letting a wrong match look certain.
    """
    picked = pick_match(
        "Dinosaur Planet", [cand("Dinosaur Planet", "android", "ios")], N64,
    )
    assert picked is not None
    assert picked[1] == "low"


def test_the_right_console_variant_outranks_the_same_named_stranger():
    """"Dinosaur Planet (N64)" is the one to pick over a bare "Dinosaur Planet".

    The "(N64)" tag must not read as an identifying word the query lacks, or the
    stranger wins on an exact-name tie. With the tag treated as noise, the
    console-matching entry wins and keeps high confidence.
    """
    picked = pick_match("Dinosaur Planet", [
        cand("Dinosaur Planet", "android"),
        cand("Dinosaur Planet (N64)", "nintendo-64"),
    ], N64)
    assert picked is not None
    assert "nintendo-64" in picked[0]["platforms"]
    assert picked[1] == "high"


def test_unconstrained_category_keeps_a_strong_name_high():
    """"Other Ports" sets no console, so a strong name is not second-guessed."""
    picked = pick_match("Sonic Unleashed", [cand("Sonic Unleashed", "xbox360")], set())
    assert picked is not None
    assert picked[1] == "high"
