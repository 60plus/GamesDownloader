"""No file holding a real secret can be staged by an ordinary `git add -A`.

This repository is pushed to two remotes and one of them is public, so the
question is not whether anybody would deliberately commit a secret. It is
whether the tree ever offers one.

It did. The ignore rule was the exact name `.env`, which leaves every copy
made beside it untracked and visible: the backup somebody takes before an
upgrade sits in the same directory as the real file, holds the same values,
and is the one thing `git add -A` in that directory would have staged. Found
in a deployment checkout during an audit, on the branch that is cherry-picked
to the public repository.

The rule now covers every variant, and this test is what keeps it covering
them. It asks git itself rather than reading the file, because what matters
is the answer git gives, not the pattern somebody wrote.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def _ignored(name: str) -> bool:
    done = subprocess.run(
        ["git", "check-ignore", "-q", "--", name],
        cwd=ROOT, capture_output=True, timeout=30,
    )
    if done.returncode not in (0, 1):
        pytest.skip(f"git nie odpowiada dla {name}: {done.stderr.decode()[:200]}")
    return done.returncode == 0


@pytest.fixture(scope="module", autouse=True)
def _needs_git():
    if not shutil.which("git"):
        pytest.skip("brak gita")
    if not (ROOT / ".git").exists():
        pytest.skip("korzen repozytorium nie jest obecny")


@pytest.mark.parametrize("name", [
    ".env",
    ".env.local",
    ".env.production",
    ".env.backup",              # the shape that was really there
    ".env.2026-backup",
    ".env.bak",
    ".env.old",
    "prod.env",
    "backend/.env",
    "frontend/.env.local",
])
def test_no_variant_of_an_environment_file_can_be_staged(name):
    assert _ignored(name), (
        f"{name} nie jest ignorowany, wiec `git add -A` by go wzial"
    )


def test_the_example_is_still_tracked():
    """The negation has to survive the broader rule. Losing it would be quiet:
    the file stays in the repository because it is already tracked, and only
    the next person to edit it finds out their change cannot be committed."""
    assert not _ignored(".env.example"), "przyklad musi zostac widoczny dla gita"
    assert (ROOT / ".env.example").is_file(), "przyklad zniknal z repozytorium"


def test_the_example_carries_no_real_secret():
    """It is the one env file in the repository, so it is the one that would
    carry a real value if somebody pasted theirs in to make the docs clearer.
    A signing key is sixty four hex characters; a placeholder is not."""
    import re

    text = (ROOT / ".env.example").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if re.fullmatch(r"[0-9a-f]{32,}", value):
            pytest.fail(f"{name.strip()} wyglada na prawdziwy sekret, nie placeholder")
