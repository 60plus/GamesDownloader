"""A torrent counts against the account that queued it.

The owner set the rule with an example: "jesli ma uploadu limit 50gb i wgra
torrent 40gb, uploaduje 2x5 to skonczy mu sie limit". Forty plus five plus five
is fifty, so the torrent is not merely allowed through, it is the part that
fills the quota up.

It did not. The quota is a sum over the games an account owns, and a game
registered by the torrent monitor was created with no owner at all, so it
counted against nobody. There are three ways into the library and the quota was
enforced on two of them.

That gap was asleep while only an admin could queue a torrent, which is where
it had sat since the quota was written. The same day the owner moved that route
down to the uploader, on the grounds that an uploader adds games and a torrent
is a game arriving, it stopped being theoretical: the role the quota exists for
gained the one way in that ignored it.

So the account is recorded on the download when it is queued, and the monitor
stamps it on the game it registers. Nothing else changes: the delete rule and
the quota both read the owner, and they now find one.

What is deliberately not here is a refusal at the moment of queueing. A magnet
link does not know its own size until the metadata arrives, so there is nothing
to weigh a limit against at that point, and refusing on a guess would be worse
than counting honestly afterwards. The owner's example does not need it either:
the torrent lands, it counts, and the uploads after it are what run out of room.
"""
from __future__ import annotations

import io
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROUTER = BACKEND / "endpoints" / "torrent" / "torrent_router.py"
MONITOR = BACKEND / "handler" / "torrent" / "seed_monitor.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


def _registration() -> str:
    """`_auto_register_game`, whole. A fixed window of characters from its
    start stopped reaching the end of it as soon as a comment was added above
    the lines being checked, and would have passed for the wrong reason the day
    the next function started inside it."""
    source = _source(MONITOR)
    start = source.index("async def _auto_register_game")
    end = re.search(r"\n(async )?def ", source[start + 10:])
    return source[start:start + 10 + end.start()] if end else source[start:]


def test_the_download_records_the_account_and_not_only_a_name():
    """created_by is a username, kept for display. A username cannot be summed
    against a quota, and it stops pointing anywhere if the account is renamed."""
    from models.torrent_download import TorrentDownload

    assert "created_by_id" in TorrentDownload.__table__.columns


def test_both_ways_of_queueing_record_who_asked():
    """A magnet link and an uploaded .torrent file are the same act, and they
    already share the one function that writes the row. Recording the account
    there rather than at each call site is what stops the gap coming back
    through whichever of the two a later change forgets."""
    source = _source(ROUTER)
    assert source.count("await _create_torrent_download(") == 2, (
        "trasy kolejkujace przestaly dzielic jedno miejsce zapisu"
    )
    start = source.index("async def _create_torrent_download")
    body = source[start:source.index("\n\n\n", start)]
    assert "created_by_id=" in body, "wspolny zapis nie odnotowuje konta"


def test_the_registered_game_belongs_to_whoever_queued_it():
    body = _registration()
    assert "published_by=None" not in body, "gra z torrenta nadal jest niczyja"
    assert "created_by_id" in body, "monitor nie przepisuje konta na gre"


def test_the_uploader_is_recorded_too():
    """Same as every other way in: owner and uploader start out equal, and only
    a claim parts them."""
    assert "uploaded_by" in _registration()


def test_the_column_is_created_and_filled_in_on_an_existing_install():
    """Torrents queued before the column exist only as a username, and that is
    enough to find the account. Without the backfill every torrent already in
    the library would stay uncounted forever."""
    source = _source(BACKEND / "main.py")
    assert '"torrent_downloads", "created_by_id"' in source
    assert "torrent_downloads" in source and "u.username" in source


def test_games_already_here_from_a_torrent_are_given_their_owner_too():
    """"A torrent counts" is not a rule about the future. The download row
    still names the game it became, so the games already in the library can be
    joined back to whoever asked for them.

    Only where nothing is recorded yet, so it can fill a blank and never
    overwrite an answer, including one an admin arrived at by claiming.
    """
    source = _source(BACKEND / "main.py")
    start = source.index("torrent_downloads.created_by_id")
    window = source[start - 2000:start + 2000]
    assert "library_games" in window and "game_id" in window, (
        "gry z torrenta sprzed kolumny nie dostaja wlasciciela"
    )
    assert "IS NULL" in window, "uzupelnienie moze nadpisac istniejacego wlasciciela"


def test_a_torrent_was_never_excluded_from_the_sum_itself():
    """The rule about what counts leaves out GOG publications and nothing else,
    so the fix is about the owner being missing rather than about the sum.

    Read from the rule itself rather than the whole module: the module talks
    about torrents now, because a transfer still on its way counts against the
    quota too (test_a_transfer_still_on_its_way_counts_against_the_quota)."""
    source = _source(BACKEND / "handler" / "library" / "quota.py")
    at = source.index("def _counts_towards_quota(")
    rule = source[at:at + re.search(r"\n(async )?def ", source[at + 1:]).start() + 1]
    assert '!= "gog"' in rule
    assert "torrent" not in rule
