#!/bin/bash
set -e

PUID=${PUID:-0}
PGID=${PGID:-0}

# ── Auto-generate AUTH_SECRET_KEY when the default placeholder is in effect ──
# The compose file exposes a placeholder ("change-me-in-production") so a
# fresh `docker compose up` works out of the box, but that placeholder MUST
# never be used as the actual signing key. We persist a random 64-char hex
# secret to /data/.secret_key so it survives container restarts; the file is
# created with mode 600 and is the single source of truth from then on.
SECRET_FILE=/data/.secret_key
mkdir -p /data
if [ -z "${GD_AUTH_SECRET_KEY}" ] || [ "${GD_AUTH_SECRET_KEY}" = "change-me-in-production" ]; then
    if [ -s "${SECRET_FILE}" ]; then
        GD_AUTH_SECRET_KEY="$(cat "${SECRET_FILE}")"
        echo "[entrypoint] AUTH_SECRET_KEY: loaded persisted key from ${SECRET_FILE}"
    else
        GD_AUTH_SECRET_KEY="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | xxd -p -c 0)"
        umask 077
        printf '%s' "${GD_AUTH_SECRET_KEY}" > "${SECRET_FILE}"
        chmod 600 "${SECRET_FILE}" 2>/dev/null || true
        echo "[entrypoint] AUTH_SECRET_KEY: generated and persisted a fresh 256-bit key to ${SECRET_FILE}"
        echo "[entrypoint] AUTH_SECRET_KEY: keep this file safe - losing it invalidates all sessions and metadata-backup secrets"
    fi
    export GD_AUTH_SECRET_KEY
fi

# ── ClamAV - fix volume permissions ───────────────────────────────────────────
# /data/clamav is a host-mounted volume created by Docker as root or the host
# user.  freshclam and clamd run as UID 100 (clamav) and will fail with
# "Can't create freshclam.dat" if the directory isn't writable by them.
chown -R clamav:clamav /data/clamav 2>/dev/null || true
chmod 775 /data/clamav 2>/dev/null || true

# ── ClamAV daemon ─────────────────────────────────────────────────────────────
# clamd is started as root BEFORE any privilege drop so it can always access
# /data/clamav (the definitions volume).  The Unix socket has mode 666 so the
# non-root uvicorn process can still connect.
#
# If no definitions exist yet, clamd cannot start - the admin must use
# Settings → Security → ClamAV → "Update Definitions" first.
if ls /data/clamav/*.cvd /data/clamav/*.cld 2>/dev/null | head -1 >/dev/null 2>&1; then
    echo "[entrypoint] ClamAV: definitions found - starting clamd in background..."
    # Start clamd detached.  Loading 3.5M+ signatures takes 30–60 s so we do NOT
    # wait here - uvicorn starts immediately and the UI shows "daemon not running"
    # until clamd finishes loading.  The admin can hit Refresh in the UI.
    clamd --config-file=/etc/clamav/clamd.conf &
    _CLAMD_PID=$!
    echo "[entrypoint] ClamAV: clamd launched (pid ${_CLAMD_PID}), signatures loading in background"
    echo "[entrypoint] ClamAV: use Settings → Security → ClamAV → Refresh once the daemon is ready"
else
    echo "[entrypoint] ClamAV: no definitions found - daemon not started"
    echo "[entrypoint] ClamAV: use Settings → Security → ClamAV → Update Definitions"
fi

# ── Transmission daemon ───────────────────────────────────────────────────────
# Generate settings.json if it doesn't exist yet (first run).
# UPnP/port-forwarding is always disabled - admins open ports manually if needed.
TR_CFG_DIR=/data/config/transmission
TR_CFG=${TR_CFG_DIR}/settings.json
mkdir -p "${TR_CFG_DIR}"
mkdir -p /data/downloads/torrents/.incomplete

if [ ! -f "${TR_CFG}" ]; then
    echo "[entrypoint] Transmission: generating default settings.json"
    cat > "${TR_CFG}" <<'TRCFG'
{
  "download-dir": "/data/downloads/torrents",
  "incomplete-dir": "/data/downloads/torrents/.incomplete",
  "incomplete-dir-enabled": true,
  "rpc-enabled": true,
  "rpc-port": 9091,
  "rpc-bind-address": "127.0.0.1",
  "rpc-authentication-required": false,
  "rpc-whitelist-enabled": false,
  "rpc-host-whitelist-enabled": false,
  "peer-port": 51413,
  "peer-port-random-on-start": false,
  "port-forwarding-enabled": false,
  "dht-enabled": true,
  "utp-enabled": true,
  "lpd-enabled": false,
  "blocklist-enabled": false,
  "start-added-torrents": true,
  "trash-original-torrent-files": false,
  "message-level": 1,
  "umask": 2
}
TRCFG
fi

# Transmission writes settings.json on exit - it must own the config dir
chown -R debian-transmission:debian-transmission "${TR_CFG_DIR}" 2>/dev/null || \
    chown -R nobody:nogroup "${TR_CFG_DIR}" 2>/dev/null || true
chmod 755 "${TR_CFG_DIR}"
chmod 600 "${TR_CFG}" 2>/dev/null || true

transmission-daemon --config-dir "${TR_CFG_DIR}" \
    --logfile "${TR_CFG_DIR}/daemon.log" &
_TR_PID=$!
echo "[entrypoint] Transmission: daemon started (pid ${_TR_PID})"

# Wait up to 10 s for Transmission RPC to become ready
_TR_READY=0
for _i in $(seq 1 20); do
    if curl -sf http://localhost:9091/transmission/rpc >/dev/null 2>&1 || \
       curl -sf http://localhost:9091/transmission/rpc 2>&1 | grep -q "409\|X-Transmission"; then
        _TR_READY=1
        break
    fi
    sleep 0.5
done
if [ "${_TR_READY}" -eq 1 ]; then
    echo "[entrypoint] Transmission: RPC ready"
else
    echo "[entrypoint] Transmission: RPC not yet ready (will retry from app)"
fi

# ── Compile theme plugin .vue files ──────────────────────────────────────────
# Theme plugins in /data/plugins/ may contain .vue files that need Vite compilation.
# The compiled output goes to /app/static/plugin-layouts/ and is loaded by the frontend.
_NODE_BIN=$(command -v node 2>/dev/null || true)
if [ -n "${_NODE_BIN}" ] && [ -f /app/plugin-compiler/compile-theme-plugins.mjs ]; then
    echo "[entrypoint] Compiling theme plugin layouts..."
    cd /app/plugin-compiler
    NODE_PATH=/app/plugin-compiler/node_modules \
        "${_NODE_BIN}" compile-theme-plugins.mjs 2>&1 || \
        echo "[entrypoint] Theme plugin compilation failed (non-fatal)"
    cd /app
fi

if [ "${PUID}" -gt 0 ] && [ "${PGID}" -gt 0 ]; then
    # Create group with PGID if it doesn't already exist
    if ! getent group "${PGID}" > /dev/null 2>&1; then
        groupadd -g "${PGID}" appgroup 2>/dev/null || true
    fi
    # Create user with PUID if it doesn't already exist
    if ! getent passwd "${PUID}" > /dev/null 2>&1; then
        useradd -u "${PUID}" -g "${PGID}" -M -s /bin/sh appuser 2>/dev/null || true
    fi
    # Fix data directory ownership so the app can write to volumes
    chown -R "${PUID}:${PGID}" /data 2>/dev/null || true
    # Drop privileges and execute the main process
    exec gosu "${PUID}:${PGID}" "$@"
fi

# PUID/PGID not set - run as current user (root by default)
exec "$@"
