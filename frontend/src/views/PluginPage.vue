<!--
  Host for a plugin-declared custom page (frontend_get_routes). The route is
  /x/<path>; this component looks up the mount fn the plugin registered via
  window.__GD__.registerRoute({ path, mount }) and hands it a plain DOM element
  plus a small context (path, api client, t). If the plugin's JS has not loaded
  yet, it retries briefly. Cleanup runs on unmount / route change.
-->
<template>
  <div class="plugin-page">
    <div ref="host" class="plugin-page-host"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { getPluginRouteMount } from "@/themes/index";
import client from "@/services/api/client";
import { useI18n } from "@/i18n";

const route = useRoute();
const { t } = useI18n();
const host = ref<HTMLElement | null>(null);
let cleanup: (() => void) | void;
let tries = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

function pluginPath(): string {
  return String((route.meta as Record<string, unknown>)?.pluginPath || "").replace(/^\/+/, "");
}

function tryMount() {
  if (!host.value) return;
  const fn = getPluginRouteMount(pluginPath());
  if (fn) {
    try {
      cleanup = fn(host.value, { path: pluginPath(), api: client, t }) || undefined;
    } catch {
      /* a plugin page that throws must not take down the app */
    }
    return;
  }
  // The plugin's injected JS may still be loading - retry, then give up quietly.
  if (tries++ < 40) timer = setTimeout(tryMount, 150);
}

function teardown() {
  if (timer) { clearTimeout(timer); timer = null; }
  try { if (typeof cleanup === "function") cleanup(); } catch { /* ignore */ }
  cleanup = undefined;
  tries = 0;
  if (host.value) host.value.innerHTML = "";
}

onMounted(tryMount);
onBeforeUnmount(teardown);
watch(() => route.fullPath, () => { teardown(); tryMount(); });
</script>

<style scoped>
.plugin-page { min-height: 60vh; padding: 20px; }
</style>
