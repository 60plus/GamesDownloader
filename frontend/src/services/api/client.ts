/**
 * Centralised Axios client with interceptors.
 *
 * - Adds Bearer token from localStorage
 * - On 401: tries to refresh access token using refresh_token, then retries
 * - If refresh fails: clears tokens and redirects to /login
 * - Queues concurrent requests while refresh is in progress
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

const TOKEN_KEY   = "gd3_token";
const REFRESH_KEY = "gd3_refresh";
const SETUP_KEY   = "gd3_setup_complete";

const client: AxiosInstance = axios.create({
  baseURL: "/api",
  timeout: 30_000,
});

// ── Request interceptor: attach token ────────────────────────────────────────
client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Token refresh state ───────────────────────────────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach(p => error ? p.reject(error) : p.resolve(token!));
  failedQueue = [];
}

function doLogout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

// ── Response interceptor: refresh on 401, handle 503 setup guard ─────────────
client.interceptors.response.use(
  response => response,
  async error => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    const status   = error.response?.status;

    // ── 401: attempt token refresh ──────────────────────────────────────────
    if (status === 401 && !original._retry) {
      // Never try to refresh on auth endpoints themselves
      const url = original.url ?? "";
      if (url.includes("/auth/refresh") || url.includes("/auth/login")) {
        doLogout();
        return Promise.reject(error);
      }

      // If a refresh is already running, queue this request
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          if (original.headers) original.headers.Authorization = `Bearer ${token}`;
          return client(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      const refreshToken = localStorage.getItem(REFRESH_KEY);
      if (!refreshToken) {
        isRefreshing = false;
        processQueue(error, null);
        doLogout();
        return Promise.reject(error);
      }

      try {
        // Use plain axios (not the intercepted client) to avoid infinite loop
        const { data } = await axios.post("/api/auth/refresh", { refresh_token: refreshToken });
        localStorage.setItem(TOKEN_KEY, data.access_token);
        localStorage.setItem(REFRESH_KEY, data.refresh_token);
        processQueue(null, data.access_token);
        if (original.headers) original.headers.Authorization = `Bearer ${data.access_token}`;
        return client(original);
      } catch (refreshErr) {
        processQueue(refreshErr, null);
        doLogout();
        return Promise.reject(refreshErr);
      } finally {
        isRefreshing = false;
      }
    }

    // ── 503: setup not complete ─────────────────────────────────────────────
    if (
      status === 503 &&
      error.response?.data?.detail === "Setup not complete"
    ) {
      localStorage.removeItem(SETUP_KEY);
      if (window.location.pathname !== "/setup") {
        window.location.href = "/setup";
      }
    }

    return Promise.reject(error);
  }
);

export default client;
