import { createRouter, createWebHistory, type RouteRecordRaw, type Router } from "vue-router";
import client from "@/services/api/client";
import { useLibrariesStore } from "@/stores/libraries";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "shell",
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
      // ── Custom user library view ────────────────────────────────────────
      {
        path: "lib/:slug",
        name: "collection",
        component: () => import("@/views/games/GamesLibrary.vue"),
        meta: { title: "Library", fullBleed: true },
      },
      // ── Plugin catalogue (store) entry detail ───────────────────────────
      // A storefront listing (PC Ports and the like) that is not a game yet.
      // The GOG model: this page is where you read what it is and pull a build,
      // which turns the listing into a game in the Games library.
      {
        path: "lib/:slug/entry/:id",
        name: "catalog-entry-detail",
        component: () => import("@/views/games/CatalogEntryDetail.vue"),
        meta: { title: "Store", fullBleed: true },
      },
      // ── Collections (game groupings, grouped under container libraries) ──
      {
        path: "collections/:lib",
        name: "collections-lib",
        component: () => import("@/views/collections/CollectionsView.vue"),
        meta: { title: "Collections", fullBleed: true },
      },
      {
        path: "collections/:lib/:slug",
        name: "collection-detail",
        component: () => import("@/views/collections/CollectionsView.vue"),
        meta: { title: "Collection", fullBleed: true },
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
      // ── ROM Downloader (remote ROM sources, browsed live) ───────────────
      // A source's platform grid, then its live ROM list. Admin-only (the
      // endpoints are LIBRARY_ADMIN). Not library routes, so every theme's
      // layout renders these through its fallback <router-view>; each theme
      // adds only the entry tile in its Retro grid.
      {
        path: "rom-sources/:sourceId",
        name: "rom-source-platforms",
        component: () => import("@/views/emulation/RomSourcePlatforms.vue"),
        meta: { title: "ROM Downloader", fullBleed: true, requiresAdmin: true },
      },
      {
        path: "rom-sources/:sourceId/:fsSlug",
        name: "rom-source-list",
        component: () => import("@/views/emulation/RomSourceList.vue"),
        meta: { title: "ROM Downloader", fullBleed: true, requiresAdmin: true },
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
        path: "dashboard",
        name: "dashboard",
        component: () => import("@/views/DashboardView.vue"),
        meta: { title: "Dashboard" },
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
    // Invite links point here (/register?code=…). Public: whoever follows one
    // has no account yet, so the auth guard must let them through.
    path: "/register",
    name: "register",
    component: () => import("@/views/Register.vue"),
    meta: { title: "Create Account", public: true },
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
  // Anything else. Without this the server hands index.html to any path it does
  // not know, the app boots, nothing matches, and <router-view /> draws an empty
  // dark screen that reads as a crash.
  //
  // A redirect rather than a page of its own: a stale bookmark or a mistyped
  // address is not worth a screen, and a static redirect is applied while the
  // route resolves, BEFORE the navigation guard runs - so the guard only ever
  // sees "/" and cannot mistake, say, /emulationXYZ for the emulation library
  // by its path prefix. Deliberately no meta.public: a stranger on a bad URL
  // should still be sent to the login page.
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    redirect: (to) => {
      // Plugin pages are grafted on only once /api/plugins/frontend/routes has
      // answered, which is after the first navigation has already resolved. A
      // deep link to one lands here purely because it arrived early, so keep it
      // and let main.ts retry the moment those routes exist.
      if (to.path.startsWith("/x/")) missedPluginPath = to.fullPath;
      return { name: "home" };
    },
  },
];

/** A /x/... deep link that resolved before the plugin routes were registered. */
let missedPluginPath: string | null = null;

/** Hand back that deep link once, for whoever is ready to retry it. */
export function takeMissedPluginPath(): string | null {
  const path = missedPluginPath;
  missedPluginPath = null;
  return path;
}

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

    // Library visibility: block routes whose library is disabled in the registry
    // (emulation library and couch mode). Fail open if the registry is unknown.
    if (token) {
      const gatedSlug =
        to.path.startsWith("/emulation") ? "emulation"
        : to.path === "/couch" ? "couch"
        : to.path.startsWith("/lib/") ? ((to.params.slug as string) || "")
        : null;
      if (gatedSlug) {
        const libs = useLibrariesStore();
        if (!libs.loaded) await libs.fetch();
        const known = libs.libraries.length > 0;
        if (known && (!libs.has(gatedSlug) || (gatedSlug === "couch" && !libs.has("emulation")))) {
          next({ name: "games-library" });
          return;
        }
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

/**
 * Add plugin-declared pages (from GET /api/plugins/frontend/routes) as children
 * of the LayoutShell so they share the app chrome. Each page lives at
 * `/x/<path>` and renders through PluginPage.vue, which invokes the mount fn the
 * plugin registered via window.__GD__.registerRoute. Idempotent.
 */
export function addPluginRoutes(
  router: Router,
  routes: { path: string; label?: string; icon?: string }[],
): void {
  for (const r of routes || []) {
    const clean = String(r?.path || "").replace(/^\/+/, "");
    if (!clean) continue;
    const name = `plugin-${clean}`;
    if (router.hasRoute(name)) continue;
    router.addRoute("shell", {
      path: `x/${clean}`,
      name,
      component: () => import("@/views/PluginPage.vue"),
      meta: { title: r.label || clean, pluginPath: clean },
    });
  }
}
