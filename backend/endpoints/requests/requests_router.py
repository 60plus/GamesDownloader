"""Game request endpoints - submit, list, vote, admin manage, search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.session import async_session_factory
from models.game_request import GameRequest, GameRequestVote

requests_router = APIRouter(prefix="/api/requests", tags=["requests"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class RequestCreate(BaseModel):
    title:         str           = Field(..., min_length=1, max_length=255)
    description:   str | None   = Field(None, max_length=2000)
    link:          str | None   = Field(None, max_length=512)
    platform:      str          = Field("games", pattern=r"^(games|roms)$")
    platform_slug: str | None   = None   # ROM platform fs_slug (e.g. "snes")
    cover_url:     str | None   = None   # from search suggestion


class RequestPatch(BaseModel):
    status:     str | None = Field(None, pattern=r"^(pending|approved|rejected|done)$")
    admin_note: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _build_response(session, rows, current_user_id: int) -> list[dict]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    vote_rows = (await session.execute(
        select(GameRequestVote.request_id, func.count().label("cnt"))
        .where(GameRequestVote.request_id.in_(ids))
        .group_by(GameRequestVote.request_id)
    )).all()
    vote_map = {r.request_id: r.cnt for r in vote_rows}
    my_votes = set((await session.execute(
        select(GameRequestVote.request_id)
        .where(GameRequestVote.request_id.in_(ids))
        .where(GameRequestVote.user_id == current_user_id)
    )).scalars().all())

    return [
        {
            "id":            r.id,
            "title":         r.title,
            "description":   r.description,
            "link":          r.link,
            "platform":      r.platform,
            "platform_slug": r.platform_slug,
            "cover_url":     r.cover_url,
            "status":        r.status,
            "admin_note":    r.admin_note,
            "user_id":       r.user_id,
            "username":      r.username,
            "vote_count":    vote_map.get(r.id, 0),
            "user_voted":    r.id in my_votes,
            "created_at":    r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── Search (type=games → IGDB; type=roms → SS+IGDB+LB via existing logic) ─────

@protected_route(requests_router.get, "/search", scopes=[Scope.REQUESTS_READ])
async def search_games_for_request(
    request: Request,
    q: str = "",
    type: str = "games",
    platform_slug: str = "",
) -> list[dict]:
    """Search external metadata sources for game suggestions."""
    if not q.strip():
        return []

    import asyncio
    from handler.config.config_handler import config_handler

    if type == "roms":
        # Reuse the full SS + IGDB + LaunchBox search from roms_router
        from handler.metadata import screenscraper_handler, igdb_rom_handler, launchbox_handler
        from handler.metadata.rom_platform_map import get_ss_id, get_igdb_id, get_launchbox_name

        ss_user  = await config_handler.get("screenscraper_username") or ""
        ss_pass  = await config_handler.get("screenscraper_password") or ""
        igdb_cid = await config_handler.get("igdb_client_id") or ""
        igdb_sec = await config_handler.get("igdb_client_secret") or ""

        ss_system_id     = get_ss_id(platform_slug)   if platform_slug else None
        igdb_platform_id = get_igdb_id(platform_slug) if platform_slug else None
        lb_platform      = get_launchbox_name(platform_slug) if platform_slug else None

        async def _empty() -> list:
            return []

        async def _lb_search():
            try:
                return await asyncio.wait_for(
                    launchbox_handler.search_candidates(q.strip(), lb_platform), timeout=10.0)
            except Exception:
                return []

        tasks = [
            screenscraper_handler.search_games(q.strip(), ss_system_id, username=ss_user, password=ss_pass)
            if ss_user and ss_pass else _empty(),
            igdb_rom_handler.search_games(q.strip(), igdb_platform_id, client_id=igdb_cid, client_secret=igdb_sec)
            if igdb_cid and igdb_sec else _empty(),
            _lb_search(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ss_results    = results[0] if isinstance(results[0], list) else []
        igdb_results  = results[1] if isinstance(results[1], list) else []
        lb_candidates = results[2] if isinstance(results[2], list) else []

        lb_results: list[dict] = []
        for r in lb_candidates:
            _lb_id = r.get("launchbox_id")
            _box   = launchbox_handler.get_box_front(_lb_id) if _lb_id and launchbox_handler._db_ready else None
            lb_results.append({
                "source": "launchbox", "name": r.get("name") or "",
                "year": r.get("release_year"), "developer": r.get("developer"),
                "cover_url": _box["url"] if _box else None,
            })

        # Merge: SS first, then IGDB, then LB - deduplicate by normalised title
        def _norm(t: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]", "", (t or "").lower())

        seen: set[str] = set()
        merged: list[dict] = []
        for item in (ss_results + igdb_results + lb_results):
            key = _norm(item.get("name", ""))
            if key and key not in seen:
                seen.add(key)
                merged.append({
                    "title":     item.get("name", ""),
                    "year":      item.get("year"),
                    "developer": item.get("developer"),
                    "cover_url": item.get("cover_url"),
                    "url":       item.get("url"),
                    "source":    item.get("source", ""),
                })
        return merged[:20]

    # ── type=games → search IGDB + GOG library + RAWG ──────────────────────
    import asyncio
    from handler.metadata import igdb_rom_handler

    igdb_cid = await config_handler.get("igdb_client_id") or ""
    igdb_sec = await config_handler.get("igdb_client_secret") or ""

    async def _igdb_search():
        if not (igdb_cid and igdb_sec):
            return []
        try:
            return await igdb_rom_handler.search_games(
                q.strip(), igdb_platform_id=None,
                client_id=igdb_cid, client_secret=igdb_sec,
            ) or []
        except Exception:
            return []

    async def _gog_search():
        """Search user's GOG library for matching titles."""
        try:
            from models.gog_game import GogGame
            async with async_session_factory() as s:
                from sqlalchemy import or_
                rows = (await s.execute(
                    select(GogGame).where(
                        or_(
                            GogGame.title.ilike(f"%{q.strip()}%"),
                            GogGame.slug.ilike(f"%{q.strip()}%"),
                        )
                    ).limit(10)
                )).scalars().all()
                return [
                    {
                        "name": r.title, "year": None,
                        "developer": getattr(r, "developer", None),
                        "cover_url": r.cover_url,
                        "url": f"https://www.gog.com/game/{r.slug}" if r.slug else None,
                        "source": "gog",
                        "description": (r.description or "")[:300],
                    }
                    for r in rows
                ]
        except Exception:
            return []

    async def _rawg_search():
        """Search RAWG for game suggestions with descriptions."""
        try:
            rawg_key = await config_handler.get("rawg_api_key") or ""
            if not rawg_key:
                return []
            import httpx
            async with httpx.AsyncClient(timeout=10) as c:
                resp = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": rawg_key, "search": q.strip(), "page_size": 8},
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return [
                    {
                        "name": g.get("name", ""),
                        "year": g.get("released", "")[:4] if g.get("released") else None,
                        "developer": None,
                        "cover_url": g.get("background_image"),
                        "url": f"https://rawg.io/games/{g.get('slug', '')}",
                        "source": "rawg",
                        "description": "",
                    }
                    for g in data.get("results", [])
                ]
        except Exception:
            return []

    results = await asyncio.gather(
        _igdb_search(), _gog_search(), _rawg_search(),
        return_exceptions=True,
    )
    igdb_res = results[0] if isinstance(results[0], list) else []
    gog_res  = results[1] if isinstance(results[1], list) else []
    rawg_res = results[2] if isinstance(results[2], list) else []

    # Merge and deduplicate
    def _norm(t: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]", "", (t or "").lower())

    seen: set[str] = set()
    merged: list[dict] = []
    # GOG first (own library), then IGDB, then RAWG
    for item in (gog_res + igdb_res + rawg_res):
        key = _norm(item.get("name") or item.get("title") or "")
        if key and key not in seen:
            seen.add(key)
            merged.append({
                "title":       item.get("name") or item.get("title", ""),
                "year":        item.get("year"),
                "developer":   item.get("developer"),
                "cover_url":   item.get("cover_url"),
                "url":         item.get("url"),
                "source":      item.get("source", "igdb"),
                "description": item.get("description", ""),
            })
    return merged[:20]


# ── Notify (badge counts) ──────────────────────────────────────────────────────

@protected_route(requests_router.get, "/notify", scopes=[Scope.REQUESTS_READ])
async def notify_counts(request: Request) -> dict:
    """Returns pending count (for admins) and current user's request statuses."""
    user = request.state.user
    user_id = user.id
    is_admin = getattr(user, "role", "") in ("admin", "editor")

    async with async_session_factory() as session:
        pending_count = 0
        if is_admin:
            pending_count = (await session.execute(
                select(func.count()).select_from(GameRequest)
                .where(GameRequest.status == "pending")
            )).scalar_one()

        my_rows = (await session.execute(
            select(GameRequest.id, GameRequest.status)
            .where(GameRequest.user_id == user_id)
        )).all()

    return {
        "pending_count": pending_count,
        "my_requests": [{"id": r.id, "status": r.status} for r in my_rows],
    }


# ── List ───────────────────────────────────────────────────────────────────────

@protected_route(requests_router.get, "", scopes=[Scope.REQUESTS_READ])
async def list_requests(request: Request) -> list[dict]:
    user_id = request.state.user.id
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(GameRequest).order_by(GameRequest.created_at.desc())
        )).scalars().all()
        return await _build_response(session, list(rows), user_id)


# ── Create ─────────────────────────────────────────────────────────────────────

@protected_route(requests_router.post, "", scopes=[Scope.REQUESTS_READ])
async def create_request(request: Request, body: RequestCreate) -> dict:
    user = request.state.user
    async with async_session_factory() as session:
        async with session.begin():
            gr = GameRequest(
                title=body.title.strip(),
                description=body.description.strip() if body.description else None,
                link=body.link.strip() if body.link else None,
                platform=body.platform,
                platform_slug=body.platform_slug or None,
                cover_url=body.cover_url or None,
                status="pending",
                user_id=user.id,
                username=getattr(user, "username", None),
            )
            session.add(gr)
        await session.refresh(gr)
        # Capture data before closing session
        gr_data = {
            "id": gr.id, "title": gr.title, "description": gr.description,
            "link": gr.link, "platform": gr.platform, "platform_slug": gr.platform_slug,
            "cover_url": gr.cover_url, "status": gr.status, "admin_note": gr.admin_note,
            "user_id": gr.user_id, "username": gr.username,
            "vote_count": 0, "user_voted": False, "created_at": str(gr.created_at),
        }
    # Webhook OUTSIDE session scope to avoid nested transactions
    try:
        from handler.notifications.webhook_handler import notify_if_configured
        ph = {
            "title": gr_data["title"],
            "username": gr_data["username"] or "Unknown",
            "platform": gr_data["platform"] or "Any",
            "status": "Pending",
            "description": gr_data["description"] or "No description provided.",
            "note": "",
        }
        await notify_if_configured(
            "request",
            f"New Game Request: {gr_data['title']}",
            gr_data["description"] or "No description provided.",
            cover_url=gr_data["cover_url"],
            fields=[
                {"name": "Requested by", "value": ph["username"], "inline": True},
                {"name": "Platform", "value": ph["platform"], "inline": True},
                {"name": "Status", "value": "Pending", "inline": True},
            ],
            color=0x3B82F6,
            tpl_title_key="tpl_request_new_title",
            tpl_body_key="tpl_request_new_body",
            placeholders=ph,
        )
    except Exception:
        pass
    return gr_data


# ── Vote ───────────────────────────────────────────────────────────────────────

@protected_route(requests_router.post, "/{request_id}/vote", scopes=[Scope.REQUESTS_READ])
async def vote_request(request: Request, request_id: int) -> dict:
    user_id = request.state.user.id
    async with async_session_factory() as session:
        gr = await session.get(GameRequest, request_id)
        if not gr:
            raise HTTPException(status_code=404, detail="Request not found")
        existing = (await session.execute(
            select(GameRequestVote)
            .where(GameRequestVote.request_id == request_id)
            .where(GameRequestVote.user_id == user_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Already voted")
        async with session.begin():
            session.add(GameRequestVote(request_id=request_id, user_id=user_id))
        cnt = (await session.execute(
            select(func.count()).where(GameRequestVote.request_id == request_id)
        )).scalar_one()
        return {"vote_count": cnt, "user_voted": True}


# ── Admin: patch ───────────────────────────────────────────────────────────────

@protected_route(requests_router.patch, "/{request_id}", scopes=[Scope.REQUESTS_WRITE])
async def patch_request(request: Request, request_id: int, body: RequestPatch) -> dict:
    async with async_session_factory() as session:
        async with session.begin():
            gr = await session.get(GameRequest, request_id)
            if not gr:
                raise HTTPException(status_code=404, detail="Request not found")
            old_status = gr.status
            if body.status is not None:
                gr.status = body.status
            if body.admin_note is not None:
                gr.admin_note = body.admin_note or None
            new_status = gr.status
            title = gr.title
            desc = gr.description or ""
            cover = gr.cover_url
            username = gr.username or "Unknown"
            note = gr.admin_note or ""
    # Webhook notification on status change
    if old_status != new_status:
        try:
            from handler.notifications.webhook_handler import notify_if_configured
            status_colors = {
                "approved": 0x22C55E,
                "rejected": 0xEF4444,
                "done": 0x7C3AED,
                "pending": 0x3B82F6,
            }
            status_labels = {
                "approved": "Approved",
                "rejected": "Rejected",
                "done": "Done",
                "pending": "Pending",
            }
            label = status_labels.get(new_status, new_status.capitalize())
            color = status_colors.get(new_status, 0x6B7280)
            fields = [
                {"name": "Requested by", "value": username, "inline": True},
                {"name": "Decision", "value": label, "inline": True},
            ]
            if note:
                fields.append({"name": "Admin note", "value": note, "inline": False})
            ph = {
                "title": title,
                "username": username,
                "status": label,
                "platform": "",
                "description": desc or "No description.",
                "note": note,
            }
            await notify_if_configured(
                "request",
                f"Game Request {label}: {title}",
                desc or "No description.",
                cover_url=cover,
                fields=fields,
                color=color,
                tpl_title_key=f"tpl_request_{new_status}_title",
                tpl_body_key=f"tpl_request_{new_status}_body",
                placeholders=ph,
            )
        except Exception:
            pass
    return {"ok": True}


# ── Admin: delete ───────────────────────────────────────────────────────────────

@protected_route(requests_router.delete, "/{request_id}", scopes=[Scope.REQUESTS_WRITE])
async def delete_request(request: Request, request_id: int) -> dict:
    async with async_session_factory() as session:
        async with session.begin():
            gr = await session.get(GameRequest, request_id)
            if not gr:
                raise HTTPException(status_code=404, detail="Request not found")
            await session.delete(gr)
    return {"ok": True}
