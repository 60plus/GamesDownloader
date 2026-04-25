<template>
  <div class="gr-page">
    <div class="gr-head">
      <div class="gr-head-left">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
          <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
        </svg>
        <div>
          <h1 class="gr-title">{{ t('requests.title') }}</h1>
          <p class="gr-sub">{{ t('requests.subtitle') }}</p>
        </div>
      </div>
      <button class="gr-new-btn" @click="dialogOpen = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        {{ t('requests.new_request') }}
      </button>
    </div>

    <!-- Filters -->
    <div class="gr-filters">
      <button
        v-for="f in filters"
        :key="f.value"
        class="gr-filter-btn"
        :class="{ active: activeFilter === f.value }"
        @click="activeFilter = f.value"
      >{{ f.label }}</button>
      <div class="gr-filter-sep" />
      <button
        v-for="p in platforms"
        :key="p.value"
        class="gr-filter-btn"
        :class="{ active: activePlatform === p.value }"
        @click="activePlatform = p.value"
      >{{ p.label }}</button>
    </div>

    <!-- List -->
    <div v-if="loading" class="gr-loading">
      <div class="gr-spinner" />
    </div>

    <div v-else-if="!filtered.length" class="gr-empty">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".12">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
      <span>{{ t('requests.no_requests') }}</span>
    </div>

    <div v-else class="gr-list">
      <div
        v-for="r in filtered"
        :key="r.id"
        class="gr-item glass"
        :class="`gr-item--${r.status}`"
      >
        <!-- Vote -->
        <div class="gr-vote">
          <button
            class="gr-vote-btn"
            :class="{ voted: r.user_voted }"
            :disabled="r.user_voted || voting === r.id"
            @click="vote(r)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="18 15 12 9 6 15"/>
            </svg>
          </button>
          <span class="gr-vote-count">{{ r.vote_count }}</span>
        </div>

        <!-- Content -->
        <div class="gr-content">
          <div class="gr-row1">
            <span class="gr-item-title">{{ r.title }}</span>
            <span class="gr-badge gr-badge--status" :class="`gr-status--${r.status}`">{{ r.status }}</span>
            <span class="gr-badge gr-badge--platform">{{ r.platform === 'roms' ? t('requests.platform_emulation') : t('requests.platform_games') }}</span>
          </div>
          <p v-if="r.description" class="gr-desc">{{ r.description }}</p>
          <a v-if="r.link" :href="r.link" target="_blank" rel="noopener noreferrer" class="gr-link">{{ r.link }}</a>
          <div v-if="r.admin_note" class="gr-admin-note">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
            {{ r.admin_note }}
          </div>
          <div class="gr-meta">
            {{ t('requests.requested_by') }} <strong>{{ r.username || t('requests.unknown') }}</strong>
            <span v-if="r.created_at"> · {{ fmtDate(r.created_at) }}</span>
          </div>
        </div>

        <!-- Admin -->
        <div v-if="isAdmin" class="gr-admin">
          <select class="gr-select" :value="r.status" @change="patchStatus(r, ($event.target as HTMLSelectElement).value)">
            <option value="pending">pending</option>
            <option value="approved">approved</option>
            <option value="rejected">rejected</option>
            <option value="done">done</option>
          </select>
          <button class="gr-icon-btn gr-icon-btn--note" @click="openNote(r)" :title="t('requests.note_title')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>
          </button>
          <button class="gr-icon-btn gr-icon-btn--del" @click="del(r)" :title="t('common.delete')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Note edit overlay -->
    <div v-if="noteId !== null" class="gr-overlay" @mousedown.self="noteId = null">
      <div class="gr-note-box glass">
        <div class="gr-note-title">{{ t('requests.admin_note') }}</div>
        <textarea v-model="noteText" class="gr-textarea" rows="3" :placeholder="t('requests.note_placeholder')" autofocus />
        <div class="gr-note-actions">
          <button class="gr-btn gr-btn--ghost" @click="noteId = null">{{ t('common.cancel') }}</button>
          <button class="gr-btn gr-btn--primary" @click="saveNote">{{ t('common.save') }}</button>
        </div>
      </div>
    </div>

    <!-- Dialog -->
    <GameRequestDialog :visible="dialogOpen" @close="dialogOpen = false; loadRequests()" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'
import GameRequestDialog from '@/components/GameRequestDialog.vue'

const { t } = useI18n()
const auth    = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')

interface Req {
  id: number; title: string; description: string | null; link: string | null
  platform: string; status: string; admin_note: string | null
  user_id: number; username: string | null
  vote_count: number; user_voted: boolean; created_at: string | null
}

const requests     = ref<Req[]>([])
const loading      = ref(false)
const dialogOpen   = ref(false)
const voting       = ref<number | null>(null)
const activeFilter   = ref('all')
const activePlatform = ref('all')

const filters = computed(() => [
  { label: t('requests.filter_all'), value: 'all' },
  { label: t('requests.filter_pending'), value: 'pending' },
  { label: t('requests.filter_approved'), value: 'approved' },
  { label: t('requests.filter_done'), value: 'done' },
  { label: t('requests.filter_rejected'), value: 'rejected' },
])
const platforms = computed(() => [
  { label: t('requests.all_libraries'), value: 'all' },
  { label: t('requests.platform_games'), value: 'games' },
  { label: t('requests.platform_emulation'), value: 'roms' },
])

const filtered = computed(() => {
  let list = [...requests.value].sort((a, b) => b.vote_count - a.vote_count || b.id - a.id)
  if (activeFilter.value !== 'all') list = list.filter(r => r.status === activeFilter.value)
  if (activePlatform.value !== 'all') list = list.filter(r => r.platform === activePlatform.value)
  return list
})

async function loadRequests() {
  loading.value = true
  try { const { data } = await client.get('/requests'); requests.value = data }
  catch { /* ignore */ } finally { loading.value = false }
}

async function vote(r: Req) {
  if (r.user_voted || voting.value === r.id) return
  voting.value = r.id
  try { const { data } = await client.post(`/requests/${r.id}/vote`); r.vote_count = data.vote_count; r.user_voted = true }
  catch { /* ignore */ } finally { voting.value = null }
}

async function patchStatus(r: Req, status: string) {
  try { await client.patch(`/requests/${r.id}`, { status }); r.status = status } catch { /* ignore */ }
}

const noteId   = ref<number | null>(null)
const noteText = ref('')
function openNote(r: Req) { noteId.value = r.id; noteText.value = r.admin_note || '' }
async function saveNote() {
  const id = noteId.value; if (id === null) return
  const r = requests.value.find(x => x.id === id)
  try { await client.patch(`/requests/${id}`, { admin_note: noteText.value }); if (r) r.admin_note = noteText.value || null; noteId.value = null } catch { /* ignore */ }
}

async function del(r: Req) {
  if (!confirm(t('requests.delete_request'))) return
  try { await client.delete(`/requests/${r.id}`); requests.value = requests.value.filter(x => x.id !== r.id) } catch { /* ignore */ }
}

function fmtDate(iso: string) {
  try {
    const lang = localStorage.getItem('gd-lang') || 'en'
    return new Date(iso).toLocaleDateString(lang === 'pl' ? 'pl-PL' : 'en-US')
  } catch { return '' }
}

onMounted(loadRequests)
</script>

<style scoped>
.gr-page { display: flex; flex-direction: column; gap: var(--space-5, 20px); max-width: 860px; margin: 0 auto; }
.gr-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4, 16px); }
.gr-head-left { display: flex; align-items: center; gap: 14px; }
.gr-title { font-size: var(--fs-2xl, 22px); font-weight: 800; color: var(--text); margin: 0; line-height: 1.1; }
.gr-sub { font-size: 13px; color: var(--muted); margin: 2px 0 0; }
.gr-new-btn {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 18px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); color: var(--pl-light);
  font-size: 13px; font-weight: 700; font-family: inherit; cursor: pointer;
  box-shadow: 0 2px 14px var(--pglow2); transition: background .15s;
}
.gr-new-btn:hover { background: var(--pl-light); }

.gr-filters { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gr-filter-sep { width: 1px; height: 20px; background: var(--glass-border); margin: 0 4px; }
.gr-filter-btn {
  padding: 5px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600; cursor: pointer;
  transition: all .15s; font-family: inherit;
}
.gr-filter-btn:hover { background: rgba(255,255,255,.09); color: var(--text); }
.gr-filter-btn.active { background: rgba(124,58,237,.15); border-color: var(--pl); color: var(--pl-light); }

.gr-loading { display: flex; justify-content: center; padding: 60px; }
.gr-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 60px; color: var(--muted); font-size: 13px; opacity: .5; }
.gr-list { display: flex; flex-direction: column; gap: var(--space-2, 8px); }

.gr-item {
  display: flex; align-items: flex-start; gap: 14px;
  padding: 14px 16px; border-radius: var(--radius); transition: background .1s;
}
.gr-item:hover { background: rgba(255,255,255,.03); }
.gr-item--done     { opacity: .65; }
.gr-item--rejected { opacity: .45; }

.gr-vote { display: flex; flex-direction: column; align-items: center; gap: 3px; flex-shrink: 0; padding-top: 1px; }
.gr-vote-btn {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.gr-vote-btn:hover:not(:disabled) { background: rgba(124,58,237,.2); border-color: var(--pl); color: var(--pl-light); }
.gr-vote-btn.voted { background: rgba(124,58,237,.15); border-color: var(--pl); color: var(--pl-light); cursor: default; }
.gr-vote-btn:disabled:not(.voted) { opacity: .35; cursor: not-allowed; }
.gr-vote-count { font-size: 13px; font-weight: 700; color: var(--text); }

.gr-content { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.gr-row1 { display: flex; align-items: center; gap: var(--space-2, 8px); flex-wrap: wrap; }
.gr-item-title { font-size: 15px; font-weight: 700; color: var(--text); }
.gr-desc { font-size: 13px; color: var(--muted); line-height: 1.5; margin: 0; }
.gr-link { font-size: var(--fs-sm, 12px); color: var(--pl-light); word-break: break-all; }
.gr-admin-note { font-size: var(--fs-sm, 12px); color: #fbbf24; display: flex; align-items: flex-start; gap: 5px; line-height: 1.5; }
.gr-meta { font-size: 11px; color: var(--muted); opacity: .65; }

.gr-badge { font-size: 9px; font-weight: 700; padding: 2px 7px; border-radius: var(--radius-xs, 4px); text-transform: uppercase; letter-spacing: .05em; flex-shrink: 0; }
.gr-badge--platform { background: rgba(255,255,255,.07); color: var(--muted); }
.gr-status--pending  { background: rgba(251,191,36,.15); color: #fbbf24; }
.gr-status--approved { background: rgba(74,222,128,.15); color: #4ade80; }
.gr-status--rejected { background: rgba(239,68,68,.15);  color: #f87171; }
.gr-status--done     { background: rgba(139,92,246,.15); color: #a78bfa; }

.gr-admin { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.gr-select {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: 6px; color: var(--text); font-size: 11px; padding: 5px 7px; cursor: pointer; outline: none;
}
.gr-icon-btn {
  width: 28px; height: 28px; border-radius: 6px; cursor: pointer; border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.06); display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.gr-icon-btn--note { color: #fbbf24; }
.gr-icon-btn--note:hover { background: rgba(251,191,36,.15); border-color: #fbbf24; }
.gr-icon-btn--del { color: #f87171; }
.gr-icon-btn--del:hover { background: rgba(239,68,68,.15); border-color: #f87171; }

.gr-overlay {
  position: fixed; inset: 0; z-index: 3000; background: rgba(0,0,0,.6); backdrop-filter: blur(5px);
  display: flex; align-items: center; justify-content: center; padding: var(--space-6, 24px);
}
.gr-note-box { width: 100%; max-width: 440px; border-radius: var(--radius); padding: var(--space-5, 20px); display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.gr-note-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.gr-note-actions { display: flex; justify-content: flex-end; gap: var(--space-2, 8px); }
.gr-textarea {
  background: rgba(255,255,255,.05); border: 1px solid var(--glass-border); border-radius: var(--radius-sm, 8px);
  color: var(--text); font-size: 13px; font-family: inherit; padding: 8px 12px; outline: none; resize: vertical; min-height: 72px;
}
.gr-textarea:focus { border-color: var(--pl); }

.gr-btn { padding: 7px 16px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; border: none; transition: all .15s; }
.gr-btn--ghost { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted); }
.gr-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.gr-btn--primary { background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); }
.gr-btn--primary:hover { background: var(--pl-light); }

.gr-spinner {
  width: 32px; height: 32px; border-radius: 50%;
  border: 3px solid rgba(255,255,255,.1); border-top-color: var(--pl);
  animation: gr-spin .7s linear infinite;
}
@keyframes gr-spin { to { transform: rotate(360deg); } }
</style>
