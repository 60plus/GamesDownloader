"""Which shelf a torrent may be filed onto.

Both queue routes take a library slug and keep it on the row. When the transfer
lands, `_resolve_target_library` turns that slug into a folder and a membership
and files the game there, checking two things: that the library is
folder-backed, and that it has a storage folder. Not whether the account that
asked may reach it.

So an uploader could name any shelf on the server, including a restricted one
they are not on, and a game would appear in it hours later when the transfer
finished.

REFUSED AT QUEUE TIME rather than at landing, and the difference matters both
ways. A refusal at queue time is an answer to somebody who is standing there and
can pick a different shelf. A check at landing would arrive hours later, with
the files already fetched, and would strand a legitimate transfer whenever an
administrator changed access while it ran - and the case that actually motivates
re-checking, an account losing its upload right mid-transfer, is answered
already: the transfer changes hands, and the administrator it moves to can reach
everything.

`user_can_access` is the registry's own rule, the same one the library screens
ask. Nothing new is invented here.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope


@pytest.fixture
def queueing(monkeypatch):
    from endpoints.torrent import torrent_router as R
    from handler.database import library_registry_handler as REG

    state = SimpleNamespace(allowed=False, asked=[], created=[])

    lib = SimpleNamespace(id=9, slug="prywatna", kind="custom_lib",
                          storage_folder="PRYWATNA")

    async def _by_slug(slug, **_k):
        return lib if slug == "prywatna" else None

    async def _can(user, target, **_k):
        state.asked.append(getattr(target, "slug", None))
        return state.allowed

    monkeypatch.setattr(REG.library_registry_handler, "get_by_slug", _by_slug)
    monkeypatch.setattr(REG.library_registry_handler, "user_can_access", _can)

    async def _create(request, title, os_name, download_dir, **kwargs):
        state.created.append({"title": title, **kwargs})
        return SimpleNamespace(
            id=1, title=title, os=os_name, status="downloading", percent_done=0.0,
            total_size=0, rate_download=0, eta=-1, error_msg=None, game_id=None,
            library=kwargs.get("library"), created_by="gdtest", created_at=None,
            completed_at=None)

    monkeypatch.setattr(R, "_create_torrent_download", _create)

    async def _add(_url, _dir):
        # (info, powod odmowy demona) - klient oddaje oba, zeby okno moglo
        # pokazac to, co demon naprawde powiedzial.
        return {"id": 5, "hashString": "abc"}, None

    monkeypatch.setattr(R.transmission_handler, "add_torrent_url", _add)
    monkeypatch.setattr(R.os, "makedirs", lambda *_a, **_k: None)

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=3, username="gdtest"),
        scopes={Scope.LIBRARY_UPLOAD}))
    return SimpleNamespace(module=R, request=request, state=state)


def _body(module, library):
    return module.AddTorrentByUrl(url="magnet:?xt=1", title="Gra", library=library)


@pytest.mark.asyncio
async def test_a_shelf_this_account_cannot_reach_is_refused(queueing):
    with pytest.raises(HTTPException) as refusal:
        await queueing.module.add_torrent_url(
            queueing.request, _body(queueing.module, "prywatna"))

    assert refusal.value.status_code in (403, 404)
    assert queueing.state.created == [], (
        "transfer zostal zakolejkowany na polke, ktorej to konto nie widzi - "
        "gra pojawi sie tam za kilka godzin"
    )
    assert queueing.state.asked == ["prywatna"], "nikt nie zapytal o dostep"


@pytest.mark.asyncio
async def test_a_shelf_this_account_may_use_goes_through(queueing):
    """THE LEGAL CASE. Filing a torrent into a custom library is a feature, and
    this is a gate: it can refuse somebody entitled as easily as somebody not."""
    queueing.state.allowed = True

    await queueing.module.add_torrent_url(
        queueing.request, _body(queueing.module, "prywatna"))

    assert queueing.state.created and queueing.state.created[0]["library"] == "prywatna"


@pytest.mark.asyncio
async def test_the_default_shelf_needs_no_permission(queueing):
    """THE COMMON CASE, and the one that would break most loudly. No library
    named means the built-in Games library, which is where nearly every torrent
    goes and which nobody is on an allowlist for."""
    for slug in (None, "", "games"):
        queueing.state.created.clear()
        queueing.state.asked.clear()

        await queueing.module.add_torrent_url(
            queueing.request, _body(queueing.module, slug))

        assert queueing.state.created, f"domyslna polka odmowiona dla {slug!r}"
        assert queueing.state.asked == [], (
            f"pytanie o dostep zadane dla domyslnej polki ({slug!r})"
        )


@pytest.mark.asyncio
async def test_a_shelf_that_does_not_exist_is_refused_too(queueing):
    """A slug nobody recognises used to be accepted and quietly turned into the
    default at landing time, hours later. Saying so now is the same courtesy as
    every other refusal in this router."""
    queueing.state.allowed = True

    with pytest.raises(HTTPException) as refusal:
        await queueing.module.add_torrent_url(
            queueing.request, _body(queueing.module, "nie-ma-takiej"))

    assert refusal.value.status_code in (403, 404)
    assert queueing.state.created == []
