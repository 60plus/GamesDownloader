"""Rewrite the schema baseline the migration guard reads.

Run it from /app inside the image (`python -m tools.schema_baseline`) when a NEW
TABLE has been added, which is the only innocent reason for that test to go red.

A new COLUMN in an existing table is not a reason to run this. It belongs in
`_COLUMN_MIGRATIONS` in main.py, because `create_all()` never alters a table
that already exists - so a column added to a model and to nothing else is fine
on a fresh install and absent from every existing one, and every query against
that model answers "Unknown column".

That used to be a docstring and nothing more: the script rebuilt the whole
snapshot from the models, so pointing it at a forgotten column wrote the column
into the baseline and the guard went quiet for good. One command, and the test
that exists to catch exactly that mistake stops being able to.

So it is incremental now. Tables already in the snapshot are copied across
untouched; only tables that are new get written. A known table that has grown a
column stops the script with the message the failing test gives, and `--force`
is there for the rare deliberate case - a column dropped from a model, say -
where a human has decided the baseline really is what needs to change.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tests._schema_snapshot import BACKEND, model_columns  # noqa: E402


def _migrated() -> set[tuple[str, str]]:
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    at = source.index("_COLUMN_MIGRATIONS = [")
    body = source[at:source.index("\n    ]", at)]
    return set(re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"', body))


def main() -> None:
    path = BACKEND / "tests" / "schema_baseline.json"
    migrated = _migrated()

    existing: dict[str, list[str]] = {}
    if path.is_file():
        existing = json.loads(io.open(path, encoding="utf-8").read())

    fresh = {
        table: sorted(c for c in columns if (table, c) not in migrated)
        for table, columns in sorted(model_columns().items())
    }

    # A table the snapshot already knows, which has gained a column that nothing
    # will add to an existing database. Writing it here is precisely the mistake
    # this file must not make easy.
    grew = sorted(
        f"{table}.{column}"
        for table, columns in fresh.items()
        if table in existing
        for column in columns
        if column not in existing[table]
    )
    forced = "--force" in sys.argv
    if grew and not forced:
        sys.exit(
            "Migawka nie sluzy do zakrywania nowych kolumn w znanych tabelach.\n"
            "Dopisz je do _COLUMN_MIGRATIONS w main.py: " + "; ".join(grew) + "\n"
            "Jesli naprawde chcesz przepisac migawke, uzyj --force."
        )

    # WITH NO FILE THERE IS NOTHING TO REFUSE.
    #
    # `grew` is "columns missing from the entry this table already has", so an
    # absent snapshot makes it empty and the check above cannot fire - and the
    # script then wrote every column of every model, forgotten ones included,
    # which is line for line the behaviour the incremental rewrite replaced.
    #
    # It is not a corner either: the guard's own failure message tells people to
    # rebuild the file with this script, so the way somebody arrives here is by
    # being sent. Writing it from nothing is the same act as --force and asks
    # for the same word.
    if not path.is_file() and not forced:
        sys.exit(
            "Nie ma migawki, wiec nie ma z czym porownac - zapis stworzy ja z "
            "modeli, RAZEM z kolumnami, ktore ktos zapomnial dopisac do "
            "_COLUMN_MIGRATIONS.\n"
            "Jesli tego wlasnie chcesz, uzyj --force."
        )

    # Known tables keep the entry they already have, so a column that was in the
    # baseline yesterday cannot quietly leave it today; new tables come in whole,
    # which is what create_all does with them anyway.
    #
    # With ONE exception, and it is the drift an ordinary run exists to fix: a
    # column that is now in `_COLUMN_MIGRATIONS` has no business in the
    # snapshot, because the snapshot records what `create_all` produces and a
    # migrated column is added by hand. That pair is exactly what the guard
    # fails on - and until now no ordinary run could clear it, so the tool
    # printed a cheerful line, exited 0, changed nothing, and left whoever ran
    # it reaching for --force, which rewrites everything.
    covered: list[str] = []
    if forced:
        out = dict(fresh)
        covered = list(grew)
    else:
        out = {**fresh, **existing}
        for table in list(out):
            if table not in existing:
                continue
            keep = [c for c in out[table] if (table, c) not in migrated]
            covered += [f"{table}.{c}" for c in out[table] if (table, c) in migrated]
            out[table] = keep
    out = {table: sorted(cols) for table, cols in sorted(out.items())}

    io.open(path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(out, indent=1, sort_keys=True) + "\n")
    added = sorted(set(fresh) - set(existing))
    print(f"{path}: {len(out)} tabel, {sum(len(v) for v in out.values())} kolumn"
          + (f"; nowe tabele: {', '.join(added)}" if added else ""))
    if covered:
        # Named, never counted. The whole point of this file is that a column
        # slipping into the snapshot leaves a trace.
        print(("ZAKRYTE przez --force: " if forced
               else "USUNIETE z migawki (sa juz w _COLUMN_MIGRATIONS): ")
              + "; ".join(sorted(covered)))


if __name__ == "__main__":
    main()
