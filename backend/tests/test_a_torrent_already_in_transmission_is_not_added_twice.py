"""A torrent that is already in Transmission is not added a second time.

Found by the adversarial round on the 1.0.34 fixes. Transmission answers an add
for a torrent it already holds with `torrent-duplicate` - the existing torrent's
id and hash - and both the client and the add routes took that for success. So a
second row was written for the caller, pointing at a transfer that belonged to
somebody else: another account's download, or a library file being seeded.

That row was never a harmless copy. The monitor weighs it against the CALLER's
quota, and a refusal removes the torrent together with its data - the other
account's partial download, or the library folder the seed shares. Its buttons
act on the same torrent. And when it completes, whichever row the monitor reaches
first files the download as that row's game.

So the client says when an add was a duplicate, and the routes refuse it with a
reason the dialog can translate. The daemon was not changed by the attempt, so
there is nothing to undo.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

HELD = {"id": 7, "name": "Somebody's game", "hashString": "abc123"}


# ── The client says which answer it got ──────────────────────────────────────

@pytest.mark.asyncio
async def test_the_client_says_when_the_daemon_already_had_it(monkeypatch):
    from handler.torrent import transmission_handler as TH

    async def _rpc(_method, _args, with_reason=False):
        return {"torrent-duplicate": dict(HELD)}, None

    monkeypatch.setattr(TH.transmission_handler, "_rpc", _rpc)

    by_link, _ = await TH.transmission_handler.add_torrent_url("magnet:?xt=urn:btih:abc123", "/tmp/x")
    by_bytes, _ = await TH.transmission_handler.add_torrent_metainfo(b"d4:infod4:name1:xee", "/tmp/x")

    assert by_link and by_link.get("duplicate") is True, (
        "odpowiedz `torrent-duplicate` wyglada jak zwykle dodanie"
    )
    assert by_bytes and by_bytes.get("duplicate") is True
    assert by_link.get("hashString") == "abc123", "zgubiono, CO demon juz trzymal"


@pytest.mark.asyncio
async def test_a_torrent_the_daemon_really_added_is_not_called_a_duplicate(monkeypatch):
    from handler.torrent import transmission_handler as TH

    async def _rpc(_method, _args, with_reason=False):
        return {"torrent-added": dict(HELD)}, None

    monkeypatch.setattr(TH.transmission_handler, "_rpc", _rpc)

    info, _ = await TH.transmission_handler.add_torrent_url("magnet:?xt=urn:btih:abc123", "/tmp/x")

    assert info and not info.get("duplicate")


# ── The routes refuse it ─────────────────────────────────────────────────────

class _Upload:
    """Enough of UploadFile for the route: a name and a stream."""

    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data
        self._at = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._at
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


@pytest.fixture
def adding(monkeypatch, tmp_path):
    from endpoints.torrent import torrent_router as R

    state = SimpleNamespace(created=[], answer=dict(HELD, duplicate=True))

    async def _daemon(*_a, **_k):
        return dict(state.answer), None

    for name in ("add_torrent_url", "add_torrent_metainfo", "add_torrent_file"):
        monkeypatch.setattr(R.transmission_handler, name, _daemon)

    async def _create(request, title, os_name, download_dir, **kwargs):
        state.created.append(kwargs)
        return SimpleNamespace(
            id=1, title=title, os=os_name, status="downloading", percent_done=0.0,
            total_size=0, rate_download=0, eta=-1, error_msg=None, game_id=None,
            library=None, created_by="gdtest", created_at=None, completed_at=None)

    async def _fits(*_a, **_k):
        return None

    async def _fetched(_url):
        return b"torrent bytes"

    # Nothing in the database holds it, and the daemon's copy is not in the
    # download area: the one duplicate that is still refused as it always was.
    # What a holder changes is test_a_torrent_somebody_already_has_says_where_it_is.
    async def _nothing_holds_it(_hash):
        return None

    async def _seeded_elsewhere(_ref):
        return dict(HELD, downloadDir="/data/games/CUSTOM/Somebody's game")

    async def _never_removed(*_a, **_k):
        raise AssertionError("duplikat zdjal torrent z demona")

    # Which shelf may be named is its own test
    # (test_a_switched_off_games_library_takes_no_new_games); here the Games
    # library is simply open.
    async def _shelf_open(*_a, **_k):
        return None

    monkeypatch.setattr(R, "_assert_shelf_allowed", _shelf_open)
    monkeypatch.setattr(R, "_what_holds", _nothing_holds_it)
    monkeypatch.setattr(R.transmission_handler, "get_torrent", _seeded_elsewhere)
    monkeypatch.setattr(R.transmission_handler, "remove_torrent", _never_removed)
    monkeypatch.setattr(R, "_create_torrent_download", _create)
    monkeypatch.setattr(R, "_refuse_if_it_does_not_fit", _fits)
    monkeypatch.setattr(R, "_fetch_torrent_file", _fetched)
    monkeypatch.setattr(R, "_SEED_DIR", str(tmp_path))
    monkeypatch.setattr(R, "_TORRENT_DIR", str(tmp_path))

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=3, username="gdtest"),
        scopes={Scope.LIBRARY_UPLOAD}))
    return SimpleNamespace(R=R, state=state, request=request)


async def _by_address(env, url):
    return await env.R.add_torrent_url(env.request, env.R.AddTorrentByUrl(url=url, title="Gra"))


async def _by_file(env):
    return await env.R.add_torrent_file(
        env.request, title="Gra", target_os="windows", library=None,
        file=_Upload("gra.torrent", b"torrent bytes"))


def _refused_as_already_there(refusal):
    return (refusal.value.status_code == 409
            and getattr(refusal.value, "refusal", {}).get("code") == "already_added")


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["magnet:?xt=urn:btih:abc123", "http://93.184.216.34/a.torrent"])
async def test_an_address_for_a_torrent_already_there_is_refused_and_writes_no_row(adding, url):
    with pytest.raises(HTTPException) as refusal:
        await _by_address(adding, url)

    assert _refused_as_already_there(refusal), (
        f"dodanie torrenta, ktory demon juz trzyma, nie zostalo odrzucone: {refusal.value.detail!r}"
    )
    assert adding.state.created == [], (
        "zapisano drugi wiersz na cudzy transfer - limit, przyciski i rejestracja "
        "gry dzialalyby na nim w imieniu tego konta"
    )


@pytest.mark.asyncio
async def test_a_torrent_file_already_there_is_refused_and_writes_no_row(adding):
    with pytest.raises(HTTPException) as refusal:
        await _by_file(adding)

    assert _refused_as_already_there(refusal)
    assert adding.state.created == []


@pytest.mark.asyncio
async def test_a_torrent_the_daemon_did_not_have_is_still_added(adding):
    """THE LEGAL CASE: every ordinary add."""
    adding.state.answer = dict(HELD)

    await _by_address(adding, "magnet:?xt=urn:btih:abc123")
    await _by_file(adding)

    assert len(adding.state.created) == 2
    assert all(c.get("info_hash") == "abc123" for c in adding.state.created)
