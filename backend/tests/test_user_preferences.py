"""One preferences dictionary, several owners - none may erase the others.

`User.preferences` is shared: the theme store writes appearance keys, the ROM
settings write whether battery saves sync themselves, and anything added later
will want its own corner too. Each caller sends only the keys it owns.

The endpoint used to store the body verbatim, so whichever screen saved last
wiped every key it did not know about. That is not a theoretical race: the theme
store saves on a debounce after any appearance change, so turning the save-sync
on and then picking a different skin would have quietly turned it back off.

These pin the merge, and pin that a caller can still change its own values.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from endpoints import users as users_module


class _FakeUser:
    def __init__(self, preferences):
        self.preferences = preferences


def _request_for(user):
    return types.SimpleNamespace(state=types.SimpleNamespace(user=user))


def _save(monkeypatch, stored, body):
    """Run the endpoint against a captured update, return what it would write."""
    captured = {}

    async def _fake_update(user, values):
        captured.update(values)
        user.preferences = values.get("preferences", user.preferences)

    monkeypatch.setattr(users_module._users_db, "update", _fake_update)
    user = _FakeUser(stored)
    asyncio.run(users_module.save_preferences(_request_for(user), body))
    return captured["preferences"]


def test_a_screen_saving_its_own_keys_leaves_the_others_alone(monkeypatch):
    out = _save(
        monkeypatch,
        stored={"theme": "vapor", "skin": "vp-steam"},
        body={"autoSyncSaves": False},
    )
    assert out == {"theme": "vapor", "skin": "vp-steam", "autoSyncSaves": False}


def test_the_theme_store_saving_does_not_wipe_the_save_sync_setting(monkeypatch):
    # The exact sequence that would have lost the setting before the merge:
    # switch sync off, then change a theme key.
    stored = _save(monkeypatch, stored={}, body={"autoSyncSaves": False})
    out = _save(monkeypatch, stored=stored, body={"theme": "neon-horizon", "heroBlur": 4})
    assert out["autoSyncSaves"] is False
    assert out["theme"] == "neon-horizon"


def test_a_caller_can_still_change_a_value_it_already_set(monkeypatch):
    out = _save(
        monkeypatch,
        stored={"autoSyncSaves": False, "theme": "vapor"},
        body={"autoSyncSaves": True},
    )
    assert out["autoSyncSaves"] is True
    assert out["theme"] == "vapor"


def test_an_empty_body_changes_nothing(monkeypatch):
    stored = {"theme": "vapor", "autoSyncSaves": True}
    assert _save(monkeypatch, stored=stored, body={}) == stored


def test_a_user_with_no_preferences_yet_starts_from_the_body(monkeypatch):
    assert _save(monkeypatch, stored=None, body={"autoSyncSaves": True}) == {"autoSyncSaves": True}


def test_it_refuses_without_a_user():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        asyncio.run(users_module.save_preferences(_request_for(None), {"autoSyncSaves": True}))
    assert e.value.status_code == 401
