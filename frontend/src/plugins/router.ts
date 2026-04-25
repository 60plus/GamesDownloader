import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";
import client from "@/services/api/client";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    component: () => import("@/layouts/LayoutShell.vue"),
    children: [
      {
        path: "",
        name: "home",
        component: () => import("@/views/GamesHome.vue"),
        meta: { title: "Home", fullBleed: true },
      },
      {
        path: "library",
        name: "library",
        component: () => import("@/views/gog/GogLibrary.vue"),
        meta: { title: "Library", fullBleed: true, requiresAdmin: true },
      },
      {
        path: "library/:id",
        name: "game-detail",
        component: () => import("@/views/gog/GogGameDetail.vue"),
        meta: { title: "Game Detail", fullBleed: true, requiresAdmin: true },
      },
      // ── GamesDownloader Library ─────────────────────────────────────────
      {
        path: "games",
        name: "games-library",
        component: () => import("@/views/games/GamesLibrary.vue"),
        meta: { title: "Games", fullBleed: true },
      },
      {
        path: "games/:id",
        name: "games-detail",
        component: () => import("@/views/games/GamesGameDetail.vue"),
        meta: { title: "Game", fullBleed: true },
      },
      // ── Emulation Library ───────────────────────────────────────────────
      {
        path: "emulation",
        name: "emulation-home",
        component: () => import("@/views/emulation/EmulationHome.vue"),
        meta: { title: "Emulation", fullBleed: true },
      },
      {
        path: "emulation/:platform",
        name: "emulation-library",
        component: () => import("@/views/emulation/EmulationLibrary.vue"),
        meta: { title: "ROMs", fullBleed: true },
      },
      {
        path: "emulation/:platform/:id",
        name: "emulation-detail",
        component: () => import("@/views/emulation/EmulationGameDetail.vue"),
        meta: { title: "ROM Detail", fullBleed: true },
      },
      {
        path: "requests",
        name: "requests",
        component: () => import("@/views/GameRequests.vue"),
        meta: { title: "Game Requests" },
      },
      {
        path: "profile",
        name: "profile",
        component: () => import("@/views/profile/ProfileView.vue"),
        meta: { title: "Profile" },
      },
      {
        path: "settings",
        name: "settings",
        component: () => import("@/views/settings/SettingsIndex.vue"),
        meta: { title: "Settings" },
      },
      {
        path: "admin/users",
        name: "admin-users",
        component: () => import("@/views/admin/AdminUsers.vue"),
        meta: { title: "User Management", requiresAdmin: true },
      },
    ],
  },
  // ── Couch Mode - full-screen, outside LayoutShell ──────────────────────────
  {
    path: "/couch",
    name: "couch",
    component: () => import("@/views/couch/CouchModeSwitcher.vue"),
    meta: { title: "Couch Mode" },
  },
  {
    path: "/dl/:token",
    name: "download",
    component: () => import("@/views/DownloadPage.vue"),
    meta: { title: "Download", public: true },
  },
  {
    path: "/sso-callback",
    name: "sso-callback",
    component: () => import("@/views/SsoCallback.vue"),
    meta: { title: "Signing in…", public: true },
  },
  {
    path: "/login",
    name: "login",
    component: () => import("@/views/Login.vue"),
    meta: { title: "Login", public: true },
  },
  {
    path: "/reset-password",
    name: "reset-password",
    component: () => import("@/views/ResetPassword.vue"),
    meta: { title: "Reset Password", public: true },
  },
  {
    path: "/setup",
    name: "setup",
    component: () => import("@/views/setup/SetupWizard.vue"),
    meta: { title: "Setup", public: true },
  },
];

export function createAppRouter() {
  const router = createRouter({
    history: createWebHistory(),
    routes,
  });

  const SETUP_KEY = "gd3_setup_complete";

  router.beforeEach(async (to, _from, next) => {
    // Check setup completion - use cached localStorage value, refresh from API once per session
    let setupComplete = localStorage.getItem(SETUP_KEY) === "1";

    if (!setupComplete) {
      try {
        const { data } = await client.get("/setup/status");
        setupComplete = data.is_setup_complete === true;
        if (setupComplete) localStorage.setItem(SETUP_KEY, "1");
      } catch {
        // If we can't reach API, allow setup route through
        setupComplete = to.name === "setup";
      }
    }

    if (!setupComplete && to.name !== "setup") {
      next({ name: "setup" });
      return;
    }

    const token = localStorage.getItem("gd3_token");
    const isPublic = to.meta.public === true;

    if (!token && !isPublic) {
      next({ name: "login" });
      return;
    }

    // Admin-only routes: check role stored in token payload
    if (to.meta.requiresAdmin) {
      try {
        const payload = JSON.parse(atob(token!.split(".")[1]));
        if (payload.role !== "admin") {
          next({ name: "games-library" });
          return;
        }
      } catch {
        next({ name: "games-library" });
        return;
      }
    }

    next();
  });

  // After a deployment, old cached JS bundles reference chunk URLs that no
  // longer exist on the server. If a dynamic import fails (chunk 404), reload
  // the page once so the browser fetches the new index.html and fresh chunks.
  // Guard against infinite reload loops with a sessionStorage flag.
  router.onError((err, to) => {
    const msg = String(err?.message ?? '') + String(err?.name ?? '')
    const isChunkError = /dynamically imported|ChunkLoad|preload CSS|failed to fetch/i.test(msg)
    if (isChunkError) {
      const key = '__gd_chunk_reload__'
      const last = Number(sessionStorage.getItem(key) || 0)
      if (Date.now() - last > 10000) {
        sessionStorage.setItem(key, String(Date.now()))
        window.location.href = to.fullPath
      }
    }
  })

  router.afterEach((to) => {
    const pageTitle = to.meta.title as string | undefined
    document.title = pageTitle ? `${pageTitle} - GamesDownloader` : 'GamesDownloader'
  })

  return router;
}
