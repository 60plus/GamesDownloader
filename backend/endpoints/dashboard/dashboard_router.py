"""Dashboard endpoints - role-aware server/user overview.

  GET /api/dashboard/me     any authenticated user: their own numbers
  GET /api/dashboard/admin  admin only: server-wide operational overview

Exposed to themes/plugins via window.__GD__.dashboard so a custom theme can
render its own dashboard instead of the built-in one.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.dashboard.dashboard_handler import dashboard_handler
from models.user import Role

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@protected_route(router.get, "/me", scopes=[Scope.LIBRARY_READ])
async def my_dashboard(
    request: Request,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
    sections: str | None = None,
) -> dict:
    """The signed-in user's own stats: downloads (count / distinct games /
    transfer / effective speed) and their game requests with status.

    Time-scoped sections (downloads + activity chart) follow the selected
    window: `days` = 1 (24h) / 7 / 30, or a custom `start`..`end` (YYYY-MM-DD,
    end inclusive) that overrides `days`.

    `sections` is a comma-separated subset of downloads, continue_playing,
    recently_played, requests - the rest come back empty and, more to the point,
    are never computed. A theme's home that only draws the two play strips
    should ask for those two rather than the lot."""
    user = request.state.user
    want = {s.strip() for s in sections.split(",") if s.strip()} if sections else None
    return await dashboard_handler.get_user_dashboard(
        user.id, days=days, start=start, end=end, sections=want,
    )


@protected_route(router.get, "/admin", scopes=[Scope.LIBRARY_READ])
async def admin_dashboard(
    request: Request,
    days: int = 30,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Server-wide operational overview (admin only): library totals and size,
    downloads and throughput, most active user, top ROM platforms, request
    queue, failed-login / banned-IP security snapshot, and disk space.

    Time-scoped sections (downloads, activity chart, most active user, email)
    follow `days`/`start`/`end` like /me; library, users, platforms, security
    and disk are point-in-time and ignore the window."""
    if request.state.user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return await dashboard_handler.get_admin_dashboard(days=days, start=start, end=end)


@protected_route(router.get, "/queue", scopes=[Scope.LIBRARY_READ])
async def download_queue(request: Request) -> dict:
    """Live server-side download queue (admin only): in-flight GOG jobs + torrents
    with progress/speed/ETA. Meant to be polled for a live view."""
    if request.state.user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return await dashboard_handler.get_download_queue()


@protected_route(router.get, "/game/{game_id}/downloaders", scopes=[Scope.LIBRARY_READ])
async def game_downloaders(request: Request, game_id: int) -> dict:
    """Admin drill-down: which users downloaded a given library game, how many
    times and how much. Powers the click-through from the Top downloaded panel."""
    if request.state.user.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return await dashboard_handler.get_game_downloaders(game_id)
