"""Every name imported from our own code must actually be there.

`test_imports.py` walks the tree and imports each module, which catches a broken
import at the top of a file. It cannot catch one written INSIDE a function,
because that line does not run until somebody clicks the thing.

That is not hypothetical. Consolidating the GOG headers into one module left
four files importing names that had moved; those were caught. The same refactor
left three more inside function bodies, and they survived a full green test run:

  * `handler/metadata/meta_sources.py` imported `_HDRS, _abs_url` from
    `library_scrape_handler`, so metadata search on any GOG game answered 500.
  * `endpoints/gog/gog_router.py` imported `GOG_JSON_HEADERS` from
    `srl_handler`, which has never defined it.
  * five modules imported `GD_BASE_PATH` from `config`, which exports
    `BASE_PATH`; three of them hid the failure behind `except ImportError` and
    silently pinned every scraped cover to `/data`.

So this reads the source instead of running it. It resolves every
`from <our.module> import <name>` in the tree, wherever it is written, and
checks the name exists in the target.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

KORZEN = pathlib.Path(__file__).resolve().parent.parent

# Our own top-level packages. Anything else is a dependency and not our problem.
NASZE = {
    "handler", "endpoints", "models", "utils", "decorators",
    "config", "middleware", "plugins", "adapters", "tasks",
}


def _pliki() -> list[pathlib.Path]:
    out = []
    for p in sorted(KORZEN.rglob("*.py")):
        czesci = p.relative_to(KORZEN).parts
        if "__pycache__" in czesci or czesci[0] in {"tests", "alembic", "migrations"}:
            continue
        out.append(p)
    return out


def _sciezka_modulu(nazwa: str) -> pathlib.Path | None:
    """Where a dotted module name lives, module file or package __init__."""
    baza = KORZEN / pathlib.Path(*nazwa.split("."))
    if baza.with_suffix(".py").is_file():
        return baza.with_suffix(".py")
    if (baza / "__init__.py").is_file():
        return baza / "__init__.py"
    return None


def _nazwy_najwyzszego_poziomu(drzewo: ast.Module) -> set[str]:
    """Everything a module offers: definitions, assignments, re-exports.

    Conditional bodies count too, because a name defined only under `if
    TYPE_CHECKING` or inside a try/except is still a name the module can offer.
    """
    nazwy: set[str] = set()

    def zbierz(cialo) -> None:
        for w in cialo:
            if isinstance(w, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nazwy.add(w.name)
            elif isinstance(w, ast.Assign):
                for cel in w.targets:
                    if isinstance(cel, ast.Name):
                        nazwy.add(cel.id)
            elif isinstance(w, ast.AnnAssign) and isinstance(w.target, ast.Name):
                nazwy.add(w.target.id)
            elif isinstance(w, (ast.Import, ast.ImportFrom)):
                for a in w.names:
                    if a.name == "*":
                        # A star re-export means we cannot know: give up on
                        # this module rather than report a name that is there.
                        nazwy.add("*")
                    else:
                        nazwy.add(a.asname or a.name.split(".")[0])
            elif isinstance(w, (ast.If, ast.Try)):
                zbierz(w.body)
                zbierz(getattr(w, "orelse", []) or [])
                zbierz(getattr(w, "finalbody", []) or [])
                for uchwyt in getattr(w, "handlers", []) or []:
                    zbierz(uchwyt.body)

    zbierz(drzewo.body)
    return nazwy


def _zebrane() -> list[tuple[str, str, str, int]]:
    """(plik, modul_docelowy, nazwa, linia) for every first-party import."""
    out = []
    for p in _pliki():
        try:
            drzewo = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                      # its own test's problem
            continue
        for w in ast.walk(drzewo):
            if not isinstance(w, ast.ImportFrom) or w.level:   # skip relative
                continue
            modul = w.module or ""
            if modul.split(".")[0] not in NASZE:
                continue
            for a in w.names:
                if a.name == "*":
                    continue
                out.append((str(p.relative_to(KORZEN)), modul, a.name, w.lineno))
    return out


ZEBRANE = _zebrane()


def test_jest_co_sprawdzac() -> None:
    """A silent zero would make the real assertion below pass on nothing."""
    assert len(ZEBRANE) > 200, f"spodziewam sie setek importow, mam {len(ZEBRANE)}"


def test_kazdy_wewnetrzny_import_wskazuje_na_istniejaca_nazwe() -> None:
    braki = []
    for plik, modul, nazwa, linia in ZEBRANE:
        cel = _sciezka_modulu(modul)
        if cel is None:
            continue                              # shadowed by a dependency
        try:
            drzewo = ast.parse(cel.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        nazwy = _nazwy_najwyzszego_poziomu(drzewo)
        if "*" in nazwy:
            continue
        # `from pakiet import podmodul` is legitimate and leaves no top-level
        # name behind, so a matching file on disk counts as the name existing.
        if nazwa in nazwy or _sciezka_modulu(f"{modul}.{nazwa}") is not None:
            continue
        braki.append(f"{plik}:{linia} importuje {nazwa!r} z {modul!r}, gdzie tego nie ma")

    assert not braki, "\n".join(braki)
