# GamesDownloaderV3 — Multi-stage Dockerfile
# Stage 1: Build Vue frontend
# Stage 2: Download EmulatorJS (self-hosted, no CDN dependency)
# Stage 3: Python backend + built frontend + EmulatorJS

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

# ── Stage 3: Backend + serve ─────────────────────────────────────────────────
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
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Plugin compiler: Vite + Vue (cached layer - rarely changes)
COPY scripts/compile-theme-plugins.mjs /app/plugin-compiler/compile-theme-plugins.mjs
RUN cd /app/plugin-compiler \
    && npm init -y >/dev/null 2>&1 \
    && npm install --no-fund --no-audit vite @vitejs/plugin-vue vue >/dev/null 2>&1

# ClamAV configuration
COPY docker/clamd.conf /etc/clamav/clamd.conf
COPY docker/freshclam.conf /etc/clamav/freshclam.conf

# Python deps (cached layer - changes only when requirements.txt changes)
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend source (changes frequently - keep last)
COPY backend/ .

# Built frontend - served as static files by FastAPI
COPY --from=frontend-build /build/dist /app/static

# EmulatorJS self-hosted (served at /emulatorjs/data/)
COPY --from=emulatorjs-stage /emulatorjs /app/static/emulatorjs

# Data directories (clamav = virus definitions volume)
RUN mkdir -p /data/{config,resources,roms,games,downloads,plugins,redis,clamav} \
    && mkdir -p /data/config/transmission \
    && mkdir -p /data/downloads/torrents/.incomplete \
    && mkdir -p /app/static/plugin-layouts

EXPOSE 8080
# Transmission RPC (9091) binds to localhost only — NOT exposed by default.
# If needed, expose manually in docker-compose.yml with proper auth.

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Entrypoint handles optional PUID/PGID privilege drop
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:socket_app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
