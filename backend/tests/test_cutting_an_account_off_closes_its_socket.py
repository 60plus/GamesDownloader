"""A socket is authenticated once, at the handshake, and never again.

`connect` reads the account from the database, checks `enabled`, checks the
token's jti against the revocation list, and works out which rooms the socket
joins. After that there is nothing: no re-validation per packet, no expiry
check, no reaction to the account being switched off. The stream of
`download:progress`, `upload:url_*`, `romsource:download_*`, `chd:convert` and
`roms:scan_progress` goes on for the life of the connection.

`drop_sockets_for_user` was written for exactly this and wired into one place:
the branch that changes a role or a permission. Every stronger action left the
socket alone -

  switching an account off        `PATCH /users/{id}` with enabled: false
  resetting a password as admin   the code beside it calls this "the
                                  containment action ... the account is
                                  believed compromised"
  forcing a logout                `DELETE /settings/security/sessions/user/{id}`
  logging out everywhere myself   the same route without a user id
  the self-service reset link     `POST /auth/reset-password`
  deleting the account            `DELETE /users/{id}`

- so an intruder who simply does not close the tab keeps watching after the
  password has been changed and every session revoked. Every HTTP request they
  make answers 401; the socket answers with the owner's activity.

THE OTHER HALF is the opposite mistake. The one branch that did drop compared
the whole `permissions` dictionary, and that dictionary also holds the upload
quota - so raising somebody's quota by a gigabyte kicked their socket, froze the
progress bar they were watching and left them to reconnect. What decides room
membership is the effective scope set, so that is what is compared.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _source(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


def _function_at(body: str, at: int) -> str:
    """The def that encloses this offset, to the end of the file if it is last.

    The first version stopped at the next `def` or decorator and had no answer
    for the last function in a file - which is exactly where `delete_user`
    sits, so the test crashed instead of reporting anything.
    """
    start = body.rindex("\nasync def ", 0, at)
    nxt = re.search(r"\n(async def |def |@)", body[at:])
    return body[start:at + nxt.start()] if nxt else body[start:]


REVOKERS = [
    "endpoints/users.py",
    "endpoints/auth.py",
    "endpoints/settings/sessions_router.py",
]


@pytest.mark.parametrize("rel", REVOKERS)
def test_every_route_that_revokes_sessions_also_drops_sockets(rel):
    """Written against the CALL rather than against a list of route names, so a
    fifth way of cutting an account off inherits the rule instead of quietly
    being the next hole."""
    body = _source(rel)
    at = 0
    found = 0
    while True:
        at = body.find("revoke_all_for_user(", at)
        if at < 0:
            break
        found += 1
        fn = _function_at(body, at)
        # The CALL, not the name. `from handler.socket_handler import
        # drop_sockets_for_user` carries the same letters, so matching the bare
        # name passed over a route that imports the helper and never uses it -
        # measured, by deleting the call and watching this stay green.
        assert "drop_sockets_for_user(" in fn, (
            f"{rel}: trasa uniewaznia sesje i zostawia otwarte gniazdo - "
            "kazde zadanie HTTP dostanie 401, a gniazdo dalej nadaje"
        )
        at += 1
    assert found, f"{rel}: test nie znajduje juz zadnego uniewaznienia sesji"


def test_deleting_an_account_drops_its_socket():
    """No session to revoke here - the row simply goes - and the socket outlives
    the account entirely."""
    body = _source("endpoints/users.py")
    at = body.index("async def delete_user(")
    assert "drop_sockets_for_user(" in _function_at(body, at), (
        "konto skasowane, a jego gniazdo dalej siedzi w pokojach user: i role:"
    )


# ── What counts as a change worth a fresh handshake ──────────────────────────

def _account(role, perms=None, enabled=True):
    from types import SimpleNamespace
    return SimpleNamespace(role=role, permissions=perms, enabled=enabled)


def test_switching_an_account_off_needs_one():
    from models.user import Role

    from endpoints.users import access_changed

    assert access_changed(_account(Role.USER), _account(Role.USER, enabled=False)), (
        "wylaczenie konta nie zamyka gniazda, wiec 'wylaczone' nie obowiazuje "
        "na kanale, ktory nadaje"
    )


def test_taking_a_permission_away_needs_one():
    from models.user import Role

    from endpoints.users import access_changed

    assert access_changed(
        _account(Role.UPLOADER),
        _account(Role.UPLOADER, {"upload": False}),
    )


def test_changing_the_role_needs_one():
    from models.user import Role

    from endpoints.users import access_changed

    assert access_changed(_account(Role.USER), _account(Role.UPLOADER))


def test_changing_only_the_quota_does_not():
    """The upload quota lives in the same `permissions` dictionary and decides
    nothing about rooms. Comparing the whole dictionary meant raising somebody's
    allowance kicked them off and froze the bar they were watching."""
    from models.user import Role

    from endpoints.users import access_changed

    assert not access_changed(
        _account(Role.UPLOADER, {"upload_quota_bytes": 1024}),
        _account(Role.UPLOADER, {"upload_quota_bytes": 2048}),
    ), "podniesienie limitu zrzuca gniazdo, chociaz nie zmienia zadnego pokoju"


def test_a_permission_set_to_what_it_already_was_does_not():
    from models.user import Role

    from endpoints.users import access_changed

    assert not access_changed(
        _account(Role.UPLOADER, {"upload": True}),
        _account(Role.UPLOADER, {"upload": True, "upload_quota_bytes": 5}),
    )


def test_an_account_that_was_already_off_does_not():
    """Saving the form again on a disabled account is not a new cut-off."""
    from models.user import Role

    from endpoints.users import access_changed

    assert not access_changed(
        _account(Role.USER, enabled=False), _account(Role.USER, enabled=False))
