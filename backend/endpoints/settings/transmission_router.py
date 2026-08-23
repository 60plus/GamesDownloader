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
    # ── RPC access ────────────────────────────────────────────────────────────
    # Transmission's own control interface, published on its own port and so
    # reached without passing through anything this application guards. It has
    # always been left open; these let an admin close it. Defaults keep the
    # existing behaviour, so nothing changes for an instance that never visits
    # this screen.
    "rpc_auth_enabled":           False,
    "rpc_username":               "",
    "rpc_whitelist_enabled":      False,
    "rpc_whitelist":              "127.0.0.1,::1,192.168.*.*",
    "rpc_host_whitelist_enabled": False,
    # Transmission's control port answers on its own socket, so nothing this
    # application guards stands in front of it. It is an implementation detail:
    # we speak to it from inside the container and nothing outside needs it.
    # Off means loopback only. Turning it on also requires authentication, or
    # the bind address stays on loopback anyway - see _rpc_bind_address.
    "rpc_expose":                 False,
    # ── The rest of what Transmission can do ──────────────────────────────────
    # Everything below was reachable only through Transmission's own web
    # interface, which is exactly the thing that is now shut. Names and units
    # follow Transmission's own, so what is set here means what it means there.
    #
    # Alternative speed limits, called turtle mode in Transmission. A second
    # pair of caps you can switch to by hand or on a schedule - slow during the
    # day, fast at night.
    "alt_speed_enabled":          False,
    "alt_speed_down":             500,     # KB/s
    "alt_speed_up":               100,     # KB/s
    "alt_speed_time_enabled":     False,
    "alt_speed_time_begin":       540,     # minutes past midnight (09:00)
    "alt_speed_time_end":         1380,    # 23:00
    "alt_speed_time_day":         127,     # bitmask, 127 = every day
    # Queues. Without them a hundred added torrents all start at once and none
    # of them finishes.
    "download_queue_enabled":     True,
    "download_queue_size":        5,
    "seed_queue_enabled":         False,
    "seed_queue_size":            10,
    "queue_stalled_enabled":      True,
    "queue_stalled_minutes":      30,
    # Stop seeding a torrent nothing has asked for in this long.
    "idle_seeding_limit_enabled": False,
    "idle_seeding_limit":         30,      # minutes
    # "required" | "preferred" | "tolerated" - Transmission's own words.
    "encryption":                 "preferred",
    "peer_limit_global":          200,
    "peer_limit_per_torrent":     50,
    "cache_size_mb":              4,
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
    rpc_auth_enabled:        bool  = False
    rpc_username:            str   = ""
    # Write-only. An empty string means "leave whatever is already stored", so
    # saving any other setting cannot silently clear the password.
    rpc_password:            str   = ""
    rpc_whitelist_enabled:   bool  = False
    rpc_whitelist:           str   = "127.0.0.1,::1,192.168.*.*"
    rpc_host_whitelist_enabled: bool = False
    # Deliberate, and refused without rpc_auth_enabled. Nothing outside the
    # container needs this port; see _rpc_bind_address.
    rpc_expose:              bool  = False

    alt_speed_enabled:          bool  = False
    alt_speed_down:             int   = 500
    alt_speed_up:               int   = 100
    alt_speed_time_enabled:     bool  = False
    alt_speed_time_begin:       int   = 540
    alt_speed_time_end:         int   = 1380
    alt_speed_time_day:         int   = 127
    download_queue_enabled:     bool  = True
    download_queue_size:        int   = 5
    seed_queue_enabled:         bool  = False
    seed_queue_size:            int   = 10
    queue_stalled_enabled:      bool  = True
    queue_stalled_minutes:      int   = 30
    idle_seeding_limit_enabled: bool  = False
    idle_seeding_limit:         int   = 30
    encryption:                 str   = "preferred"
    peer_limit_global:          int   = 200
    peer_limit_per_torrent:     int   = 50
    cache_size_mb:              int   = 4


@protected_route(transmission_router.get, "", scopes=[Scope.SETTINGS_READ])
async def get_transmission_settings(request: Request) -> dict:
    saved = {}
    raw = await config_handler.get("transmission_settings")
    if raw:
        try:
            saved = json.loads(raw)
        except Exception:
            saved = {}
    out = {**_DEFAULTS, **saved}
    # The password is write-only: sending it back would put it in every reply
    # to anyone who can read settings, and in the browser's memory, for no gain.
    # The screen only needs to know whether one exists.
    out["rpc_password_set"] = bool(str(saved.get("rpc_password", "")).strip())
    out.pop("rpc_password", None)
    return out


@protected_route(transmission_router.post, "", scopes=[Scope.SETTINGS_WRITE])
async def save_transmission_settings(request: Request, body: TransmissionConfig) -> dict:
    data = body.model_dump()

    # An empty password field means "unchanged", not "clear it". Without this,
    # saving any other setting on this screen would drop the password, and the
    # screen cannot send back what it was never given.
    if not str(data.get("rpc_password", "")).strip():
        prev = await config_handler.get("transmission_settings")
        if prev:
            try:
                data["rpc_password"] = json.loads(prev).get("rpc_password", "")
            except Exception:
                data["rpc_password"] = ""

    await config_handler.set("transmission_settings", json.dumps(data), sensitive=True)
    await config_handler.set("transmission_enabled", str(data["enabled"]).lower())

    # Write live settings.json so Transmission picks them up on next start
    _write_transmission_json(data)

    # Apply speed limits live via RPC (no restart needed)
    try:
        from handler.torrent.transmission_handler import transmission_handler
        # Re-read credentials before talking to it: if authentication was just
        # switched on, the cached "no auth" would make this very call fail.
        transmission_handler.forget_auth()
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
            # Everything below takes effect immediately, which is the point of
            # having it here rather than only in settings.json: turtle mode is
            # useless if switching it on means restarting the container.
            "alt-speed-enabled":        data["alt_speed_enabled"],
            "alt-speed-down":           data["alt_speed_down"],
            "alt-speed-up":             data["alt_speed_up"],
            "alt-speed-time-enabled":   data["alt_speed_time_enabled"],
            "alt-speed-time-begin":     data["alt_speed_time_begin"],
            "alt-speed-time-end":       data["alt_speed_time_end"],
            "alt-speed-time-day":       data["alt_speed_time_day"],
            "download-queue-enabled":   data["download_queue_enabled"],
            "download-queue-size":      data["download_queue_size"],
            "seed-queue-enabled":       data["seed_queue_enabled"],
            "seed-queue-size":          data["seed_queue_size"],
            "queue-stalled-enabled":    data["queue_stalled_enabled"],
            "queue-stalled-minutes":    data["queue_stalled_minutes"],
            "idle-seeding-limit-enabled": data["idle_seeding_limit_enabled"],
            "idle-seeding-limit":       data["idle_seeding_limit"],
            "encryption":               data["encryption"],
            "peer-limit-global":        data["peer_limit_global"],
            "peer-limit-per-torrent":   data["peer_limit_per_torrent"],
            "cache-size-mb":            data["cache_size_mb"],
        }
        if announce_ip:
            session_updates["announce-ip"] = announce_ip
        await transmission_handler.set_session(session_updates)
    except Exception as exc:
        logger.warning("Could not apply live Transmission settings: %s", exc)

    logger.info("Transmission settings saved by %s", getattr(request.state, "user", "?"))
    return {"ok": True, "note": "Port and peer settings require a container restart."}


def _rpc_bind_address(settings: dict) -> str:
    """Which interface Transmission's own control port listens on.

    This used to be the constant "0.0.0.0", while authentication and the
    whitelist both default to off. The container's first run writes 127.0.0.1,
    so the socket was only thrown open the moment an admin saved this screen -
    and saving it to change the seed ratio did it just as thoroughly as saving
    it to change anything else. Unauthenticated Transmission RPC accepts a
    torrent with a download directory of the caller's choosing, which writes
    files anywhere the container can reach.

    Transmission is an implementation detail here: this application talks to it
    from inside the same container, and nothing outside needs the port. So it
    stays on loopback unless an admin has deliberately opened it AND put
    something in front of it.
    """
    if not settings.get("rpc_expose", False):
        return "127.0.0.1"
    # Opening it demands a lock. Refusing to widen the socket without one is
    # the whole point; an admin who wants it open and unguarded can edit
    # settings.json by hand and own that decision explicitly.
    if not settings.get("rpc_auth_enabled", False):
        logger.warning(
            "Transmission RPC exposure requested without authentication - "
            "keeping it on loopback")
        return "127.0.0.1"
    return "0.0.0.0"


def _write_transmission_json(settings: dict) -> None:
    """Write Transmission's native settings.json from our settings dict."""
    exposed = _rpc_bind_address(settings) != "127.0.0.1"
    cfg = {
        "download-dir":                   "/data/downloads/torrents",
        "incomplete-dir":                 "/data/downloads/torrents/.incomplete",
        "incomplete-dir-enabled":         True,
        "rpc-enabled":                    True,
        "rpc-port":                       9091,
        "rpc-bind-address":               _rpc_bind_address(settings),
        # Enabling authentication also teaches this application's own RPC
        # client to sign in, so turning it on does not cut downloads off.
        "rpc-authentication-required":    bool(settings.get("rpc_auth_enabled", False)),
        "rpc-username":                   settings.get("rpc_username", "").strip(),
        "rpc-password":                   settings.get("rpc_password", ""),
        # An exposed port gets the whitelist whether or not the box was ticked.
        # On loopback the whitelist is redundant, and forcing it there would
        # break an instance whose list does not happen to mention 127.0.0.1.
        "rpc-whitelist-enabled":          bool(settings.get("rpc_whitelist_enabled", False)) or exposed,
        "rpc-whitelist":                  settings.get("rpc_whitelist", "").strip(),
        "rpc-host-whitelist-enabled":     bool(settings.get("rpc_host_whitelist_enabled", False)),
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
        # Written here as well as pushed live, so a restart does not undo them.
        "alt-speed-enabled":              settings.get("alt_speed_enabled", False),
        "alt-speed-down":                 settings.get("alt_speed_down", 500),
        "alt-speed-up":                   settings.get("alt_speed_up", 100),
        "alt-speed-time-enabled":         settings.get("alt_speed_time_enabled", False),
        "alt-speed-time-begin":           settings.get("alt_speed_time_begin", 540),
        "alt-speed-time-end":             settings.get("alt_speed_time_end", 1380),
        "alt-speed-time-day":             settings.get("alt_speed_time_day", 127),
        "download-queue-enabled":         settings.get("download_queue_enabled", True),
        "download-queue-size":            settings.get("download_queue_size", 5),
        "seed-queue-enabled":             settings.get("seed_queue_enabled", False),
        "seed-queue-size":                settings.get("seed_queue_size", 10),
        "queue-stalled-enabled":          settings.get("queue_stalled_enabled", True),
        "queue-stalled-minutes":          settings.get("queue_stalled_minutes", 30),
        "idle-seeding-limit-enabled":     settings.get("idle_seeding_limit_enabled", False),
        "idle-seeding-limit":             settings.get("idle_seeding_limit", 30),
        "encryption":                     settings.get("encryption", "preferred"),
        "peer-limit-global":              settings.get("peer_limit_global", 200),
        "peer-limit-per-torrent":         settings.get("peer_limit_per_torrent", 50),
        "cache-size-mb":                  settings.get("cache_size_mb", 4),
    }
    try:
        os.makedirs(os.path.dirname(_TR_CFG_PATH), exist_ok=True)
        with open(_TR_CFG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as exc:
        logger.warning("Could not write Transmission settings.json: %s", exc)

    # The daemon starts from the entrypoint, before this application is up, so
    # it cannot ask the database whether the port was deliberately opened. This
    # marker is how it finds out; without it the entrypoint pulls the bind
    # address back to loopback on every boot. Absence has to mean closed, which
    # is why the failure path below removes it rather than leaving it be.
    marker = os.path.join(os.path.dirname(_TR_CFG_PATH), "rpc-exposed")
    try:
        if exposed:
            with open(marker, "w") as f:
                f.write("Transmission RPC is published deliberately.\n")
        elif os.path.exists(marker):
            os.unlink(marker)
    except Exception as exc:
        logger.warning("Could not update the Transmission exposure marker: %s", exc)
