"""The dashboard's live queue asks for the live rows, not for everything.

`list_jobs()` is `select(DownloadJob) ORDER BY created_at DESC` with no WHERE
and no LIMIT, and the dashboard called it every one and a half seconds while an
admin had the tab open, then dropped all but the two or three unfinished rows in
Python. Every historical row was fetched, hydrated into an ORM object, sorted
and thrown away - and nothing ever prunes finished rows, so the cost grew for
the life of the install, one row per GOG file ever downloaded.

The status tuple that says "not finished yet" had also grown four copies: one
on the model's comment, one private name in zip_packer imported across modules,
and one written out inline in the filter this replaces.
"""
from __future__ import annotations

import inspect
import pathlib
import re

from handler.dashboard.dashboard_handler import DashboardHandler
from handler.gog.gog_download_handler import GogDownloadHandler
from models.download_job import PENDING_STATES

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Every value the column takes, from the comment beside it on the model.
ALL_STATES = (
    "pending", "queued", "downloading", "paused",
    "completed", "failed", "cancelled",
)


# ── Which states count as live ───────────────────────────────────────────────

def test_the_live_states_are_the_unfinished_ones():
    assert set(PENDING_STATES) == {"pending", "queued", "downloading", "paused"}


def test_no_finished_state_counts_as_live():
    """Including one would put completed downloads back in the live panel;
    dropping one hides a real download from the admin - `paused` in particular,
    which would take the Resume button with it."""
    finished = set(ALL_STATES) - set(PENDING_STATES)
    assert finished == {"completed", "failed", "cancelled"}


def test_the_tuple_is_not_written_out_anywhere_else():
    """It used to be copied. A copy that drifts is a queue that disagrees with
    itself about what is running."""
    pattern = re.compile(r'"pending",\s*"queued",\s*"downloading",\s*"paused"')
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if path.parent.name == "tests" or path.name == "download_job.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == [], f"copy of the live-status tuple in: {offenders}"


# ── Who asks for what ────────────────────────────────────────────────────────

def test_the_live_listing_filters_in_sql():
    source = inspect.getsource(GogDownloadHandler.list_active_jobs)
    assert "PENDING_STATES" in source
    assert ".where(" in source


def test_the_full_history_listing_is_still_there_for_the_tray():
    """The download tray shows history on purpose; only the 1.5-second poller
    changed."""
    source = inspect.getsource(GogDownloadHandler.list_jobs)
    assert "where" not in source.lower()


def test_the_dashboard_queue_no_longer_fetches_the_history():
    source = inspect.getsource(DashboardHandler.get_download_queue)
    assert "list_active_jobs()" in source
    assert "list_jobs()" not in source


# ── The index that makes the filter cheap ────────────────────────────────────

def test_both_new_indexes_are_registered_as_migrations():
    source = (BACKEND / "main.py").read_text(encoding="utf-8")
    assert "ix_dl_jobs_status_created" in source
    assert "ON download_jobs (status, created_at)" in source
    assert "ix_roms_platform_fs_name" in source
    assert "ON roms (platform_id, fs_name(255))" in source


def test_every_index_migration_is_named_after_the_index_it_creates():
    """The startup check asks information_schema whether `index_name` exists and
    skips the DDL if it does. A name that does not match what the statement
    creates would re-run the CREATE on every boot and log a warning forever."""
    source = (BACKEND / "main.py").read_text(encoding="utf-8")
    block = source[source.index("_INDEX_MIGRATIONS = ["):]
    block = block[: block.index("\n    ]")]
    pairs = re.findall(r'\("(\w+)",\s*"(\w+)",\s*\n?\s*"CREATE (?:UNIQUE )?INDEX (\w+) ON (\w+)', block)
    assert pairs, "no migration entries parsed"
    for declared_name, declared_table, ddl_name, ddl_table in pairs:
        assert declared_name == ddl_name, f"{declared_name} creates {ddl_name}"
        assert declared_table == ddl_table, f"{declared_name} on {declared_table} vs {ddl_table}"
