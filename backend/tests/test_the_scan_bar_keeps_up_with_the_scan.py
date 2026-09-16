"""Three more ways the scan indicator described something other than the scan.

STUCK ON "STARTING". The catch-up call lifts the phase only from "idle". The
card that pressed Scan itself is already on "starting", so when the socket never
delivers - the Classic layout, a rebuilt connection - the watchdog goes on
fetching the platform and the counters every ten seconds and the template never
shows them, because the "starting" branch has no room for them. The Stop button
lives in the scanning branch, so it never appears either: no progress, no way to
stop, for the whole run.

THE LINGER TIMER FROM THE PREVIOUS SCAN. `finish()` arms a five second timer to
clear the result. Start another scan inside those five seconds and the timer
still fires, clearing a bar that now belongs to a scan which is running.

A REFUSAL READ AS A NETWORK BLIP. `refresh()` swallows every error so that a
failed catch-up cannot report an idle scanner while one is running. That is
right for a dropped connection and wrong for a 403: an account whose upload
permission was revoked keeps the role that puts it in the progress room, so it
is drawn a bar it may never fetch the status for, and the refusal disappears
silently every ten seconds for the life of the page.

Also here because it is the same screen: the shortened "scan stopped" wording
was only ever written into the fallback argument of `t()`, which the catalogue
never reaches.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"


def _composable() -> str:
    return io.open(FRONTEND / "src" / "composables" / "useRomScan.ts",
                   encoding="utf-8").read()


def _fn(source: str, name: str) -> str:
    at = source.index(name)
    nxt = source.find("\n  function ", at + 5)
    nxt2 = source.find("\n  async function ", at + 5)
    ends = [e for e in (nxt, nxt2) if e != -1]
    return source[at:min(ends)] if ends else source[at:]


def test_the_catch_up_lifts_a_card_that_is_still_on_starting():
    body = _fn(_composable(), "async function refresh(")
    at = body.index('phase.value = state.value.platform')
    guard = body[:at]
    assert '"starting"' in guard.split("if (state.value.running")[-1], (
        "nadrobienie podnosi faze tylko z 'idle', wiec karta, ktora sama "
        "nacisnela Skanuj, zostaje na 'Rozpoczynanie' do konca skanu - bez "
        "postepu i bez przycisku Stop"
    )


def test_the_linger_timer_only_clears_the_result_it_was_armed_for():
    body = _fn(_composable(), "function finish(")
    at = body.index("setTimeout(")
    timer = body[at:]
    assert '"done"' in timer, (
        "zegar dogaszania gasi pasek bezwarunkowo, wiec zegar poprzedniego "
        "skanu kasuje wskaznik nastepnego, ktory wlasnie trwa"
    )


def test_a_refusal_is_not_treated_as_a_dropped_connection():
    body = _fn(_composable(), "async function refresh(")
    at = body.index("} catch")
    handler = body[at:]
    assert "403" in handler, (
        "kazdy blad jest polykany tak samo, wiec konto z odebranym "
        "uprawnieniem widzi pasek, ktorego statusu nie moze pobrac, i odmowa "
        "znika po cichu co dziesiec sekund do konca zycia strony"
    )


def test_a_dropped_connection_is_still_swallowed():
    """The caution that made the empty catch right in the first place: a failed
    catch-up must not report an idle scanner while one is running.

    CUT ON THE STATEMENT, not on the letters. This test used to split the
    handler on "403" and check the part before it, and the first "403" in that
    handler is the word inside the comment that explains the branch - so the
    slice was three lines of English prose and the assertion could not fail. It
    was measured: putting `phase.value = "idle"` at the top of the catch left
    this green.
    """
    body = _fn(_composable(), "async function refresh(")
    at = body.index("} catch")
    handler = body[at:]
    branch = handler.index("if (status === 403)")
    before_the_branch = handler[:branch]
    assert "phase.value" not in before_the_branch and "IDLE" not in before_the_branch, (
        "awaria sieci wygasza wskaznik trwajacego skanu"
    )


def test_that_test_reads_code_and_not_a_comment():
    """A guard on the guard above, because it was empty for a release.

    Whatever it slices has to contain something executable - if it is only
    comment and whitespace again, it is checking nothing and saying nothing.
    """
    body = _fn(_composable(), "async function refresh(")
    at = body.index("} catch")
    handler = body[at:]
    before_the_branch = handler[:handler.index("if (status === 403)")]
    code = [
        line.strip() for line in before_the_branch.splitlines()[1:]
        if line.strip() and not line.strip().startswith("//")
    ]
    assert code, (
        "wycinek badany przez test wyzej to sam komentarz - asercja nie ma "
        "czego sprawdzic i nie moze zawiesc"
    )


# ── The stopped-scan wording ─────────────────────────────────────────────────

def test_the_stopped_message_is_short_where_the_screen_reads_it():
    """`t(key, fallback)` takes the catalogue value when there is one, and there
    always is. Shortening the fallback changed nothing on screen."""
    catalogues = [FRONTEND / "src" / "i18n" / "en.json"]
    catalogues += sorted((FRONTEND / "public" / "i18n").glob("*.json"))

    for path in catalogues:
        data = json.loads(io.open(path, encoding="utf-8").read())
        value = data.get("scan.stopped")
        assert value, f"{path.name}: brak klucza scan.stopped"
        assert "marked missing" not in value and "oznaczone jako brakuj" not in value, (
            f"{path.name}: komunikat o zatrzymanym skanie nadal niesie zdanie, "
            "ktore mialo z niego zniknac - skrocono tylko wartosc zapasowa t()"
        )


def test_every_catalogue_still_answers_for_this_key():
    """A key present in one language and missing in another is a screen that
    falls back to the developer's argument in the other seven."""
    en = json.loads(io.open(FRONTEND / "src" / "i18n" / "en.json", encoding="utf-8").read())
    for path in sorted((FRONTEND / "public" / "i18n").glob("*.json")):
        data = json.loads(io.open(path, encoding="utf-8").read())
        assert "scan.stopped" in data, f"{path.name}: brak klucza"
        assert data["scan.stopped"] != en["scan.stopped"], (
            f"{path.name}: nieprzetlumaczone"
        )
