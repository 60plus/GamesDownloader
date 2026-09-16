"""Writing over a file has to change what that file costs.

The quota is a sum of `LibraryFile.size_bytes` in SQL - never a stored counter,
never measured from disk. So the row is the only thing that says how big a file
is, and `_finalize_upload` returned from its duplicate branch without touching
it: the bytes on disk changed, the number the quota reads did not.

That makes the limit a suggestion. Write one byte under a name, then send the
real file with overwrite: the disk grows, `used_bytes` does not, and the next
request starts from the same full allowance. Repeat.

The same branch is on the store's path - a catalogue entry downloaded a second
time reuses the first game and passes `overwrite=True` - so this is not an
exotic corner.

Two things have to move together, which is why they are tested together: the row
learns the new size, and the room calculation stops counting the OLD size against
the person replacing it. Without the second half the fix would refuse a perfectly
legal replacement by an account whose quota is nearly filled by the very file
being replaced.
"""

from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _fn(name: str) -> str:
    source = io.open(BACKEND / "endpoints" / "library" / "upload_router.py",
                     encoding="utf-8").read()
    at = source.index(name)
    nxt = source.find("\nasync def ", at + 10)
    return source[at:nxt if nxt != -1 else len(source)]


def test_the_quota_reads_the_row_and_nothing_else():
    """The premise. If the sum ever started measuring the disk, this whole file
    would be about nothing."""
    source = io.open(BACKEND / "handler" / "library" / "quota.py",
                     encoding="utf-8").read()
    at = source.index("async def used_bytes(")
    body = source[at:source.index("\ndef _counts_towards_quota", at)]
    assert "LibraryFile.size_bytes" in body
    assert "getsize" not in body and "stat(" not in body, (
        "suma czyta dysk, wiec wiersz nie jest juz jedynym zrodlem prawdy"
    )


def test_replacing_a_file_writes_the_new_size_onto_the_row():
    body = _fn("async def _finalize_upload(")
    # The BRANCH, found by the marker it returns, not by the first mention of
    # the word - the function's own docstring says "duplicate guard" long before
    # the code does, so slicing on that read the wrong half of the function.
    at = body.index('"duplicate": True')
    branch = body[:at]
    assert "update_file" in branch or "size_bytes=size" in branch, (
        "galaz duplikatu wychodzi bez zapisu, wiec `size_bytes` zostaje stary "
        "i limit liczy sie ze starej wartosci - nadpisywac mozna bez konca"
    )


def test_replacing_a_file_charges_it_to_whoever_replaced_it():
    """This test used to assert the opposite, and its reason did not hold.

    It said leaving `published_by` alone stopped a second fetch "quietly
    handing them the first account's file". Measured: nothing is handed over.
    `LibraryFile.published_by` is read in exactly two places - the quota sum
    (`coalesce(file.published_by, game.published_by)`) and `release_files_of` -
    and no permission anywhere reads it. Who may edit, download or delete is
    decided from the GAME's owner, in `handler/library/ownership.py`.

    So the column is a billing attribution, and leaving it made one account's
    allowance move by another account's action: B fetching the same catalogue
    entry rewrote the size on A's row, A's bar jumped, and B was charged
    nothing. The row follows the bytes now.

    The second reason - "an administrator's claim must not be undone" - is about
    the GAME, which this branch still does not touch. A claim moves the game; a
    later re-download says who brought the current bytes, which is what the
    column means.
    """
    body = _fn("async def _finalize_upload(")
    at = body.index('"duplicate": True')
    branch = body[:at]
    assert '"published_by"' in branch, (
        "galaz duplikatu zostawia wlasciciela pliku, wiec limit konta A rusza "
        "sie od czynnosci konta B"
    )
    assert "if owner_id:" in branch, (
        "wlasciciel przepisywany takze wtedy, gdy nie ma kogo obciazyc - None "
        "nad prawdziwym wlascicielem zdejmuje bajty ze wszystkich sum"
    )


def test_the_game_itself_still_does_not_change_hands():
    """The half of the old reason that IS true: a re-download must not move the
    game, and with it the right to edit or delete it."""
    body = _fn("async def _finalize_upload(")
    at = body.index('"duplicate": True')
    branch = body[:at]
    assert "_lib.update(game" not in branch and "game.published_by" not in branch, (
        "galaz duplikatu rusza wlasciciela GRY, wiec ponowne pobranie oddaje "
        "cudza gre pobierajacemu i cofa przejecie przez admina"
    )


def test_the_room_left_gives_back_what_is_being_replaced():
    body = _fn("async def upload_game_file(")
    assert "room_left" in body, "test szuka nie tam"
    assert "prior" in body or "replacing" in body, (
        "miejsce liczone bez oddania starego rozmiaru - konto, ktorego limit "
        "wypelnia wlasnie ten plik, nie moze go podmienic"
    )


def test_the_store_path_still_asks_for_an_overwrite():
    """The reason this branch is reached at all in ordinary use."""
    source = io.open(BACKEND / "handler" / "library" / "catalog_sync_handler.py",
                     encoding="utf-8").read()
    assert "overwrite=True" in source, (
        "sciezka sklepu przestala nadpisywac - sprawdz, czy ta naprawa jest "
        "jeszcze o czymkolwiek"
    )
