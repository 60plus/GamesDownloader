"""No query in the ROM handler may name a file without naming its folder.

Every write and every read that decides what a disc set is now carries the
directory. What holds that in place is the question, because the way it comes
back is not a rewrite - it is one new query, written in the shape of the
fifteen around it, that asks `WHERE platform_id = ? AND fs_name = ?` because
that is what the neighbours look like. The library then goes quiet in exactly
the way it did before: a row overwritten, a set merged, a DELETE reaching into
the folder next door.

A uniqueness constraint in the database would be the stronger fence, and it
cannot be had cheaply here. `fs_path` and `fs_name` are 512-character columns,
so a unique index over them has to be taken on a prefix - and a prefix index
does not enforce what it looks like it enforces: two rows whose first 255
characters match are duplicates to it even when the files are different, so a
legitimate ROM would be refused at insert. The exact alternative, a stored
hash column, is not available in the SQLite the tests run on.

So the fence is here instead, read off the code with the parser rather than
with a substring search: every `.where(...)` in the handler that constrains a
file name must constrain the directory too. Three functions are named as
deliberate exceptions, and each of them says in its own docstring why.
"""
from __future__ import annotations

import ast
import pathlib

HANDLER = (pathlib.Path(__file__).resolve().parent.parent
           / "handler" / "database" / "rom_handler.py")

# Asking about a file by name, or about the files that belong to one.
NAMES_A_FILE = {"fs_name", "track_of"}

ALLOWED = {
    # The weaker question, and it says so: is this name spoken for ANYWHERE on
    # this platform. The upload gate and the download stamp need exactly that.
    "any_row_named",
    # Both still platform-wide, both protective: they decide whether a file a
    # deletion wants to take belongs to somebody else's entry. Narrowing them
    # means deleting MORE, so they move with the scanner's descent into
    # per-game folders, where a test can show both directions on a real tree.
    "fs_names_with_rows",
    "stems_with_rows",
    # Where a game already lives, asked by a file about to be written: the same
    # file or another disc of the same title, in whichever folder it is in. The
    # folder is the ANSWER, so it cannot be part of the question.
    "files_starting_with",
    # Matching a save restored from another install. The archive carries a file
    # name and no folder, so there is no directory to ask about - and rather
    # than guess between two namesakes it now treats an ambiguous name as no
    # match at all.
    "find_for_import",
}


def _columns(node: ast.AST) -> set[str]:
    return {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def test_every_query_about_a_file_also_names_its_folder() -> None:
    tree = ast.parse(HANDLER.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.name in ALLOWED:
            continue
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "where"):
                continue
            columns: set[str] = set()
            for arg in call.args:
                columns |= _columns(arg)
            if columns & NAMES_A_FILE and "fs_path" not in columns:
                offenders.append(f"{fn.name} (linia {call.lineno})")
    assert not offenders, (
        "zapytanie o plik bez podania katalogu: " + ", ".join(offenders)
    )


def test_the_exceptions_are_still_there_and_still_explain_themselves() -> None:
    """An allow-list nobody maintains is a list that grows. If one of these is
    renamed or scoped, this test says so rather than letting the name sit here
    protecting nothing."""
    tree = ast.parse(HANDLER.read_text(encoding="utf-8"))
    found = {
        fn.name: ast.get_docstring(fn) or ""
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for name in ALLOWED:
        assert name in found, f"{name} juz nie istnieje, zdejmij go z listy wyjatkow"
        assert found[name].strip(), (
            f"{name} jest wyjatkiem bez wyjasnienia - powod ma byc w kodzie, "
            "nie tylko w tescie"
        )
