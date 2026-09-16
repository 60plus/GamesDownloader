"""Adding a column to a model does not add it to anybody's database.

`create_all()` creates missing TABLES and never alters an existing one, so a
column added to a model appears on a fresh install and nowhere else. What puts
it on an existing database is the hand-kept `_COLUMN_MIGRATIONS` list in
main.py, which runs one ALTER TABLE per entry at startup.

The alembic directory alongside it is documentation. There is no
`alembic_version` table on a running install and `alembic upgrade` is not in the
entrypoint - measured on the server: `library_games.metadata_locked` is present
because the list carries it, not because migration 004 ran.

That is easy to get wrong in exactly one direction, and it was: a column was
added to the model and to alembic, the deployed image then had a model asking
for a column the table did not have, and every quota query answered "Unknown
column" - which is the uploads panel and the pre-flight of every upload.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
MAIN = BACKEND / "main.py"
VERSIONS = BACKEND / "alembic" / "versions"


def _migration_list() -> set[tuple[str, str]]:
    """The (table, column) pairs main.py will actually ALTER into place."""
    source = io.open(MAIN, encoding="utf-8").read()
    at = source.index("_COLUMN_MIGRATIONS = [")
    body = source[at:source.index("\n    ]", at)]
    return set(re.findall(r'\(\s*"([^"]+)",\s*"([^"]+)",\s*"', body))


def test_the_list_is_readable():
    """A parse that quietly returns nothing would make every check below pass."""
    pairs = _migration_list()
    assert len(pairs) > 20, f"odczytano tylko {len(pairs)} wpisow, wzorzec sie rozjechal"
    assert ("roms", "published_by") in pairs


def test_every_column_alembic_adds_is_also_in_the_list():
    """The two have to agree, because only one of them runs.

    Alembic is kept as the written record of what changed and when; the list is
    what an existing database actually gets. A column in one and not the other
    is a deployed image whose model asks for something that is not there.
    """
    if not VERSIONS.is_dir():
        pytest.fail(f"brak {VERSIONS} - test nie ma czego sprawdzic")

    pairs = _migration_list()
    missing = []
    for path in sorted(VERSIONS.glob("*.py")):
        source = io.open(path, encoding="utf-8").read()
        for table, column in re.findall(
                r"op\.add_column\(\s*['\"]([^'\"]+)['\"]\s*,\s*sa\.Column\(\s*['\"]([^'\"]+)['\"]",
                source):
            if (table, column) not in pairs:
                missing.append(f"{path.name}: {table}.{column}")
        # The loop form, which 004 uses: one add_column over a tuple of tables.
        for tables, column in re.findall(
                r"for table in \(([^)]*)\):\s*\n\s*op\.add_column\(\s*table,\s*sa\.Column\(\s*\n?\s*['\"]([^'\"]+)['\"]",
                source):
            for table in re.findall(r"['\"]([^'\"]+)['\"]", tables):
                if (table, column) not in pairs:
                    missing.append(f"{path.name}: {table}.{column}")

    assert not missing, (
        "kolumny sa w alembicu, ale nie w _COLUMN_MIGRATIONS, wiec na istniejacej "
        "bazie ich nie bedzie: " + "; ".join(missing)
    )


def test_the_file_owner_column_is_carried():
    """The one this test was written for. The quota reads it on every upload."""
    assert ("library_files", "published_by") in _migration_list(), (
        "model pyta o library_files.published_by, a nic tej kolumny nie doda"
    )


# ── Reading the models, which is the half this file was missing ──────────────
#
# Everything above compares the list against ALEMBIC. That catches a column
# written down in two places and kept in only one, and it catches nothing at
# all about the mistake in the header: alembic does not run here, so a column
# added to a model and to no list whatsoever passed every check on this page.
#
# The baseline below is what the models held once every entry in
# `_COLUMN_MIGRATIONS` is taken away - so the list is not merely allowed by this
# test, it is REQUIRED by it, and deleting an entry from it fails here rather
# than on somebody's install. A brand new TABLE needs nothing: create_all makes
# whole tables and only ever refuses to alter one that exists.

BASELINE = pathlib.Path(__file__).resolve().parent / "schema_baseline.json"


def _baseline() -> dict[str, set[str]]:
    import json

    if not BASELINE.is_file():
        pytest.fail(f"brak {BASELINE} - odtworz go skryptem tools/schema_baseline.py")
    return {t: set(c) for t, c in json.loads(io.open(BASELINE, encoding="utf-8").read()).items()}


def test_the_baseline_is_readable():
    """A snapshot that parsed to nothing would allow every column below."""
    base = _baseline()
    assert len(base) > 20, f"odczytano {len(base)} tabel"
    assert "library_games" in base and "title" in base["library_games"]


def test_the_baseline_does_not_quietly_cover_a_migrated_column():
    """It is the models MINUS the list, so nothing in the list may appear in it.

    Without this the file could be regenerated after a mistake and go on
    passing, which is how a guard becomes a decoration.
    """
    base = _baseline()
    both = [f"{t}.{c}" for t, c in _migration_list() if c in base.get(t, ())]
    assert not both, (
        "kolumny sa i w bazowej migawce, i w _COLUMN_MIGRATIONS - migawke "
        "odtworzono po bledzie: " + "; ".join(sorted(both))
    )


def test_every_column_a_model_declares_reaches_an_existing_database():
    """The one this whole file is named after.

    A column added to a model, with or without an alembic revision, and without
    an entry in `_COLUMN_MIGRATIONS`: fine on a fresh install, and on every
    existing one the table simply does not have it. Every SELECT against that
    model then answers "Unknown column" - which took out the uploads panel and
    the pre-flight of every upload during this release.
    """
    from tests._schema_snapshot import model_columns

    base = _baseline()
    migrated = _migration_list()
    missing = []
    for table, columns in sorted(model_columns().items()):
        if table not in base:
            continue        # a new table; create_all makes those in full
        for column in sorted(columns - base[table]):
            if (table, column) not in migrated:
                missing.append(f"{table}.{column}")

    assert not missing, (
        "model prosi o kolumny, ktorych nic nie doda do istniejacej bazy - dopisz "
        "je do _COLUMN_MIGRATIONS w main.py: " + "; ".join(missing)
    )


# ── The guard must not be switchable off by the tool meant to maintain it ────
#
# The test above goes red when a model grows a column that nothing will add to
# an existing database. The only tool for that red is `tools/schema_baseline.py`
# - and it used to rebuild the whole snapshot from the models, so pointing it at
# the forgotten column wrote the column INTO the baseline and the guard went
# quiet for good. One command, and the check that exists to catch exactly that
# mistake stops being able to.
#
# Reaching for the script instead of reading the assertion is an ordinary thing
# to do at the end of a long day; the docstring saying "do not" is not a guard.

def _run_baseline(tmp_path, models, migrated, existing=None, argv=()):
    """Drive the script's own logic against a fake set of models."""
    import json as _json
    import sys as _sys

    import tools.schema_baseline as tool

    path = tmp_path / "schema_baseline.json"
    if existing is not None:
        io.open(path, "w", encoding="utf-8").write(_json.dumps(existing))

    class _Backend:
        def __truediv__(self, part):
            return tmp_path if part == "tests" else tmp_path / part

    real_backend, real_cols, real_migrated, real_argv = (
        tool.BACKEND, tool.model_columns, tool._migrated, _sys.argv)
    tool.BACKEND = _Backend()
    tool.model_columns = lambda: models
    tool._migrated = lambda: migrated
    _sys.argv = ["schema_baseline", *argv]
    try:
        tool.main()
    finally:
        (tool.BACKEND, tool.model_columns, tool._migrated, _sys.argv) = (
            real_backend, real_cols, real_migrated, real_argv)
    return _json.loads(io.open(path, encoding="utf-8").read())


def test_a_new_table_is_written_into_the_snapshot(tmp_path):
    """The one innocent reason to run it: create_all makes whole tables, so a
    new one needs no migration line and belongs in the baseline."""
    out = _run_baseline(
        tmp_path,
        models={"old": {"id"}, "brand_new": {"id", "name"}},
        migrated=set(),
        existing={"old": ["id"]},
    )
    assert out["brand_new"] == ["id", "name"]
    assert out["old"] == ["id"]


def test_a_new_column_in_a_known_table_stops_the_script(tmp_path):
    """The case this is all about. It has to refuse, and say where the column
    actually belongs."""
    with pytest.raises(SystemExit) as raised:
        _run_baseline(
            tmp_path,
            models={"old": {"id", "forgotten"}},
            migrated=set(),
            existing={"old": ["id"]},
        )
    message = str(raised.value)
    assert "old.forgotten" in message
    assert "_COLUMN_MIGRATIONS" in message, (
        "skrypt odmawia, ale nie mowi, gdzie ta kolumna nalezy"
    )


def test_a_column_already_in_the_migration_list_is_not_a_new_column(tmp_path):
    """Doing it right must not trip the refusal: a column with a migration line
    is deliberately absent from the baseline."""
    out = _run_baseline(
        tmp_path,
        models={"old": {"id", "done_properly"}},
        migrated={("old", "done_properly")},
        existing={"old": ["id"]},
    )
    assert out["old"] == ["id"]


def test_force_is_there_for_the_deliberate_case(tmp_path):
    """A column dropped from a model, say. Somebody has to be able to say so -
    but by typing --force, not by running the ordinary command."""
    out = _run_baseline(
        tmp_path,
        models={"old": {"id", "forgotten"}},
        migrated=set(),
        existing={"old": ["id"]},
        argv=("--force",),
    )
    assert out["old"] == ["forgotten", "id"]


def test_a_first_run_with_no_snapshot_asks_for_the_word(tmp_path):
    """There has to be a way to create the file in the first place, and it is
    the same act as --force.

    With no file there is nothing to compare against, so `grew` is empty and the
    refusal above cannot fire - the script wrote every column of every model,
    forgotten ones included, which is the behaviour the incremental rewrite
    replaced. And it is the door people are sent through: the failing guard's
    message tells them to rebuild the file with this script.
    """
    import pytest as _pytest

    with _pytest.raises(SystemExit) as stop:
        _run_baseline(tmp_path, models={"a": {"id", "zapomniana"}}, migrated=set())
    assert "--force" in str(stop.value)

    out = _run_baseline(tmp_path, models={"a": {"id"}}, migrated=set(),
                        argv=("--force",))
    assert out == {"a": ["id"]}
