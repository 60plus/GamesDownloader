"""A file that was refused has to be reported as refused.

The upload route answers with two lists: `saved` and `rejected`, the second one
carrying a reason per file. Both screens read the first and threw the second
away, so every refusal was rendered as "0 ROM(s) uploaded successfully!" - a
sentence that says nothing and reads as success.

It is not a corner case. It fires for the ordinary refusals this release
added or tightened: a file that is not a ROM, a name that belongs to another
account, a subchannel file too large to be one, and anything the virus scanner
stops. Two of those turned up within minutes of somebody testing by hand, and
in both the person on the screen could not tell what had happened.

Read as text: this project has no frontend test runner, so what is checked here
is narrow - that both surfaces read `rejected`, that they say it through ONE
helper rather than two spellings of it, that every reason the server can send
has something to say, and that every catalogue can say it.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

SURFACES = [
    FRONTEND / "src" / "layouts" / "ClassicLayout.vue",
    FRONTEND / "src" / "views" / "emulation" / "EmulationHome.vue",
]
HELPER = FRONTEND / "src" / "lib" / "uploadResult.ts"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


def _server_reasons() -> set[str]:
    """Every `action` the upload route can put in `rejected`.

    Read off the route rather than listed here, so a new refusal cannot be
    added on the server and quietly render as nothing on the screen.
    """
    source = io.open(BACKEND / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()
    body = source[source.index("async def upload_roms("):]
    return set(re.findall(r'"action":\s*"([a-z_]+)"', body))


def test_the_route_really_reports_reasons():
    """A guard on the test. If `rejected` ever stops carrying a reason, the
    assertions below are about nothing."""
    reasons = _server_reasons()
    assert "already_here" in reasons and "extension_not_recognised" in reasons, (
        f"trasa wgrywania nie odsyla juz powodow odmowy: {reasons}"
    )


@pytest.mark.parametrize("path", SURFACES, ids=lambda p: p.name)
def test_the_screen_stops_counting_only_what_landed(path):
    """Asked as "does it still read `saved.length`", not as "does the word
    `rejected` appear anywhere".

    The first version of this test asked the second question and ClassicLayout
    passed it on a COMMENT that happens to use the word - the letters-instead-of
    -instruction trap this whole audit round keeps turning up, hit here again.
    """
    body = _read(path)
    assert "data.saved?.length" not in body, (
        f"{path.name} nadal liczy tylko to, co wyladowalo, wiec kazda odmowa "
        "wyglada jak '0 ROM(s) uploaded successfully!' - zdanie, ktore nic nie "
        "znaczy"
    )
    assert "describeUpload(data" in body, (
        f"{path.name} nie oddaje calej odpowiedzi do opisania"
    )


@pytest.mark.parametrize("path", SURFACES, ids=lambda p: p.name)
def test_both_screens_say_it_the_same_way(path):
    """One helper, not two spellings. Two copies of a rule is how the read and
    the write of a game's shelves came to disagree earlier in this same round."""
    body = _read(path)
    assert "describeUpload" in body, (
        f"{path.name} sklada komunikat po swojemu"
    )


def test_every_reason_the_server_can_send_has_something_to_say():
    helper = _read(HELPER)
    missing = [r for r in _server_reasons() if r not in helper]
    assert not missing, (
        "serwer odsyla powody, o ktorych ekran nie ma nic do powiedzenia: "
        + "; ".join(sorted(missing))
    )


def test_a_threat_is_named_even_though_its_action_is_not_fixed():
    """ClamAV's own verdict decides that one - quarantined, deleted, reported -
    so it cannot be matched on the action. The presence of a threat is what
    says which case it is."""
    helper = _read(HELPER)
    assert "threat" in helper, (
        "plik zatrzymany przez skaner antywirusowy nie ma jak byc opisany"
    )


def test_nothing_uploaded_does_not_read_as_success():
    helper = _read(HELPER)
    assert "uploaded_none" in helper, (
        "zero wgranych plikow nadal renderuje sie napisem o powodzeniu"
    )


def test_a_clean_upload_still_reads_as_one():
    """The half that was right. A fix that made every upload look like a
    problem would be worse than the message it replaces."""
    helper = _read(HELPER)
    assert "uploaded_ok" in helper, (
        "udane wgranie przestalo miec swoj wlasny komunikat"
    )


# ── The themes ship their own copy of this screen ────────────────────────────
#
# Fixing the core was half of it, and the half the person testing could not
# see: they were on Vapor, which brings its own ROM upload dialog and its own
# copy of the message. The theme is a separate repository and cannot import
# from the core, so the helper is offered through `__GD__.utils` - the section
# whose comment already says it exists because "plugins cannot import @/utils
# directly". Copying the mapping into the theme would be the second spelling
# this whole change exists to remove.

def test_the_core_offers_the_helper_to_themes():
    body = _read(FRONTEND / "src" / "main.ts")
    at = body.index("utils: {")
    block = body[at:body.index("}", at)]
    assert "describeUpload" in block, (
        "rdzen nie wystawia opisu wyniku wgrywania, wiec kazdy motyw z wlasnym "
        "oknem musi napisac te regule od nowa"
    )


# There is no test here for the theme's own dialog, and that is deliberate.
#
# `vapor_build/gd3-vapor` is a sibling checkout: absent from the image, absent
# from CI. A test pointed at it would skip every single time, which this
# codebase has already decided is a note that looks like coverage rather than
# coverage - see the same reasoning at the end of
# test_plugin_events_are_documented.py. So the note is here in words instead.
#
# WHAT VAPOR HAS TO DO, and what was checked by hand on the live install:
#   VaporAddRomsDialog.vue calls `__GD__.utils.describeUpload(data, t)` and
#   falls back to `library.uploaded_ok` when the helper is absent, because a
#   theme runs against whatever core the person has and `min_gd` is 1.0.33.
#
# HOW THIS WAS FOUND, because it is the interesting part: the core was fixed,
# the tests were green, and the person testing still saw the old sentence. They
# were on Vapor, which ships its own copy of this screen. The served bundle
# said so - the core chunk carried the new keys and the theme's layout.js
# carried the old one.


def test_every_catalogue_can_say_all_of_it():
    catalogues = [FRONTEND / "src" / "i18n" / "en.json"]
    catalogues += sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    if len(catalogues) < 2:
        pytest.skip("frontend tree not present")
    helper = _read(HELPER)
    keys = sorted(set(re.findall(r"'(library\.(?:reject_|upload)[a-z_]+)'", helper)))
    assert len(keys) >= 5, f"test nie znajduje kluczy w pomocniku: {keys}"
    for path in catalogues:
        have = json.loads(_read(path))
        for key in keys:
            assert key in have, f"brak {key} w {path.name}"
            assert have[key].strip(), f"puste {key} w {path.name}"
