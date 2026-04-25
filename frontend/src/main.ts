import { createApp } from "vue";
import * as VueRuntime from "vue";
import * as VueRouterRuntime from "vue-router";
import App from "./App.vue";
import { createAppRouter } from "./plugins/router";
import { createAppPinia } from "./plugins/pinia";
import { vuetify } from "./plugins/vuetify";
import { registerTheme, registerPluginLayout, registerPluginCouchMode } from "./themes/index";
import { useCouchNav, navPaused as couchNavPaused } from "./composables/useCouchNav";
import { useCouchTheme } from "./composables/useCouchTheme";
import { getEjsCore } from "./utils/ejsCores";
import i18n from "./i18n";
import { useAuthStore } from "./stores/auth";
import { useSocketStore } from "./stores/socket";
import { useThemeStore } from "./stores/theme";
import { useNotificationStore } from "./stores/notifications";
import client from "./services/api/client";

import DownloadManager from "./components/gog/DownloadManager.vue";
import RandomGamePicker from "./components/RandomGamePicker.vue";
import AmbientBackground from "./components/common/AmbientBackground.vue";

import "@mdi/font/css/materialdesignicons.css";
import "./styles/base.css";
import "./styles/glass.css";
import "./styles/skins.css";

const app = createApp(App);

app.use(createAppPinia());
app.use(createAppRouter());
app.use(vuetify);

// Register shared components globally so plugin themes can use them
app.component("DownloadManager", DownloadManager);
app.component("RandomGamePicker", RandomGamePicker);
app.component("AmbientBackground", AmbientBackground);

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
  },
  api: client,
  registerTheme,
  registerPluginLayout,
  registerPluginCouchMode,
  composables: {
    useCouchNav,
    couchNavPaused,
    useCouchTheme,
  },
  getEjsCore,
  i18n,
  notifications: {
    add: (n: any) => useNotificationStore().add(n),
    dismiss: (id: string) => useNotificationStore().dismiss(id),
    remove: (id: string) => useNotificationStore().remove(id),
    get store() { return useNotificationStore(); },
  },
};

app.mount("#app");

// Load plugin translations (i18n.json files from installed plugins)
client.get("/plugins/frontend/i18n").then((res: any) => {
  if (res.data && typeof res.data === "object") {
    i18n.merge(res.data);
  }
}).catch(() => { /* no plugins or not authenticated yet */ });

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
