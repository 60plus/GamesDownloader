"""Three ways the snapshot tool could still bury the thing it guards.

The guard is this: `create_all()` never alters a table that already exists, so a
column added to a model and to nothing else is fine on a fresh install and
absent from every existing one, and every query against that model answers
"Unknown column". The snapshot records what the guard knew, and the tool that
rewrites it was made incremental so that pointing it at a forgotten column
refuses instead of writing the column in.

Three doors were left open, and the first two share a shape: the refusal is
reached only through a comparison with what is already in the file.

  NO FILE AT ALL. `grew` is computed as "columns not in the entry this table
  already has", so with no file there are no entries, `grew` is empty and the
  refusal cannot fire. The tool then writes every column from the models -
  which is, line for line, the behaviour the incremental rewrite replaced. And
  it is a door somebody is pushed through: the failing guard's own message says
  to rebuild the file with this script.

  --force SAYS NOTHING. It computes the list of covered columns and throws it
  away. Rewriting the snapshot deliberately is what the flag is for; doing it
  without naming what was covered is how a forgotten column leaves no trace.

  A MIGRATED COLUMN ALREADY IN THE SNAPSHOT. The guard fails when a column is
  BOTH in the snapshot and in `_COLUMN_MIGRATIONS` - the snapshot is meant to
  hold what `create_all` produces, and a migrated column is added by hand. An
  ordinary run cannot fix that: known tables keep the entry they have. So the
  tool printed a cheerful line, exited 0 and changed nothing, leaving the build
  red and pushing whoever ran it towards `--force`, which rewrites everything.
"""

from __future__ import annotations

import io
import json

import pytest


def _run(tmp_path, models, migrated, existing=None, argv=()):
    """The script's own `main`, against a made-up set of models."""
    import sys as _sys

    import tools.schema_baseline as tool

    path = tmp_path / "schema_baseline.json"
    if existing is not None:
        io.open(path, "w", encoding="utf-8").write(json.dumps(existing))

    class _Backend:
        def __truediv__(self, part):
            return tmp_path if part == "tests" else tmp_path / part

    saved = (tool.BACKEND, tool.model_columns, tool._migrated, _sys.argv)
    tool.BACKEND = _Backend()
    tool.model_columns = lambda: models
    tool._migrated = lambda: migrated
    _sys.argv = ["schema_baseline", *argv]
    try:
        tool.main()
    finally:
        (tool.BACKEND, tool.model_columns, tool._migrated, _sys.argv) = saved
    return json.loads(io.open(path, encoding="utf-8").read())


def _refused(tmp_path, **kw):
    with pytest.raises(SystemExit) as stop:
        _run(tmp_path, **kw)
    return str(stop.value)


# ── No file at all ───────────────────────────────────────────────────────────

def test_writing_the_file_from_nothing_is_a_decision(tmp_path):
    """With no file there is nothing to compare against, so every column in
    every model is written in - forgotten ones included. That is the same act as
    --force and it asks for the same word."""
    message = _refused(tmp_path, models={"roms": {"id", "zapomniana"}},
                       migrated=set())

    assert "--force" in message
    assert not (tmp_path / "schema_baseline.json").exists(), (
        "brak pliku omija odmowe i skrypt zapisuje KAZDA kolumne z modeli, "
        "czyli dokladnie to zachowanie, ktore przyrostowy zapis zastapil"
    )


def test_and_it_can_still_be_written(tmp_path):
    """There has to be a way to make the file in the first place - the failing
    guard's message tells people to."""
    out = _run(tmp_path, models={"a": {"id"}}, migrated=set(), argv=("--force",))
    assert out == {"a": ["id"]}


# ── What --force covered ─────────────────────────────────────────────────────

def test_force_names_the_columns_it_covered(tmp_path, capsys):
    _run(tmp_path, models={"roms": {"id", "zapomniana"}}, migrated=set(),
         existing={"roms": ["id"]}, argv=("--force",))

    printed = capsys.readouterr().out
    assert "roms.zapomniana" in printed, (
        "--force zakrywa nowe kolumny w znanych tabelach bez slowa, chociaz ma "
        "ich gotowa liste - a to jest dokladnie ten blad, ktory ta migawka ma "
        "lapac"
    )


def test_an_ordinary_run_still_refuses_them(tmp_path):
    message = _refused(tmp_path, models={"roms": {"id", "zapomniana"}},
                       migrated=set(), existing={"roms": ["id"]})
    assert "roms.zapomniana" in message
    assert "_COLUMN_MIGRATIONS" in message


# ── A migrated column left in the snapshot ───────────────────────────────────

def test_an_ordinary_run_removes_a_column_the_migrations_now_cover(tmp_path, capsys):
    """The one drift an ordinary run is FOR. The guard fails on exactly this
    pair, and the tool could not fix it."""
    out = _run(tmp_path, models={"gog_games": {"id", "meta_ratings"}},
               migrated={("gog_games", "meta_ratings")},
               existing={"gog_games": ["id", "meta_ratings"]})

    assert out == {"gog_games": ["id"]}, (
        "kolumna dopisana do _COLUMN_MIGRATIONS zostaje w migawce, wiec straznik "
        "swieci na czerwono, a narzedzie konczy sie zerem i nie zmienia nic"
    )
    assert "gog_games.meta_ratings" in capsys.readouterr().out


def test_nothing_else_leaves_the_snapshot_on_an_ordinary_run(tmp_path):
    """The protection that makes the tool incremental has to survive: a column
    that was in the baseline yesterday cannot quietly leave it today just
    because somebody deleted it from a model."""
    out = _run(tmp_path, models={"roms": {"id"}}, migrated=set(),
               existing={"roms": ["id", "stara"]})

    assert out == {"roms": ["id", "stara"]}


def test_force_is_still_the_way_to_drop_one(tmp_path):
    out = _run(tmp_path, models={"roms": {"id"}}, migrated=set(),
               existing={"roms": ["id", "stara"]}, argv=("--force",))

    assert out == {"roms": ["id"]}
