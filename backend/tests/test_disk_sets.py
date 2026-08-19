"""Which files are disks of one game.

Get this wrong in one direction and a three-disk RPG shows up as three games,
none of which can be finished. Get it wrong in the other and two unrelated
titles merge into one entry whose second "disk" is a different game. Both have
happened here, so both directions are tested.
"""
from __future__ import annotations

from utils.disk_sets import group_disks, sort_key


def _numbers(names):
    return {name: n for name, (_title, n) in group_disks(names).items()}


# ── Named disks ───────────────────────────────────────────────────────────────

def test_the_usual_marker():
    names = [
        "Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT]",
        "Legion (1996)(Gobi)(PL)(Disk 2 of 2)[cr WT]",
    ]
    got = group_disks(names)
    assert sorted(n for _t, n in got.values()) == [1, 2]
    assert len({t for t, _n in got.values()}) == 1   # one game, not two


def test_the_marker_in_its_other_spellings():
    for first, second in (
        ("Game [Disk 1]", "Game [Disk 2]"),
        ("Game Disc 1", "Game Disc 2"),
        ("Game_Disk1", "Game_Disk2"),
        ("Game (Disk 1 z 2)", "Game (Disk 2 z 2)"),
    ):
        assert len(_numbers([first, second])) == 2, first


def test_a_lettered_marker_counts_as_a_number():
    got = _numbers(["Game (Disk A)", "Game (Disk B)"])
    assert sorted(got.values()) == [1, 2]


def test_a_bare_number_is_not_a_disk_number():
    # Otherwise "1943" becomes disk 1943 of "The Battle of Midway".
    assert not group_disks(["1943 - The Battle of Midway", "1942"])


def test_a_file_called_only_disk_1_says_nothing():
    assert not group_disks(["Disk 1", "Disk 2"])


# ── Lettered disks, the convention with no marker at all ──────────────────────

def test_letters_at_the_end_are_disks():
    # How Silmarils shipped, and the reason this was written: three tiles in
    # the library for one game.
    got = _numbers([
        "Ishar 2 (Silmarils) A",
        "Ishar 2 (Silmarils) B",
        "Ishar 2 (Silmarils) C",
    ])
    assert sorted(got.values()) == [1, 2, 3]
    assert got["Ishar 2 (Silmarils) A"] == 1


def test_lettered_disks_share_one_title():
    titles = {t for t, _ in group_disks(["Foo A", "Foo B"]).values()}
    assert titles == {"foo"}


def test_letters_with_a_gap_are_left_alone():
    # "Ultima I" and "Ultima V" are two games, not disks 9 and 22 of one.
    assert not group_disks(["Ultima I", "Ultima V"])


def test_a_lone_letter_is_not_a_set():
    assert not group_disks(["Ishar 2 (Silmarils) A", "Dungeon Master"])


def test_a_letter_glued_to_the_title_is_not_a_disk():
    # No separator, no marker: this is just a name.
    assert not group_disks(["GameA", "GameB"])


def test_named_disks_win_over_a_bare_letter_beside_them():
    got = group_disks(["Game (Disk 1)", "Game (Disk 2)", "Game A", "Game B"])
    assert set(got) == {"Game (Disk 1)", "Game (Disk 2)"}


# ── Names that must not be mistaken for disks ─────────────────────────────────

def test_the_word_disk_inside_another_word_is_not_a_marker():
    assert not group_disks(["Diskette Manager", "Diskette Copier"])
    assert not group_disks(["Disco Fever", "Disco Fever 2"])


def test_the_real_amiga_library_groups_only_what_it_should():
    got = group_disks([
        "Dungeon Master v3.60 (FTL + Psygnosis)",
        "Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT]",
        "Legion (1996)(Gobi)(PL)(Disk 2 of 2)[cr WT]",
        "Ishar 2 (Silmarils) A",
        "Ishar 2 (Silmarils) B",
        "Ishar 2 (Silmarils) C",
        "Mentor_v1.1_Pl",
    ])
    assert "Dungeon Master v3.60 (FTL + Psygnosis)" not in got
    assert "Mentor_v1.1_Pl" not in got
    assert len({t for t, _ in got.values()}) == 2
    assert len(got) == 5


# ── Ordering ──────────────────────────────────────────────────────────────────

def test_disk_10_sorts_after_disk_2():
    names = ["Game (Disk 10)", "Game (Disk 2)", "Game (Disk 1)"]
    assert sorted(names, key=sort_key) == [
        "Game (Disk 1)", "Game (Disk 2)", "Game (Disk 10)",
    ]
