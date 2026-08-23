"""Every module must import.

This exists because a refactor left four files importing a name that had been
moved. Ruff was satisfied - the names were used consistently within each file -
and no test touched those modules, so the first thing to notice was the server,
which then would not start. A missing import is the cheapest possible failure
to catch and the most expensive one to find in production.

The test walks the source tree rather than a hand-kept list, so a new module is
covered the moment it is written.
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

KORZEN = pathlib.Path(__file__).resolve().parent.parent
PAKIETY = ("handler", "endpoints", "models", "utils", "decorators", "config")


def _moduly() -> list[str]:
    out = []
    for pakiet in PAKIETY:
        katalog = KORZEN / pakiet
        if not katalog.is_dir():
            continue
        for p in sorted(katalog.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            wzgl = p.relative_to(KORZEN).with_suffix("")
            nazwa = ".".join(wzgl.parts)
            if nazwa.endswith(".__init__"):
                nazwa = nazwa[: -len(".__init__")]
            out.append(nazwa)
    return out


MODULY = _moduly()


def test_znaleziono_moduly() -> None:
    """A silent zero here would make every other assertion in this file pass."""
    assert len(MODULY) > 100, f"spodziewam sie calego drzewa, znalazlem {len(MODULY)}"


@pytest.mark.parametrize("nazwa", MODULY)
def test_modul_sie_importuje(nazwa: str) -> None:
    importlib.import_module(nazwa)
