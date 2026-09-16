"""Whoever put the bytes there is who they are charged to.

When an upload lands on a path that already has a row, the row is the only
thing that says how big the file is - `used_bytes` is a SUM over
`LibraryFile.size_bytes` in SQL, never a counter and never measured from the
disk. So the size is written, and that much was right.

The owner was left alone, on the grounds that a catalogue entry fetched a second
time reuses the first account's GAME on purpose. True of the game, and not of
the file: `published_by` on a file row means "who brought these bytes in", and
after the replacement that is the account that just replaced them.

Leaving it made one account's allowance move by another account's action. The
store route hardcodes `overwrite=True` and needs only LIBRARY_UPLOAD and
STORE_ACCESS, so B fetching the same catalogue entry rewrote the size on A's
row: A's bar jumped, A could be pushed over the limit and refused their next
upload for something they did not do, and B - who actually put the bytes on the
disk - was charged nothing and could repeat it.

Not closed with a refusal. Two accounts fetching the same catalogue entry is
what that route is for, and refusing the second would break it. The row simply
follows the bytes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

A, B = 3, 8
REL = "custom/gra/build.zip"


@pytest.fixture
def finalize(tmp_path, monkeypatch):
    from endpoints.library import upload_router as R
    from handler.clamav import clamav_handler as clam

    prior = SimpleNamespace(id=1, file_path=REL, size_bytes=1_000,
                            published_by=A, is_available=False)
    writes: list = []

    async def _files(_game_id):
        return [prior]

    async def _update(row, data):
        writes.append(dict(data))
        for k, v in data.items():
            setattr(row, k, v)
        return row

    async def _clam_off():
        return False

    monkeypatch.setattr(R._lib, "get_files_for_game", _files)
    monkeypatch.setattr(R._lib, "update_file", _update)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", _clam_off)
    monkeypatch.setattr(R, "_rel_from_abs", lambda _p: REL)

    dest = tmp_path / "build.zip"
    dest.write_bytes(b"x")

    async def _run(owner_id):
        return await R._finalize_upload(
            game_id=42, dest_path=dest, filename="build.zip", size=40_000,
            os_platform="windows", file_type="game", language=None,
            version=None, actor="u", owner_id=owner_id,
        )

    return _run, prior, writes


@pytest.mark.asyncio
async def test_the_row_follows_the_bytes(finalize):
    run, prior, _writes = finalize

    out = await run(B)

    assert out["duplicate"] is True
    assert prior.size_bytes == 40_000, "rozmiar nadal klamie o tym, co lezy na dysku"
    assert prior.published_by == B, (
        "limit konta A rusza sie od czynnosci konta B: A moze zostac wypchniete "
        "ponad przydzial i dostac 413 za cos, czego nie zrobilo, a B, ktore "
        "naprawde przyniosло bajty, nie jest obciazone niczym"
    )


@pytest.mark.asyncio
async def test_replacing_my_own_file_changes_nothing_about_who_owns_it(finalize):
    run, prior, _writes = finalize

    await run(A)

    assert prior.published_by == A
    assert prior.size_bytes == 40_000


@pytest.mark.asyncio
async def test_a_path_with_no_account_behind_it_leaves_the_owner_alone(finalize):
    """Some ways in carry no account at all - a server-side fetch, a job with no
    caller. Writing None over a real owner would take the bytes off everybody's
    total and make the sum smaller than the disk."""
    run, prior, _writes = finalize

    await run(None)

    assert prior.published_by == A
    assert prior.size_bytes == 40_000


@pytest.mark.asyncio
async def test_the_file_is_marked_present_again(finalize):
    """The half that was already right: a row marked unavailable and then
    replaced on disk is available again."""
    run, prior, _writes = finalize

    await run(B)

    assert prior.is_available is True
