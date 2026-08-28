# GamesDownloaderV3 — Multi-stage Dockerfile
# Stage 1: Build Vue frontend
# Stage 2: Download EmulatorJS (self-hosted, no CDN dependency)
# Stage 3: Download vAmigaWeb (self-hosted, Amiga WHDLoad only)
# Stage 4: Python backend + built frontend + both emulators

# ── Stage 1: Frontend build ──────────────────────────────────────────────────
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-fund 2>/dev/null || npm install --no-fund
RUN npm audit --audit-level=high || true
COPY frontend/ .
RUN npm run build

# ── Stage 2: Download EmulatorJS ─────────────────────────────────────────────
FROM alpine:3.20 AS emulatorjs-stage
RUN apk add --no-cache wget 7zip ca-certificates

ARG EMULATORJS_VERSION=4.2.3
ARG EMULATORJS_SHA256=07d451bc06fa3ad04ab30d9b94eb63ac34ad0babee52d60357b002bde8f3850b

RUN wget -q "https://github.com/EmulatorJS/EmulatorJS/releases/download/v${EMULATORJS_VERSION}/${EMULATORJS_VERSION}.7z" && \
    echo "${EMULATORJS_SHA256}  ${EMULATORJS_VERSION}.7z" | sha256sum -c - && \
    7z x -y "${EMULATORJS_VERSION}.7z" -o/emulatorjs && \
    rm -f "${EMULATORJS_VERSION}.7z"

# ── Stage 3: Download vAmigaWeb ──────────────────────────────────────────────
# EmulatorJS covers every platform in the library except one case: its Amiga
# core aborts on WHDLoad hard-drive installs, which is the form most of the
# Amiga catalogue takes.  vAmigaWeb runs them, so WHDLoad titles are handed to
# this emulator and everything else stays on EmulatorJS.
#
# This repository is the project's own binary deployment; sources and licence
# (GPL-3.0) live at https://github.com/vAmigaWeb/vAmigaWeb.  Pinned to a commit
# rather than a tag: the deployment repo publishes no releases, and the commit
# hash is itself the integrity check that a downloaded archive would need.
FROM alpine:3.20 AS vamigaweb-stage
RUN apk add --no-cache git ca-certificates

ARG VAMIGAWEB_COMMIT=03c6f00eb73a742625fb36e32b2ea447e3b98289

RUN git init -q /vamigaweb && cd /vamigaweb && \
    git remote add origin https://github.com/vAmigaWeb/vAmigaWeb.github.io.git && \
    git fetch -q --depth 1 origin "${VAMIGAWEB_COMMIT}" && \
    git checkout -q FETCH_HEAD && \
    test -f vAmiga.wasm && \
    # Drop what a self-hosted instance never serves: the upstream site's own
    # documentation and demo downloads (25 MB), the debug console, the source
    # maps and the in-app script editor.
    rm -rf .git doc js/eruda.js js/cm6 js/*.map && \
    # Remove the upstream site's analytics beacon.  A self-hosted install must
    # not phone a third party on every launch, and nothing else references it.
    sed -i 's#<script src=https://cloud\.umami\.is/script\.js[^>]*></script>##' index.html && \
    ! grep -q "umami" index.html

# ── Stage 4: Backend + serve ─────────────────────────────────────────────────
FROM python:3.13-slim

# System deps + Node.js (for plugin .vue compilation on startup)
# Combined into one layer to reduce image size
#
# `upgrade` runs before the installs because the base image is rebuilt on its
# own schedule and this one is not. Between the two there is always a window
# in which Debian has published a security fix that the base does not yet
# carry, and a build that never upgrades never takes it. Today that window
# holds openssl and nothing else: the upgrade moves three packages.
#
# gosu is deliberately absent, and removing it was the single largest
# improvement available here. It is one small Go binary, called once at
# startup to step down from root, and it carries a statically linked Go
# runtime into the image along with 46 advisories against Go's networking and
# TLS libraries - code gosu never enters. Debian will not rebuild it against a
# newer Go on this timescale, so those advisories stay as long as the binary
# does. setpriv does the same job, ships in util-linux, and is already here
# because Debian installs util-linux everywhere. See entrypoint.sh.
#
# ffmpeg, by contrast, has to stay, and it is worth writing down why because
# it looks so removable. One feature needs it: yt-dlp gluing together the
# separate video and audio streams YouTube serves, for the trailer download
# in the metadata editor. It is expensive company - it brings the critical
# libtiff advisory in through gdk-pixbuf and three more in cjson through
# librist - so it was removed, and that broke every trailer button. Measured
# from inside the image on 2026-08-28: of the 53 and 48 formats YouTube
# offered for two videos, none carried video and audio together. The
# pre-merged streams a no-ffmpeg download would need are simply not served
# any more. If this is worth another attempt, the way through is a smaller
# ffmpeg carrying only the mp4 muxer, pinned by checksum like EmulatorJS.
#
# Node stays on NodeSource, and that was tested rather than assumed. Debian
# ships 20.19.2 with its own security backports, which sounded strictly
# better than NodeSource's un-backported 22.23.2, and Vite 8 accepts it
# (^20.19.0 || >=22.12.0). Built and measured on 2026-08-28, it went the
# other way: critical advisories against the image went from 7 to 11.
#
# Debian unbundles what node vendors, so node-undici arrives as its own
# package carrying two criticals and eight highs of its own, and it cannot be
# dropped - removing it removes nodejs. NodeSource keeps the same undici
# inside the binary where a scanner cannot see it, so part of that difference
# is honesty rather than exposure. What is not ambiguous: 20 is an older LTS
# line than 22, both answer "no fix available", and the swap saved 40 MB
# rather than the 225 MB the package listing suggested.
#
# The `clamav` package is gone too. It carries clamscan, sigtool and clambc,
# none of which this project ever invokes: scanning goes through clamd over
# its socket and updates through freshclam, which come from clamav-daemon and
# clamav-freshclam. clamav-daemon does not depend on it.
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    clamav-daemon \
    transmission-daemon \
    transmission-cli \
    ffmpeg \
    lhasa \
    mame-tools \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# mame-tools ships nine programs and GD uses one of them. The other eight are
# emulator-side tooling for cassettes, floppies and cartridge images, and they
# are what pulls MAME's GPL-2.0-or-later format library into the picture -
# chdman itself carries a BSD-3-Clause header. Dropping them keeps the image
# to what it actually runs, and the package's own copyright file stays where
# apt put it either way.
RUN set -eu; \
    cd /usr/bin; \
    rm -f castool floptool imgtool jedutil ldresample ldverify romcmp unidasm; \
    command -v chdman >/dev/null || { echo "chdman missing after install"; exit 1; }

# Plugin compiler: Vite + Vue (cached layer - rarely changes).
# Versions pinned to the known-good set. npm has a long-standing bug where it
# silently skips a package's platform-specific optional dependency when the
# install hits a transient hiccup (npm/cli#4828). For Vite/rolldown that drops
# the @rolldown/binding-<platform> native .node, which only surfaces at runtime
# as "Cannot find native binding". Retry until the binding is actually present
# (arch-agnostic glob), and fail the build loudly if it never installs.
COPY scripts/compile-theme-plugins.mjs /app/plugin-compiler/compile-theme-plugins.mjs
RUN cd /app/plugin-compiler \
    && npm init -y >/dev/null 2>&1 \
    && for i in 1 2 3; do \
         npm install --no-fund --no-audit vite@8.0.16 @vitejs/plugin-vue@6.0.7 vue@3.5.38 >/dev/null 2>&1; \
         if ls node_modules/@rolldown/binding-*/*.node >/dev/null 2>&1; then break; fi; \
         echo "plugin-compiler: rolldown native binding missing, retry $i/3"; \
         rm -rf node_modules package-lock.json; \
       done \
    && ls node_modules/@rolldown/binding-*/*.node >/dev/null 2>&1 \
       || { echo "FATAL: rolldown native binding failed to install"; exit 1; }

# npm has now done the only job it has here, and everything past this point
# reaches node directly: entrypoint.sh runs compile-theme-plugins.mjs, and
# nothing in the backend shells out to npm. What would otherwise stay behind
# is npm's own dependency tree, which accounted for 16 advisories against the
# published image including a critical one in tar. node and the compiler's
# node_modules are untouched; only the package manager goes.
RUN set -eu; \
    rm -rf /usr/lib/node_modules/npm /usr/bin/npm /usr/bin/npx; \
    command -v node >/dev/null || { echo "node missing after npm removal"; exit 1; }; \
    node -e 'process.exit(0)'; \
    ! command -v npm >/dev/null

# ClamAV configuration
COPY docker/clamd.conf /etc/clamav/clamd.conf
COPY docker/freshclam.conf /etc/clamav/freshclam.conf

# Python deps (cached layer - changes only when requirements.txt changes)
WORKDIR /app
COPY backend/requirements.txt .
# pip itself is upgraded first. It is not only build tooling here: installing a
# plugin runs `pip install --target` inside the running container, so the pip
# that ships in the base image sits in a live code path handling packages an
# admin points it at. The version python:3.13-slim carries has six advisories
# against it; the application's own dependencies have none.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# The licences themselves, which the image has never carried. The comment on
# the vAmigaWeb layer below sends the reader to NOTICE.md for the source link
# GPL-3.0 requires, and until now that file was not in the image at all: a
# pointer to something nobody running this could open. Both licences travel
# with the thing they cover.
COPY LICENSE LICENSE-ASSETS NOTICE.md /app/

# Backend source (changes frequently - keep last)
COPY backend/ .

# Built frontend - served as static files by FastAPI
COPY --from=frontend-build /build/dist /app/static

# EmulatorJS self-hosted (served at /emulatorjs/data/)
COPY --from=emulatorjs-stage /emulatorjs /app/static/emulatorjs

# vAmigaWeb self-hosted (served at /vamigaweb/) - Amiga WHDLoad only.
# GPL-3.0; see NOTICE.md for the source link the licence requires.
COPY --from=vamigaweb-stage /vamigaweb /app/static/vamigaweb

# Data directories (clamav = virus definitions volume)
RUN mkdir -p /data/{config,resources,games,downloads,plugins,redis,clamav,firmware} \
    && mkdir -p /data/config/transmission \
    && mkdir -p /data/downloads/torrents/.incomplete \
    && mkdir -p /app/static/plugin-layouts

EXPOSE 8080
# Transmission RPC (9091) binds to localhost only and is not published.
# This was true of the first-run settings.json and untrue the moment an admin
# saved the Transmission settings screen, which rewrote the bind address to
# 0.0.0.0 while authentication defaulted to off. It is now true on both paths:
# opening the port takes a deliberate toggle AND authentication, and
# docker-compose.yml no longer maps it.

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Entrypoint handles optional PUID/PGID privilege drop
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
