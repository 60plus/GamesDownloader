"""Route protection decorator - scope-based authorization.

Usage:
    @protected_route(router.get, "/games", [Scope.GOG_READ])
    async def list_games(request: Request) -> list[GameSchema]:
        ...
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Sequence

from fastapi import HTTPException, Request, status

from handler.auth.scopes import Scope


def protected_route(
    method: Callable,
    path: str,
    scopes: Sequence[Scope] | None = None,
    **route_kwargs: Any,
) -> Callable:
    """Register a FastAPI route that requires authentication and scope check."""

    def decorator(func: Callable) -> Callable:
        @method(path, **route_kwargs)
        @functools.wraps(func)
        async def wrapper(request: Request, *args: Any, **kwargs: Any) -> Any:
            user = getattr(request.state, "user", None)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            if scopes:
                user_scopes = getattr(request.state, "scopes", set())
                missing = [s for s in scopes if s not in user_scopes]
                if missing:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Missing scopes: {', '.join(str(s) for s in missing)}",
                    )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
