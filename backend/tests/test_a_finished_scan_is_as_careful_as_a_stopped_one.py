"""The same care on the way out, whichever door the scan leaves by.

`scan_roms_path` has four exits and they had four different levels of caution.

STOPPED, the rarest, is the careful one: rows this run created are taken back,
except any somebody has already played or saved against, and the present flags
are restored.

FINISHED, the common one, adopts renamed files - it pairs a row that went
missing with a row this run created, moves the file fields across and DELETES
the new row. `rom_saves`, `rom_save_states` and `rom_plays` hang off that row by
`ondelete="CASCADE"`, and a scan of a large library runs for many minutes with
every new row visible and playable as soon as it lands. So a player who started
a game during the scan and saved has that save deleted at the end of it, with
nothing said. The guard for exactly this was written for the Stop path and given
one call site.

FAILED restores the flags and takes back the rows a rename would have absorbed -
and only those. A new row with no donor is one the next scan finds again, so
removing it buys nothing and costs a full re-read of everything the run had got
through.

CANCELLED, which is the same door as FAILED in Python and a different thing
entirely in fact: the process is going away on a five second clock, so this exit
does the one bulk update and nothing else.

WHAT THIS FILE READS. Slices of source, which catch only what somebody thought
of - so the behaviour is tested by running the scan in
test_a_scan_that_falls_over_keeps_its_work.py, and these assertions are here to
say that the two exits keep asking ONE rule rather than growing a second copy of
it. That is the thing a behavioural test cannot see.
"""

from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _source() -> str:
    return io.open(BACKEND / "handler" / "filesystem" / "rom_scanner.py",
                   encoding="utf-8").read()


def _scan() -> str:
    source = _source()
    at = source.index("async def scan_roms_path(")
    return source[at:]


def _stopped_branch(body: str) -> str:
    """The Stop branch ALONE.

    `if scan_cancelled():` appears three times in this function - twice inside
    the walk, checking whether to give up early - and indexing on the first one
    swept in 282 lines instead of 40. It happened to contain the right words, so
    the assertions passed for the wrong reason and would have gone on passing if
    the branch itself had been emptied.
    """
    end = body.index("# The walk finished")
    at = body.rindex("if scan_cancelled():", 0, end)
    return body[at:end]


def _failed_branch(body: str) -> str:
    at = body.index("except BaseException:")
    return body[at:body.index("\n        raise", at)]


def _cancelled_branch(body: str) -> str:
    at = body.index("except asyncio.CancelledError:")
    return body[at:body.index("\n        raise", at)]


def _rule() -> str:
    """The one place that decides which created rows a rename would take."""
    source = _source()
    at = source.index("async def _renames_this_run(")
    return source[at:source.index("\nasync def ", at + 10)]


def test_the_stopped_exit_is_still_the_careful_one():
    """The reference the other two are measured against. If this ever stops
    asking, the assertions below are copying the wrong thing."""
    branch = _stopped_branch(_scan())
    assert "ids_with_player_data" in branch
    assert "restore_present" in branch


def test_the_stopped_branch_is_the_branch_and_not_the_whole_walk():
    """A guard on the slice above, because it was wrong once and nothing said
    so: the marker matched a line inside the walk and the test read 282 lines
    of it."""
    branch = _stopped_branch(_scan())
    assert 'stats["cancelled"] = True' in branch, "wycinek nie jest galezia Stop"
    assert len(branch.splitlines()) < 60, (
        f"wycinek ma {len(branch.splitlines())} wierszy - to nie jest sama "
        "galez Stop, tylko kawal spaceru razem z nia"
    )


def _merge() -> str:
    source = _source()
    at = source.index("async def _merge_renamed(")
    return source[at:source.index("\n# ", at)]


def test_the_finished_exit_does_not_adopt_over_somebody_s_save():
    """Adoption deletes the row it adopted FROM, and the cascade takes the
    player's data with it. It is carried across first, and if that cannot be
    done without choosing between two memory cards, the merge is skipped."""
    merge = _merge()
    assert "move_player_data(" in merge, (
        "scalenie kasuje wiersz z danymi gracza bez przeniesienia ich - zapis "
        "zrobiony w trakcie skanu znika przez kaskade"
    )
    assert "continue" in merge, (
        "odmowa przeniesienia nie zatrzymuje scalenia, wiec karta pamieci ginie"
    )


def test_the_question_of_who_played_is_not_part_of_finding_the_rename():
    """The condition `adopt_renamed_files` is built on is "the only candidate on
    either side". Thinning the list handed to it turned a key with two arrivals
    into a key with one as soon as somebody had played one of them, and the pair
    it was written to refuse was then accepted. So the matching does not know
    about player data at all."""
    assert "ids_with_player_data" not in _rule(), (
        "dopasowanie zna dane gracza, wiec warunek jednoznacznosci liczy "
        "innych kandydatow niz ma liczyc"
    )


def test_both_exits_ask_the_same_rule():
    """The point of the helper. Two spellings of "which rows would a rename have
    taken" is how the failed exit came to delete everything the run had made."""
    body = _scan()
    assert "_renames_this_run(" in _failed_branch(body), (
        "wyjscie przez wyjatek liczy sobie samo, ktore wiersze zabrac"
    )
    finished = body[body.index("# ── Renames"):body.index("except asyncio.CancelledError:")]
    assert "_renames_this_run(" in finished, (
        "wyjscie zwykle liczy sobie samo, ktore wiersze scalic"
    )


def test_the_failed_exit_takes_back_what_a_rename_would_have_absorbed():
    """Same reasoning as the Stop path, written down there: a new row left
    behind is a row no future scan will create again, so the old row holding the
    artwork, the saves and the play history is missing for good."""
    branch = _failed_branch(_scan())
    assert "restore_present" in branch, "wyjatek przestal przywracac flagi"
    assert "rom_handler.delete(" in branch, (
        "wyjatek w srodku spaceru zostawia wiersze, ktore adopcja by wchlonela, "
        "wiec kazda przemianowana gra jest na polce dwa razy i zaden pozniejszy "
        "skan juz ich nie sparuje"
    )


def test_the_failed_exit_restores_the_flags_first():
    """The cheaper and more important half. If the row cleanup throws, the
    library must still not be left with everything marked missing."""
    branch = _failed_branch(_scan())
    assert branch.index("restore_present") < branch.index("rom_handler.delete("), (
        "flagi przywracane po kasowaniu wierszy - jesli kasowanie padnie, "
        "biblioteka zostaje z polowa pozycji oznaczonych jako brakujace"
    )


def test_shutting_down_does_the_cheap_half_only():
    """A container stop cancels the task and gives it a few seconds. A delete per
    row, each in its own transaction, does not finish - so the run gets undone
    partway, which is the one outcome nobody chose."""
    branch = _cancelled_branch(_scan())
    assert "restore_present" in branch, (
        "zamykanie nie przywraca flag, wiec biblioteka wstaje ciemna"
    )
    assert "rom_handler.delete(" not in branch and "_renames_this_run(" not in branch, (
        "przy zamykaniu serwera skaner zabiera sie za prace, na ktora nie ma "
        "czasu, i cofa bieg CZESCIOWO"
    )


def test_the_cancelled_clause_comes_first():
    """`except BaseException` catches CancelledError too, so the cheap clause is
    only reached if it is written above it."""
    body = _scan()
    assert body.index("except asyncio.CancelledError:") < body.index("except BaseException:")


def test_the_failure_still_reaches_the_caller():
    """Restored and re-raised. A scan that never works has to look like one that
    failed, not like one that keeps finding nothing."""
    body = _scan()
    at = body.index("except BaseException:")
    assert "raise" in body[at:at + 2600]


def test_the_guard_is_asked_once_per_exit_and_not_per_row():
    """It is one query over a list. Called inside a loop it would be one round
    trip per row, on the exits that already have thousands of them."""
    body = _scan()
    asked = [at for at in range(len(body))
             if body.startswith("ids_with_player_data", at)]
    assert len(asked) >= 2, (
        "wyjscia przestaly pytac o dane gracza"
    )
    for at in asked:
        line_start = body.rindex("\n", 0, at)
        prefix = body[line_start + 1:at]
        indent = len(prefix) - len(prefix.lstrip())
        assert indent <= 16, "pytanie o dane gracza wolane w petli po wierszach"
