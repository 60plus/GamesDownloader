"""Every server event a theme may subscribe to is on one list, and written down.

Theme plugins do not get the raw socket. They get `__GD__.events.on(name, cb)`
with an allow-list, so a theme cannot listen to somebody else's uploads or to
anything the core has not decided to publish.

That list is the plugin API. It is also the thing that silently grows: adding an
event to it costs one line and nothing anywhere fails if the documentation never
learns about it, so a theme author reads HOOKS.md and does not know the event
exists. This ties the two together.

Also asserted: the shape stays a set of quoted names, because the check that
uses it is a set membership and a typo in the list is a `console.warn` at
runtime and nothing at all at build time.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_MAIN = _ROOT / "frontend" / "src" / "main.ts"
# The template repo sits beside the application one, and is not always checked
# out - on CI it is not there at all.
_HOOKS = _ROOT.parent / "gd3-plugin-template" / "docs" / "HOOKS.md"


def _allow_list() -> list[str]:
    if not _MAIN.exists():
        pytest.skip("frontend tree not present")
    source = io.open(_MAIN, encoding="utf-8").read()
    start = source.index("const PLUGIN_SOCKET_EVENTS = new Set([")
    end = source.index("]);", start)
    block = source[start:end]
    # Comments first. They quote example payloads - "packaging"|"completed" and
    # friends - and reading those as entries is how the first version of this
    # test failed against a perfectly good list.
    block = re.sub(r"//[^\n]*", "", block)
    return re.findall(r'"([^"]+)"', block)


def test_the_allow_list_is_readable_at_all():
    events = _allow_list()
    assert len(events) >= 10, "lista dozwolonych zdarzen nie daje sie odczytac"
    assert all(":" in e for e in events), (
        f"wpis, ktory nie wyglada na nazwe zdarzenia: {[e for e in events if ':' not in e]}"
    )


def test_no_event_is_listed_twice():
    """A set swallows a duplicate silently, so the list can carry one for years
    and the only symptom is a reader wondering which is the real entry."""
    events = _allow_list()
    seen = [e for e in events if events.count(e) > 1]
    assert not seen, f"zdarzenia wypisane dwa razy: {sorted(set(seen))}"


def test_the_scan_events_are_exposed():
    """A theme with its own Retro screen has to be able to show where a scan is.
    Without these it is back to polling a boolean every two seconds, which is
    what the core stopped doing."""
    events = _allow_list()
    assert "roms:scan_progress" in events
    assert "roms:scan_complete" in events


# There was a fourth test here, asserting every exposed event appears in the
# template repo's HOOKS.md. It could never run: that repo is a sibling checkout,
# absent from the test container and from CI, so the test skipped every single
# time. A test that always skips is not coverage, it is a note that looks like
# coverage - so the note is here in words instead.
#
#   WHEN ADDING AN EVENT TO THE LIST ABOVE, DOCUMENT IT IN
#   gd3-plugin-template/docs/HOOKS.md IN THE SAME SITTING.
#
# Nothing enforces that. It is the plugin API, and an event nobody wrote down is
# an event no theme author knows exists.
