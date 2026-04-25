<template>
  <Teleport to="body">
    <Transition name="grd-fade">
      <div v-if="visible" class="grd-backdrop" @mousedown.self="$emit('close')">
        <div class="grd-box glass">

          <!-- Header -->
          <div class="grd-header">
            <div class="grd-header-left">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              <span>{{ t('requests.title') }}</span>
              <span class="grd-platform-tag">{{ defaultPlatform === 'roms' ? t('requests.platform_emulation') : t('nav.games_library') }}</span>
            </div>
            <div class="grd-header-right">
              <div class="grd-tabs">
                <button class="grd-tab" :class="{ active: tab === 'submit' }" @click="tab = 'submit'">{{ t('requests.request_a_game') }}</button>
                <button class="grd-tab" :class="{ active: tab === 'list' }" @click="tab = 'list'; loadRequests()">
                  {{ t('requests.all_requests') }}
                  <span v-if="requests.length" class="grd-tab-badge">{{ requests.length }}</span>
                </button>
                <button v-if="hasGogAccount" class="grd-tab" :class="{ active: tab === 'mygog' }" @click="tab = 'mygog'; loadGogGames()">
                  {{ t('requests.my_gog') }}
                  <span v-if="gogGames.length" class="grd-tab-badge">{{ gogGames.length }}</span>
                </button>
              </div>
              <button class="grd-close" @click="$emit('close')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- ══ TAB: Submit ══ -->
          <div v-if="tab === 'submit'" class="grd-body">
            <form class="grd-form" @submit.prevent="submitRequest">

              <!-- Title + search -->
              <div class="grd-field">
                <label class="grd-label">{{ t('requests.game_title_req') }}</label>
                <div class="grd-search-wrap">
                  <input
                    v-model="form.title"
                    class="grd-input"
                    :placeholder="defaultPlatform === 'roms' ? 'e.g. Super Mario World' : 'e.g. The Witcher 3'"
                    required maxlength="255" autofocus
                    @input="onTitleInput"
                  />
                  <div v-if="searching" class="grd-search-spinner" />
                </div>

                <!-- Suggestions grid -->
                <div v-if="suggestions.length && !selectedGame" class="grd-suggestions">
                  <div class="grd-sug-header">
                    <span>{{ t('requests.found_matches', { count: suggestions.length }) }}</span>
                    <button type="button" class="grd-sug-skip" @click="suggestions = []">{{ t('requests.enter_manually') }}</button>
                  </div>
                  <div class="grd-sug-grid">
                    <button
                      v-for="(s, i) in suggestions"
                      :key="i"
                      type="button"
                      class="grd-sug-card"
                      @click="selectSuggestion(s)"
                    >
                      <div class="grd-sug-cover">
                        <img v-if="s.cover_url" :src="s.cover_url" :alt="s.title" loading="lazy" />
                        <div v-else class="grd-sug-cover-empty">
                          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".3">
                            <rect x="3" y="3" width="18" height="18" rx="2"/>
                          </svg>
                        </div>
                      </div>
                      <div class="grd-sug-info">
                        <span class="grd-sug-title">{{ s.title }}</span>
                        <span class="grd-sug-year">{{ s.year || '-' }}</span>
                        <span v-if="s.developer" class="grd-sug-dev">{{ s.developer }}</span>
                        <span class="grd-sug-src">{{ s.source }}</span>
                      </div>
                    </button>
                  </div>
                </div>

                <!-- Selected game preview -->
                <div v-if="selectedGame" class="grd-selected">
                  <img v-if="selectedGame.cover_url" :src="selectedGame.cover_url" class="grd-selected-cover" />
                  <div class="grd-selected-info">
                    <span class="grd-selected-title">{{ selectedGame.title }}</span>
                    <span class="grd-selected-meta">{{ selectedGame.year }}{{ selectedGame.developer ? ' · ' + selectedGame.developer : '' }}</span>
                    <span class="grd-selected-src">via {{ selectedGame.source }}</span>
                  </div>
                  <button type="button" class="grd-selected-clear" @click="clearSelection" title="Choose different">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                  </button>
                </div>

                <!-- No results -->
                <div v-if="searchDone && !suggestions.length && !selectedGame && form.title.length >= 3" class="grd-no-results">
                  {{ t('requests.no_matches') }}
                </div>
              </div>

              <!-- Platform selector for ROMs - custom dropdown with icons -->
              <div v-if="defaultPlatform === 'roms'" class="grd-field">
                <label class="grd-label">{{ t('requests.platform_req') }}</label>
                <div class="grd-plat-picker">
                  <button type="button" class="grd-plat-trigger" @click="platOpen = !platOpen">
                    <template v-if="selectedPlatform">
                      <img :src="`/platforms/icons/${selectedPlatform.fs_slug}.png`" class="grd-plat-icon" @error="($event.target as HTMLImageElement).style.display='none'" />
                      <span>{{ selectedPlatform.name }}</span>
                    </template>
                    <span v-else class="grd-plat-placeholder">{{ t('requests.select_platform') }}</span>
                    <svg class="grd-plat-chevron" :class="{ open: platOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
                  </button>
                  <template v-if="platOpen">
                    <div class="grd-plat-backdrop" @click="platOpen = false" />
                    <div class="grd-plat-dropdown">
                      <div class="grd-plat-search-wrap">
                        <input v-model="platSearch" class="grd-plat-search-input" :placeholder="t('requests.filter_platforms')" @click.stop />
                      </div>
                      <div class="grd-plat-list">
                        <button
                          v-for="p in filteredPlatforms"
                          :key="p.fs_slug"
                          type="button"
                          class="grd-plat-option"
                          :class="{ selected: form.platform_slug === p.fs_slug }"
                          @click.stop="selectPlatform(p)"
                        >
                          <img :src="`/platforms/icons/${p.fs_slug}.png`" class="grd-plat-icon" @error="($event.target as HTMLImageElement).style.display='none'" />
                          <span>{{ p.name }}</span>
                        </button>
                      </div>
                    </div>
                  </template>
                </div>
              </div>

              <div class="grd-field">
                <label class="grd-label">{{ t('requests.additional_info') }}</label>
                <textarea
                  v-model="form.description"
                  class="grd-textarea"
                  :placeholder="t('requests.info_placeholder')"
                  rows="2" maxlength="2000"
                />
              </div>

              <div class="grd-field">
                <label class="grd-label">{{ t('requests.link_label') }}</label>
                <input v-model="form.link" class="grd-input" placeholder="https://…" maxlength="512" />
              </div>

              <div v-if="submitError" class="grd-msg grd-msg--err">{{ submitError }}</div>
              <div v-if="submitOk" class="grd-msg grd-msg--ok">{{ t('requests.submitted') }}</div>

              <div class="grd-form-footer">
                <button type="button" class="grd-btn grd-btn--ghost" @click="$emit('close')">{{ t('common.cancel') }}</button>
                <button
                  type="submit"
                  class="grd-btn grd-btn--primary"
                  :disabled="submitting || (defaultPlatform === 'roms' && !form.platform_slug)"
                >
                  <span v-if="submitting" class="grd-spinner" />
                  {{ submitting ? t('requests.submitting') : t('requests.submit_request') }}
                </button>
              </div>
            </form>
          </div>

          <!-- ══ TAB: My GOG ══ -->
          <div v-else-if="tab === 'mygog'" class="grd-body grd-body--mygog">
            <div v-if="gogLoading" class="grd-loading"><span class="grd-spinner grd-spinner--lg" /></div>
            <div v-else-if="!gogGames.length" class="grd-empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".15">
                <rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="7.5" cy="12" r="1.5"/><circle cx="16.5" cy="12" r="1.5"/>
              </svg>
              <span>{{ t('requests.no_gog_synced') }}</span>
            </div>
            <div v-else class="grd-mygog-grid">
              <div v-for="g in gogGames" :key="g.gog_id" class="grd-mygog-card">
                <div class="grd-mygog-cover">
                  <img v-if="g.cover_url" :src="g.cover_url" :alt="g.title" loading="lazy" />
                  <div v-else class="grd-mygog-cover-empty">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".3">
                      <rect x="3" y="3" width="18" height="18" rx="2"/>
                    </svg>
                  </div>
                </div>
                <div class="grd-mygog-info">
                  <div class="grd-mygog-title">{{ g.title }}</div>
                  <div v-if="g.release_date" class="grd-mygog-date">{{ g.release_date }}</div>
                </div>
                <button
                  class="grd-mygog-req-btn"
                  :class="{ requested: requestedGogIds.has(g.gog_id) }"
                  @click="requestGogGame(g)"
                  :disabled="requestedGogIds.has(g.gog_id) || requestingGogId === g.gog_id"
                >
                  <span v-if="requestingGogId === g.gog_id" class="grd-spinner" />
                  {{ requestedGogIds.has(g.gog_id) ? t('requests.requested') : t('library.request') }}
                </button>
              </div>
            </div>
          </div>

          <!-- ══ TAB: List ══ -->
          <div v-else-if="tab === 'list'" class="grd-body grd-body--list">
            <div v-if="loading" class="grd-loading"><span class="grd-spinner grd-spinner--lg" /></div>
            <div v-else-if="!requests.length" class="grd-empty">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".15">
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
              </svg>
              <span>{{ t('requests.no_requests_yet') }}</span>
            </div>
            <div v-else class="grd-list">
              <div v-for="r in sortedRequests" :key="r.id" class="grd-item" :class="`grd-item--${r.status}`">
                <!-- Cover -->
                <div class="grd-item-cover">
                  <img v-if="r.cover_url" :src="r.cover_url" :alt="r.title" />
                  <div v-else class="grd-item-cover-empty">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity=".2">
                      <rect x="3" y="3" width="18" height="18" rx="2"/>
                    </svg>
                  </div>
                </div>

                <!-- Vote -->
                <div class="grd-vote-col">
                  <button class="grd-vote-btn" :class="{ voted: r.user_voted }" :disabled="r.user_voted || voting === r.id" @click="vote(r)">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
                  </button>
                  <span class="grd-vote-count">{{ r.vote_count }}</span>
                </div>

                <!-- Content -->
                <div class="grd-item-body">
                  <div class="grd-item-top">
                    <span class="grd-item-title">{{ r.title }}</span>
                    <span class="grd-status-badge" :class="`grd-status--${r.status}`">{{ r.status }}</span>
                    <span class="grd-platform-badge">
                      {{ r.platform === 'roms' ? t('requests.platform_emulation') : t('requests.platform_games') }}
                      <template v-if="r.platform_slug"> · {{ r.platform_slug }}</template>
                    </span>
                  </div>
                  <div v-if="r.description" class="grd-item-desc">{{ r.description }}</div>
                  <div v-if="r.link" class="grd-item-link">
                    <a :href="r.link" target="_blank" rel="noopener noreferrer" class="grd-link">{{ r.link }}</a>
                  </div>
                  <div v-if="r.admin_note" class="grd-admin-note">
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
                    {{ r.admin_note }}
                  </div>
                  <div class="grd-item-meta">{{ t('requests.requested_by') }} {{ r.username || t('requests.unknown') }}<span v-if="r.created_at"> · {{ formatDate(r.created_at) }}</span></div>
                </div>

                <!-- Admin -->
                <div v-if="isAdmin" class="grd-admin-col">
                  <select class="grd-status-select" :value="r.status" @change="patchStatus(r, ($event.target as HTMLSelectElement).value)">
                    <option value="pending">pending</option>
                    <option value="approved">approved</option>
                    <option value="rejected">rejected</option>
                    <option value="done">done</option>
                  </select>
                  <button class="grd-note-btn" @click="openNoteEdit(r)">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                  </button>
                  <button class="grd-del-btn" @click="deleteReq(r)">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Admin note overlay -->
            <div v-if="noteEditId !== null" class="grd-note-overlay" @mousedown.self="noteEditId = null">
              <div class="grd-note-box glass">
                <div class="grd-note-title">{{ t('requests.admin_note') }}</div>
                <textarea v-model="noteEditText" class="grd-textarea" rows="3" :placeholder="t('requests.note_placeholder')" autofocus />
                <div class="grd-note-actions">
                  <button class="grd-btn grd-btn--ghost" @click="noteEditId = null">{{ t('common.cancel') }}</button>
                  <button class="grd-btn grd-btn--primary" @click="saveNote">{{ t('common.save') }}</button>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useI18n } from '@/i18n'
import client from '@/services/api/client'
import { useAuthStore } from '@/stores/auth'
import { useRequestNotify } from '@/composables/useRequestNotify'

const { t } = useI18n()

const props = defineProps<{ visible: boolean; defaultPlatform?: string }>()
const emit  = defineEmits(['close'])

const auth    = useAuthStore()
const isAdmin = computed(() => auth.user?.role === 'admin')
const { markSeen } = useRequestNotify()

// ── Tabs ─────────────────────────────────────────────────────────────────────
const tab = ref<'submit' | 'list' | 'mygog'>('submit')

watch(() => props.visible, (v) => {
  if (v) { tab.value = 'submit'; resetForm(); loadRequests(); checkGogAccount(); gogGamesLoaded.value = false }
})

// ── My GOG tab ──────────────────────────────────────────────────────────────
const hasGogAccount   = ref(false)
const gogGames        = ref<any[]>([])
const gogLoading      = ref(false)
const gogGamesLoaded  = ref(false)
const requestedGogIds = ref<Set<number>>(new Set())
const requestingGogId = ref<number | null>(null)

async function checkGogAccount() {
  try {
    const { data } = await client.get('/gog/user/auth/status')
    hasGogAccount.value = !!data?.authenticated
  } catch {
    hasGogAccount.value = false
  }
}

async function loadGogGames() {
  if (gogGamesLoaded.value || gogLoading.value) return
  gogLoading.value = true
  try {
    const { data } = await client.get('/gog/user/library/games')
    gogGames.value = data
    gogGamesLoaded.value = true
    // Check which GOG games are already requested
    await refreshRequestedGogIds()
  } catch { gogGames.value = [] } finally {
    gogLoading.value = false
  }
}

async function refreshRequestedGogIds() {
  // Scan existing requests to find gog_user requests by this user
  const ids = new Set<number>()
  for (const r of requests.value) {
    if (r.platform === 'gog_user') {
      // Match by title since we don't store gog_id in requests
      const match = gogGames.value.find(g => g.title === r.title)
      if (match) ids.add(match.gog_id)
    }
  }
  requestedGogIds.value = ids
}

async function requestGogGame(g: any) {
  if (requestedGogIds.value.has(g.gog_id) || requestingGogId.value !== null) return
  requestingGogId.value = g.gog_id
  try {
    const payload: Record<string, any> = {
      title:       g.title,
      description: null,
      link:        null,
      platform:    'gog_user',
      platform_slug: null,
      cover_url:   g.cover_url || null,
    }
    const { data } = await client.post('/requests', payload)
    requests.value.unshift(data)
    requestedGogIds.value = new Set([...requestedGogIds.value, g.gog_id])
  } catch { /* ignore */ } finally {
    requestingGogId.value = null
  }
}

// ── ROM platforms for selector ────────────────────────────────────────────────
interface RomPlatform { fs_slug: string; name: string }
const romPlatforms = ref<RomPlatform[]>([])

async function loadRomPlatforms() {
  if (romPlatforms.value.length) return
  try {
    const { data } = await client.get('/roms/platforms/known')
    romPlatforms.value = data.map((p: any) => ({ fs_slug: p.fs_slug, name: p.name }))
      .sort((a: RomPlatform, b: RomPlatform) => a.name.localeCompare(b.name))
  } catch { /* ignore */ }
}

onMounted(() => { if (props.defaultPlatform === 'roms') loadRomPlatforms() })
watch(() => props.defaultPlatform, (p) => { if (p === 'roms') loadRomPlatforms() })

// ── Custom platform picker ────────────────────────────────────────────────────
const platOpen   = ref(false)
const platSearch = ref('')

const selectedPlatform = computed(() =>
  romPlatforms.value.find(p => p.fs_slug === form.value.platform_slug) ?? null
)
const filteredPlatforms = computed(() => {
  const q = platSearch.value.toLowerCase()
  return q ? romPlatforms.value.filter(p => p.name.toLowerCase().includes(q)) : romPlatforms.value
})
function selectPlatform(p: RomPlatform) {
  form.value.platform_slug = p.fs_slug
  platOpen.value = false
  platSearch.value = ''
}

// ── Submit form ───────────────────────────────────────────────────────────────
const form = ref({ title: '', description: '', link: '', platform_slug: '' })
const submitting  = ref(false)
const submitError = ref('')
const submitOk    = ref(false)

// Search state
interface Suggestion { title: string; year: number | null; developer: string | null; cover_url: string | null; url?: string | null; source: string }
const suggestions  = ref<Suggestion[]>([])
const selectedGame = ref<Suggestion | null>(null)
const searching    = ref(false)
const searchDone   = ref(false)
let   searchTimer: ReturnType<typeof setTimeout> | null = null

function resetForm() {
  form.value = { title: '', description: '', link: '', platform_slug: '' }
  suggestions.value = []; selectedGame.value = null
  submitError.value = ''; submitOk.value = false; searchDone.value = false
  platOpen.value = false; platSearch.value = ''
}

function onTitleInput() {
  selectedGame.value = null
  suggestions.value  = []
  searchDone.value   = false
  if (searchTimer) clearTimeout(searchTimer)
  if (form.value.title.length < 3) return
  searchTimer = setTimeout(doSearch, 500)
}

async function doSearch() {
  searching.value = true
  searchDone.value = false
  try {
    const params: Record<string, string> = {
      q: form.value.title,
      type: props.defaultPlatform || 'games',
    }
    if (props.defaultPlatform === 'roms' && form.value.platform_slug) {
      params.platform_slug = form.value.platform_slug
    }
    const { data } = await client.get('/requests/search', { params })
    suggestions.value = data
  } catch { suggestions.value = [] } finally {
    searching.value  = false
    searchDone.value = true
  }
}

// Re-search when platform changes (for ROMs)
watch(() => form.value.platform_slug, () => {
  if (props.defaultPlatform === 'roms' && form.value.title.length >= 3) {
    suggestions.value = []; selectedGame.value = null
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(doSearch, 300)
  }
})

function selectSuggestion(s: Suggestion) {
  selectedGame.value = s
  form.value.title   = s.title
  suggestions.value  = []
  // Auto-fill link and description from suggestion
  if (s.url && !form.value.link) {
    form.value.link = s.url
  }
  if ((s as any).description && !form.value.description) {
    form.value.description = (s as any).description
  }
}

function clearSelection() {
  selectedGame.value = null
  suggestions.value  = []
  searchDone.value   = false
}

async function submitRequest() {
  submitError.value = ''; submitOk.value = false; submitting.value = true
  try {
    const payload: Record<string, any> = {
      title:         form.value.title.trim(),
      description:   form.value.description || null,
      link:          form.value.link || null,
      platform:      props.defaultPlatform || 'games',
      platform_slug: props.defaultPlatform === 'roms' ? (form.value.platform_slug || null) : null,
      cover_url:     selectedGame.value?.cover_url || null,
    }
    const { data } = await client.post('/requests', payload)
    requests.value.unshift(data)
    submitOk.value = true
    resetForm()
    setTimeout(() => { tab.value = 'list'; submitOk.value = false }, 1400)
  } catch (e: any) {
    submitError.value = e?.response?.data?.detail || 'Failed to submit'
  } finally { submitting.value = false }
}

// ── Request list ──────────────────────────────────────────────────────────────
interface GameReq {
  id: number; title: string; description: string | null; link: string | null
  platform: string; platform_slug: string | null; cover_url: string | null
  status: string; admin_note: string | null
  user_id: number; username: string | null
  vote_count: number; user_voted: boolean; created_at: string | null
}

const requests = ref<GameReq[]>([])
const loading  = ref(false)
const voting   = ref<number | null>(null)

const sortedRequests = computed(() =>
  [...requests.value].sort((a, b) => b.vote_count - a.vote_count || b.id - a.id)
)

async function loadRequests() {
  if (loading.value) return
  loading.value = true
  try {
    const { data } = await client.get('/requests')
    requests.value = data
    // Mark current user's requests as seen - clears the user badge
    const userId = auth.user?.id
    if (userId) markSeen(data.filter((r: GameReq) => r.user_id === userId))
  } catch { /* ignore */ } finally { loading.value = false }
}

async function vote(r: GameReq) {
  if (r.user_voted || voting.value === r.id) return
  voting.value = r.id
  try { const { data } = await client.post(`/requests/${r.id}/vote`); r.vote_count = data.vote_count; r.user_voted = true }
  catch { /* ignore */ } finally { voting.value = null }
}

// ── Admin ─────────────────────────────────────────────────────────────────────
async function patchStatus(r: GameReq, status: string) {
  try { await client.patch(`/requests/${r.id}`, { status }); r.status = status } catch { /* ignore */ }
}

const noteEditId   = ref<number | null>(null)
const noteEditText = ref('')

function openNoteEdit(r: GameReq) { noteEditId.value = r.id; noteEditText.value = r.admin_note || '' }
async function saveNote() {
  const id = noteEditId.value; if (id === null) return
  const r = requests.value.find(x => x.id === id)
  try { await client.patch(`/requests/${id}`, { admin_note: noteEditText.value }); if (r) r.admin_note = noteEditText.value || null; noteEditId.value = null } catch { /* ignore */ }
}

async function deleteReq(r: GameReq) {
  if (!confirm(t('requests.delete_request'))) return
  try { await client.delete(`/requests/${r.id}`); requests.value = requests.value.filter(x => x.id !== r.id) } catch { /* ignore */ }
}

function formatDate(iso: string) {
  try {
    const lang = localStorage.getItem('gd-lang') || 'en'
    return new Date(iso).toLocaleDateString(lang === 'pl' ? 'pl-PL' : 'en-US')
  } catch { return '' }
}
</script>

<style scoped>
/* ── Backdrop & box ─────────────────────────────────────────────────────────── */
.grd-backdrop {
  position: fixed; inset: 0; z-index: 3000;
  background: rgba(0,0,0,.65); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center; padding: var(--space-4, 16px);
}
.grd-box {
  width: 720px; max-width: 100%; max-height: 90vh;
  border-radius: var(--radius); display: flex; flex-direction: column;
  box-shadow: 0 24px 80px rgba(0,0,0,.7); overflow: hidden;
}

/* ── Header ────────────────────────────────────────────────────────────────── */
.grd-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--glass-border);
  background: rgba(124,58,237,.07); flex-shrink: 0; gap: var(--space-3, 12px); flex-wrap: wrap;
}
.grd-header-left { display: flex; align-items: center; gap: 9px; font-size: 15px; font-weight: 700; color: var(--text); }
.grd-platform-tag {
  font-size: var(--fs-xs, 10px); font-weight: 700; padding: 2px 8px; border-radius: 10px;
  background: rgba(124,58,237,.2); color: var(--pl-light); text-transform: uppercase; letter-spacing: .05em;
}
.grd-header-right { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.grd-tabs { display: flex; gap: var(--space-1, 4px); }
.grd-tab {
  padding: 5px 12px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 600;
  color: var(--muted); background: none; border: none; cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 6px;
}
.grd-tab:hover { background: rgba(255,255,255,.06); color: var(--text); }
.grd-tab.active { background: rgba(255,255,255,.08); color: var(--text); box-shadow: inset 0 -2px 0 var(--pl); }
.grd-tab-badge { font-size: var(--fs-xs, 10px); font-weight: 700; padding: 1px 6px; border-radius: 10px; background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); }
.grd-close {
  width: 28px; height: 28px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.grd-close:hover { background: rgba(255,255,255,.12); color: var(--text); }

/* ── Body ───────────────────────────────────────────────────────────────────── */
.grd-body { flex: 1; overflow-y: auto; padding: 18px 20px; min-height: 0; }
.grd-body--list { padding: 0; position: relative; }

/* ── Form ───────────────────────────────────────────────────────────────────── */
.grd-form { display: flex; flex-direction: column; gap: 14px; }
.grd-field { display: flex; flex-direction: column; gap: 5px; }
.grd-label { font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.grd-label-opt { font-weight: 400; text-transform: none; letter-spacing: 0; opacity: .7; }
.grd-input, .grd-textarea, .grd-select {
  background: rgba(255,255,255,.05); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); color: var(--text); font-size: 13px; font-family: inherit;
  padding: 8px 12px; outline: none; transition: border-color .15s;
}
.grd-input:focus, .grd-textarea:focus, .grd-select:focus { border-color: var(--pl); }
.grd-textarea { resize: vertical; min-height: 60px; }
.grd-select { cursor: pointer; }

/* ── Custom platform picker ──────────────────────────────────────────────────── */
.grd-plat-picker { position: relative; }
.grd-plat-trigger {
  width: 100%; display: flex; align-items: center; gap: var(--space-2, 8px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); color: var(--text); font-size: 13px; font-family: inherit;
  padding: 8px 12px; cursor: pointer; text-align: left; transition: border-color .15s;
}
.grd-plat-trigger:hover { border-color: rgba(255,255,255,.25); }
.grd-plat-trigger:focus-visible { outline: 2px solid var(--pl); border-color: var(--pl); }
.grd-plat-placeholder { color: var(--muted); }
.grd-plat-chevron { margin-left: auto; flex-shrink: 0; transition: transform .15s; }
.grd-plat-chevron.open { transform: rotate(180deg); }
.grd-plat-icon { width: 20px; height: 20px; object-fit: contain; flex-shrink: 0; }
.grd-plat-backdrop { position: fixed; inset: 0; z-index: 3010; }
.grd-plat-dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 3020;
  background: #1a1025; border: 1px solid var(--glass-border);
  border-radius: 10px; overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,.65);
}
.grd-plat-search-wrap { padding: 7px 8px; border-bottom: 1px solid var(--glass-border); }
.grd-plat-search-input {
  width: 100%; background: rgba(255,255,255,.07); border: 1px solid var(--glass-border);
  border-radius: 6px; color: var(--text); font-size: var(--fs-sm, 12px); font-family: inherit;
  padding: 5px 10px; outline: none; box-sizing: border-box;
}
.grd-plat-search-input:focus { border-color: var(--pl); }
.grd-plat-list { max-height: 200px; overflow-y: auto; }
.grd-plat-option {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 7px 12px; background: none; border: none; cursor: pointer;
  color: var(--text); font-size: 13px; font-family: inherit; text-align: left;
  transition: background .1s;
}
.grd-plat-option:hover { background: rgba(255,255,255,.06); }
.grd-plat-option.selected { background: rgba(124,58,237,.15); color: var(--pl-light); }

/* Search wrap */
.grd-search-wrap { position: relative; }
.grd-search-spinner {
  position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.2); border-top-color: var(--pl);
  animation: grd-spin .7s linear infinite;
}

/* ── Suggestions grid ────────────────────────────────────────────────────────── */
.grd-suggestions {
  margin-top: 6px; border: 1px solid var(--glass-border); border-radius: 10px; overflow: hidden;
  background: rgba(0,0,0,.25);
}
.grd-sug-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; font-size: 11px; color: var(--muted);
  border-bottom: 1px solid var(--glass-border); background: rgba(255,255,255,.03);
}
.grd-sug-skip {
  font-size: 11px; font-weight: 600; color: var(--pl-light); background: none; border: none;
  cursor: pointer; padding: 0; text-decoration: underline;
}
.grd-sug-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: var(--space-2, 8px); padding: 10px; max-height: 280px; overflow-y: auto;
}
.grd-sug-card {
  display: flex; flex-direction: column; gap: 5px;
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); cursor: pointer; padding: 0 0 8px;
  text-align: left; transition: all .15s; overflow: hidden;
}
.grd-sug-card:hover { background: rgba(124,58,237,.12); border-color: var(--pl); transform: translateY(-1px); }
.grd-sug-cover { width: 100%; aspect-ratio: 3/4; overflow: hidden; background: rgba(0,0,0,.4); }
.grd-sug-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.grd-sug-cover-empty { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.grd-sug-info { padding: 0 8px; display: flex; flex-direction: column; gap: 1px; }
.grd-sug-title { font-size: 11px; font-weight: 700; color: var(--text); line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.grd-sug-year { font-size: var(--fs-xs, 10px); color: var(--muted); }
.grd-sug-dev { font-size: var(--fs-xs, 10px); color: var(--muted); opacity: .7; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grd-sug-src { font-size: 9px; color: var(--pl-light); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-top: 2px; }

/* ── Selected game ───────────────────────────────────────────────────────────── */
.grd-selected {
  display: flex; align-items: center; gap: var(--space-3, 12px); margin-top: 8px;
  padding: 10px 12px; border-radius: var(--radius-sm, 8px);
  background: rgba(124,58,237,.1); border: 1px solid rgba(124,58,237,.3);
}
.grd-selected-cover { width: 42px; height: 56px; object-fit: cover; border-radius: var(--radius-xs, 4px); flex-shrink: 0; }
.grd-selected-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.grd-selected-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.grd-selected-meta { font-size: var(--fs-sm, 12px); color: var(--muted); }
.grd-selected-src { font-size: var(--fs-xs, 10px); color: var(--pl-light); font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.grd-selected-clear {
  width: 26px; height: 26px; border-radius: 6px; flex-shrink: 0;
  background: rgba(255,255,255,.08); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s;
}
.grd-selected-clear:hover { background: rgba(239,68,68,.15); border-color: #f87171; color: #f87171; }

.grd-no-results { font-size: var(--fs-sm, 12px); color: var(--muted); opacity: .7; margin-top: 4px; font-style: italic; }

/* ── Messages & footer ───────────────────────────────────────────────────────── */
.grd-msg { padding: 8px 12px; border-radius: 6px; font-size: var(--fs-sm, 12px); }
.grd-msg--err { background: rgba(239,68,68,.1); color: #f87171; border: 1px solid rgba(239,68,68,.3); }
.grd-msg--ok  { background: rgba(74,222,128,.1); color: #4ade80; border: 1px solid rgba(74,222,128,.3); }
.grd-form-footer { display: flex; justify-content: flex-end; gap: var(--space-2, 8px); padding-top: 4px; }

/* ── List view ──────────────────────────────────────────────────────────────── */
.grd-loading { display: flex; justify-content: center; align-items: center; padding: var(--space-12, 48px); }
.grd-empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: var(--space-12, 48px); color: var(--muted); font-size: 13px; opacity: .6; }
.grd-list { display: flex; flex-direction: column; }
.grd-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--glass-border); transition: background .1s; }
.grd-item:last-child { border-bottom: none; }
.grd-item:hover { background: rgba(255,255,255,.03); }
.grd-item--done { opacity: .65; }
.grd-item--rejected { opacity: .5; }

.grd-item-cover { width: 36px; height: 48px; border-radius: var(--radius-xs, 4px); overflow: hidden; flex-shrink: 0; background: rgba(255,255,255,.05); }
.grd-item-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.grd-item-cover-empty { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }

.grd-vote-col { display: flex; flex-direction: column; align-items: center; gap: 2px; flex-shrink: 0; padding-top: 2px; }
.grd-vote-btn { width: 26px; height: 26px; border-radius: 6px; background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .15s; }
.grd-vote-btn:hover:not(:disabled) { background: rgba(124,58,237,.2); border-color: var(--pl); color: var(--pl-light); }
.grd-vote-btn.voted { background: rgba(124,58,237,.15); border-color: var(--pl); color: var(--pl-light); cursor: default; }
.grd-vote-btn:disabled:not(.voted) { opacity: .4; cursor: not-allowed; }
.grd-vote-count { font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--text); }

.grd-item-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.grd-item-top { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.grd-item-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.grd-item-desc { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }
.grd-item-link { font-size: 11px; }
.grd-link { color: var(--pl-light); text-decoration: none; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; vertical-align: bottom; }
.grd-link:hover { text-decoration: underline; }
.grd-admin-note { font-size: 11px; color: #fbbf24; display: flex; align-items: flex-start; gap: 5px; line-height: 1.4; }
.grd-item-meta { font-size: 11px; color: var(--muted); opacity: .6; }

.grd-status-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: var(--radius-xs, 4px); text-transform: uppercase; letter-spacing: .05em; flex-shrink: 0; }
.grd-status--pending  { background: rgba(251,191,36,.15); color: #fbbf24; }
.grd-status--approved { background: rgba(74,222,128,.15); color: #4ade80; }
.grd-status--rejected { background: rgba(239,68,68,.15);  color: #f87171; }
.grd-status--done     { background: rgba(139,92,246,.15); color: #a78bfa; }
.grd-platform-badge { font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: var(--radius-xs, 4px); text-transform: uppercase; background: rgba(255,255,255,.07); color: var(--muted); flex-shrink: 0; }

.grd-admin-col { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }
.grd-status-select { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); border-radius: 6px; color: var(--text); font-size: 11px; padding: 4px 6px; cursor: pointer; outline: none; }
.grd-note-btn, .grd-del-btn { width: 26px; height: 26px; border-radius: 6px; cursor: pointer; background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); display: flex; align-items: center; justify-content: center; transition: all .15s; }
.grd-note-btn { color: #fbbf24; }
.grd-note-btn:hover { background: rgba(251,191,36,.15); border-color: #fbbf24; }
.grd-del-btn { color: #f87171; }
.grd-del-btn:hover { background: rgba(239,68,68,.15); border-color: #f87171; }

.grd-note-overlay { position: absolute; inset: 0; z-index: 10; background: rgba(0,0,0,.5); backdrop-filter: blur(4px); display: flex; align-items: center; justify-content: center; padding: var(--space-6, 24px); }
.grd-note-box { width: 100%; max-width: 440px; border-radius: var(--radius); padding: 18px 20px; display: flex; flex-direction: column; gap: var(--space-3, 12px); }
.grd-note-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.grd-note-actions { display: flex; justify-content: flex-end; gap: var(--space-2, 8px); }

/* ── Buttons ────────────────────────────────────────────────────────────────── */
.grd-btn { padding: 7px 16px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer; border: none; display: flex; align-items: center; gap: 6px; transition: all .15s; }
.grd-btn--ghost { background: rgba(255,255,255,.06); border: 1px solid var(--glass-border); color: var(--muted); }
.grd-btn--ghost:hover { background: rgba(255,255,255,.12); color: var(--text); }
.grd-btn--primary { background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); box-shadow: 0 2px 12px var(--pglow2); }
.grd-btn--primary:hover { background: var(--pl-light); }
.grd-btn--primary:disabled { opacity: .55; cursor: not-allowed; }

/* ── Spinner ────────────────────────────────────────────────────────────────── */
.grd-spinner { display: inline-block; width: 13px; height: 13px; border-radius: 50%; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; animation: grd-spin .7s linear infinite; }
.grd-spinner--lg { width: 28px; height: 28px; border-width: 3px; }
@keyframes grd-spin { to { transform: rotate(360deg); } }

/* ── Transition ─────────────────────────────────────────────────────────────── */
.grd-fade-enter-active, .grd-fade-leave-active { transition: opacity .2s ease, transform .2s ease; }
.grd-fade-enter-from, .grd-fade-leave-to { opacity: 0; transform: scale(.97); }

/* ── My GOG tab ─────────────────────────────────────────────────────────────── */
.grd-body--mygog { padding: 12px 16px; }
.grd-mygog-grid {
  display: flex; flex-direction: column; gap: 2px;
}
.grd-mygog-card {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: var(--radius-sm, 8px);
  transition: background .1s;
}
.grd-mygog-card:hover { background: rgba(255,255,255,.04); }
.grd-mygog-cover {
  width: 36px; height: 48px; border-radius: var(--radius-xs, 4px);
  overflow: hidden; flex-shrink: 0; background: rgba(255,255,255,.05);
}
.grd-mygog-cover img {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.grd-mygog-cover-empty {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
}
.grd-mygog-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.grd-mygog-title {
  font-size: 13px; font-weight: 700; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.grd-mygog-date { font-size: 11px; color: var(--muted); }
.grd-mygog-req-btn {
  flex-shrink: 0; padding: 5px 12px; border-radius: var(--radius-sm);
  font-size: 11px; font-weight: 700; font-family: inherit;
  border: 1px solid var(--pl); background: rgba(124,58,237,.15);
  color: var(--pl-light); cursor: pointer; transition: all .15s;
  display: flex; align-items: center; gap: 5px;
}
.grd-mygog-req-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--pl) 25%, transparent); color: var(--pl-light); }
.grd-mygog-req-btn:disabled { opacity: .5; cursor: not-allowed; }
.grd-mygog-req-btn.requested {
  background: rgba(74,222,128,.1); border-color: rgba(74,222,128,.3);
  color: #4ade80; cursor: default;
}

/* ── Mobile ──────────────────────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .grd-backdrop { padding: var(--space-2, 8px); align-items: flex-end; }
  .grd-box { max-height: 92vh; border-radius: 16px 16px 0 0; width: 100%; }
  .grd-header { flex-wrap: wrap; }
  .grd-header-right { width: 100%; justify-content: space-between; }
  .grd-sug-grid { grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); }
}
</style>
