<template>
  <div class="rgp-wrap" ref="wrapRef">
    <!-- Dice button -->
    <button
      class="rgp-btn"
      :class="{ active: open, rolling: rolling }"
      @click="toggle"
      :title="t('random.pick_title')"
    >
      <svg class="dice-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="3" width="18" height="18" rx="3" ry="3"/>
        <circle cx="8.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
        <circle cx="15.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
        <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>
        <circle cx="8.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
        <circle cx="15.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
      </svg>
    </button>

    <!-- Popover panel -->
    <Transition name="rgp-pop">
      <div v-if="open" class="rgp-panel glass">
        <div class="rgp-panel-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="3" ry="3"/>
            <circle cx="8.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="15.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="8.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="15.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
          </svg>
          {{ t('random.title') }}
        </div>

        <!-- Source -->
        <div class="rgp-row">
          <label class="rgp-label">{{ t('random.library') }}</label>
          <div class="rgp-chips">
            <button
              v-for="s in sources"
              :key="s.value"
              class="rgp-chip"
              :class="{ active: selectedSource === s.value }"
              @click="selectedSource = s.value"
            >{{ s.label }}</button>
          </div>
        </div>

        <!-- Platform -->
        <div class="rgp-row">
          <label class="rgp-label">{{ t('random.platform') }}</label>
          <div class="rgp-chips">
            <button class="rgp-chip" :class="{ active: platform === '' }" @click="platform = ''">{{ t('random.any') }}</button>
            <button class="rgp-chip" :class="{ active: platform === 'win' }" @click="platform = 'win'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M3 12V6.75l6-1.02V12H3zm7-6.37L21 3.75V12h-11V5.63zM3 13h6v6.13l-6-1.02V13zm7 6.37V13h11v8.25L10 19.37z"/></svg>
              Windows
            </button>
            <button class="rgp-chip" :class="{ active: platform === 'mac' }" @click="platform = 'mac'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C9.5 2 7.5 3.5 7.5 3.5S5 2.5 3.5 5c-1.5 2.5-.5 6 1 8 1 1.5 2 3 3.5 3s2-.5 4-.5 2.5.5 4 .5 2.5-1.5 3.5-3c1-1.5 2-4 1-7-1-3-3-4-5-4a5 5 0 0 0-2 .5S14 2 12 2z"/></svg>
              macOS
            </button>
            <button class="rgp-chip" :class="{ active: platform === 'linux' }" @click="platform = 'linux'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="4" r="2"/><path d="M12 6v4M8 18s-1-6 1-9m7 9s1-6-1-9"/><path d="M7 18c-1 0-2 1-2 2h10c0-1-1-2-2-2"/></svg>
              Linux
            </button>
          </div>
        </div>

        <!-- Genre -->
        <div class="rgp-row" v-if="availableGenres.length">
          <label class="rgp-label">{{ t('random.genre') }}</label>
          <div class="rgp-genre-wrap">
            <select v-model="selectedGenre" class="rgp-select">
              <option value="">{{ t('random.any_genre') }}</option>
              <option v-for="g in availableGenres" :key="g" :value="g">{{ g }}</option>
            </select>
          </div>
        </div>

        <!-- Available only -->
        <div class="rgp-row rgp-row--toggle">
          <label class="rgp-label">{{ t('random.has_files') }}</label>
          <button
            class="rgp-toggle"
            :class="{ on: availableOnly }"
            @click="availableOnly = !availableOnly"
          >
            <span class="rgp-toggle-knob" />
          </button>
        </div>

        <!-- Status / result preview -->
        <div v-if="filteredCount !== null" class="rgp-count">
          <span v-if="filteredCount > 0">{{ filteredCount === 1 ? t('random.matching', { count: filteredCount }) : t('random.matching_plural', { count: filteredCount }) }}</span>
          <span v-else class="rgp-count--none">{{ t('random.no_match') }}</span>
        </div>
        <div v-else-if="loadingGames" class="rgp-count">{{ t('common.loading') }}</div>

        <!-- Roll button -->
        <button
          class="rgp-roll-btn"
          :class="{ disabled: filteredCount === 0 || loadingGames }"
          :disabled="filteredCount === 0 || loadingGames || rolling"
          @click="pickRandom"
        >
          <svg class="roll-icon" :class="{ spin: rolling }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <rect x="3" y="3" width="18" height="18" rx="3" ry="3"/>
            <circle cx="8.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="15.5" cy="8.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="8.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
            <circle cx="15.5" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>
          </svg>
          {{ rolling ? t('random.rolling') : t('random.roll') }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const router = useRouter()
const auth   = useAuthStore()

const isAdmin = computed(() => auth.user?.role === 'admin')

// ── State ────────────────────────────────────────────────────────────────────
const open         = ref(false)
const rolling      = ref(false)
const loadingGames = ref(false)
const wrapRef      = ref<HTMLElement>()

const selectedSource = ref<'all' | 'games' | 'gog'>('all')
const platform       = ref('')
const selectedGenre  = ref('')
const availableOnly  = ref(false)

const allGames     = ref<any[]>([])
const allGogGames  = ref<any[]>([])

// ── Sources (GOG only visible to admin) ─────────────────────────────────────
const sources = computed(() => {
  const opts: { value: 'all' | 'games' | 'gog'; label: string }[] = [
    { value: 'all', label: t('random.all') },
    { value: 'games', label: t('random.games') },
  ]
  if (isAdmin.value) opts.push({ value: 'gog', label: 'GOG' })
  return opts
})

// ── Merged pool based on source filter ───────────────────────────────────────
const gamePool = computed(() => {
  const tagged = [
    ...allGames.value.map(g => ({ ...g, _lib: 'games' })),
    ...(isAdmin.value ? allGogGames.value.map(g => ({ ...g, _lib: 'gog' })) : []),
  ]
  if (selectedSource.value === 'games') return tagged.filter(g => g._lib === 'games')
  if (selectedSource.value === 'gog')   return tagged.filter(g => g._lib === 'gog')
  return tagged
})

// ── Available genres from pool ───────────────────────────────────────────────
const availableGenres = computed(() => {
  const set = new Set<string>()
  for (const g of gamePool.value) {
    for (const genre of (g.genres as string[] | null) ?? []) set.add(genre)
  }
  return Array.from(set).sort()
})

// ── Filtered list ────────────────────────────────────────────────────────────
const filteredGames = computed(() => {
  let list = gamePool.value
  if (platform.value === 'win')   list = list.filter(g => g.os_windows)
  if (platform.value === 'mac')   list = list.filter(g => g.os_mac)
  if (platform.value === 'linux') list = list.filter(g => g.os_linux)
  if (selectedGenre.value)        list = list.filter(g => (g.genres ?? []).includes(selectedGenre.value))
  if (availableOnly.value)        list = list.filter(g => (g.file_count ?? g._fileCount ?? 0) > 0)
  return list
})

const filteredCount = computed(() => loadingGames.value ? null : filteredGames.value.length)

// ── Data loading ─────────────────────────────────────────────────────────────
async function loadGames() {
  if (allGames.value.length && allGogGames.value.length) return
  loadingGames.value = true
  try {
    const tasks: Promise<any>[] = [
      client.get('/library/games', { params: { limit: '2000' } }),
    ]
    if (isAdmin.value) tasks.push(client.get('/gog/library/games'))
    const [libRes, gogRes] = await Promise.allSettled(tasks)

    if (libRes.status === 'fulfilled') {
      allGames.value = (libRes.value.data.items as any[]).map(g => ({
        id: g.id,
        slug: g.slug,
        title: g.title,
        cover_path: g.cover_path,
        genres: g.genres ?? [],
        os_windows: g.os_windows ?? false,
        os_mac: g.os_mac ?? false,
        os_linux: g.os_linux ?? false,
        file_count: (g.files as any[])?.filter((f: any) => f.is_available).length ?? 0,
      }))
    }
    if (gogRes && gogRes.status === 'fulfilled') {
      allGogGames.value = (gogRes.value.data as any[]).map(g => ({
        id: g.id,
        slug: g.slug,
        title: g.title,
        cover_path: g.cover_path,
        genres: g.genres ?? [],
        os_windows: g.os_windows ?? true,
        os_mac: g.os_mac ?? false,
        os_linux: g.os_linux ?? false,
        file_count: 1, // GOG games are always "available"
      }))
    }
  } catch (e) {
    console.error('RandomGamePicker: failed to load games', e)
  } finally {
    loadingGames.value = false
  }
}

// ── Toggle open ──────────────────────────────────────────────────────────────
function toggle() {
  open.value = !open.value
  if (open.value) loadGames()
}

// ── Pick random ───────────────────────────────────────────────────────────────
async function pickRandom() {
  const list = filteredGames.value
  if (!list.length) return

  rolling.value = true

  // Short "rolling" animation delay
  await new Promise(r => setTimeout(r, 480))

  const game = list[Math.floor(Math.random() * list.length)]
  open.value = false
  rolling.value = false

  if (game._lib === 'gog') {
    router.push({ name: 'game-detail', params: { id: game.id } })
  } else {
    router.push({ name: 'games-detail', params: { id: game.id } })
  }
}

// ── Click outside ────────────────────────────────────────────────────────────
function onDocClick(e: MouseEvent) {
  if (open.value && wrapRef.value && !wrapRef.value.contains(e.target as Node)) {
    open.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick, true))
onUnmounted(() => document.removeEventListener('click', onDocClick, true))
</script>

<style scoped>
.rgp-wrap {
  position: relative;
}

/* ── Dice button ──────────────────────────────────────────────────────────── */
.rgp-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  border: 1px solid var(--glass-border, rgba(255,255,255,0.08));
  background: rgba(255,255,255,0.04);
  color: var(--text-muted, rgba(255,255,255,0.5));
  cursor: pointer;
  transition: background .15s, color .15s, border-color .15s, transform .12s;
}
.rgp-btn:hover {
  background: rgba(255,255,255,0.09);
  color: var(--text, #fff);
  border-color: rgba(255,255,255,0.15);
}
.rgp-btn.active {
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  color: var(--pl-light);
  border-color: color-mix(in srgb, var(--pl) 35%, transparent);
}
.rgp-btn.rolling .dice-icon {
  animation: dice-shake 0.22s ease-in-out infinite alternate;
}

@keyframes dice-shake {
  from { transform: rotate(-18deg) scale(1.05); }
  to   { transform: rotate(18deg) scale(1.1); }
}

/* ── Panel ────────────────────────────────────────────────────────────────── */
.rgp-panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 300px;
  padding: var(--space-4, 16px);
  border-radius: 14px;
  z-index: 500;
  display: flex;
  flex-direction: column;
  gap: var(--space-3, 12px);
  backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 160%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px, 20px)) saturate(var(--glass-sat, 160%));
  border: 1px solid var(--glass-border, rgba(255,255,255,0.09));
  box-shadow: 0 8px 40px rgba(0,0,0,0.5);
}

.rgp-panel-header {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .06em;
  text-transform: uppercase;
  color: var(--text-muted, rgba(255,255,255,0.45));
  padding-bottom: 10px;
  border-bottom: 1px solid var(--glass-border, rgba(255,255,255,0.07));
}

/* ── Rows ─────────────────────────────────────────────────────────────────── */
.rgp-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rgp-row--toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}
.rgp-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted, rgba(255,255,255,0.45));
  letter-spacing: .04em;
}

/* ── Chips ────────────────────────────────────────────────────────────────── */
.rgp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.rgp-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1, 4px);
  padding: 4px 9px;
  border-radius: 6px;
  font-size: 11.5px;
  font-weight: 500;
  border: 1px solid var(--glass-border, rgba(255,255,255,0.08));
  background: rgba(255,255,255,0.04);
  color: var(--text-muted, rgba(255,255,255,0.5));
  cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.rgp-chip:hover {
  background: rgba(255,255,255,0.08);
  color: var(--text, #fff);
}
.rgp-chip.active {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--pl-light);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
}

/* ── Genre select ─────────────────────────────────────────────────────────── */
.rgp-genre-wrap {
  display: flex;
}
.rgp-select {
  width: 100%;
  padding: 5px 8px;
  border-radius: 7px;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--glass-border, rgba(255,255,255,0.09));
  color: var(--text, #fff);
  font-size: var(--fs-sm, 12px);
  cursor: pointer;
  outline: none;
}
.rgp-select option {
  background: #1a1030;
  color: #fff;
}

/* ── Toggle ───────────────────────────────────────────────────────────────── */
.rgp-toggle {
  position: relative;
  width: 34px;
  height: 18px;
  border-radius: 9px;
  border: 1px solid var(--glass-border, rgba(255,255,255,0.12));
  background: rgba(255,255,255,0.06);
  cursor: pointer;
  transition: background .18s, border-color .18s;
  flex-shrink: 0;
}
.rgp-toggle.on {
  background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1));
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  box-shadow: 0 0 8px var(--pglow2);
}
.rgp-toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255,255,255,0.4);
  transition: transform .18s, background .18s;
}
.rgp-toggle.on .rgp-toggle-knob {
  transform: translateX(16px);
  background: #fff;
}

/* ── Count ────────────────────────────────────────────────────────────────── */
.rgp-count {
  font-size: 11.5px;
  color: var(--text-muted, rgba(255,255,255,0.4));
  text-align: center;
  padding: 2px 0;
}
.rgp-count--none {
  color: rgba(239,68,68,0.7);
}

/* ── Roll button ──────────────────────────────────────────────────────────── */
.rgp-roll-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  width: 100%;
  padding: 9px 0;
  border-radius: 9px;
  border: none;
  background: color-mix(in srgb, var(--pl) 25%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity .15s, transform .1s;
}
.rgp-roll-btn:hover:not(.disabled) {
  background: color-mix(in srgb, var(--pl) 40%, transparent);
  border-color: var(--pl);
  color: #fff;
  transform: translateY(-1px);
}
.rgp-roll-btn.disabled,
.rgp-roll-btn:disabled {
  opacity: .3;
  cursor: not-allowed;
  transform: none;
}
.roll-icon.spin {
  animation: roll-spin .4s linear infinite;
}
@keyframes roll-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* ── Transition ───────────────────────────────────────────────────────────── */
.rgp-pop-enter-active { transition: opacity .15s, transform .15s; }
.rgp-pop-leave-active { transition: opacity .12s, transform .1s; }
.rgp-pop-enter-from  { opacity: 0; transform: translateY(-6px) scale(.97); }
.rgp-pop-leave-to    { opacity: 0; transform: translateY(-4px) scale(.98); }
</style>
