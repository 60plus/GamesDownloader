"""
GogAuthHandler - GOG OAuth2 token exchange + storage with encryption.

GOG Galaxy public OAuth credentials (widely known, used by many clients).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.config.config_handler import _decrypt, _encrypt
from handler.database.base_handler import DBBaseHandler
from models.gog_account import GogAccount

GOG_CLIENT_ID     = "46899977096215655"
GOG_CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
GOG_REDIRECT_URI  = "https://embed.gog.com/on_login_success?origin=client"
GOG_AUTH_URL      = (
    "https://auth.gog.com/auth"
    "?client_id=46899977096215655"
    "&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient"
    "&response_type=code"
    "&layout=client2"
)
GOG_TOKEN_URL     = "https://auth.gog.com/token"
GOG_USER_URL      = "https://embed.gog.com/userData.json"
GOG_USER2_URL     = "https://users.gog.com/users/{user_id}"

def _normalize_url(url: str) -> str:
    """Convert protocol-relative or root-relative GOG URLs to absolute https://."""
    url = url.strip()
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return "https://images.gog.com" + url
    return url


_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


class GogAuthHandler(DBBaseHandler):
    model = GogAccount

    def get_auth_url(self) -> str:
        return GOG_AUTH_URL

    @begin_session
    async def exchange_code(self, code_or_url: str, user_id: int | None = None, *, session: AsyncSession = None) -> dict:
        """Exchange auth code (or full redirect URL) for tokens. Returns status dict.

        user_id: when set, stores the account for a specific user.
                 When None, stores as the legacy admin account.
        """
        import re
        # Accept full redirect URL or bare code
        m = re.search(r"[?&]code=([^&\s]+)", code_or_url)
        code = m.group(1) if m else code_or_url.strip()

        async with httpx.AsyncClient(headers=_HDRS) as client:
            resp = await client.get(GOG_TOKEN_URL, params={
                "client_id":     GOG_CLIENT_ID,
                "client_secret": GOG_CLIENT_SECRET,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  GOG_REDIRECT_URI,
            })
            resp.raise_for_status()
            data = resp.json()

        access_token  = data["access_token"]
        refresh_token = data["refresh_token"]
        expires_in    = int(data.get("expires_in", 3600))
        expires_at    = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # GOG includes user_id in the token exchange response
        user_id_from_token = str(data.get("user_id", "") or "")

        # Fetch GOG user info
        user_info = await self._fetch_user_info(access_token, user_id_from_token)

        # Download avatar locally for reliability (CDN may block in some environments)
        if user_info.get("avatar") and user_info.get("userId"):
            try:
                from handler.gog.media_handler import download_avatar
                local_avatar = await download_avatar(str(user_info["userId"]), user_info["avatar"])
                if local_avatar:
                    user_info["avatar"] = local_avatar
                    logger.info("GOG avatar downloaded locally: %s", local_avatar)
                else:
                    logger.warning(
                        "GOG avatar download returned None for user_id=%s url=%s",
                        user_info["userId"], user_info["avatar"],
                    )
            except Exception as exc:
                logger.warning(
                    "GOG avatar download failed for user_id=%s url=%s: %s",
                    user_info.get("userId"), user_info.get("avatar"), exc,
                )
                # Keep CDN URL as fallback

        # Upsert GogAccount - filter by user_id
        stmt = select(GogAccount)
        if user_id is not None:
            stmt = stmt.where(GogAccount.user_id == user_id)
        else:
            stmt = stmt.where(GogAccount.user_id.is_(None))
        result = await session.execute(stmt)
        account = result.scalars().first()
        if account:
            account.access_token     = _encrypt(access_token)
            account.refresh_token    = _encrypt(refresh_token)
            account.expires_at       = expires_at
            account.gog_username     = user_info.get("username")
            account.avatar_url       = user_info.get("avatar")
            account.gog_user_id      = str(user_info.get("userId", ""))
            account.email            = user_info.get("email") or None
            account.country          = user_info.get("country") or None
            account.gog_created_date = user_info.get("created_date") or None
            account.games_count      = user_info.get("games_count")
            account.movies_count     = user_info.get("movies_count")
        else:
            session.add(GogAccount(
                user_id          = user_id,
                gog_user_id      = str(user_info.get("userId", "")),
                gog_username     = user_info.get("username"),
                avatar_url       = user_info.get("avatar"),
                email            = user_info.get("email") or None,
                country          = user_info.get("country") or None,
                gog_created_date = user_info.get("created_date") or None,
                games_count      = user_info.get("games_count"),
                movies_count     = user_info.get("movies_count"),
                access_token     = _encrypt(access_token),
                refresh_token    = _encrypt(refresh_token),
                expires_at       = expires_at,
            ))

        return {
            "authenticated": True,
            "username":   user_info.get("username"),
            "avatar_url": user_info.get("avatar"),
        }

    @begin_session
    async def get_status(self, user_id: int | None = None, *, session: AsyncSession = None) -> dict:
        stmt = select(GogAccount)
        if user_id is not None:
            stmt = stmt.where(GogAccount.user_id == user_id)
        else:
            stmt = stmt.where(GogAccount.user_id.is_(None))
        result = await session.execute(stmt)
        account = result.scalars().first()
        if not account:
            return {"authenticated": False}
        expires_at_iso = (
            account.expires_at.isoformat() if account.expires_at else None
        )
        return {
            "authenticated":  True,
            "username":       account.gog_username,
            "avatar_url":     account.avatar_url,
            "user_id":        account.gog_user_id,
            "expires_at":     expires_at_iso,
            "email":          account.email,
            "country":        account.country,
            "created_date":   account.gog_created_date,
            "games_count":    account.games_count,
            "movies_count":   account.movies_count,
        }

    @begin_session
    async def get_access_token(self, user_id: int | None = None, *, session: AsyncSession = None) -> str | None:
        stmt = select(GogAccount)
        if user_id is not None:
            stmt = stmt.where(GogAccount.user_id == user_id)
        else:
            stmt = stmt.where(GogAccount.user_id.is_(None))
        result = await session.execute(stmt)
        account = result.scalars().first()
        if not account or not account.access_token:
            return None
        # Auto-refresh if expired (DB returns offset-naive; treat as UTC)
        expires_at = account.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and datetime.now(timezone.utc) >= expires_at:
            await self._refresh_tokens(account, session=session)
        return _decrypt(account.access_token)

    @begin_session
    async def disconnect(self, user_id: int | None = None, *, session: AsyncSession = None) -> None:
        stmt = select(GogAccount)
        if user_id is not None:
            stmt = stmt.where(GogAccount.user_id == user_id)
        else:
            stmt = stmt.where(GogAccount.user_id.is_(None))
        result = await session.execute(stmt)
        account = result.scalars().first()
        if account:
            await session.delete(account)

    async def _fetch_user_info(self, access_token: str, known_user_id: str = "") -> dict:
        """Fetch GOG profile info: username, avatar, email, country, creation date, library counts.

        Strategy:
        1. embed.gog.com/userData.json - primary source for email, country, purchasedItems,
           username, avatar (v1 API).
        2. users.gog.com/users/{id} - structured avatar with extensions + created_date (Galaxy API).
        3. embed.gog.com/users/info/{id} - fallback for creation date (userSince timestamp).
        """
        headers     = {**_HDRS, "Authorization": f"Bearer {access_token}"}
        user_id     = known_user_id
        username    = ""
        avatar      = ""
        email       = ""
        country     = ""
        created_date = ""
        games_count: int | None = None
        movies_count: int | None = None

        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15) as client:

            # Step 1 - userData.json (email, country, purchasedItems, username, avatar)
            try:
                resp = await client.get(GOG_USER_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    if not user_id:
                        user_id = str(data.get("userId") or data.get("galaxyUserId") or "")
                    username = data.get("username") or ""
                    email    = data.get("email") or ""
                    country  = data.get("country") or ""
                    purchased = data.get("purchasedItems") or {}
                    if isinstance(purchased, dict):
                        gc = purchased.get("games")
                        mc = purchased.get("movies")
                        games_count  = int(gc)  if gc  is not None else None
                        movies_count = int(mc)  if mc  is not None else None
                    av_raw = (
                        data.get("avatar")
                        or (data.get("avatars") or {}).get("large2x")
                        or (data.get("avatars") or {}).get("large")
                        or ""
                    )
                    if av_raw:
                        avatar = _normalize_url(str(av_raw))
            except Exception:
                pass

            # Step 2 - users.gog.com (Galaxy API: structured avatar + created_date)
            if user_id:
                try:
                    r = await client.get(GOG_USER2_URL.format(user_id=user_id))
                    if r.status_code == 200:
                        d = r.json()
                        if not username:
                            username = d.get("username") or ""
                        created_date = d.get("created_date") or ""
                        av_obj = d.get("avatar") or {}
                        if isinstance(av_obj, dict):
                            av_raw = (
                                av_obj.get("large2x") or av_obj.get("large")
                                or av_obj.get("sdk_img_176") or av_obj.get("sdk_img_128")
                                or av_obj.get("sdk_img_64") or ""
                            )
                            if av_raw and not avatar:
                                avatar = _normalize_url(str(av_raw))
                        elif isinstance(av_obj, str) and av_obj and not avatar:
                            avatar = _normalize_url(av_obj)
                except Exception:
                    pass

            # Step 3 - users/info fallback for creation date (userSince Unix timestamp)
            if not created_date and user_id:
                try:
                    r2 = await client.get(f"https://embed.gog.com/users/info/{user_id}")
                    if r2.status_code == 200:
                        d2 = r2.json()
                        user_since = d2.get("userSince")
                        if user_since:
                            from datetime import timezone
                            dt = datetime.fromtimestamp(int(user_since), tz=timezone.utc)
                            created_date = dt.isoformat()
                except Exception:
                    pass

        return {
            "username":     username,
            "userId":       user_id,
            "avatar":       avatar,
            "email":        email,
            "country":      country,
            "created_date": created_date,
            "games_count":  games_count,
            "movies_count": movies_count,
        }

    @begin_session
    async def _refresh_tokens(self, account: GogAccount, *, session: AsyncSession = None) -> None:
        try:
            rt = _decrypt(account.refresh_token)
            async with httpx.AsyncClient(headers=_HDRS) as client:
                resp = await client.get(GOG_TOKEN_URL, params={
                    "client_id":     GOG_CLIENT_ID,
                    "client_secret": GOG_CLIENT_SECRET,
                    "grant_type":    "refresh_token",
                    "refresh_token": rt,
                })
                resp.raise_for_status()
                data = resp.json()
            account.access_token  = _encrypt(data["access_token"])
            account.refresh_token = _encrypt(data["refresh_token"])
            account.expires_at    = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
        except Exception:
            pass  # Keep old token; will fail on actual API call


gog_auth_handler = GogAuthHandler()
