import { createApp } from "vue";
import * as VueRuntime from "vue";
import * as VueRouterRuntime from "vue-router";
import App from "./App.vue";
// Country-flag icons (CSS sprites). Replaces the bare emoji flags that
// failed to render on Windows Chrome / Edge - the package ships
// `.fi.fi-<iso2>` classes plus the SVG masks they reference.
import "flag-icons/css/flag-icons.min.css";
import { createAppRouter, addPluginRoutes } from "./plugins/router";
import { createAppPinia } from "./plugins/pinia";
import { vuetify } from "./plugins/vuetify";
import { registerTheme, registerPluginLayout, registerPluginCouchMode, registerMetadataTab, registerDetailRow, resolveDetailRows, registerHomeSections, getHomeSections, registerManagedSettings, isSettingManaged, registerPluginRoute, pluginNavRoutes, setPluginNavRoutes } from "./themes/index";
import { useCouchNav, navPaused as couchNavPaused } from "./composables/useCouchNav";
import { useDialog } from "./composables/useDialog";
import { useCouchTheme } from "./composables/useCouchTheme";
import { getEjsCore } from "./utils/ejsCores";
import { buildLanguageList } from "./utils/langMap";
import { sanitizeHtml } from "./utils/sanitize";
import i18n from "./i18n";
import { useAuthStore } from "./stores/auth";
import { useSocketStore } from "./stores/socket";
import { useThemeStore } from "./stores/theme";
import { useLibrariesStore } from "./stores/libraries";
import { useCollectionsStore } from "./stores/collections";
import { useNotificationStore } from "./stores/notifications";
import { LIBRARY_ICONS, LIBRARY_ICON_NAMES, libraryIconMarkup } from "./lib/libraryIcons";
import libraryActions from "./lib/libraryActions";
import catalogActions from "./lib/catalogActions";
import dashboardActions from "./lib/dashboardActions";
import client from "./services/api/client";

import DownloadManager from "./components/gog/DownloadManager.vue";
import DownloadDialog from "./components/gog/DownloadDialog.vue";
import RandomGamePicker from "./components/RandomGamePicker.vue";
import AmbientBackground from "./components/common/AmbientBackground.vue";
import GameRequestDialog from "./components/GameRequestDialog.vue";
import { openMetadataEditor, openCollectionEditor, closeMetadataEditor, closeCollectionEditor, openRomMetadataEditor, closeRomMetadataEditor } from "./lib/pluginUi";
import { openAbout } from "./lib/about";

import "@mdi/font/css/materialdesignicons.css";
import "./styles/base.css";
import "./styles/glass.css";
import "./styles/skins.css";

const app = createApp(App);

app.use(createAppPinia());
const router = createAppRouter();
app.use(router);
app.use(vuetify);

// Register shared components globally so plugin themes can use them
app.component("DownloadManager", DownloadManager);
// GOG server-download dialog (v-model + gog-id + game-title) so a plugin theme
// rendering its own GOG detail page reuses the core download flow.
app.component("DownloadDialog", DownloadDialog);
app.component("RandomGamePicker", RandomGamePicker);
app.component("AmbientBackground", AmbientBackground);
// Game request dialog (visible + default-platform + @close) so plugin themes
// can offer the "Request a game" flow without re-implementing it.
app.component("GameRequestDialog", GameRequestDialog);

// ── Expose plugin API on window for compiled theme plugins ──────────────────
// Theme plugins compiled on container startup import from window.__GD__
// instead of bundled node_modules.
//
// SECURITY: plugins get a RESTRICTED view of stores - no direct token access.
// The API client is shared (it already has the Bearer interceptor) because
// plugins need to fetch data. This is equivalent to browser extensions having
// access to page cookies - the admin installed the plugin knowingly.

// Auth store proxy: expose user info and role but NOT the raw JWT token
// Returns a factory function (like useAuthStore) that always returns the same proxy
function createSafeAuthStore() {
  let _proxy: any = null;
  return () => {
    if (_proxy) return _proxy;
    const store = useAuthStore();
    _proxy = new Proxy(store, {
      get(target, prop) {
        if (prop === 'token' || prop === 'refreshToken') return undefined;
        return (target as any)[prop];
      }
    });
    return _proxy;
  };
}

// Progress events plugins may subscribe to via __GD__.events - a narrow,
// read-only bridge; raw socket emit/on stays off-limits.
const PLUGIN_SOCKET_EVENTS = new Set([
  "torrent:download_progress",
  "torrent:download_complete",
  "torrent:download_error",
  "upload:url_progress",
  "upload:url_complete",
  "upload:url_error",
  // Packaging progress, so a theme can follow __GD__.library.package() jobs
  // ({ id, status: "packaging"|"completed"|"failed", done, total }).
  "download:packaging",
]);

function createPluginEventBridge() {
  return {
    /** Subscribe to a whitelisted server event. Returns an unsubscribe fn. */
    on(event: string, cb: (data: any) => void): () => void {
      if (!PLUGIN_SOCKET_EVENTS.has(event)) {
        console.warn(`[__GD__.events] event "${event}" is not exposed to plugins`);
        return () => {};
      }
      const store = useSocketStore();
      store.socket?.on(event, cb);
      return () => store.socket?.off(event, cb);
    },
  };
}

// Socket store proxy: expose sync progress but NOT raw emit/on
function createSafeSocketStore() {
  let _proxy: any = null;
  return () => {
    if (_proxy) return _proxy;
    const store = useSocketStore();
    _proxy = new Proxy(store, {
      get(target, prop) {
        if (prop === 'socket') return undefined;
        return (target as any)[prop];
      }
    });
    return _proxy;
  };
}

(window as any).__GD__ = {
  Vue: VueRuntime,
  VueRouter: VueRouterRuntime,
  stores: {
    auth: createSafeAuthStore(),
    socket: createSafeSocketStore(),
    theme: useThemeStore,
    libraries: useLibrariesStore,
    collections: useCollectionsStore,
  },
  api: client,
  // Narrow subscription bridge for server progress events (whitelist only):
  // __GD__.events.on("upload:url_progress", cb) -> unsubscribe fn.
  events: createPluginEventBridge(),
  // Shared utility helpers for theme/plugin authors (plugins cannot import
  // @/utils directly - they only have window.__GD__). buildLanguageList(dict)
  // returns the same {name, flag} list the built-in themes use for language
  // flags; sanitizeHtml(html) is the same sanitizer used for descriptions.
  utils: {
    buildLanguageList,
    sanitizeHtml,
  },
  registerTheme,
  registerPluginLayout,
  registerPluginCouchMode,
  registerMetadataTab,
  registerDetailRow,
  // Consumer side of registerDetailRow, for plugin themes that render their
  // own game detail pages and must show plugin rows natively.
  resolveDetailRows,
  // Custom plugin pages. A plugin's backend hook frontend_get_routes declares
  // {path,label,icon} (fetched below into the router + `pluginRoutes`), and its
  // injected JS calls registerRoute({path, mount}) to render the page content.
  // Themes read `pluginRoutes` (reactive) to show nav links to /x/<path>.
  registerRoute: registerPluginRoute,
  pluginRoutes: pluginNavRoutes,
  // Theme-declared home sections. A theme layout with its own extra home-page
  // sections (trailer shelf, genre tiles...) calls register() on mount (and the
  // returned unregister on unmount); Settings -> Libraries then offers per-user
  // on/off toggles for them. The theme reads isHidden(id) to skip a section and
  // re-reads on the `gd-theme-updated` DOM event (fired when a toggle changes).
  homeSections: {
    /** register([{id, label}]) -> unregister(). `label` may be an i18n key. */
    register: registerHomeSections,
    /** The active theme's registered sections (reactive; used by Settings). */
    list: getHomeSections,
    /** Has this user switched the section off? (per-user, per-theme) */
    isHidden: (id: string) => useThemeStore().isHomeSectionHidden(id),
    /** `ids` sorted into this user's chosen order (unmoved ones keep the
     *  theme's own order, at the end). Lay sections out with this. */
    order: (ids: string[]) => useThemeStore().orderHomeSections(ids),
    /** A per-section switch this theme declared in register()'s `options`.
     *  Falls back to the `default` declared there until the user touches it, so
     *  register() stays the single source of truth - passing a different `dflt`
     *  here is what let Settings show a switch off while the page rendered it
     *  on. `dflt` remains for callers with no registration to read. */
    isOptionOn: (sectionId: string, optId: string, dflt?: boolean) => {
      const declared = getHomeSections()
        .find((s) => s.id === sectionId)?.options
        ?.find((o) => o.id === optId)?.default;
      return useThemeStore().isHomeSectionOptionOn(
        sectionId, optId, dflt ?? declared ?? false,
      );
    },
    // ── Writes, for a theme with its own on-page layout editor ──────────────
    // Persisted per-user, per-theme and synced to the server like every other
    // theme setting, so a layout follows the user to another browser. Ids the
    // user never arranged keep the theme's own order (see order()), which is
    // what lets sections that come and go at runtime - a new collection, a
    // library you just created - appear without disturbing the saved layout.
    /** Persist the section order the user arranged. */
    setOrder: (ids: string[]) => useThemeStore().setHomeSectionOrder(ids),
    /** Show or hide one section (explicit, unlike toggle). */
    setHidden: (id: string, hidden: boolean) =>
      useThemeStore().setHomeSectionHidden(id, hidden),
    /** Flip one section's visibility. */
    toggle: (id: string) => useThemeStore().toggleHomeSection(id),
    /** Set one of the per-section switches declared in register(). */
    setOption: (sectionId: string, optId: string, on: boolean) =>
      useThemeStore().setHomeSectionOption(sectionId, optId, on),
    /** Drop the user's whole layout (order, hidden, options) for this theme and
     *  fall back to what register() declared. Leaves the theme's other
     *  settings, such as skin or cover size, untouched. */
    reset: () => useThemeStore().resetHomeSectionLayout(),
  },
  // A theme that ships its own editor for these settings claims them here, and
  // Settings stops drawing its own controls for them. Without this the same
  // switches live in two places and quietly drift apart.
  managedSettings: {
    /** claim(["homeSections", ...]) -> unclaim(). */
    register: registerManagedSettings,
    /** Is this setting handled by the active theme? */
    isManaged: isSettingManaged,
  },
  // Public, theme/plugin-facing API for the per-theme "recently added" home
  // feed. Themes call recentLibraries.get() to learn which library slugs the
  // user wants a recently-added row for (already filtered to visible, non-couch
  // libraries), and re-read it on the `gd-theme-updated` DOM event. This lets a
  // 3rd-party theme honour the user's choice without reaching into store
  // internals or requiring any change to GD itself.
  recentLibraries: {
    /** Raw stored selection (null = "all libraries"). */
    getRaw: () => useThemeStore().getRecentLibraries(),
    /** Resolved slugs to show a recently-added row for (visible, non-couch). */
    get: () => {
      const raw = useThemeStore().getRecentLibraries();
      const vis = useLibrariesStore().visible
        .filter((l: { kind: string }) => l.kind !== "couch")
        .map((l: { slug: string }) => l.slug);
      return raw === null ? vis : vis.filter((s: string) => raw.includes(s));
    },
    /** Convenience: should this library show a recently-added row? */
    isEnabled: (slug: string) => {
      const lib = useLibrariesStore();
      if (!lib.has(slug) || lib.isHidden(slug)) return false;
      const raw = useThemeStore().getRecentLibraries();
      return raw === null || raw.includes(slug);
    },
    /** Persist a new selection (per-user, per-theme). */
    set: (slugs: string[]) => useThemeStore().setRecentLibraries(slugs),
  },
  // Public collections API (admin-curated game groupings). The Collections tab
  // already appears in stores.libraries().visible (slug "collections", route
  // "/collections"); these let a theme render its grid / detail data-driven.
  collections: {
    /** Reactive list of collections (read after boot, or call fetch() first). */
    list: () => useCollectionsStore().list,
    /** (Re)load the collections list. */
    fetch: () => useCollectionsStore().fetch(),
    /** A loaded collection by slug. */
    bySlug: (slug: string) => useCollectionsStore().bySlug(slug),
    /** A collection's full detail incl. its member games. */
    get: (slug: string) => useCollectionsStore().get(slug),
    /** The collection slugs a game belongs to. */
    forGame: (gameId: number | string) => useCollectionsStore().forGame(gameId),
    /** Route for a single collection (nested under its container library). */
    route: (slug?: string) => useCollectionsStore().route(slug),
    /** Route for a container library's collection grid. */
    libraryRoute: (librarySlug: string) => useCollectionsStore().libraryRoute(librarySlug),
  },
  // Unified, library-aware "add content" API. A theme keeps its own dialogs but
  // calls these instead of raw api.post(), so create-game / upload-file /
  // upload-from-url / add-torrent / scan all honour the current library (folder
  // + membership) with no per-theme logic. The URL-upload and torrent calls run
  // server-side and report progress over socket.io - use __GD__.events.on(...)
  // to follow "upload:url_*" / "torrent:download_*" keyed on the returned id.
  //   library.createGame({title, library})            -> game (has .id)
  //   library.uploadFile(gameId, file, {os, fileType, onProgress})
  //   library.uploadFromUrl(gameId, {url, os, fileType}) -> {id, filename}
  //   library.addTorrent({source, title, os, library, isFile}) -> download
  //   library.scan(librarySlug?)                       -> {created, updated, ...}
  //   library.addByUpload({library, title, file, os, fileType, onProgress}) -> game
  library: libraryActions,
  // Plugin catalogues (stores). A theme brings its own shelf layout and calls
  // these for the data, instead of hard-coding the endpoints the way the first
  // storefront theme did - which is why the store worked in one theme only.
  //   catalog.listEntries(catalogId)     -> entries on offer
  //   catalog.getEntry(entryId)          -> one offer, with detail
  //   catalog.download(entryId, {assets}) -> pull builds; the offer becomes a game
  //   catalog.sync(catalogId)            -> re-read the catalogue (admin)
  //   catalog.listCatalogs()             -> catalogues the plugins registered
  catalog: catalogActions,
  // Role-aware Dashboard data (built-in core overview). dashboard.me() returns
  // the signed-in user's own stats; dashboard.admin() returns the server-wide
  // admin overview (admin only). A plugin theme can render its own dashboard
  // from these instead of the built-in DashboardView.
  dashboard: dashboardActions,
  composables: {
    useCouchNav,
    couchNavPaused,
    useCouchTheme,
  },
  // Imperative access to the shared core editors, for themes that render their
  // own detail pages. The panels stay core components (plugin metadata tabs
  // mount inside them); PluginUiHost in App.vue renders the requested one.
  // openMetadataEditor({game, apiPrefix?, onSaved?, onClosed?});
  // openCollectionEditor(collectionOrSlug, {onUpdated?, onDeleted?, onClosed?}).
  // Saves also dispatch 'gd-game-updated' / 'gd-collection-updated' DOM events.
  ui: {
    openMetadataEditor,
    openCollectionEditor,
    closeMetadataEditor,
    closeCollectionEditor,
    // openRomMetadataEditor({rom, onSaved?, onClosed?}) - the emulation twin;
    // saves also dispatch a 'gd-rom-updated' DOM event.
    openRomMetadataEditor,
    closeRomMetadataEditor,
    // Styled in-app dialogs (same look in every theme) so plugins never have
    // to fall back to the browser-native window.confirm()/alert() popups.
    // confirm(msg, {title?, danger?, confirmText?, cancelText?}) -> Promise<boolean>
    confirm: (msg: string, opts?: Record<string, unknown>) => useDialog().gdConfirm(msg, opts as any),
    alert: (msg: string, opts?: Record<string, unknown>) => useDialog().gdAlert(msg, opts as any),
    // openAbout() - the shared About dialog (logo, version, Discord invite);
    // themes add an "About" entry to their user menu and call this.
    openAbout,
  },
  getEjsCore,
  // Built-in library icon set, for themes/plugins that render library glyphs
  // natively. library(name) returns the inner SVG markup (24x24, currentColor);
  // wrap it in <svg viewBox="0 0 24 24" ...> and set `color`/`stroke` to tint.
  icons: {
    library: (name: string) => libraryIconMarkup(name),
    libraryNames: () => [...LIBRARY_ICON_NAMES],
    libraryAll: () => ({ ...LIBRARY_ICONS }),
  },
  i18n,
  notifications: {
    add: (n: any) => useNotificationStore().add(n),
    dismiss: (id: string) => useNotificationStore().dismiss(id),
    remove: (id: string) => useNotificationStore().remove(id),
    get store() { return useNotificationStore(); },
  },
};

app.mount("#app");

// Load the data-driven library registry (no-op if not authenticated yet;
// re-fetched after login in the auth store).
useLibrariesStore().fetch();
useCollectionsStore().fetch();

// Load plugin translations (i18n.json files from installed plugins)
client.get("/plugins/frontend/i18n").then((res: any) => {
  if (res.data && typeof res.data === "object") {
    i18n.merge(res.data);
  }
}).catch(() => { /* no plugins or not authenticated yet */ });

// Load plugin-declared custom pages (frontend_get_routes): wire each into the
// router at /x/<path> and expose them for theme nav via __GD__.pluginRoutes.
client.get("/plugins/frontend/routes").then((res: any) => {
  if (Array.isArray(res.data) && res.data.length) {
    addPluginRoutes(router, res.data);
    setPluginNavRoutes(res.data);
  }
}).catch(() => { /* no plugin pages or not authenticated yet */ });

// Check for plugin updates (admin only, respects interval setting)
setTimeout(() => {
  const auth = useAuthStore();
  if (auth.user?.role !== "admin") return;
  const interval = localStorage.getItem("gd3_plugin_check_interval") || "6h";
  if (interval === "off") return;
  const intervalMs: Record<string, number> = { "1h": 3600000, "6h": 21600000, "24h": 86400000 };
  const ms = intervalMs[interval] || 21600000;
  const lastCheck = parseInt(localStorage.getItem("gd3_plugin_check_last") || "0", 10);
  if (Date.now() - lastCheck < ms) return;
  client.get("/plugins/store/updates").then((res: any) => {
    localStorage.setItem("gd3_plugin_check_last", String(Date.now()));
    const { count, updates } = res.data || {};
    if (count > 0) {
      const details = updates.map((u: any) => `${u.name}: ${u.installed} -> ${u.available}`);
      useNotificationStore().add({
        id: "plugin-updates",
        count,
        label: i18n.t("pstore.updates_badge"),
        details,
        action: "/settings?tab=pluginstore",
        actionLabel: i18n.t("pstore.go_to_store"),
      });
    }
  }).catch(() => {});
}, 3000);
