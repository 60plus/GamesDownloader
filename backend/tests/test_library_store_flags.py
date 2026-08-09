"""The two per-library switches, at the boundary where themes read them.

is_store decides which navigation group a library lands in, and
adds_to_default_library decides whether its games reach the home page. Both are
consumed by theme plugins compiled against whatever core happens to be running,
so the serialiser has to answer for a row that predates the columns as well as
one that has them.
"""
from __future__ import annotations

from endpoints.library.libraries_router import (
    LibraryCreateBody,
    LibraryUpdateBody,
    _library_to_dict,
)


class _Row:
    """Stand-in for a Library ORM row, built with whatever columns are given."""

    _DEFAULTS = {
        "slug": "pc-ports", "name": "PC Ports", "kind": "custom_lib",
        "icon": None, "color": None, "enabled": True, "sort_order": 50,
        "is_builtin": False, "storage_folder": "pc-ports",
    }

    def __init__(self, **over):
        for k, v in {**self._DEFAULTS, **over}.items():
            setattr(self, k, v)


def test_flags_are_serialised():
    d = _library_to_dict(_Row(is_store=True, adds_to_default_library=True,
                              visibility="public"))
    assert d["is_store"] is True
    assert d["adds_to_default_library"] is True


def test_a_row_without_the_columns_reads_false():
    """The upgrade window: a theme polling /api/libraries mid-migration.

    Missing must serialise as False rather than raise - a 500 here blanks the
    whole navigation, which is a far worse failure than a Store tab that has not
    appeared yet.
    """
    d = _library_to_dict(_Row())
    assert d["is_store"] is False
    assert d["adds_to_default_library"] is False
    assert d["visibility"] == "public"


def test_truthy_database_values_become_real_booleans():
    """MySQL hands back 1/0 for TINYINT, and themes compare with ===."""
    d = _library_to_dict(_Row(is_store=1, adds_to_default_library=0))
    assert d["is_store"] is True
    assert d["adds_to_default_library"] is False


def test_a_new_library_opts_into_neither():
    """Creating a library must not silently change where its games show up."""
    body = LibraryCreateBody(name="PC Ports")
    assert body.is_store is False
    assert body.adds_to_default_library is False


def test_an_update_leaves_unmentioned_flags_alone():
    """None means "not part of this PATCH" - the handler skips those fields, so
    renaming a library cannot quietly demote it out of the Store."""
    body = LibraryUpdateBody(name="Renamed")
    assert body.is_store is None
    assert body.adds_to_default_library is None


def test_a_flag_can_be_switched_off_explicitly():
    """False has to survive as False and not be confused with "unset"."""
    body = LibraryUpdateBody(is_store=False)
    assert body.is_store is False
    assert body.is_store is not None
