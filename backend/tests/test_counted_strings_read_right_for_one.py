"""A counted string must still read correctly when the count is one.

"Remove 1 entries" and "Usuniesz 1 pozycji" are both wrong, and no single
string can fix them: a bare number followed by a noun needs agreement that
depends on the number, and the eight languages here disagree about how. English
wants a plural above one, Polish and Russian want three different endings, and
none of that survives a `{n}` substituted into the middle of a sentence.

The fix is not plural rules. It is writing the sentence so the number does not
govern a noun - "Entries to remove: 3", "Remove these entries (3)" - which reads
the same whatever the count is. This test holds the line for the strings that
carry a count, because the wrong version only shows itself when somebody
happens to have exactly one of something.
"""
from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_BUNDLED = _ROOT / "frontend" / "src" / "i18n" / "en.json"
_PUBLIC = _ROOT / "frontend" / "public" / "i18n"

# Every key whose value carries {n}. Listed rather than discovered so that a new
# counted string is a deliberate addition here, not something that slips in.
COUNTED = [
    "xc.n_patterns",
    "xc.n_files",
    "xc.covers_n",
    "xc.apply",
    "xc.confirm",
    "xc.removed",
    "xc.removed_some",
    "xc.removed_failed",
    "mr.button",
    "mr.remove",
    "mr.confirm",
    "mr.removed",
    "mr.removed_failed",
    "scan.found",
]


def _files() -> list[pathlib.Path]:
    if not _BUNDLED.exists():
        pytest.skip("frontend tree not present")
    return [_BUNDLED, *sorted(_PUBLIC.glob("*.json"))]


def _governs_a_word(text: str) -> bool:
    """Is the count immediately in front of a word it would have to agree with.

    The shape to catch is a number followed by a noun - "{n} entries",
    "z biblioteki {n} pozycji" - wherever in the sentence it sits. Checking only
    the start of the string was the first version of this test, and it passed
    the very string that sent me looking: the count was in the middle.

    Punctuation after the count is what makes it safe. "Entries to remove: {n}."
    and "Remove these entries ({n})" report a value rather than counting the
    next word, and they read the same at one, two and five in all eight.
    """
    return any(re.match(r"\s+\w", rest) or rest[:1].isalpha()
               for rest in text.split("{n}")[1:])


@pytest.mark.parametrize("path", _files())
def test_no_counted_string_puts_the_number_in_front_of_a_noun(path: pathlib.Path):
    messages = json.loads(io.open(path, encoding="utf-8").read())
    wrong = [k for k in COUNTED if k in messages and _governs_a_word(messages[k])]
    assert not wrong, (
        f"{path.name}: w tych napisach liczba stoi przed slowem, ktore musialoby "
        f"sie do niej odmienic, wiec przy jedynce wyjdzie zla forma: {wrong}"
    )


@pytest.mark.parametrize("path", _files())
def test_every_counted_string_still_has_its_number(path: pathlib.Path):
    """The other way to break this is to lose the count while rewording."""
    messages = json.loads(io.open(path, encoding="utf-8").read())
    missing = [k for k in COUNTED if k in messages and "{n}" not in messages[k]]
    assert not missing, f"{path.name}: napisy zgubily licznik: {missing}"


def test_the_counted_strings_exist_at_all():
    """A rename that leaves this list pointing at nothing would make both tests
    above pass by checking nothing."""
    messages = json.loads(io.open(_BUNDLED, encoding="utf-8").read())
    assert [k for k in COUNTED if k in messages] == COUNTED
