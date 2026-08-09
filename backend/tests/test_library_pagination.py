"""Per-game denials must be excluded inside the query, not after it.

Filtering the page in Python left holes in it - the database had already
counted out a full LIMIT - and the total counted rows the caller would never
receive. These tests compile the statements and read the SQL, so they need no
database.
"""
from __future__ import annotations

from sqlalchemy import func, select

from handler.database.library_handler import LibraryHandler
from models.library_game import LibraryGame


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _handler() -> LibraryHandler:
    return LibraryHandler()


def test_page_query_excludes_denied_ids():
    stmt = _handler()._active_filters(
        select(LibraryGame), None, False, None, exclude_ids=[7, 9]
    )
    sql = _sql(stmt).lower()
    assert "not in" in sql
    assert "7" in sql and "9" in sql


def test_count_query_excludes_the_same_ids():
    """The count must agree with the page, or the last page is unreachable."""
    stmt = _handler()._active_filters(
        select(func.count()).select_from(LibraryGame), None, False, None,
        exclude_ids=[7, 9],
    )
    assert "not in" in _sql(stmt).lower()


def test_no_exclusion_clause_when_nothing_is_denied():
    """An admin, or a user with no denials, must not pay for an empty NOT IN."""
    for empty in (None, [], set()):
        stmt = _handler()._active_filters(
            select(LibraryGame), None, False, None, exclude_ids=empty
        )
        assert "not in" not in _sql(stmt).lower()


def test_exclusion_survives_a_search_term():
    """The two filters combine; a search must not drop the denial."""
    stmt = _handler()._active_filters(
        select(LibraryGame), "zelda", False, None, exclude_ids=[3]
    )
    sql = _sql(stmt).lower()
    assert "not in" in sql
    assert "zelda" in sql


def test_exclusion_survives_a_library_filter():
    stmt = _handler()._active_filters(
        select(LibraryGame), None, False, 4, exclude_ids=[3]
    )
    assert "not in" in _sql(stmt).lower()


def test_limit_is_applied_after_the_exclusion():
    """The whole point: the database excludes first, then counts out a page.

    If LIMIT were applied to the unfiltered set the page would arrive full and
    be trimmed afterwards, which is the behaviour this replaced.
    """
    h = _handler()
    stmt = h._active_filters(select(LibraryGame), None, False, None, exclude_ids=[5])
    stmt = h._apply_sort(stmt, "title_asc").limit(100).offset(0)
    sql = _sql(stmt).lower()
    assert sql.index("not in") < sql.index("limit")
