"""The screens have to tell a scan that broke from one that ended.

The scan now announces its failure, which is half a fix on its own: every
surface renders `summary.error` as one fixed sentence, "The ROM folder is not
there. Check Settings > ROMs.", because until now `path_missing` was the only
error there was. Sending `failed` without touching them would point somebody at
a setting that is correct and say nothing about the scan that actually died.

Read as text, because this project has no frontend test runner. That catches
only what somebody thought to look for, so what is checked here is narrow and
specific: that the three surfaces branch on WHICH error it was, that the string
exists in every catalogue, and that the Classic sidebar stops writing "ROM scan
complete." into the operator's log after a scan that did not complete.
"""

from __future__ import annotations

import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"

SURFACES = [
    FRONTEND / "src" / "layouts" / "ClassicLayout.vue",
    FRONTEND / "src" / "views" / "emulation" / "EmulationHome.vue",
    FRONTEND / "src" / "views" / "emulation" / "EmulationLibrary.vue",
]


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


@pytest.mark.parametrize("path", SURFACES, ids=lambda p: p.name)
def test_the_surface_says_which_kind_of_ending_it_was(path):
    body = _read(path)
    assert "scan.path_missing" in body, "ekran nie renderuje juz bledu skanu"
    assert "'path_missing'" in body or '"path_missing"' in body, (
        f"{path.name} renderuje KAZDY blad skanu jako 'brakuje folderu ROM-ow' "
        "- po awarii skanu wysyla czlowieka do poprawiania ustawienia, ktore "
        "jest poprawne"
    )
    assert "scan.failed" in body, (
        f"{path.name} nie ma co powiedziec o skanie, ktory padl"
    )


def test_the_operator_log_does_not_call_a_failure_a_completion():
    """The Classic sidebar writes a line into the log the operator reads. It said
    "ROM scan complete." on every ending, including the one where the walk died
    partway."""
    body = _read(SURFACES[0])
    at = body.index("const romScan = useRomScan(")
    callback = body[at:body.index("\n}", at)]
    assert "ROM scan complete." in callback, "test szuka nie tego, co trzeba"
    line = callback[callback.index("pushLog") - 200:callback.index("ROM scan complete.")]
    assert "error" in line, (
        "dziennik operatora melduje 'ROM scan complete.' takze po skanie, "
        "ktory sie wywrocil"
    )


def test_every_catalogue_can_say_it():
    """The i18n job compares the catalogues against each other, so a key added
    to one and forgotten in the others is a red build - and a missing string
    renders as the key itself."""
    catalogues = [FRONTEND / "src" / "i18n" / "en.json"]
    catalogues += sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    if len(catalogues) < 2:
        pytest.skip("frontend tree not present")
    for path in catalogues:
        keys = json.loads(_read(path))
        assert "scan.failed" in keys, f"brak scan.failed w {path.name}"
        assert keys["scan.failed"].strip(), f"puste scan.failed w {path.name}"
