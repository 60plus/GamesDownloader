"""A question that gets replaced has to be answered, and its tick has to go.

The dialog state is one object shared by the whole application, so opening a
second question overwrites the first. Two things went wrong with that, and both
of them end in somebody deleting what they did not agree to.

THE PROMISE IS ABANDONED. `gdConfirm` stores its `resolve` in that shared state,
and the second call replaces it. The first caller waits for ever and its "did
they agree" branch never runs.

THE TICK CARRIES OVER. The destructive questions are guarded by a tick box, and
the component clears it when `visible` turns true. In this race `visible` was
already true, so the watcher never fired: the tick somebody set while reading
question A stayed set under question B, one click from confirming something they
had not read.

Reachable without doing anything odd. The My uploads bin asks the server what a
removal would take before it asks the person, and that call reads the disc set,
counts every account's saves and stats the files - seconds on a disc title.
Click the bin on a slow one, see nothing happen, click the bin on a quick one,
tick the box; the slow one's answer arrives and quietly takes the dialog over.

There is no JS test runner here, so this reads the two files. The assertions are
about the mechanism, not the wording.
"""

from __future__ import annotations

import io
import pathlib

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
COMPOSABLE = FRONTEND / "composables" / "useDialog.ts"
COMPONENT = FRONTEND / "components" / "GdDialog.vue"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.fail(f"brak {path} - test nie ma czego sprawdzic")
    return io.open(path, encoding="utf-8").read()


def test_the_question_being_replaced_is_answered():
    source = _read(COMPOSABLE)
    assert "_displace" in source, (
        "drugie pytanie podmienia resolve pierwszego, wiec ten, kto na nie "
        "czekal, czeka w nieskonczonosc"
    )
    # Answered false: nobody confirmed it, which is what actually happened.
    at = source.index("function _displace")
    body = source[at:source.index("\n  }", at)]
    assert "pending?.(false)" in body


@pytest.mark.parametrize("opener", ["gdConfirm", "gdAlert"])
def test_both_openers_do_it(opener):
    source = _read(COMPOSABLE)
    at = source.index(f"function {opener}(")
    body = source[at:source.index("return new Promise", at)]
    assert "_displace()" in body, f"{opener} zostawia poprzednie pytanie bez odpowiedzi"


def test_every_open_moves_the_counter():
    """`visible` is already true when a second question arrives, so it cannot be
    what the component watches."""
    source = _read(COMPOSABLE)
    assert "seq:" in source, "brak licznika otwarc w stanie dialogu"
    assert source.count("dialogState.seq        += 1") == 2, (
        "licznik nie rusza sie przy kazdym otwarciu"
    )


def test_the_tick_is_cleared_on_the_counter_not_on_visibility():
    source = _read(COMPONENT)
    assert "watch(() => dialogState.seq" in source, (
        "reset ptaszka wisi na `visible`, ktore w tym wyscigu sie nie zmienia"
    )
    at = source.index("watch(() => dialogState.seq")
    body = source[at:source.index("})", at)]
    assert "ticked.value = false" in body
    assert "imageBroken.value = false" in body, (
        "obrazek z poprzedniego pytania zostaje nad nowym"
    )


def test_the_guard_still_reads_the_tick():
    """The reset would be pointless if the button stopped asking."""
    source = _read(COMPONENT)
    assert "guarded && !ticked" in source


# ── A key press belongs to the question that was on screen ───────────────────
#
# The tick guards the mouse and it guards `confirm()`, and that was taken for
# enough. It is not enough for the KEYBOARD. Four screens ask a guarded question
# and then an unguarded one - "delete the entry and its saves?" followed by "the
# files on disk as well?" - and Enter held down repeats about thirty times a
# second. The first press answers the guarded question, the next one lands on
# the question that replaced it: the one that takes bytes off the disk, and the
# one with no tick to stop it. The dialog cross-fades for 0.18s on top of that,
# so there is a stretch where the second question cannot be read at all.

def _dialog() -> str:
    import io as _io
    import pathlib

    path = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "frontend" / "src" / "components" / "GdDialog.vue")
    return _io.open(path, encoding="utf-8").read()


def _fn_body(source: str, name: str) -> str:
    at = source.index(name)
    end = source.index("\n}", at)
    return source[at:end]


def test_a_held_key_does_not_answer_twice():
    body = _fn_body(_dialog(), "function onKeydown(")
    assert "e.repeat" in body, (
        "przytrzymany Enter powtarza sie ~30 razy na sekunde, wiec jedno "
        "nacisniecie odpowiada na dwa pytania z rzedu"
    )


def test_a_press_is_tied_to_the_question_that_was_on_screen():
    """Autorepeat is not the only way. Two quick presses do it as well, and a
    question that opens while the key is already down catches the tail of it."""
    body = _fn_body(_dialog(), "function onKeydown(")
    assert "dialogState.seq" in body, (
        "nacisniecie nie jest zwiazane z konkretnym pytaniem, wiec trafia w to, "
        "ktore akurat jest na ekranie"
    )


def test_the_binding_is_released_when_the_key_comes_up():
    """Otherwise the first press would arm the dialog for the rest of the page:
    every later Enter would read as the tail of one long press."""
    assert "keyup" in _dialog(), "nic nie zwalnia powiazania klawisza z pytaniem"


def test_the_guarded_question_still_refuses_an_unticked_confirm():
    """The rule that was already right, kept: the tick guards the button, the
    key, and anything else that reaches confirm()."""
    body = _fn_body(_dialog(), "function confirm(")
    assert "guarded.value && !ticked.value" in body
