"""Transmission settings - GET/POST /api/settings/downloads/transmission."""
from __future__ import annotations

import json
import logging
import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler

logger = logging.getLogger(__name__)

transmission_router = APIRouter(
    prefix="/api/settings/downloads/transmission", tags=["transmission-settings"]
)

_TR_CFG_PATH = "/data/config/transmission/settings.json"

_DEFAULTS = {
    "enabled":                    False,
    "peer_port":                  51413,
    "peer_port_random":           False,
    "port_forwarding_enabled":    False,   # UPnP - off by default
    "announce_ip":                "",      # external IP/host override (empty = auto)
    "dht_enabled":                True,
    "utp_enabled":                True,
    "lpd_enabled":                False,
    "blocklist_enabled":          False,
    "speed_limit_down_enabled":   False,
    "speed_limit_down":           0,
    "speed_limit_up_enabled":     False,
    "speed_limit_up":             0,
    "ratio_limit_enabled":        False,
    "ratio_limit":                2.0,
    "trash_original":             False,
    "message_level":              1,
}


class TransmissionConfig(BaseModel):
    enabled:                 bool  = False
    peer_port:               int   = 51413
    peer_port_random:        bool  = False
    port_forwarding_enabled: bool  = False
    announce_ip:             str   = ""   # IP/hostname announced to trackers
    dht_enabled:             bool  = True
    utp_enabled:             bool  = True
    lpd_enabled:             bool  = False
    blocklist_enabled:       bool  = False
    speed_limit_down_enabled: bool = False
    speed_limit_down:        int   = 0
    speed_limit_up_enabled:  bool  = False
    speed_limit_up:          int   = 0
    ratio_limit_enabled:     bool  = False
    ratio_limit:             float = 2.0
    trash_original:          bool  = False
    message_level:           int   = 1


@protected_route(transmission_router.get, "", scopes=[Scope.SETTINGS_READ])
async def get_transmission_settings(request: Request) -> dict:
    raw = await config_handler.get("transmission_settings")
    if raw:
        try:
            saved = json.loads(raw)
            return {**_DEFAULTS, **saved}
        except Exception:
            pass
    return _DEFAULTS.copy()


@protected_route(transmission_router.post, "", scopes=[Scope.SETTINGS_WRITE])
async def save_transmission_settings(request: Request, body: TransmissionConfig) -> dict:
    data = body.model_dump()
    await config_handler.set("transmission_settings", json.dumps(data))
    await config_handler.set("transmission_enabled", str(data["enabled"]).lower())

    # Write live settings.json so Transmission picks them up on next start
    _write_transmission_json(data)

    # Apply speed limits live via RPC (no restart needed)
    try:
        from handler.torrent.transmission_handler import transmission_handler
        announce_ip = data.get("announce_ip", "").strip()
        session_updates: dict = {
            "speed-limit-down-enabled": data["speed_limit_down_enabled"],
            "speed-limit-down":         data["speed_limit_down"],
            "speed-limit-up-enabled":   data["speed_limit_up_enabled"],
            "speed-limit-up":           data["speed_limit_up"],
            "seedRatioLimit":           data["ratio_limit"],
            "seedRatioLimited":         data["ratio_limit_enabled"],
            "dht-enabled":              data["dht_enabled"],
            "utp-enabled":              data["utp_enabled"],
            "lpd-enabled":              data["lpd_enabled"],
            "announce-ip-enabled":      bool(announce_ip),
        }
        if announce_ip:
            session_updates["announce-ip"] = announce_ip
        await transmission_handler.set_session(session_updates)
    except Exception as exc:
        logger.warning("Could not apply live Transmission settings: %s", exc)

    logger.info("Transmission settings saved by %s", getattr(request.state, "user", "?"))
    return {"ok": True, "note": "Port and peer settings require a container restart."}


def _write_transmission_json(settings: dict) -> None:
    """Write Transmission's native settings.json from our settings dict."""
    cfg = {
        "download-dir":                   "/data/downloads/torrents",
        "incomplete-dir":                 "/data/downloads/torrents/.incomplete",
        "incomplete-dir-enabled":         True,
        "rpc-enabled":                    True,
        "rpc-port":                       9091,
        "rpc-bind-address":               "0.0.0.0",
        "rpc-authentication-required":    False,
        "rpc-whitelist-enabled":          False,
        "rpc-host-whitelist-enabled":     False,
        "start-added-torrents":           True,
        "trash-original-torrent-files":   settings.get("trash_original", False),
        "umask":                          2,
        "peer-port":                      settings.get("peer_port", 51413),
        "peer-port-random-on-start":      settings.get("peer_port_random", False),
        "port-forwarding-enabled":        settings.get("port_forwarding_enabled", False),
        "announce-ip-enabled":            bool(settings.get("announce_ip", "").strip()),
        "announce-ip":                    settings.get("announce_ip", "").strip(),
        "dht-enabled":                    settings.get("dht_enabled", True),
        "utp-enabled":                    settings.get("utp_enabled", True),
        "lpd-enabled":                    settings.get("lpd_enabled", False),
        "blocklist-enabled":              settings.get("blocklist_enabled", False),
        "speed-limit-down-enabled":       settings.get("speed_limit_down_enabled", False),
        "speed-limit-down":               settings.get("speed_limit_down", 0),
        "speed-limit-up-enabled":         settings.get("speed_limit_up_enabled", False),
        "speed-limit-up":                 settings.get("speed_limit_up", 0),
        "ratio-limit":                    settings.get("ratio_limit", 2.0),
        "ratio-limit-enabled":            settings.get("ratio_limit_enabled", False),
        "message-level":                  settings.get("message_level", 1),
    }
    try:
        os.makedirs(os.path.dirname(_TR_CFG_PATH), exist_ok=True)
        with open(_TR_CFG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as exc:
        logger.warning("Could not write Transmission settings.json: %s", exc)
