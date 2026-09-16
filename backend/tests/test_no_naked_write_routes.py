"""No route that writes is left without a permission, anywhere.

`protected_route` refuses an anonymous caller whatever else it is told, but the
scope check is written `if scopes:`, so a route that declares none asks only
that somebody be signed in. On an instance that allows registration, that is
close enough to asking nothing.

Three had ended up that way, and one of them mattered: the security alert
settings. Any account could read the address the alarms are sent to and, worse,
post the five switches back with all of them off, silencing failed-login, new-
IP, new-account, new-admin and brute-force warnings, or point them somewhere
else. No credential was exposed. The alarm was.

There is a sister test for the library routes, written the same week, but it
only walks five routers. This one walks every router the application mounts,
because the gap was in none of the five and the next one will be somewhere
nobody thought to name either.

Read-only routes are deliberately out of scope here: several are public by
design, and deciding which is a different argument than this one.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ENDPOINTS = pathlib.Path(__file__).resolve().parent.parent / "endpoints"

WRITING = {"post", "put", "patch", "delete"}

# A route may declare nothing only for a reason written down here. The list is
# the point: it turns "nobody noticed" into "somebody decided".
ALLOWED_WITHOUT_SCOPES: dict[str, str] = {
    "POST /config (sessions_router.py)":
        "Refuses a non-admin inside the handler, by role, because the answer "
        "is the same for every caller and needs no scope of its own.",
    "DELETE /{session_id} (sessions_router.py)":
        "Admin, or the owner of that session. That is an ownership question, "
        "which scopes cannot express, so the handler asks it.",
    "DELETE / (sessions_router.py)":
        "Signs the caller out of their own sessions everywhere, so being "
        "signed in is the whole of the permission it needs.",
    "DELETE /user/{user_id} (sessions_router.py)":
        "Refuses a non-admin inside the handler, by role, before it touches "
        "the target account.",
}

# The decorator takes its permissions either way round, and the two spellings
# sit side by side in this codebase:
#     @protected_route(router.post, "/x", scopes=[Scope.A])
#     @protected_route(router.patch, "/x", [Scope.A])
# Reading only the first spelling reports the second as unguarded, which is a
# false alarm about exactly the thing this file exists to raise a true one about.
DECORATOR = re.compile(
    r'@protected_route\(\s*[A-Za-z_][\w.]*\.(\w+)\s*,\s*"([^"]*)"\s*(?:,(?P<rest>[^)]*))?\)',
    re.S,
)


def _declares_scopes(rest: str | None) -> bool:
    """Whether anything after the path names a permission, however it is passed.

    `scopes=None` counts as declaring nothing, which is what /me does on
    purpose: it is about the caller, so being signed in is the whole test.
    """
    if not rest:
        return False
    if "scopes=None" in rest.replace(" ", ""):
        return False
    return "scopes" in rest or "Scope" in rest


def naked_write_routes() -> list[str]:
    out = []
    for path in sorted(ENDPOINTS.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for match in DECORATOR.finditer(source):
            verb, route = match.group(1).lower(), match.group(2)
            if verb not in WRITING or _declares_scopes(match.group("rest")):
                continue
            out.append(f"{verb.upper()} {route or '/'} ({path.name})")
    return out


def test_the_scan_found_the_routers():
    """A guard on the guard: a rename that made the pattern match nothing would
    leave every assertion below vacuously true."""
    files = list(ENDPOINTS.rglob("*.py"))
    assert len(files) > 10, f"znalazlem tylko {len(files)} plikow z trasami"
    hits = sum(len(DECORATOR.findall(p.read_text(encoding="utf-8")))
               for p in files)
    assert hits > 100, f"wzorzec dopasowal tylko {hits} tras, cos jest nie tak"


def test_nothing_that_writes_asks_only_for_a_login():
    offenders = [r for r in naked_write_routes() if r not in ALLOWED_WITHOUT_SCOPES]
    assert offenders == [], (
        "trasy zapisujace bez zadnego uprawnienia, czyli otwarte dla kazdego "
        f"zalogowanego: {offenders}"
    )


def test_the_allowance_list_says_why():
    for route, reason in ALLOWED_WITHOUT_SCOPES.items():
        assert len(reason) > 20, f"{route}: wpis bez wyjasnienia"


@pytest.mark.parametrize("route", sorted(ALLOWED_WITHOUT_SCOPES))
def test_the_allowance_list_does_not_name_routes_that_are_gone(route):
    """A stale allowance forgives a route that may come back under the same
    name meaning something else."""
    assert route in naked_write_routes(), f"{route} juz nie istnieje w tej postaci"
