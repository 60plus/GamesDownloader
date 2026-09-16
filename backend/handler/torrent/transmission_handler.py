"""Transmission RPC client - thin async wrapper around the Transmission JSON-RPC API."""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RPC_URL     = "http://localhost:9091/transmission/rpc"
_TIMEOUT     = 10
_LABEL       = "gamesdownloader"

# Transmission status codes
STATUS = {
    0: "stopped",
    1: "check_wait",
    2: "checking",
    3: "download_wait",
    4: "downloading",
    5: "seed_wait",
    6: "seeding",
}


class TransmissionHandler:
    def __init__(self) -> None:
        self._session_id: str = ""
        self._auth: tuple[str, str] | None = None
        self._auth_loaded: bool = False

    # ── RPC transport ─────────────────────────────────────────────────────────

    def forget_auth(self) -> None:
        """Drop the cached credentials so the next call re-reads the settings.

        Called when an admin saves the Transmission screen: without it, turning
        authentication on would lock this client out until the next restart.
        """
        self._auth_loaded = False

    async def _get_auth(self) -> tuple[str, str] | None:
        """Credentials for the RPC, or None while authentication is off.

        Cached because progress polling calls the RPC often and this would
        otherwise be a database read every time.
        """
        if self._auth_loaded:
            return self._auth
        self._auth = None
        try:
            import json as _json

            from handler.config.config_handler import config_handler
            raw = await config_handler.get("transmission_settings")
            if raw:
                saved = _json.loads(raw)
                if saved.get("rpc_auth_enabled"):
                    user = str(saved.get("rpc_username", "")).strip()
                    if user:
                        self._auth = (user, str(saved.get("rpc_password", "")))
        except Exception:
            self._auth = None          # unreadable settings must not stop the client
        self._auth_loaded = True
        return self._auth

    async def _rpc(self, method: str, args: dict | None = None,
                   *, with_reason: bool = False):
        """Send a Transmission RPC request, handling 409 session renewal.

        `with_reason` also hands back what the daemon said when it refused.
        That text was written to the log and dropped on the floor, so a route
        could only answer "Transmission rejected the torrent" while the daemon
        had said "invalid or corrupt torrent file" - and the owner, reading the
        vaguer one, took it for a size problem. Optional, so the dozen other
        callers keep the shape they have.
        """
        def _out(value, reason=None):
            return (value, reason) if with_reason else value

        payload = {"method": method, "arguments": args or {}}
        headers = {"X-Transmission-Session-Id": self._session_id}
        auth = await self._get_auth()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, auth=auth) as client:
                resp = await client.post(_RPC_URL, json=payload, headers=headers)
                if resp.status_code == 409:
                    self._session_id = resp.headers.get("X-Transmission-Session-Id", "")
                    headers["X-Transmission-Session-Id"] = self._session_id
                    resp = await client.post(_RPC_URL, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Transmission RPC %s → HTTP %s", method, resp.status_code)
                    return _out(None, f"HTTP {resp.status_code}")
                data = resp.json()
                if data.get("result") != "success":
                    logger.warning("Transmission RPC %s failed: %s", method, data.get("result"))
                    return _out(None, str(data.get("result") or ""))
                return _out(data.get("arguments"))
        except Exception as exc:
            logger.debug("Transmission RPC error (%s): %s", method, exc)
            # Not the exception's own words: they name the RPC address and, on
            # some paths, files inside the container, and this reason is shown
            # in the dialog of whoever added the torrent.
            return _out(None, "Transmission could not be reached.")

    # ── Status ────────────────────────────────────────────────────────────────

    async def is_available(self) -> bool:
        """Return True if Transmission daemon is reachable."""
        result = await self._rpc("session-get", {"fields": ["version"]})
        return result is not None

    async def get_session(self) -> dict | None:
        return await self._rpc("session-get")

    # ── Torrent management ────────────────────────────────────────────────────

    _TORRENT_FIELDS = [
        "id", "name", "hashString", "status", "percentDone",
        "downloadDir", "totalSize", "sizeWhenDone", "error", "errorString",
        "rateDownload", "rateUpload", "eta", "labels",
        "uploadedEver", "isFinished", "addedDate", "peersGettingFromUs",
        # For the "everything the daemon holds" view: what a torrent has given
        # back, who it is talking to, and where it sits in the queue.
        "uploadRatio", "peersConnected", "peersSendingToUs",
        "downloadedEver", "queuePosition", "doneDate", "isStalled",
    ]

    async def add_torrent_file(
        self,
        torrent_path: str,
        download_dir: str,
        labels: list[str] | None = None,
    ) -> tuple[dict | None, str | None]:
        """Add a .torrent file by path. Returns (info, reason), as
        `add_torrent_metainfo` does."""
        try:
            with open(torrent_path, "rb") as f:
                content = f.read()
        except OSError as exc:
            logger.error("Cannot read torrent file %s: %s", torrent_path, exc)
            return None, "The torrent file could not be read."
        return await self.add_torrent_metainfo(content, download_dir, labels)

    async def add_torrent_metainfo(
        self,
        content: bytes,
        download_dir: str,
        labels: list[str] | None = None,
    ) -> tuple[dict | None, str | None]:
        """Add a torrent from the bytes of its .torrent file.

        Returns (info, reason). The reason is what the daemon said when it
        refused, so the dialog can show that instead of a shrug.
        """
        import base64
        args: dict[str, Any] = {
            "metainfo":     base64.b64encode(content).decode(),
            "download-dir": download_dir,
            "labels":       labels or [_LABEL],
        }
        result, reason = await self._rpc("torrent-add", args, with_reason=True)
        if not result:
            return None, reason
        added = result.get("torrent-added")
        if added:
            return added, None
        # An add for a torrent the daemon already holds is answered with that
        # torrent - somebody else's download, or a library file being seeded.
        # Marked, so a route that writes a row for the caller can refuse it
        # rather than hand them a transfer that is not theirs.
        held = result.get("torrent-duplicate")
        return ({**held, "duplicate": True} if held else None), None

    async def add_torrent_url(
        self,
        url: str,
        download_dir: str,
        labels: list[str] | None = None,
    ) -> tuple[dict | None, str | None]:
        """Add a torrent by magnet link.

        An http(s) address is NOT for this: the daemon would fetch it itself,
        past every guard. The router fetches those and adds their bytes.

        Returns (info, reason) - see `add_torrent_file` above.
        """
        args: dict[str, Any] = {
            "filename":     url,
            "download-dir": download_dir,
            "labels":       labels or [_LABEL],
        }
        result, reason = await self._rpc("torrent-add", args, with_reason=True)
        if not result:
            return None, reason
        added = result.get("torrent-added")
        if added:
            return added, None
        # An add for a torrent the daemon already holds is answered with that
        # torrent - somebody else's download, or a library file being seeded.
        # Marked, so a route that writes a row for the caller can refuse it
        # rather than hand them a transfer that is not theirs.
        held = result.get("torrent-duplicate")
        return ({**held, "duplicate": True} if held else None), None

    async def get_torrent(self, torrent_id: int | str) -> dict | None:
        result = await self._rpc("torrent-get", {
            "ids":    [torrent_id],
            "fields": self._TORRENT_FIELDS,
        })
        if not result:
            return None
        torrents = result.get("torrents", [])
        return torrents[0] if torrents else None

    async def get_all_torrents(self, label: str = _LABEL) -> list[dict]:
        result = await self._rpc("torrent-get", {"fields": self._TORRENT_FIELDS})
        if not result:
            return []
        torrents = result.get("torrents", [])
        if label:
            torrents = [t for t in torrents if label in (t.get("labels") or [])]
        return torrents

    async def remove_torrent(self, torrent_id: int | str, *, delete_data: bool = False) -> bool:
        result = await self._rpc("torrent-remove", {
            "ids":             [torrent_id],
            "delete-local-data": delete_data,
        })
        return result is not None

    async def pause_torrent(self, torrent_id: int | str) -> bool:
        return await self._rpc("torrent-stop", {"ids": [torrent_id]}) is not None

    async def resume_torrent(self, torrent_id: int | str) -> bool:
        return await self._rpc("torrent-start", {"ids": [torrent_id]}) is not None

    async def verify_torrent(self, torrent_id: int | str) -> bool:
        return await self._rpc("torrent-verify", {"ids": [torrent_id]}) is not None

    async def get_stats(self) -> dict | None:
        return await self._rpc("session-stats")

    # ── Per-file selection ────────────────────────────────────────────────────
    # A torrent is often a shelf rather than a game: a hundred titles in one
    # bundle, and no reason to pull the other ninety-nine.

    async def get_files(self, torrent_id: int | str) -> list[dict]:
        """Every file in the torrent, with what has arrived and whether we want it.

        `wanted` and `priority` come back as parallel arrays in `fileStats`,
        indexed the same way as `files` - Transmission's own shape, kept rather
        than flattened, so the index a caller sends back means the same thing at
        both ends.
        """
        result = await self._rpc("torrent-get", {
            "ids":    [torrent_id],
            "fields": ["id", "name", "files", "fileStats"],
        })
        torrents = (result or {}).get("torrents") or []
        if not torrents:
            return []
        t = torrents[0]
        files = t.get("files") or []
        stats = t.get("fileStats") or []
        out = []
        for i, f in enumerate(files):
            st = stats[i] if i < len(stats) else {}
            total = f.get("length") or 0
            done  = f.get("bytesCompleted") or 0
            out.append({
                "index":           i,
                "name":            f.get("name") or "",
                "length":          total,
                "bytes_completed": done,
                "percent":         round(done / total * 100, 1) if total else 0.0,
                "wanted":          bool(st.get("wanted", True)),
                "priority":        st.get("priority", 0),
            })
        return out

    async def set_files_wanted(self, torrent_id: int | str, wanted: list[int],
                               unwanted: list[int]) -> bool:
        """Choose which files to fetch. Empty lists are left out entirely.

        Transmission reads `files-wanted: []` as "want nothing", which is not
        what an empty list means to a caller that simply had nothing to add.
        """
        args: dict = {"ids": [torrent_id]}
        if wanted:
            args["files-wanted"] = wanted
        if unwanted:
            args["files-unwanted"] = unwanted
        if len(args) == 1:
            return True
        return await self._rpc("torrent-set", args) is not None

    async def set_torrent_limits(self, torrent_id: int, values: dict) -> bool:
        """Per-torrent overrides: bandwidth, seed ratio, peer count, priority."""
        if not values:
            return True
        return await self._rpc("torrent-set", {"ids": [torrent_id], **values}) is not None

    async def move_in_queue(self, torrent_id: int, where: str) -> bool:
        """Reorder a torrent in the download queue."""
        method = {
            "top":    "queue-move-top",
            "up":     "queue-move-up",
            "down":   "queue-move-down",
            "bottom": "queue-move-bottom",
        }.get(where)
        if not method:
            return False
        return await self._rpc(method, {"ids": [torrent_id]}) is not None

    # ── Settings ──────────────────────────────────────────────────────────────

    async def set_session(self, settings: dict) -> bool:
        return await self._rpc("session-set", settings) is not None


transmission_handler = TransmissionHandler()
