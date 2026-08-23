"""Ruff runs as part of the suite, not only in CI.

This exists because of a real bug. Folding two copies of a download access
check into a shared helper removed the `user = request.state.user` binding the
rest of the function still relied on, and
`GET /api/library/download/{file_id}` raised NameError from then on. Nothing
noticed for a day: no test covers that route, the browser reaches files through
the token route instead, and the lint that would have said so runs only on
GitHub - which the working branch is not pushed to mid-cycle.

Ruff was already the right tool and already in CI. What was missing was having
it in the loop that runs during work.

The rule set comes from pyproject.toml and is deliberately narrow - undefined
names, use-before-assignment, redefinitions, bad format strings, dead locals,
syntax errors. Style is intentionally out. This passes no `--select` of its
own: overriding that configuration would make the suite and CI disagree about
what passes, and it would switch on unused-import reporting, which this project
turns off on purpose because several imports exist precisely for their side
effect of registering a model.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent


def test_ruff_reports_no_errors():
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff is not installed - it is in requirements-dev.txt")

    result = subprocess.run(
        [ruff, "check", "--output-format", "concise", str(BACKEND)],
        capture_output=True,
        text=True,
        # From the root, so ruff reads the same pyproject.toml CI does.
        cwd=str(ROOT),
    )
    assert result.returncode == 0, (
        "ruff found problems:\n" + (result.stdout or result.stderr)
    )
