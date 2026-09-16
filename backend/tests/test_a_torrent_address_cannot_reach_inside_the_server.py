"""A torrent address is not a way into the server's own network.

Finding #18 of the 1.0.34 pre-release audit, confirmed by a skeptic.

In 1.0.33 only an administrator could add a torrent by address. 1.0.34 opened the
route to uploaders, and the address still went to Transmission verbatim. The
daemon fetches an http(s) address itself, through libcurl, which follows redirects
and resolves names on its own - so an uploader could make the server request
`127.0.0.1` inside the container, `169.254.169.254`, or anything a redirect pointed
at. And the refusal now quotes what the daemon's fetch got back, which turns a
blind request into a probe of what answers.

The project's own policy already says what is allowed (`utils/net_guard.py`):
loopback, link-local, reserved and unspecified addresses are always refused, and a
host on the home network is allowed for uploads, so a self-hoster can pull from
their own NAS. The upload-by-address route follows that policy on every redirect
hop. This route now does the same: an http(s) address is fetched HERE, through
that guard, capped at the size a .torrent can be, and only its bytes reach
Transmission. A magnet link carries no address to fetch and goes to the daemon as
it did.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

#: A public address written as a literal, so the guard can judge it without DNS -
#: the test container may have no resolver at all.
PUBLIC = "http://93.184.216.34/a.torrent"


@pytest.fixture
def adding(monkeypatch):
    from endpoints.torrent import torrent_router as R

    state = SimpleNamespace(by_url=[], by_bytes=[], created=[])

    async def _by_url(url, _dir):
        state.by_url.append(url)
        return {"id": 5, "hashString": "abc"}, None

    async def _by_bytes(content, _dir):
        state.by_bytes.append(content)
        return {"id": 6, "hashString": "def"}, None

    monkeypatch.setattr(R.transmission_handler, "add_torrent_url", _by_url)
    monkeypatch.setattr(R.transmission_handler, "add_torrent_metainfo", _by_bytes,
                        raising=False)

    async def _create(request, title, os_name, download_dir, **kwargs):
        state.created.append(kwargs)
        return SimpleNamespace(
            id=1, title=title, os=os_name, status="downloading", percent_done=0.0,
            total_size=0, rate_download=0, eta=-1, error_msg=None, game_id=None,
            library=None, created_by="gdtest", created_at=None, completed_at=None)

    monkeypatch.setattr(R, "_create_torrent_download", _create)
    monkeypatch.setattr(R.os, "makedirs", lambda *_a, **_k: None)

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=3, username="gdtest"),
        scopes={Scope.LIBRARY_UPLOAD}))
    return SimpleNamespace(R=R, state=state, request=request)


def _body(R, url):
    return R.AddTorrentByUrl(url=url, title="Gra")


def _serving(handler):
    return httpx.MockTransport(handler)


# ── What the server must not be made to fetch ────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:9091/transmission/rpc",
    "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/x.torrent",
    "http://0.0.0.0:8080/x.torrent",
])
async def test_an_address_inside_the_server_is_refused_before_anything_fetches_it(adding, url):
    with pytest.raises(HTTPException) as refusal:
        await adding.R.add_torrent_url(adding.request, _body(adding.R, url))

    assert refusal.value.status_code == 400, (
        "adres wewnatrz serwera nie zostal odrzucony"
    )
    assert adding.state.by_url == [], (
        "adres poszedl do Transmission, ktore samo go pobiera i idzie za przekierowaniami"
    )
    assert adding.state.by_bytes == [] and adding.state.created == []


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "/downloads/another-account/game.torrent",
    "ftp://93.184.216.34/a.torrent",
    "gopher://127.0.0.1:6379/_INFO",
])
async def test_an_address_that_is_neither_a_magnet_nor_the_web_is_refused(adding, monkeypatch, url):
    """Transmission reads a local path given as `filename` too.

    Refused by name, before anything tries to fetch it. The first version of
    this test passed with the scheme check deleted, because the fetch then
    failed on its own - a refusal that rests on the HTTP client's list of
    schemes, and says "could not download" about a path on the server's disk."""
    fetched: list[str] = []

    async def _fetch(u):
        fetched.append(u)
        return b"torrent bytes"

    monkeypatch.setattr(adding.R, "_fetch_torrent_file", _fetch)

    with pytest.raises(HTTPException) as refusal:
        await adding.R.add_torrent_url(adding.request, _body(adding.R, url))

    assert refusal.value.status_code == 400
    assert refusal.value.refusal.get("code") == "url_unsupported"
    assert fetched == [], f"{url!r} poszedl do pobrania zamiast zostac odrzucony"
    assert adding.state.by_url == [] and adding.state.by_bytes == []


@pytest.mark.asyncio
async def test_a_web_address_is_fetched_here_and_only_its_bytes_reach_transmission(adding, monkeypatch):
    async def _fetched(url):
        assert url == PUBLIC
        return b"torrent bytes"

    monkeypatch.setattr(adding.R, "_fetch_torrent_file", _fetched, raising=False)

    await adding.R.add_torrent_url(adding.request, _body(adding.R, PUBLIC))

    assert adding.state.by_url == [], (
        "adres http nadal idzie do Transmission, a nie przez straznika w aplikacji"
    )
    assert adding.state.by_bytes == [b"torrent bytes"]


@pytest.mark.asyncio
async def test_a_public_address_that_redirects_inside_is_refused_on_the_redirect():
    """The reason a check before the request is not enough: the first hop is
    public, and the second is not."""
    from endpoints.torrent import torrent_router as R

    def handler(request):
        if request.url.host == "93.184.216.34":
            return httpx.Response(302, headers={
                "Location": "http://127.0.0.1:9091/transmission/rpc"})
        return httpx.Response(200, content=b"SHOULD NEVER BE READ")

    with pytest.raises(HTTPException) as refusal:
        await R._fetch_torrent_file(PUBLIC, transport=_serving(handler))

    assert refusal.value.status_code == 400, (
        "przekierowanie do adresu wewnetrznego nie zostalo zatrzymane"
    )


@pytest.mark.asyncio
async def test_an_address_serving_more_than_a_torrent_file_can_be_is_refused():
    from endpoints.torrent import torrent_router as R

    big = b"x" * (R._MAX_TORRENT_BYTES + 1)

    with pytest.raises(HTTPException) as refusal:
        await R._fetch_torrent_file(
            PUBLIC, transport=_serving(lambda _r: httpx.Response(200, content=big)))

    assert refusal.value.status_code == 413


@pytest.mark.asyncio
async def test_an_address_that_trickles_is_cut_off_rather_than_held_open(monkeypatch):
    """A limit per read is not a limit on the fetch: its clock starts again with
    every chunk, so a server sending a byte just inside it holds the request - and
    the uploader's dialog - open for as long as it likes. The whole fetch has one
    deadline."""
    import asyncio

    from endpoints.torrent import torrent_router as R

    monkeypatch.setattr(R, "_FETCH_DEADLINE_SECONDS", 0.3, raising=False)

    class _Trickle(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(40):
                await asyncio.sleep(0.05)
                yield b"x"

    loop = asyncio.get_running_loop()
    started = loop.time()
    with pytest.raises(HTTPException) as refusal:
        await R._fetch_torrent_file(
            PUBLIC, transport=_serving(lambda _r: httpx.Response(200, stream=_Trickle())))

    assert refusal.value.status_code == 502
    assert loop.time() - started < 1.5, "pobieranie adresu nie ma jednego terminu"


@pytest.mark.asyncio
async def test_a_failed_fetch_says_so_without_quoting_what_came_back():
    """What the other end answered is exactly what makes a probe out of this."""
    from endpoints.torrent import torrent_router as R

    def handler(_request):
        return httpx.Response(404, content=b"router admin page secret")

    with pytest.raises(HTTPException) as refusal:
        await R._fetch_torrent_file(PUBLIC, transport=_serving(handler))

    said = str(refusal.value.detail)
    assert refusal.value.status_code == 502
    assert "secret" not in said and "404" not in said, (
        "odmowa cytuje, co odpowiedzial adres - to zamienia ja w sonde"
    )


# ── What must keep working ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_magnet_link_still_goes_to_transmission_as_it_is(adding):
    """THE LEGAL CASE for the routing: a magnet is a hash, not an address."""
    magnet = "magnet:?xt=urn:btih:abc"

    await adding.R.add_torrent_url(adding.request, _body(adding.R, magnet))

    assert adding.state.by_url == [magnet]


@pytest.mark.asyncio
async def test_a_torrent_on_a_nas_in_the_home_network_can_still_be_added():
    """THE LEGAL CASE for the guard: the same policy the upload-by-address route
    has always had - a self-hoster pulls from their own network."""
    from endpoints.torrent import torrent_router as R

    got = await R._fetch_torrent_file(
        "http://192.168.0.10/a.torrent",
        transport=_serving(lambda _r: httpx.Response(200, content=b"from the nas")))

    assert got == b"from the nas"


# ── What the daemon's failures say ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_unreachable_daemon_is_not_reported_in_the_exceptions_own_words(monkeypatch):
    from handler.torrent import transmission_handler as TH

    class _Boom:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            raise RuntimeError("connect to 127.0.0.1:9091 failed reading /opt/secret")

        async def __aexit__(self, *_a):
            return False

    async def _no_auth():
        return None

    monkeypatch.setattr(TH.httpx, "AsyncClient", _Boom)
    monkeypatch.setattr(TH.transmission_handler, "_get_auth", _no_auth)

    value, reason = await TH.transmission_handler._rpc(
        "torrent-add", {}, with_reason=True)

    assert value is None
    assert reason, "odmowa nic nie mowi"
    assert "127.0.0.1" not in reason and "/opt/secret" not in reason, (
        "powod odmowy niesie tekst wyjatku, ktory trafia do okna uploadera"
    )
