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
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    clamav \
    clamav-daemon \
    transmission-daemon \
    transmission-cli \
    ffmpeg \
    lhasa \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

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
