<!--
  Dashboard - a host page for plugin widget cards (widget_get_cards hook). Fetches
  the aggregated cards from /api/plugins/dashboard/cards and renders them as a
  responsive grid of data tiles. A card with an internal `link` (e.g. a plugin
  page /x/<path>) navigates on click. Empty state when no plugin contributes a
  card. Core stat cards can be layered in later (Stats Dashboard).
-->
<template>
  <div class="dash">
    <h1 class="dash-title">Dashboard</h1>
    <div v-if="loading" class="dash-empty">…</div>
    <div v-else-if="cards.length" class="dash-grid">
      <div
        v-for="c in cards"
        :key="c.id"
        class="dash-card glass"
        :class="{ 'dash-card--link': isInternal(c.link) }"
        @click="go(c.link)"
      >
        <div class="dash-card-top">
          <i v-if="isMdi(c.icon)" :class="['mdi', c.icon, 'dash-card-ico']"></i>
          <img v-else-if="c.icon" :src="c.icon" class="dash-card-ico-img" alt="" />
          <span class="dash-card-title">{{ c.title }}</span>
        </div>
        <div v-if="c.value !== null && c.value !== undefined" class="dash-card-value">{{ c.value }}</div>
        <div v-if="c.subtitle" class="dash-card-sub">{{ c.subtitle }}</div>
      </div>
    </div>
    <div v-else class="dash-empty">No dashboard widgets yet - plugins can add cards here.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import client from "@/services/api/client";

interface Card {
  id: string;
  title: string;
  value?: unknown;
  subtitle?: string;
  icon?: string;
  link?: string;
}

const router = useRouter();
const cards = ref<Card[]>([]);
const loading = ref(true);

function isMdi(icon?: string): boolean {
  return !!icon && icon.startsWith("mdi-");
}
function isInternal(link?: string): boolean {
  return !!link && link.startsWith("/");
}
function go(link?: string): void {
  if (isInternal(link)) router.push(link as string);
}

onMounted(async () => {
  try {
    const { data } = await client.get("/plugins/dashboard/cards");
    cards.value = Array.isArray(data) ? data : [];
  } catch {
    cards.value = [];
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.dash { padding: 24px 28px; max-width: 1200px; margin: 0 auto; }
.dash-title { font-size: 22px; font-weight: 700; margin-bottom: 18px; color: var(--text, #eee); }
.dash-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.dash-card { border-radius: 12px; padding: 16px 18px; display: flex; flex-direction: column; gap: 6px; }
.dash-card--link { cursor: pointer; }
.dash-card--link:hover { filter: brightness(1.08); }
.dash-card-top { display: flex; align-items: center; gap: 8px; }
.dash-card-ico { font-size: 18px; opacity: 0.85; }
.dash-card-ico-img { width: 18px; height: 18px; }
.dash-card-title { font-size: 12.5px; font-weight: 600; letter-spacing: 0.3px; opacity: 0.8; text-transform: uppercase; }
.dash-card-value { font-size: 26px; font-weight: 700; color: var(--text, #eee); }
.dash-card-sub { font-size: 12px; opacity: 0.65; }
.dash-empty { opacity: 0.6; font-size: 14px; padding: 40px 0; }
</style>
