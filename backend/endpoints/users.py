"""User management endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse

from config import RESOURCES_PATH
from decorators.auth import protected_route
from handler.auth.passwords import ensure_password_ok, hash_password, verify_password
from handler.auth.scopes import Scope
from handler.database.session_handler import session_handler
from handler.database.users_handler import UsersHandler
from models.user import User
from schemas.user import PasswordChange, UserCreate, UserResponse, UserUpdate
from utils.async_utils import fire_task
from utils.uploads import read_upload_capped

router = APIRouter(prefix="/users", tags=["users"])
_users_db = UsersHandler()

_AVATARS_DIR = Path(RESOURCES_PATH) / "avatars"
_ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


def _require_auth(request: Request) -> None:
    if not getattr(request.state, "user", None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


# ── Self ───────────────────────────────────────────────────────────────────────

@protected_route(router.get, "/me", scopes=None)
async def get_current_user(request: Request) -> UserResponse:
    return UserResponse.model_validate(request.state.user)


@router.get("/me/preferences")
async def get_preferences(request: Request) -> dict:
    """Return the current user's UI appearance preferences."""
    _require_auth(request)
    return request.state.user.preferences or {}


@router.put("/me/preferences")
async def save_preferences(request: Request, data: dict = Body(...)) -> dict:
    """Save the current user's preferences.

    The keys sent are merged over the ones already stored rather than replacing
    them wholesale. Every caller owns a slice of this dictionary and sends only
    its own: the theme store writes its appearance keys, the ROM settings write
    whether saves sync themselves. Replacing meant whichever of them saved last
    silently wiped the other's settings - and since the theme store saves on a
    debounce after any appearance change, that would have been often.
    """
    _require_auth(request)
    merged = dict(request.state.user.preferences or {})
    merged.update(data)
    await _users_db.update(request.state.user, {"preferences": merged})
    return {"ok": True}


@router.get("/me/notifications")
async def get_notification_prefs(request: Request) -> dict:
    """The current user's email opt-in plus whether email is even available
    (SMTP configured on the server). The opt-in toggle is only useful when
    smtp_ready is true. No credentials are exposed."""
    _require_auth(request)
    from handler.config.config_handler import config_handler
    host = (await config_handler.get("smtp_host") or "").strip()
    from_addr = (await config_handler.get("smtp_from_address") or "").strip()
    return {
        "smtp_ready": bool(host and from_addr),
        "recently_added": bool(getattr(request.state.user, "notify_recently_added", True)),
    }


@router.put("/me/notifications")
async def save_notification_prefs(request: Request, data: dict = Body(...)) -> dict:
    """Toggle the current user's 'recently added' email opt-in."""
    _require_auth(request)
    val = bool(data.get("recently_added", True))
    await _users_db.update(request.state.user, {"notify_recently_added": val})
    return {"ok": True, "recently_added": val}


@router.post("/me/password")
async def change_password(request: Request, data: PasswordChange) -> dict:
    """Change own password. Requires current password to confirm."""
    _require_auth(request)
    user = request.state.user
    if not verify_password(data.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    ensure_password_ok(data.new_password)
    await _users_db.update(user, {"hashed_password": hash_password(data.new_password)})
    # A password change that leaves the old sessions alive is not a password
    # change: whoever was signed in with the old one still is. Everything but
    # this browser goes, so the person doing it stays where they are.
    revoked = await session_handler.revoke_all_for_user(
        user.username, keep_access_jti=getattr(request.state, "token_jti", None),
    )
    return {"ok": True, "sessions_revoked": revoked}


@router.post("/me/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)) -> dict:
    """Upload a profile picture. Accepted: PNG, JPG, JPEG, GIF, WEBP (max 5 MB)."""
    _require_auth(request)
    user = request.state.user
    ext = Path(file.filename or "avatar.png").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported format. Allowed: {', '.join(_ALLOWED_EXTS)}")
    content = await read_upload_capped(file, _MAX_AVATAR_BYTES, what="Avatar file")
    _AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    dest = _AVATARS_DIR / f"{user.id}{ext}"
    # Remove old avatar files with different extension
    for old in _AVATARS_DIR.glob(f"{user.id}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest.write_bytes(content)
    await _users_db.update(user, {"avatar_path": str(dest)})
    avatar_url = f"/resources/avatars/{user.id}{ext}"
    return {"ok": True, "avatar_url": avatar_url}


@router.get("/me/avatar")
async def get_avatar(request: Request):
    """Serve the current user's avatar.

    SECURITY: Only serves local files under the avatars directory. External
    http(s) avatar paths (legacy values from older versions) are treated as
    not-found - the user must re-upload via this endpoint or via the GOG
    setup flow which downloads to /resources/avatars locally.
    """
    _require_auth(request)
    user = request.state.user
    if not user.avatar_path or user.avatar_path.startswith("http"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar set")
    p = Path(user.avatar_path).resolve()
    avatars_root = _AVATARS_DIR.resolve()
    try:
        p.relative_to(avatars_root)
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No avatar set")
    if p.is_file():
        return FileResponse(str(p))
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar file not found")


# ── Admin ──────────────────────────────────────────────────────────────────────

@protected_route(router.get, "", [Scope.USERS_READ])
async def list_users(request: Request) -> list[UserResponse]:
    users = await _users_db.get_all(limit=500)
    return [UserResponse.model_validate(u) for u in users]


@protected_route(router.post, "", [Scope.USERS_WRITE])
async def create_user(request: Request, data: UserCreate) -> UserResponse:
    """Admin: create a new user."""
    existing = await _users_db.get_by_username(data.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    ensure_password_ok(data.password)
    user = await _users_db.create(User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        enabled=True,
    ))
    return UserResponse.model_validate(user)


@protected_route(router.patch, "/{user_id}", [Scope.USERS_WRITE])
async def update_user(request: Request, user_id: int, data: UserUpdate) -> UserResponse:
    me = request.state.user
    user = await _users_db.get_by_id(user_id)
    if not user:
        from exceptions.common import NotFoundException
        raise NotFoundException("User", user_id)
    # Prevent admin from demoting themselves
    from models.user import Role
    if me.id == user_id and data.role is not None and data.role != Role.ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own admin role")
    prev_role = user.role
    updated = await _users_db.update(user, data.model_dump(exclude_unset=True))

    # Alert when a user is promoted to admin
    if data.role is not None and data.role == Role.ADMIN and prev_role != Role.ADMIN:
        from handler.email.alerts import maybe_alert
        fire_task(maybe_alert("new_admin", updated.username, None))

    return UserResponse.model_validate(updated)


@protected_route(router.post, "/{user_id}/reset-password", [Scope.USERS_WRITE])
async def admin_reset_password(request: Request, user_id: int, data: dict) -> dict:
    """Admin: forcefully reset a user's password without requiring the old one."""
    from pydantic import BaseModel
    new_pwd = data.get("new_password", "")
    ensure_password_ok(new_pwd)
    user = await _users_db.get_by_id(user_id)
    if not user:
        from exceptions.common import NotFoundException
        raise NotFoundException("User", user_id)
    await _users_db.update(user, {"hashed_password": hash_password(new_pwd)})
    # This is the containment action: an admin resets a password because the
    # account is believed compromised. Leaving the intruder's refresh token
    # minting fresh access tokens made it a no-op. No exception here, because
    # the target is somebody else and all of their sessions are suspect.
    revoked = await session_handler.revoke_all_for_user(user.username)
    return {"ok": True, "sessions_revoked": revoked}


@protected_route(router.delete, "/{user_id}", [Scope.USERS_WRITE])
async def delete_user(request: Request, user_id: int) -> dict:
    """Admin: delete a user. Cannot delete yourself."""
    me = request.state.user
    if me.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
    user = await _users_db.get_by_id(user_id)
    if not user:
        from exceptions.common import NotFoundException
        raise NotFoundException("User", user_id)
    await _users_db.delete(user)
    return {"ok": True}
