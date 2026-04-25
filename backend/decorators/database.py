"""Database session decorator - async version.

Injects an AsyncSession into handler methods, auto-commits on success,
rolls back on error.
"""

from __future__ import annotations

import functools
from typing import Any, Callable

from handler.database.session import async_session_factory


def begin_session(func: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a handler method so it receives ``session`` as last kwarg."""

    @functools.wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        if "session" in kwargs and kwargs["session"] is not None:
            return await func(self, *args, **kwargs)

        async with async_session_factory() as session:
            async with session.begin():
                kwargs["session"] = session
                result = await func(self, *args, **kwargs)
                return result

    return wrapper
