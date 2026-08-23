<template>
  <div class="rsp-home">

    <!-- Title bar -->
    <div class="rsp-title-bar">
      <div class="rsp-title-left">
        <button class="lib-back-btn" @click="router.push('/emulation')" :title="t('romsrc.back_to_retro', 'Retro')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          {{ t('nav.emulation', 'Emulation') }}
        </button>
        <!-- The owning plugin's own icon when it ships one; the generic glyph is
             only the fallback for a source whose plugin has no art. -->
        <img v-if="sourceIcon && !iconFail" :src="sourceIcon" class="rsp-title-logo" :alt="headerTitle" @error="iconFail = true" />
        <svg v-else width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" class="rsp-title-ico">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
          <polyline points="12 8 12 14"/><polyline points="9 11 12 14 15 11"/>
        </svg>
        <div>
          <h1 class="title-text">{{ headerTitle }}</h1>
          <p class="title-sub">{{ platforms.length }} {{ t('romsrc.platforms', 'platforms') }}</p>
        </div>
      </div>

      <div class="rsp-title-right">
        <!-- Same card sizes as the Retro grid, sharing its setting: the two
             grids are the same object and reading them differently is jarring. -->
        <div class="size-group" :title="t('romsrc.card_size', 'Card size')">
          <button
            v-for="sz in cardSizes"
            :key="sz.id"
            class="size-btn"
            :class="{ active: cardSize === sz.id }"
            @click="cardSize = sz.id"
          >{{ sz.label }}</button>
        </div>

        <!-- A source caches its listings, so a platform that came back empty
             while the archive was down keeps looking empty afterwards. This is
             how to say "forget that and ask again" without waiting it out. -->
        <button
          class="rsp-refresh"
          :class="{ busy: refreshing }"
          :disabled="refreshing"
          :title="t('romsrc.refresh_hint', 'Refresh the lists from the source')"
          @click="refreshLists"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
            <polyline points="23 4 23 10 17 10"/>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          <span>{{ t('romsrc.refresh', 'Refresh') }}</span>
        </button>
      </div>
    </div>

    <!-- Not configured -->
    <div v-if="notConfigured" class="rsp-notice">
      <div class="rsp-notice-icon">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      </div>
      <p class="rsp-notice-title">{{ t('romsrc.not_configured', 'Not configured') }}</p>
      <p class="rsp-notice-sub">{{ t('romsrc.configure_hint', 'Add your credentials in Settings, Plugins to browse this source.') }}</p>
      <button class="rsp-notice-btn" @click="router.push('/settings?tab=plugins')">{{ t('romsrc.open_settings', 'Open plugin settings') }}</button>
    </div>

    <!-- Loading -->
    <div v-else-if="loading" class="rsp-loading"><span class="spinner" /></div>

    <!-- Error -->
    <div v-else-if="errMsg" class="rsp-notice">
      <p class="rsp-notice-title">{{ t('romsrc.error', 'Could not load platforms') }}</p>
      <p class="rsp-notice-sub">{{ errMsg }}</p>
    </div>

    <!-- Empty -->
    <div v-else-if="!platforms.length" class="rsp-notice">
      <p class="rsp-notice-title">{{ t('romsrc.no_platforms', 'This source offers no recognised platforms.') }}</p>
    </div>

    <!-- Platform grid -->
    <div v-else class="rsp-grid" :style="{
      '--card-min': cardSizeMap[cardSize].min + 'px',
      '--card-height': cardSizeMap[cardSize].height + 'px',
      '--card-icon': cardSizeMap[cardSize].icon + 'px',
      '--card-logo': cardSizeMap[cardSize].logo + 'px',
    }">
      <div
        v-for="(p, idx) in platforms"
        :key="p.fs_slug"
        class="rsp-card"
        :style="cardStyle(p.fs_slug)"
        @click="openPlatform(p)"
      >
        <div class="rsp-hero">
          <img
            :src="art(p.fs_slug).fanart"
            class="rsp-hero-bg"
            :style="{ animationDelay: `-${idx * 7}s` }"
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
          <div class="rsp-hero-overlay" />
        </div>
        <div class="rsp-icon-wrap">
          <img
            :src="art(p.fs_slug).icon"
            :alt="p.display"
            class="rsp-icon"
            @error="($event.target as HTMLImageElement).style.display='none'"
          />
        </div>
        <div class="rsp-footer">
          <img
            :src="art(p.fs_slug).name"
            :alt="p.display"
            class="rsp-name-logo"
            @error="($event.target as HTMLImageElement).style.display='none'; ($event.target as HTMLImageElement).nextElementSibling?.removeAttribute('style')"
          />
          <span class="rsp-name-text" style="display:none">{{ p.display }}</span>
          <span v-if="p.count != null" class="rsp-count">{{ p.count }} {{ t('emulation.roms_count', 'ROMs') }}</span>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import romSourceActions, { type RomSourcePlatform } from '@/lib/romSourceActions'
import { usePlatformMetaStore } from '@/stores/platformMeta'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const platformMeta = usePlatformMetaStore()

const sourceId = computed(() => String(route.params.sourceId || ''))

const sourceName = ref('')
const providerName = ref('')
const sourceIcon = ref('')
const iconFail = ref(false)
// The feature heads the page (the plugin the user installed); the source name
// stays as the sub-line, so a second source under the same plugin reads the
// same at the top and differs only in the detail line.
const headerTitle = computed(
  () => providerName.value || sourceName.value || t('romsrc.title', 'ROM Downloader'),
)
const notConfigured = ref(false)
const platforms = ref<RomSourcePlatform[]>([])
const loading = ref(true)
const errMsg = ref('')

const cardSizes = [
  { id: 'xs',  label: 'XS' },
  { id: 's',   label: 'S'  },
  { id: 'm',   label: 'M'  },
  { id: 'l',   label: 'L'  },
  { id: 'xl',  label: 'XL' },
  { id: 'xxl', label: 'XXL'},
] as const
type CardSizeId = typeof cardSizes[number]['id']
const cardSizeMap: Record<CardSizeId, { min: number; height: number; icon: number; logo: number }> = {
  xs:  { min: 140, height: 120, icon: 44,  logo: 80  },
  s:   { min: 180, height: 155, icon: 58,  logo: 100 },
  m:   { min: 220, height: 195, icon: 76,  logo: 130 },
  l:   { min: 260, height: 230, icon: 92,  logo: 155 },
  xl:  { min: 300, height: 268, icon: 108, logo: 180 },
  xxl: { min: 360, height: 320, icon: 130, logo: 210 },
}
const cardSize = ref<CardSizeId>((localStorage.getItem('emu-home-card-size') as CardSizeId) || 'm')
watch(cardSize, v => localStorage.setItem('emu-home-card-size', v))

function art(fsSlug: string) {
  return romSourceActions.platformArt(fsSlug)
}

function cardStyle(fsSlug: string): Record<string, string> {
  const color = platformMeta.getColor(fsSlug)
  return color ? { '--platform-color': `#${color}` } : {}
}

function openPlatform(p: RomSourcePlatform) {
  router.push(romSourceActions.route(sourceId.value, p.fs_slug))
}

// Switching source keeps this component mounted, and a source browses live: a
// cold one can take a minute to answer. Without a monotonic guard the slow
// answer for the source the user left lands on top of the one they moved to,
// and the page then shows A's platforms under B's name.
let loadSeq = 0

const refreshing = ref(false)

async function refreshLists() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    await romSourceActions.refreshSource(sourceId.value)
  } catch { /* the reload below is worth doing either way */ }
  refreshing.value = false
  await load()
}

async function load() {
  const seq = ++loadSeq
  loading.value = true
  errMsg.value = ''
  notConfigured.value = false
  platforms.value = []
  try {
    // Source meta first: name + configured state (so an unconfigured source
    // shows the notice instead of a failing platform fetch).
    const sources = await romSourceActions.list()
    if (seq !== loadSeq) return
    const src = sources.find(s => s.id === sourceId.value)
    sourceName.value = src?.name || ''
    providerName.value = src?.plugin_name || ''
    sourceIcon.value = src?.icon || ''
    iconFail.value = false
    if (src && src.requires_auth && src.configured === false) {
      notConfigured.value = true
      loading.value = false
      return
    }
    const list = await romSourceActions.platforms(sourceId.value)
    if (seq !== loadSeq) return
    platforms.value = list
  } catch (e: any) {
    if (seq !== loadSeq) return
    if (e?.response?.status === 409) notConfigured.value = true
    else errMsg.value = e?.response?.data?.detail || String(e)
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

onMounted(() => {
  platformMeta.fetchIfNeeded()
  load()
})
watch(sourceId, () => load())
</script>

<style scoped>
.rsp-home {
  display: flex;
  flex-direction: column;
  gap: var(--space-6, 24px);
  padding: 24px 32px;
  min-height: 100%;
}

/* ── Title bar ──────────────────────────────────────────────────────────── */
.rsp-title-bar {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: var(--space-3, 12px); flex-shrink: 0;
  padding: 14px 20px;
  background: var(--glass-bg);
  backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  -webkit-backdrop-filter: blur(var(--glass-blur-px,22px)) saturate(var(--glass-sat,180%));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  box-shadow: 0 2px 16px rgba(0,0,0,0.2);
}
.rsp-title-left { display: flex; align-items: center; gap: var(--space-3, 12px); }
.lib-back-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  font-size: var(--fs-sm, 12px); font-weight: 500; color: var(--muted);
  background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
  cursor: pointer; font-family: inherit; transition: all var(--transition);
  margin-right: 4px; flex-shrink: 0;
}
.lib-back-btn:hover { color: var(--text); background: rgba(255,255,255,.1); }
.rsp-title-ico { color: #14b8a6; filter: drop-shadow(0 0 8px rgba(20,184,166,.5)); flex-shrink: 0; }
/* The plugin's art is a wide emblem, so it keeps its aspect instead of being
   squeezed into the square a glyph would have used. */
.rsp-title-logo { height: 52px; width: auto; max-width: 110px; object-fit: contain; flex-shrink: 0; border-radius: 6px; }
.title-text { font-size: 20px; font-weight: 700; color: var(--text); margin: 0; }
.title-sub  { font-size: var(--fs-sm, 12px); color: var(--muted); margin: 0; }
.rsp-title-right { display: flex; align-items: center; gap: var(--space-2, 8px); }

/* Card size buttons (same control the Retro grid uses) */
.size-group { display: flex; align-items: center; border: 1px solid var(--glass-border); border-radius: var(--radius-sm); overflow: hidden; }
.size-btn {
  padding: 5px 8px; font-size: var(--fs-xs, 10px); font-weight: 600; font-family: inherit;
  background: transparent; border: none; color: var(--muted);
  cursor: pointer; transition: background var(--transition), color var(--transition);
  line-height: 1;
}
.size-btn + .size-btn { border-left: 1px solid var(--glass-border); }
.size-btn:hover  { background: rgba(255,255,255,.07); color: var(--text); }
.size-btn.active { background: var(--pl-dim); color: var(--pl-light); }

/* ── Notice (configure / error / empty) ─────────────────────────────────── */
.rsp-notice {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--space-3, 12px); padding: 72px 24px; text-align: center;
}
.rsp-notice-icon {
  width: 76px; height: 76px; border-radius: 20px;
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); margin-bottom: 4px;
}
.rsp-notice-title { font-size: var(--fs-xl, 18px); font-weight: 700; color: var(--text); margin: 0; }
.rsp-notice-sub   { font-size: 13px; color: var(--muted); max-width: 420px; margin: 0; }
.rsp-notice-btn {
  margin-top: 6px; padding: 8px 16px; border-radius: var(--radius-sm);
  border: 1px solid var(--pl); background: var(--pl-dim); color: var(--pl-light);
  font-size: 13px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: all var(--transition);
}
.rsp-notice-btn:hover { background: color-mix(in srgb, var(--pl) 25%, transparent); }

/* ── Loading ────────────────────────────────────────────────────────────── */
.rsp-loading { display: flex; align-items: center; justify-content: center; padding: 80px; color: var(--muted); }
.spinner {
  width: 22px; height: 22px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.15); border-top-color: var(--pl-light);
  animation: spin .8s linear infinite; display: inline-block;
}

/* ── Platform grid (mirrors EmulationHome) ──────────────────────────────── */
.rsp-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(var(--card-min, 220px), 1fr));
  gap: var(--space-4, 16px);
}
.rsp-card {
  position: relative;
  height: var(--card-height, 195px);
  border-radius: var(--radius);
  overflow: hidden;
  cursor: pointer;
  background: #0c0817;
  border: 1px solid var(--glass-border);
  transition: border-color var(--transition), transform 0.2s;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
}
.rsp-card:hover {
  border-color: color-mix(in srgb, var(--platform-color, var(--pl)) 70%, transparent);
  box-shadow: 0 0 16px color-mix(in srgb, var(--platform-color, var(--pl)) 25%, transparent);
  transform: translateY(-2px);
}
.rsp-hero { position: absolute; inset: 0; z-index: 0; }
.rsp-hero-bg {
  position: absolute; inset: -10px;
  width: calc(100% + 20px); height: calc(100% + 20px);
  object-fit: cover;
  filter: blur(var(--gd-hero-blur, 14px)) saturate(110%) brightness(.35);
}
.rsp-hero-overlay {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at 50% 30%, color-mix(in srgb, var(--pl) 18%, transparent) 0%, transparent 70%),
              linear-gradient(to bottom, rgba(0,0,0,.1) 0%, rgba(0,0,0,.5) 100%);
}
.rsp-icon-wrap { position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; flex: 1; }
.rsp-icon {
  width: var(--card-icon, 76px); height: var(--card-icon, 76px);
  object-fit: contain; filter: drop-shadow(0 4px 16px rgba(0,0,0,.6));
}
.rsp-footer {
  position: relative; z-index: 1; width: 100%;
  padding: 8px 12px 12px;
  display: flex; flex-direction: column; align-items: center; gap: var(--space-1, 4px);
  background: linear-gradient(to top, rgba(0,0,0,.7) 0%, transparent 100%);
}
.rsp-name-logo {
  max-width: var(--card-logo, 130px); max-height: 28px; object-fit: contain;
  filter: drop-shadow(0 1px 4px rgba(0,0,0,.8)) brightness(1.1);
}
.rsp-name-text {
  font-size: 11px; font-weight: 700; color: rgba(255,255,255,.9);
  text-align: center; letter-spacing: .3px; text-shadow: 0 1px 4px rgba(0,0,0,.8);
}
.rsp-count { font-size: var(--fs-xs, 10px); color: rgba(255,255,255,.5); font-weight: 500; }
/* Refresh: quiet next to the size buttons until it is doing something. */
.rsp-refresh {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; margin-left: 10px;
  font-size: var(--fs-sm, 12px); font-weight: 600; color: var(--muted);
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px); cursor: pointer;
  transition: color var(--transition), border-color var(--transition);
}
.rsp-refresh:hover:not(:disabled) {
  color: var(--text);
  border-color: color-mix(in srgb, var(--pl) 45%, transparent);
}
.rsp-refresh:disabled { cursor: default; opacity: .7; }
.rsp-refresh.busy svg { animation: spin 1s linear infinite; }
</style>
