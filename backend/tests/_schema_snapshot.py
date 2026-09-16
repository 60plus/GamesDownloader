"""Every column the models declare, read from the models themselves.

Shared by the migration guard and by the script that regenerates its baseline,
so the two can never be reading different things - which is the whole failure
this guards against, one level up.
"""

from __future__ import annotations

import importlib
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def model_columns() -> dict[str, set[str]]:
    """{table name: {column names}} for every model in backend/models.

    Imported rather than parsed. A column can be declared by a mixin, by a
    base class or by a name this file has never heard of, and a regex over the
    source would miss all three and call the result coverage.
    """
    from models.base import Base

    for path in sorted((BACKEND / "models").glob("*.py")):
        if path.stem.startswith("_"):
            continue
        importlib.import_module(f"models.{path.stem}")

    return {
        name: {c.name for c in table.columns}
        for name, table in Base.metadata.tables.items()
    }
