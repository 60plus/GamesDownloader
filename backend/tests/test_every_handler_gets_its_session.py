"""A handler method that asks for a session must be given one.

`@begin_session` is what puts a real session into the `session=None` parameter.
A method that declares the parameter and is missing the decorator gets None and
dies on `session.execute` the first time anything calls it.

This is not hypothetical. Adding a method to a handler put its decorator on the
wrong line: the new method ended up with `@begin_session` twice and the method
below it with none, and `get_member_library_ids` then threw AttributeError for
all four of its callers - the membership dialog, uploads, the custom library
scan and notification recipients. Nothing failed at import, no test covered it,
and it reached the server. The shape is invisible in a diff and obvious to a
loop, so here is the loop.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest


def _handler_modules():
    import handler.database as pkg

    out = []
    for info in pkgutil.iter_modules(pkg.__path__):
        try:
            out.append(importlib.import_module(f"handler.database.{info.name}"))
        except Exception:  # noqa: BLE001 - a module that will not import is
            continue       # a different problem, and its own tests say so
    return out


def _methods_taking_a_session():
    """Every handler method that ASKS to be handed a session.

    `session=None` is the asking shape: the decorator fills it in, and without
    the decorator it stays None. A method declaring `session` with no default is
    a different thing entirely - a private helper demanding that its caller pass
    the session it is already inside - and it must NOT be decorated, or it would
    open a second one. `RomHandler._sheet_of` and `_tracks_of` are those.
    """
    found = []
    for module in _handler_modules():
        for cls_name, cls in inspect.getmembers(module, inspect.isclass):
            if cls.__module__ != module.__name__:
                continue
            for fn_name, fn in inspect.getmembers(cls, inspect.isfunction):
                if fn_name.startswith("__"):
                    continue
                try:
                    params = inspect.signature(fn).parameters
                except (TypeError, ValueError):
                    continue
                param = params.get("session")
                if param is None or param.default is not None:
                    continue
                found.append((f"{module.__name__}.{cls_name}.{fn_name}", fn))
    return found


def test_the_scan_found_methods_to_check():
    """A rename or a move that empties this list would make the test below pass
    by looking at nothing."""
    assert len(_methods_taking_a_session()) > 50


@pytest.mark.parametrize(
    "name,fn",
    _methods_taking_a_session(),
    ids=[name for name, _ in _methods_taking_a_session()],
)
def test_a_method_that_wants_a_session_is_decorated(name, fn):
    assert getattr(fn, "__wrapped__", None) is not None, (
        f"{name} deklaruje `session=` ale nie ma @begin_session, wiec dostanie "
        f"None i padnie na pierwszym uzyciu"
    )


def test_no_method_is_wrapped_twice():
    """Two of the same decorator opens two sessions where one was meant, and it
    is how the missing one above went unnoticed: the line was not lost, it was
    duplicated onto the neighbour."""
    doubled = []
    for name, fn in _methods_taking_a_session():
        inner = getattr(fn, "__wrapped__", None)
        if inner is not None and getattr(inner, "__wrapped__", None) is not None:
            doubled.append(name)
    assert not doubled, f"@begin_session nalozony wiecej niz raz: {doubled}"
