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

    # ── RPC transport ─────────────────────────────────────────────────────────

    async def _rpc(self, method: str, args: dict | None = None) -> dict | None:
        """Send a Transmission RPC request, handling 409 session renewal."""
        payload = {"method": method, "arguments": args or {}}
        headers = {"X-Transmission-Session-Id": self._session_id}
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(_RPC_URL, json=payload, headers=headers)
                if resp.status_code == 409:
                    self._session_id = resp.headers.get("X-Transmission-Session-Id", "")
                    headers["X-Transmission-Session-Id"] = self._session_id
                    resp = await client.post(_RPC_URL, json=payload, headers=headers)
                if resp.status_code != 200:
                    logger.warning("Transmission RPC %s → HTTP %s", method, resp.status_code)
                    return None
                data = resp.json()
                if data.get("result") != "success":
                    logger.warning("Transmission RPC %s failed: %s", method, data.get("result"))
                    return None
                return data.get("arguments")
        except Exception as exc:
            logger.debug("Transmission RPC error (%s): %s", method, exc)
            return None

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
        "uploadedEver", "isFinished", "addedDate",
    ]

    async def add_torrent_file(
        self,
        torrent_path: str,
        download_dir: str,
        labels: list[str] | None = None,
    ) -> dict | None:
        """Add a .torrent file by path. Returns torrent info dict or None."""
        import base64
        try:
            with open(torrent_path, "rb") as f:
                metainfo = base64.b64encode(f.read()).decode()
        except OSError as exc:
            logger.error("Cannot read torrent file %s: %s", torrent_path, exc)
            return None
        args: dict[str, Any] = {
            "metainfo":     metainfo,
            "download-dir": download_dir,
            "labels":       labels or [_LABEL],
        }
        result = await self._rpc("torrent-add", args)
        if not result:
            return None
        return result.get("torrent-added") or result.get("torrent-duplicate")

    async def add_torrent_url(
        self,
        url: str,
        download_dir: str,
        labels: list[str] | None = None,
    ) -> dict | None:
        """Add a torrent by URL (magnet or http(s) .torrent URL)."""
        args: dict[str, Any] = {
            "filename":     url,
            "download-dir": download_dir,
            "labels":       labels or [_LABEL],
        }
        result = await self._rpc("torrent-add", args)
        if not result:
            return None
        return result.get("torrent-added") or result.get("torrent-duplicate")

    async def get_torrent(self, torrent_id: int) -> dict | None:
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

    async def remove_torrent(self, torrent_id: int, *, delete_data: bool = False) -> bool:
        result = await self._rpc("torrent-remove", {
            "ids":             [torrent_id],
            "delete-local-data": delete_data,
        })
        return result is not None

    async def pause_torrent(self, torrent_id: int) -> bool:
        return await self._rpc("torrent-stop", {"ids": [torrent_id]}) is not None

    async def resume_torrent(self, torrent_id: int) -> bool:
        return await self._rpc("torrent-start", {"ids": [torrent_id]}) is not None

    async def verify_torrent(self, torrent_id: int) -> bool:
        return await self._rpc("torrent-verify", {"ids": [torrent_id]}) is not None

    async def get_stats(self) -> dict | None:
        return await self._rpc("session-stats")

    # ── Settings ──────────────────────────────────────────────────────────────

    async def set_session(self, settings: dict) -> bool:
        return await self._rpc("session-set", settings) is not None


transmission_handler = TransmissionHandler()
