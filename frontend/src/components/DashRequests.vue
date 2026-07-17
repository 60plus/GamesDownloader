<!--
  DashRequests - admin review queue for game requests, embedded in the Dashboard.
  Lists every request (filterable by status) and lets an admin approve / reject /
  mark done / delete inline; each status change fires the existing webhook + email
  to the requester (server side). Rendered only for admins.
-->
<template>
  <div class="drq glass">
    <div class="drq-h">
      <i class="mdi mdi-inbox-multiple-outline drq-h-ico"></i>{{ t("requests.title", "Game requests") }}
      <span v-if="counts.pending" class="drq-h-badge">{{ counts.pending }} {{ t("requests.pending", "pending") }}</span>
    </div>

    <div class="drq-filters">
      <button v-for="f in filters" :key="f" class="drq-chip" :class="{ active: filter === f }" @click="filter = f">
        {{ t("requests.status_" + f, cap(f)) }}<span class="drq-chip-n">{{ f === "all" ? list.length : (counts[f] || 0) }}</span>
      </button>
    </div>

    <div v-if="loading" class="drq-loading"><span class="drq-spin"></span></div>
    <div v-else-if="!shown.length" class="drq-empty">{{ t("requests.empty", "No requests here.") }}</div>

    <div v-else class="drq-list">
      <div v-for="r in shown" :key="r.id" class="drq-row">
        <div class="drq-cover">
          <img v-if="r.cover_url" :src="r.cover_url" class="drq-cover-img" alt="" @error="(e) => ((e.target as HTMLImageElement).style.display = 'none')" />
          <i v-else class="mdi mdi-gamepad-variant-outline drq-cover-ph"></i>
        </div>
        <div class="drq-info">
          <div class="drq-title">{{ r.title }}</div>
          <div class="drq-meta">
            <span v-if="r.username"><i class="mdi mdi-account-outline"></i>{{ r.username }}</span>
            <span class="drq-sep">·</span>
            <span><i class="mdi mdi-shape-outline"></i>{{ r.platform }}</span>
            <template v-if="r.vote_count"><span class="drq-sep">·</span><span><i class="mdi mdi-thumb-up-outline"></i>{{ r.vote_count }}</span></template>
          </div>
        </div>
        <span class="drq-badge" :class="'st-' + r.status">{{ t("requests.status_" + r.status, cap(r.status)) }}</span>
        <div class="drq-actions">
          <button class="drq-act ok" :disabled="busyId === r.id || r.status === 'approved'" :title="t('requests.approve', 'Approve')" @click="setStatus(r, 'approved')"><i class="mdi mdi-check"></i></button>
          <button class="drq-act warn" :disabled="busyId === r.id || r.status === 'rejected'" :title="t('requests.reject', 'Reject')" @click="setStatus(r, 'rejected')"><i class="mdi mdi-close"></i></button>
          <button class="drq-act done" :disabled="busyId === r.id || r.status === 'done'" :title="t('requests.mark_done', 'Mark done')" @click="setStatus(r, 'done')"><i class="mdi mdi-check-all"></i></button>
          <button class="drq-act del" :disabled="busyId === r.id" :title="t('common.delete', 'Delete')" @click="remove(r)"><i class="mdi mdi-trash-can-outline"></i></button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useI18n } from "@/i18n";
import dashboardActions, { type GameRequestItem } from "@/lib/dashboardActions";

const { t } = useI18n();
const list = ref<GameRequestItem[]>([]);
const loading = ref(true);
const busyId = ref<number | null>(null);
const filter = ref<string>("all");
const filters = ["all", "pending", "approved", "rejected", "done"];

const counts = computed<Record<string, number>>(() => {
  const c: Record<string, number> = {};
  for (const r of list.value) c[r.status] = (c[r.status] || 0) + 1;
  return c;
});
const shown = computed(() => (filter.value === "all" ? list.value : list.value.filter((r) => r.status === filter.value)));

function cap(s: string): string { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

async function setStatus(r: GameRequestItem, status: string): Promise<void> {
  if (busyId.value) return;
  busyId.value = r.id;
  try { await dashboardActions.setRequestStatus(r.id, { status }); r.status = status; }
  catch { /* silent */ } finally { busyId.value = null; }
}
async function remove(r: GameRequestItem): Promise<void> {
  if (busyId.value) return;
  busyId.value = r.id;
  try { await dashboardActions.deleteRequest(r.id); list.value = list.value.filter((x) => x.id !== r.id); }
  catch { /* silent */ } finally { busyId.value = null; }
}

onMounted(async () => {
  try { list.value = await dashboardActions.requests(); } catch { /* silent */ } finally { loading.value = false; }
});
</script>

<style scoped>
.drq { border-radius: 12px; padding: 14px 16px; margin-top: 14px; }
.drq-h { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; opacity: 0.7; margin-bottom: 10px; }
.drq-h-ico { font-size: 26px; opacity: 0.9; color: var(--accent, #38d3db); }
.drq-h-badge { margin-left: 4px; font-size: 10px; padding: 2px 8px; border-radius: 20px; text-transform: none; letter-spacing: 0; background: color-mix(in srgb, #fbbf24 22%, transparent); color: #fbbf24; font-weight: 600; }
.drq-filters { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.drq-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; padding: 3px 10px; border-radius: 20px; border: 0; cursor: pointer; background: color-mix(in srgb, var(--accent, #38d3db) 10%, transparent); color: var(--text, #eee); opacity: 0.75; transition: opacity 0.15s ease, filter 0.15s ease; }
.drq-chip:hover { opacity: 1; }
.drq-chip.active { opacity: 1; filter: brightness(1.15); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent, #38d3db) 55%, transparent); }
.drq-chip-n { font-size: 10px; opacity: 0.7; font-variant-numeric: tabular-nums; }
.drq-loading { display: flex; justify-content: center; padding: 18px 0; }
.drq-spin { width: 15px; height: 15px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.25); border-top-color: var(--accent, #38d3db); animation: drqSpin 0.7s linear infinite; }
@keyframes drqSpin { to { transform: rotate(360deg); } }
.drq-empty { font-size: 12.5px; opacity: 0.5; padding: 12px 0; }
.drq-list { display: flex; flex-direction: column; gap: 6px; max-height: 420px; overflow-y: auto; }
.drq-row { display: flex; align-items: center; gap: 10px; padding: 6px; border-radius: 8px; background: rgba(255,255,255,0.03); }
.drq-cover { width: 34px; height: 46px; flex: 0 0 auto; border-radius: 5px; overflow: hidden; background: rgba(255,255,255,0.06); display: flex; align-items: center; justify-content: center; }
.drq-cover-img { width: 100%; height: 100%; object-fit: cover; }
.drq-cover-ph { font-size: 18px; opacity: 0.35; }
.drq-info { flex: 1; min-width: 0; }
.drq-title { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.drq-meta { font-size: 11px; opacity: 0.6; display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 2px; }
.drq-meta i { font-size: 12px; margin-right: 2px; }
.drq-sep { opacity: 0.5; }
.drq-badge { flex: 0 0 auto; font-size: 10px; padding: 2px 8px; border-radius: 20px; font-weight: 600; text-transform: capitalize; background: rgba(255,255,255,0.1); }
.st-pending { background: color-mix(in srgb, #fbbf24 22%, transparent); color: #fbbf24; }
.st-approved { background: color-mix(in srgb, #4ade80 20%, transparent); color: #4ade80; }
.st-rejected { background: color-mix(in srgb, #f87171 20%, transparent); color: #f87171; }
.st-done { background: color-mix(in srgb, #a78bfa 22%, transparent); color: #a78bfa; }
.drq-actions { display: flex; gap: 4px; flex: 0 0 auto; }
.drq-act { width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border: 0; border-radius: 6px; cursor: pointer; font-size: 14px; background: rgba(255,255,255,0.06); color: var(--text, #eee); transition: filter 0.15s ease; }
.drq-act:hover:not(:disabled) { filter: brightness(1.25); }
.drq-act:disabled { opacity: 0.35; cursor: default; }
.drq-act.ok { background: color-mix(in srgb, #4ade80 16%, transparent); color: #4ade80; }
.drq-act.warn { background: color-mix(in srgb, #f87171 16%, transparent); color: #f87171; }
.drq-act.done { background: color-mix(in srgb, #a78bfa 16%, transparent); color: #a78bfa; }
.drq-act.del { background: rgba(255,255,255,0.06); opacity: 0.7; }
</style>
