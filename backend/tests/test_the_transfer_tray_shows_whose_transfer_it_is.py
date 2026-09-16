"""Two halves of one complaint: the owner cannot see their own transfer, and
the administrator cannot see whose it is.

THE ROUTE WAS ALREADY RIGHT. `GET /rom-sources/downloads` asks for the three
permissions a ROM-source download needs and, unless the caller holds
ROMS_WRITE, narrows the answer to the jobs that caller started. An uploader may
see their own; that was settled when the route was written.

THE SCREEN NEVER SHOWED IT. The tray hangs behind `v-if="isAdmin"` in four
places - the two core layouts and both themes - so the account the route was
narrowed FOR never had a tray at all. It also made the previous acceptance test
unmeasurable: the question was whether cutting an account off stops its live
view, and that account had no live view to lose.

AND IT SAID NOTHING ABOUT WHOSE. `as_dict()` carries no owner, so an
administrator - the one caller who sees everybody's jobs - saw them all as if
they were their own. The name is added by the ROUTE and only for the caller who
sees other people's: an uploader gets nothing but their own jobs, so handing
them other account names would be a leak for no purpose.
"""

from __future__ import annotations

import io
import pathlib
from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"

ME, SOMEBODY_ELSE = 3, 1
NEEDED = {Scope.LIBRARY_UPLOAD, Scope.STORE_ACCESS, Scope.ROMS_READ}


def _request(scopes, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


@pytest.fixture
def jobs(monkeypatch):
    from endpoints.roms import rom_sources_router as R

    all_jobs = [
        {"id": 1, "filename": "Army Men.chd", "fs_slug": "psx", "status": "downloading"},
        {"id": 2, "filename": "Cudze.chd", "fs_slug": "psx", "status": "downloading"},
    ]
    owners = {1: ME, 2: SOMEBODY_ELSE}

    def _list_jobs():
        return [dict(j) for j in all_jobs]

    def _own_jobs(user_id):
        return [SimpleNamespace(id=i) for i, o in owners.items() if o == user_id]

    async def _names(ids):
        return {ME: "gdtest", SOMEBODY_ELSE: "60plus"}

    monkeypatch.setattr(R.rsh, "list_jobs", _list_jobs)
    monkeypatch.setattr(R.rsh, "own_jobs", _own_jobs)
    monkeypatch.setattr(R.rsh, "job_owners", lambda: dict(owners), raising=False)
    monkeypatch.setattr(R, "_resolve_usernames", _names, raising=False)
    return R


@pytest.mark.asyncio
async def test_an_uploader_sees_their_own_and_only_their_own(jobs):
    R = jobs
    out = await R.list_downloads(_request(NEEDED))
    assert [j["id"] for j in out["jobs"]] == [1]


@pytest.mark.asyncio
async def test_an_uploader_is_not_told_other_account_names(jobs):
    """They only ever get their own jobs, so a name here would be a leak that
    buys nothing."""
    R = jobs
    out = await R.list_downloads(_request(NEEDED))
    assert all("started_by" not in j for j in out["jobs"]), (
        "lista podaje nazwy kont komus, kto i tak widzi wylacznie swoje zadania"
    )


@pytest.mark.asyncio
async def test_an_administrator_is_told_whose_each_one_is(jobs):
    R = jobs
    out = await R.list_downloads(_request(NEEDED | {Scope.ROMS_WRITE}, user_id=SOMEBODY_ELSE))

    by_id = {j["id"]: j for j in out["jobs"]}
    assert set(by_id) == {1, 2}, "admin przestal widziec cudze transfery"
    assert by_id[1].get("started_by") == "gdtest", (
        "admin widzi cudze pobrania nieodroznialne od swoich - tak jakby to on "
        "je sciagal"
    )
    assert by_id[2].get("started_by") == "60plus"


# ── The screen ───────────────────────────────────────────────────────────────

def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


LAYOUTS = [
    FRONTEND / "src" / "layouts" / "ClassicLayout.vue",
    FRONTEND / "src" / "layouts" / "ModernLayout.vue",
]


def test_the_auth_store_answers_the_question_once():
    """`canUseStores` next door exists for exactly this reason, and says so:
    three skins each kept their own copy of a permission rule and disagreed."""
    body = _read(FRONTEND / "src" / "stores" / "auth.ts")
    assert "canSeeTransfers" in body, (
        "kazdy uklad pyta o to po swojemu, wiec beda sie rozjezdzac"
    )


def test_both_screen_rules_come_from_one_reading_of_the_permissions():
    """`canUseStores` had the same gap and it was found while writing the one
    beside it: it reads the ROLE and the store chip, and never the upload chip -
    though `_PERM_REVOKE` takes LIBRARY_UPLOAD away without touching the role,
    and every store route requires it. So an account with the upload chip
    switched off was shown a storefront that refuses it.

    Both rules are now the same reading of the same three permissions, which is
    the only way they cannot drift apart again."""
    body = _read(FRONTEND / "src" / "stores" / "auth.ts")
    assert "function heldScopes" in body, (
        "kazda regula czyta uprawnienia po swojemu"
    )
    for name in ("canUseStores", "canSeeTransfers"):
        at = body.index(f"const {name}")
        rule = body[at:at + 400]
        assert "heldScopes" in rule, f"{name} nie korzysta ze wspolnego odczytu"


def test_the_reading_mirrors_the_servers_overrides():
    """Each permission checked for BOTH readings the server's tables give it,
    by the exact expression.

    Asked as "do these words appear" first, and a mutation walked straight
    through it: deleting the revoke half of the upload rule left every one of
    those words still in the function, because the other permissions supply
    them. The third time this round that a test of mine matched letters instead
    of an instruction.
    """
    body = _read(FRONTEND / "src" / "stores" / "auth.ts")
    at = body.index("function heldScopes")
    rule = body[at:body.index("\n  }", at)]

    # `_PERM_GRANT` hands a scope to a role that lacks it; `_PERM_REVOKE` takes
    # one away without touching the role. A rule that reads only one of those
    # is wrong in one direction, silently.
    for expression in (
        "p.upload === true",           # granted to a lower role
        "p.upload !== false",          # not revoked from one that has it
        "p.store_access === true",     # granted, which is the ordinary way
        "p.store_access !== false",    # not revoked from an admin
        "p.access_emulation !== false",
    ):
        assert expression in rule, (
            f"odczyt uprawnien nie zawiera `{expression}`, wiec rozjedzie sie "
            "z trasa w jedna strone i nikt tego nie zobaczy"
        )


@pytest.mark.parametrize("path", LAYOUTS, ids=lambda p: p.name)
def test_the_layout_gates_the_tray_on_the_permission(path):
    body = _read(path)
    at = body.index("<DownloadManager")
    tag = body[at:body.index(">", at)]
    assert "isAdmin" not in tag, (
        f"{path.name} chowa tacke za rola, wiec konto, dla ktorego trasa zostala "
        "zawezona, nie ma jej wcale"
    )
    assert "canSeeTransfers" in tag


def test_the_tray_renders_the_owner_when_it_is_given_one():
    body = _read(FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue")
    assert "started_by" in body, (
        "tacka nie pokazuje, czyj jest transfer, nawet gdy serwer to podaje"
    )


def test_a_live_event_does_not_erase_the_name_it_just_drew():
    """REPORTED BY THE OWNER, as an administrator watching somebody else's ROM
    download: "nie widze kto pobiera ... widac ze sie cos pobiera ale nie kto".

    The route was right and the fetch was right. `fetchRomJobs` reads the list
    over HTTP and puts `started_by` on the row. Then the socket arrives: every
    branch of `handleRomSource` REBUILDS that row from the event payload, which
    carries no owner, so the field is dropped. A live download emits about one
    event a second, so the name was on screen for the moment after a reload and
    gone by the next tick - which reads as "it never shows it".

    Asserted per ASSIGNMENT rather than once over the file: the bug was not a
    missing feature, it was three assignments out of four forgetting a field
    that the fourth sets. One more branch added later would do it again.
    """
    body = _read(FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue")

    at = body.index("function handleRomSource")
    handler = body[at:body.index("\nfunction ", at + 10)]

    assignments = handler.count("romItems[id] = {")
    assert assignments >= 3, (
        f"ksztalt tej funkcji sie zmienil, test moze juz nie badac tego, co mysli "
        f"({assignments} przypisan)"
    )
    assert handler.count("started_by") >= assignments, (
        "ktoras z galezi zdarzenia przebudowuje wiersz bez nazwy konta, wiec "
        "pierwszy takt postepu ja kasuje i administrator widzi transfer bez "
        "wlasciciela"
    )


def test_the_torrent_section_does_not_have_the_same_hole():
    """The same trap, in the section written the day after: its live branch also
    rebuilds the row, and the owner has to survive that."""
    body = _read(FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue")

    at = body.index("function handleTorrent")
    handler = body[at:body.index("\nfunction ", at + 10)]
    assert "created_by: cur?.created_by" in handler, (
        "zdarzenie o postepie torrenta gubi nazwe konta tak samo, jak gubila ja "
        "sekcja ROM-ow"
    )


# The two themes carry their own copy of this layout and are gated the same way,
# in `vapor_build/gd3-vapor/VaporLayout.vue` and
# `nh_build/neon-horizon/NeonHorizonLayout.vue`. There is no test for them here
# on purpose: both are sibling checkouts, absent from the image and from CI, so
# a test pointed at them would skip every time - the same reasoning as at the
# end of test_a_refused_upload_says_so_on_screen.py.
