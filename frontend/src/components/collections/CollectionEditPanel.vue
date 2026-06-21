<!--
  CollectionEditPanel - admin editor for a collection's metadata.

  Mirrors the game metadata editor (LibraryMetadataPanel): a centred glass
  overlay with the artwork previews (cover / hero / logo) on the left and a
  tabbed editor on the right - Cover, Hero, Logo, Description and Details. The
  artwork tabs search SteamGridDB, IGDB, Wikipedia and metadata plugins; the
  Details tab holds the manual fields. The cover can also be uploaded; scraped
  art (cover / hero / logo) is pulled to the server by the PATCH on Save.
-->
<template>
  <div class="cep-overlay" @click.self="$emit('close')">
    <div class="cep-panel" @click.stop>

      <!-- ── Header ──────────────────────────────────────────────────────────── -->
      <div class="cep-header">
        <div class="cep-header-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          <span>{{ t('collections.edit') }}</span>
          <span class="cep-name">- {{ collection.name }}</span>
        </div>
        <button class="cep-close" @click="$emit('close')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- ── Body ────────────────────────────────────────────────────────────── -->
      <div class="cep-body">

        <!-- Left: artwork previews -->
        <div class="cep-left">
          <div class="cep-asset">
            <div class="cep-label">{{ t('meta.tab_cover') }}</div>
            <div class="cep-cover-box" :class="{ 'cep-cover-box--fan': !coverPath }">
              <img v-if="coverPath" :src="coverPath" :alt="name" class="cep-cover-img" />
              <CollectionCover v-else :covers="collection.member_covers" :name="name" color="var(--pl)" />
            </div>
            <label class="cep-upload-btn">
              <input type="file" accept="image/png,image/jpeg,image/webp" class="cep-file" @change="onCoverFile" />
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              {{ t('collections.cover_upload') }}
            </label>
            <button v-if="coverPath" class="cep-ghost-btn" :disabled="coverBusy" @click="revertArt('cover')">{{ t('collections.cover_revert') }}</button>
          </div>

          <div v-if="heroPath" class="cep-asset">
            <div class="cep-label">{{ t('meta.tab_hero') }}</div>
            <div class="cep-hero-box"><img :src="heroPath" :alt="name" /></div>
            <button class="cep-ghost-btn" :disabled="coverBusy" @click="revertArt('hero')">{{ t('collections.cover_revert') }}</button>
          </div>

          <div v-if="logoPath" class="cep-asset">
            <div class="cep-label">{{ t('meta.tab_logo') }}</div>
            <div class="cep-logo-box"><img :src="logoPath" :alt="name" /></div>
            <button class="cep-ghost-btn" :disabled="coverBusy" @click="revertArt('logo')">{{ t('collections.cover_revert') }}</button>
          </div>

          <p class="cep-hint">{{ t('collections.cover_hint') }}</p>
          <div v-if="coverMsg" class="cep-cover-msg">{{ coverMsg }}</div>
        </div>

        <!-- Right: tabs -->
        <div class="cep-right">
          <div class="cep-tabs">
            <button class="cep-tab" :class="{ active: tab === 'cover' }" @click="switchTab('cover')">{{ t('meta.tab_cover') }}</button>
            <button class="cep-tab" :class="{ active: tab === 'hero' }" @click="switchTab('hero')">{{ t('meta.tab_hero') }}</button>
            <button class="cep-tab" :class="{ active: tab === 'logo' }" @click="switchTab('logo')">{{ t('meta.tab_logo') }}</button>
            <button class="cep-tab" :class="{ active: tab === 'description' }" @click="switchTab('description')">{{ t('meta.tab_description') }}</button>
            <button class="cep-tab" :class="{ active: tab === 'details' }" @click="switchTab('details')">{{ t('meta.tab_details') }}</button>
          </div>

          <!-- Artwork tab (cover / hero / logo) -->
          <div v-show="activeArtKind" class="cep-form">
            <div class="cep-search-row">
              <input v-model="searchQuery" class="cep-input" :placeholder="t('collections.scrape_placeholder')" @keydown.enter.prevent="searchActiveArt" />
              <button class="cep-search-btn" :disabled="!!activeArt?.searching" @click="searchActiveArt">
                <div v-if="activeArt?.searching" class="cep-spinner"></div>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                {{ t('collections.scrape_btn') }}
              </button>
            </div>
            <div v-if="activeArt?.searching" class="cep-scrape-status"><div class="cep-spinner"></div> {{ t('collections.scrape_searching') }}</div>
            <div v-else-if="activeArt?.done && !activeArt?.results.length" class="cep-hint">{{ t('collections.scrape_no_results') }}</div>
            <div v-else-if="activeArt?.results.length" class="cep-cover-grid" :class="{ 'cep-cover-grid--wide': tab !== 'cover' }">
              <div v-for="(cv, i) in (activeArt?.results || [])" :key="cv.source + ':' + i" class="cep-cover-option" :class="{ selected: activeSelectedUrl === cv.url }" :title="cv.label" @click="selectActiveArt(cv)">
                <div class="cep-cover-option-img" :class="artImgClass">
                  <img :src="cv.thumb || cv.url" loading="lazy" />
                  <span v-if="activeSelectedUrl === cv.url" class="cep-cover-check">✓</span>
                </div>
                <div class="cep-cover-src">{{ cv.source }}</div>
              </div>
            </div>
          </div>

          <!-- Description tab -->
          <div v-show="tab === 'description'" class="cep-form">
            <div class="cep-search-row">
              <input v-model="searchQuery" class="cep-input" :placeholder="t('collections.scrape_placeholder')" @keydown.enter.prevent="runDescSearch" />
              <button class="cep-search-btn" :disabled="descSearching" @click="runDescSearch">
                <div v-if="descSearching" class="cep-spinner"></div>
                <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                {{ t('collections.scrape_btn') }}
              </button>
            </div>
            <p class="cep-hint">{{ t('collections.scrape_hint') }}</p>
            <div v-if="searchError" class="cep-err" style="font-size:12px">{{ searchError }}</div>
            <div v-if="descSearching" class="cep-scrape-status"><div class="cep-spinner"></div> {{ t('collections.scrape_searching') }}</div>
            <div v-else-if="descDone && !descResults.length" class="cep-hint">{{ t('collections.scrape_no_results') }}</div>
            <div v-else-if="descResults.length" class="cep-results">
              <div v-for="r in descResults" :key="r._key" class="cep-result">
                <img v-if="r.cover_url" :src="r.cover_url" class="cep-result-thumb" loading="lazy" />
                <div v-else class="cep-result-thumb cep-result-thumb--ph">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" opacity=".5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>
                </div>
                <div class="cep-result-body">
                  <div class="cep-result-name">{{ r.name }}<span class="cep-result-src">{{ r.provider_id }}</span></div>
                  <div v-if="r.snippet" class="cep-result-snippet">{{ r.snippet }}</div>
                </div>
                <button class="cep-result-apply" :disabled="applyingDescId === r._key" @click="applyDescription(r)">
                  <div v-if="applyingDescId === r._key" class="cep-spinner"></div>
                  <span v-else>{{ t('collections.scrape_use_desc') }}</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Details tab -->
          <div v-show="tab === 'details'" class="cep-form">
            <div class="cep-section">{{ t('collections.basics') }}</div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('collections.field_name') }}</label>
              <input v-model="name" class="cep-input" maxlength="200" />
            </div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('collections.field_description') }} <span class="cep-hint">({{ t('collections.desc_long_hint') }})</span></label>
              <textarea v-model="description" rows="5" class="cep-textarea"></textarea>
            </div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('collections.field_description_short') }} <span class="cep-hint">({{ t('collections.desc_short_hint') }})</span></label>
              <textarea v-model="descriptionShort" rows="3" class="cep-textarea" maxlength="500"></textarea>
            </div>

            <div class="cep-section" style="margin-top:6px">{{ t('collections.details') }}</div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('collections.year_range') }}</label>
              <label class="cep-check"><input type="checkbox" v-model="yearsAuto" /><span>{{ t('collections.auto_from_games') }}</span></label>
              <div v-if="!yearsAuto" class="cep-field-row">
                <input v-model.number="yearFrom" type="number" class="cep-input" :placeholder="t('collections.year_from')" />
                <input v-model.number="yearTo" type="number" class="cep-input" :placeholder="t('collections.year_to')" />
              </div>
            </div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('collections.field_rating') }}</label>
              <label class="cep-check"><input type="checkbox" v-model="ratingAuto" /><span>{{ t('collections.rating_auto') }}</span></label>
              <input v-if="!ratingAuto" v-model.number="ratingManual" type="number" min="0" max="5" step="0.1" class="cep-input" />
              <span v-else class="cep-hint">{{ avgHint }}</span>
            </div>
            <div class="cep-field">
              <label class="cep-field-label">{{ t('detail.time_to_beat') }}</label>
              <label class="cep-check"><input type="checkbox" v-model="hltbAuto" /><span>{{ t('collections.auto_from_games') }}</span></label>
              <div v-if="!hltbAuto" class="cep-field-row">
                <input v-model.number="hltbMainH" type="number" min="0" step="0.5" class="cep-input" :placeholder="t('collections.hltb_main_h')" />
                <input v-model.number="hltbCompleteH" type="number" min="0" step="0.5" class="cep-input" :placeholder="t('collections.hltb_complete_h')" />
              </div>
              <span v-else class="cep-hint">{{ hltbHint }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Footer ──────────────────────────────────────────────────────────── -->
      <div class="cep-footer">
        <button class="cep-btn-delete" :disabled="busy" @click="onDelete">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          {{ t('collections.delete') }}
        </button>
        <div class="cep-footer-right">
          <span v-if="saveError" class="cep-err">{{ saveError }}</span>
          <span v-else-if="saveOk" class="cep-ok">✓ {{ t('meta.saved') }}</span>
          <button class="cep-btn-cancel" @click="$emit('close')">{{ t('common.cancel') }}</button>
          <button class="cep-btn-save" :disabled="busy || !canSave" @click="save">
            <div v-if="busy" class="cep-spinner"></div>
            <span v-else>{{ t('common.save') }}</span>
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import CollectionCover from '@/components/collections/CollectionCover.vue'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'

const props = defineProps<{ collection: any }>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'updated'): void
  (e: 'deleted', slug: string): void
}>()

const { t } = useI18n()
const { gdConfirm } = useDialog()

const c = props.collection
const tab = ref<'cover' | 'hero' | 'logo' | 'description' | 'details'>('cover')

const name        = ref<string>(c.name || '')
const description = ref<string>(c.description || '')
const descriptionShort = ref<string>(c.description_short || '')
// Year range: auto unless an override is explicitly set (the *_auto flags are
// only false when overridden, so undefined/true default to auto = checked).
const yearsAuto = ref<boolean>(c.start_year_auto !== false && c.end_year_auto !== false)
const yearFrom  = ref<number | null>(c.start_year ?? null)
const yearTo    = ref<number | null>(c.end_year ?? null)
// Rating: auto = average of member ratings (stored null); override = manual 0-5.
const ratingAuto   = ref<boolean>(c.rating_auto !== false)
const ratingManual = ref<number | null>(c.rating_auto ? null : (c.rating ?? null))
// Artwork: current values (preview) + the scraped URL to persist on Save.
const coverPath = ref<string | null>(c.cover_path ?? null)
const heroPath  = ref<string | null>(c.hero_path ?? null)
const logoPath  = ref<string | null>(c.logo_path ?? null)
const scrapedCover = ref<string | null>(null)
const scrapedHero  = ref<string | null>(null)
const scrapedLogo  = ref<string | null>(null)
const selectedCover = ref<string | null>(null)
const selectedHero  = ref<string | null>(null)
const selectedLogo  = ref<string | null>(null)
// Time to Beat: auto = average of member playtimes (stored null); override = manual hours.
const hltbAuto      = ref<boolean>(c.hltb_auto !== false)
const hltbMainH     = ref<number | null>(c.hltb_auto ? null : (c.hltb_main_s ? c.hltb_main_s / 3600 : null))
const hltbCompleteH = ref<number | null>(c.hltb_auto ? null : (c.hltb_complete_s ? c.hltb_complete_s / 3600 : null))

// The computed member-average rating, shown as a hint while in auto mode.
const avg = computed<number | null>(() => (c.rating != null ? Number(c.rating) : null))
const avgHint = computed(() =>
  t('collections.rating_avg', { value: avg.value != null ? avg.value.toFixed(1) : '-' }),
)
function _fmtH(s: number | null | undefined): string {
  if (!s) return '-'
  const h = Math.floor(s / 3600); const m = Math.round((s % 3600) / 60)
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`
}
const hltbHint = computed(() => t('collections.hltb_avg', { main: _fmtH(c.hltb_main_s), complete: _fmtH(c.hltb_complete_s) }))

const busy      = ref(false)
const coverBusy = ref(false)
const saveError = ref('')
const saveOk    = ref(false)
const coverMsg  = ref('')

// ── Find metadata: artwork (cover / hero / logo) + description ──────────────
// Search by the FULL collection name - "collection" / "series" are an important
// part of the query (e.g. "BioShock Collection" finds "BioShock: The Collection").
const searchQuery = ref<string>(c.name || '')

type ArtState = { results: any[]; searching: boolean; done: boolean }
const art = reactive<Record<'covers' | 'heroes' | 'logos', ArtState>>({
  covers: { results: [], searching: false, done: false },
  heroes: { results: [], searching: false, done: false },
  logos:  { results: [], searching: false, done: false },
})
const activeArtKind = computed<'covers' | 'heroes' | 'logos' | null>(() =>
  tab.value === 'cover' ? 'covers' : tab.value === 'hero' ? 'heroes' : tab.value === 'logo' ? 'logos' : null)
const activeArt = computed<ArtState | null>(() => activeArtKind.value ? art[activeArtKind.value] : null)
const artImgClass = computed(() => tab.value === 'hero' ? 'cep-art-hero' : tab.value === 'logo' ? 'cep-art-logo' : '')
const activeSelectedUrl = computed(() => tab.value === 'cover' ? selectedCover.value : tab.value === 'hero' ? selectedHero.value : selectedLogo.value)

// Description (text)
const searchError    = ref('')
const descSearching  = ref(false)
const descDone       = ref(false)
const descResults    = ref<any[]>([])
const applyingDescId = ref<string>('')

function _stripHtml(s: string): string {
  return (s || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
}

const canSave = computed(() => name.value.trim().length > 0)

function switchTab(name: 'cover' | 'hero' | 'logo' | 'description' | 'details') {
  tab.value = name
  const kind = activeArtKind.value
  if (kind && !art[kind].done && !art[kind].searching) searchActiveArt()
  if (name === 'description' && !descDone.value && !descSearching.value) runDescSearch()
}

async function searchActiveArt() {
  const kind = activeArtKind.value
  if (!kind) return
  const q = searchQuery.value.trim()
  if (!q) return
  const a = art[kind]
  a.searching = true; a.done = false; a.results = []
  try {
    const { data } = await client.get(`/plugins/metadata/collections/${kind}`, { params: { q } })
    a.results = Array.isArray(data) ? data : []
  } catch { /* artwork is best-effort */ } finally {
    a.searching = false; a.done = true
  }
}

function selectActiveArt(item: any) {
  if (tab.value === 'cover') { selectedCover.value = item.url; scrapedCover.value = item.url; coverPath.value = item.url }
  else if (tab.value === 'hero') { selectedHero.value = item.url; scrapedHero.value = item.url; heroPath.value = item.url }
  else if (tab.value === 'logo') { selectedLogo.value = item.url; scrapedLogo.value = item.url; logoPath.value = item.url }
}

async function runDescSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  searchError.value = ''
  descSearching.value = true; descDone.value = false; descResults.value = []
  // Same method as the game editor: rich descriptions from IGDB / RAWG / Steam
  // (by the full collection name), with Wikipedia last as a fallback.
  const base = `/collections/${c.slug}/meta-sources`
  const igdbOut: any[] = [], rawgOut: any[] = [], steamOut: any[] = [], wikiOut: any[] = []
  await Promise.all([
    client.get(base, { params: { source: 'igdb', q } }).then(r => {
      for (const x of (r.data?.candidates || []).slice(0, 3)) {
        if (x.description) igdbOut.push({ provider_id: 'igdb', name: x.name || q, snippet: _stripHtml(x.description).slice(0, 320), description: x.description, description_short: x.description_short || '', cover_url: x.cover_url })
      }
    }).catch(() => {}),
    client.get(base, { params: { source: 'rawg', q } }).then(async r => {
      const top = (r.data?.candidates || [])[0]
      if (top) {
        const slug = top.slug || String(top.id)
        const d = await client.get(base, { params: { source: 'rawg-detail', q: slug } }).then(rr => rr.data).catch(() => null)
        if (d?.description) rawgOut.push({ provider_id: 'rawg', name: top.name || q, snippet: _stripHtml(d.description).slice(0, 320), description: d.description, description_short: d.description_short || '', cover_url: d.cover_url || top.background_image })
      }
    }).catch(() => {}),
    client.get(base, { params: { source: 'steam', q } }).then(r => {
      const d = r.data
      if (d?.found && d.description) steamOut.push({ provider_id: 'steam', name: d.name || q, snippet: _stripHtml(d.description).slice(0, 320), description: d.description, description_short: d.description_short || '' })
    }).catch(() => {}),
    client.get('/plugins/metadata/collections/search', { params: { q } }).then(r => {
      for (const x of (Array.isArray(r.data) ? r.data : []).filter((y: any) => y.provider_id === 'wikipedia')) {
        wikiOut.push({ provider_id: 'wikipedia', name: x.name, snippet: x.snippet, cover_url: x.cover_url, _fetch: { provider_id: x.provider_id, id: x.provider_collection_id } })
      }
    }).catch(() => {}),
  ])
  const merged = [...igdbOut, ...rawgOut, ...steamOut, ...wikiOut]
  merged.forEach((m, i) => { m._key = m.provider_id + ':' + i })
  descResults.value = merged
  descSearching.value = false; descDone.value = true
}

async function applyDescription(card: any) {
  applyingDescId.value = card._key; searchError.value = ''
  try {
    // IGDB / RAWG / Steam cards carry the full prose; a Wikipedia card has only a
    // snippet, so its full description is fetched on apply. Year range and rating
    // stay auto (member-derived); artwork is picked in the Cover/Hero/Logo tabs.
    let desc = card.description, short = card.description_short
    if (desc == null && card._fetch) {
      const { data } = await client.get('/plugins/metadata/collections/fetch', {
        params: { provider_id: card._fetch.provider_id, id: card._fetch.id },
      })
      desc = data?.description; short = data?.description_short
    }
    if (desc) description.value = desc
    if (short) descriptionShort.value = short
  } catch (err: any) {
    searchError.value = err?.response?.data?.detail || 'Fetch failed'
  } finally {
    applyingDescId.value = ''
  }
}

async function onCoverFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  coverBusy.value = true; coverMsg.value = ''
  try {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await client.post(`/collections/${c.slug}/cover`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    coverPath.value = data.cover_path
    scrapedCover.value = null; selectedCover.value = null
    coverMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverMsg.value = err?.response?.data?.detail || 'Upload failed'
  } finally {
    coverBusy.value = false
    input.value = ''
  }
}

async function revertArt(kind: 'cover' | 'hero' | 'logo') {
  const field = kind === 'cover' ? 'cover_path' : kind === 'hero' ? 'hero_path' : 'logo_path'
  coverBusy.value = true; coverMsg.value = ''
  try {
    await client.patch(`/collections/${c.slug}`, { [field]: null })
    if (kind === 'cover') { coverPath.value = null; scrapedCover.value = null; selectedCover.value = null }
    else if (kind === 'hero') { heroPath.value = null; scrapedHero.value = null; selectedHero.value = null }
    else { logoPath.value = null; scrapedLogo.value = null; selectedLogo.value = null }
    coverMsg.value = t('meta.saved')
    emit('updated')
  } catch (err: any) {
    coverMsg.value = err?.response?.data?.detail || 'Failed'
  } finally {
    coverBusy.value = false
  }
}

async function save() {
  if (!canSave.value) return
  busy.value = true; saveError.value = ''; saveOk.value = false
  try {
    const payload: Record<string, unknown> = {
      name: name.value.trim(),
      description: description.value ? description.value : null,
      description_short: descriptionShort.value ? descriptionShort.value : null,
      start_year: yearsAuto.value ? null : (yearFrom.value != null ? Number(yearFrom.value) : null),
      end_year:   yearsAuto.value ? null : (yearTo.value != null ? Number(yearTo.value) : null),
      rating:     ratingAuto.value ? null : (ratingManual.value != null ? Number(ratingManual.value) : null),
      hltb_main_s:     hltbAuto.value ? null : (hltbMainH.value != null ? Math.round(Number(hltbMainH.value) * 3600) : null),
      hltb_complete_s: hltbAuto.value ? null : (hltbCompleteH.value != null ? Math.round(Number(hltbCompleteH.value) * 3600) : null),
    }
    // Scraped artwork (external URLs) is pulled to the server by the PATCH.
    if (scrapedCover.value) payload.cover_path = scrapedCover.value
    if (scrapedHero.value) payload.hero_path = scrapedHero.value
    if (scrapedLogo.value) payload.logo_path = scrapedLogo.value
    await client.patch(`/collections/${c.slug}`, payload)
    saveOk.value = true
    emit('updated')
    setTimeout(() => emit('close'), 700)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Save failed'
  } finally {
    busy.value = false
  }
}

async function onDelete() {
  const ok = await gdConfirm(
    t('collections.delete_confirm', { name: c.name }),
    { title: t('collections.delete'), danger: true, confirmText: t('common.delete'), cancelText: t('common.cancel') },
  )
  if (!ok) return
  busy.value = true; saveError.value = ''
  try {
    await client.delete(`/collections/${c.slug}`)
    emit('deleted', c.slug)
  } catch (err: any) {
    saveError.value = err?.response?.data?.detail || 'Delete failed'
    busy.value = false
  }
}

// Auto-search the initial (cover) tab, like the game editor.
onMounted(() => { if (activeArtKind.value) searchActiveArt() })
</script>

<style scoped>
.cep-overlay {
  position: fixed; inset: 0; z-index: 8000;
  background: rgba(0,0,0,.72); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  animation: cep-fade-in .18s ease;
}
@keyframes cep-fade-in { from { opacity: 0; } to { opacity: 1; } }

.cep-panel {
  width: 90vw; max-width: 820px; max-height: 90vh;
  background: var(--glass-bg, rgba(15,10,30,.85));
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  border-radius: 16px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--pl) 15%, transparent),
              0 24px 60px rgba(0,0,0,.6),
              0 0 40px color-mix(in srgb, var(--pl) 8%, transparent);
  display: flex; flex-direction: column; overflow: hidden;
  animation: cep-slide-up .2s cubic-bezier(.23,1,.32,1);
}
@keyframes cep-slide-up { from { transform: translateY(24px); opacity: 0; } to { transform: none; opacity: 1; } }

.cep-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--glass-border); flex-shrink: 0;
}
.cep-header-left {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text);
}
.cep-name { color: var(--muted); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 360px; }
.cep-close {
  width: 32px; height: 32px; border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all .15s; flex-shrink: 0;
}
.cep-close:hover { background: rgba(255,255,255,.12); color: var(--text); }

.cep-body { display: flex; flex: 1; overflow: hidden; min-height: 0; }

/* Left - artwork previews */
.cep-left {
  width: 210px; flex-shrink: 0; padding: 18px;
  border-right: 1px solid var(--glass-border);
  overflow-y: auto; background: rgba(255,255,255,.02);
  display: flex; flex-direction: column; gap: 14px;
}
.cep-asset { display: flex; flex-direction: column; gap: 8px; }
.cep-label {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px;
}
/* The box wraps a custom cover at its natural aspect ratio (landscape /
   portrait / square); the auto fan falls back to a square. */
.cep-cover-box {
  position: relative; width: 100%;
  border-radius: var(--radius-sm, 8px); overflow: hidden;
  background: var(--bg2, rgba(0,0,0,.3)); border: 1px solid var(--glass-border);
}
.cep-cover-box--fan { aspect-ratio: 1 / 1; }
.cep-cover-img { display: block; width: 100%; height: auto; }
.cep-hero-box {
  position: relative; width: 100%; aspect-ratio: 16 / 9; overflow: hidden;
  border-radius: var(--radius-sm, 8px); background: var(--bg2, rgba(0,0,0,.3)); border: 1px solid var(--glass-border);
}
.cep-hero-box img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cep-logo-box {
  position: relative; width: 100%; aspect-ratio: 16 / 9; overflow: hidden;
  border-radius: var(--radius-sm, 8px); background: rgba(0,0,0,.4); border: 1px solid var(--glass-border);
}
.cep-logo-box img { width: 100%; height: 100%; object-fit: contain; padding: 8px; display: block; }
.cep-upload-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 8px 12px; border-radius: var(--radius-sm); cursor: pointer;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--text); font-size: 12px; font-weight: 600; transition: all .15s;
}
.cep-upload-btn:hover { background: rgba(255,255,255,.12); border-color: rgba(255,255,255,.25); }
.cep-file { display: none; }
.cep-ghost-btn {
  padding: 6px 12px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 12px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-ghost-btn:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.cep-ghost-btn:disabled { opacity: .5; cursor: not-allowed; }
.cep-hint { margin: 0; font-size: 11px; color: var(--muted); line-height: 1.5; }
.cep-cover-msg { font-size: 12px; color: #4ade80; }

/* Right - tabbed editor */
.cep-right { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.cep-tabs {
  display: flex; gap: 2px; padding: 10px 18px 0; flex-wrap: wrap;
  border-bottom: 1px solid var(--glass-border); flex-shrink: 0;
}
.cep-tab {
  padding: 8px 12px; background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--muted); font-size: 12px; font-weight: 700; font-family: inherit;
  text-transform: uppercase; letter-spacing: .6px; cursor: pointer; transition: all .15s;
}
.cep-tab:hover:not(.active) { color: var(--text); }
.cep-tab.active { color: var(--pl-light); border-bottom-color: var(--pl); }

.cep-form { flex: 1; padding: 18px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.cep-section {
  font-size: var(--fs-xs, 10px); font-weight: 700; color: var(--pl-light);
  text-transform: uppercase; letter-spacing: 1.2px;
  padding-bottom: 4px; border-bottom: 1px solid var(--glass-border);
}
.cep-field { display: flex; flex-direction: column; gap: 6px; }
.cep-field-label { font-size: 11px; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .8px; }
.cep-field-row { display: flex; gap: var(--space-2, 8px); }
.cep-input {
  flex: 1; background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
  color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; transition: border-color .15s; width: 100%;
}
.cep-input:focus { border-color: var(--pl); }
.cep-textarea {
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); color: var(--text); font-size: 13px; font-family: inherit;
  padding: 9px 12px; outline: none; resize: vertical; transition: border-color .15s; line-height: 1.6;
}
.cep-textarea:focus { border-color: var(--pl); }
.cep-check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); cursor: pointer; }
.cep-check input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; accent-color: var(--pl); }

/* Footer */
.cep-footer {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-top: 1px solid var(--glass-border);
  flex-shrink: 0; background: rgba(255,255,255,.02);
}
.cep-footer-right { display: flex; align-items: center; gap: 10px; }
.cep-ok  { color: #4ade80; font-size: 13px; }
.cep-err { color: #f87171; font-size: 13px; }
.cep-btn-delete {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 16px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, #ef4444 16%, transparent); border: 1px solid color-mix(in srgb, #ef4444 40%, transparent);
  color: #fca5a5; font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-btn-delete:hover:not(:disabled) { background: color-mix(in srgb, #ef4444 28%, transparent); border-color: #ef4444; color: #fff; }
.cep-btn-delete:disabled { opacity: .5; cursor: not-allowed; }
.cep-btn-cancel {
  padding: 9px 20px; border-radius: var(--radius-sm);
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--muted); font-size: 13px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-btn-cancel:hover { background: rgba(255,255,255,.12); color: var(--text); }
.cep-btn-save {
  display: inline-flex; align-items: center; gap: var(--space-2, 8px);
  padding: 9px 22px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 20%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 50%, transparent);
  color: var(--pl-light); font-size: 13px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s; box-shadow: 0 2px 12px var(--pglow2, transparent);
}
.cep-btn-save:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); border-color: var(--pl); color: #fff; }
.cep-btn-save:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.cep-spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.25); border-top-color: var(--pl-light, #fff);
  animation: cep-spin .7s linear infinite;
}
@keyframes cep-spin { to { transform: rotate(360deg); } }

/* Metadata search - shared search row */
.cep-search-row { display: flex; gap: var(--space-2, 8px); }
.cep-search-btn {
  display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
  padding: 9px 14px; border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--pl) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 45%, transparent);
  color: var(--pl-light); font-size: 12px; font-weight: 700; font-family: inherit;
  cursor: pointer; transition: all .15s;
}
.cep-search-btn:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 28%, transparent); border-color: var(--pl); color: #fff; }
.cep-search-btn:disabled { opacity: .55; cursor: not-allowed; }
.cep-scrape-status { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }

/* Description list */
.cep-results { display: flex; flex-direction: column; gap: 8px; max-height: 320px; overflow-y: auto; }
.cep-result {
  display: flex; align-items: center; gap: 10px; padding: 8px;
  background: rgba(255,255,255,.04); border: 1px solid var(--glass-border); border-radius: var(--radius-sm);
}
.cep-result-thumb { width: 38px; height: 52px; flex-shrink: 0; object-fit: cover; border-radius: 4px; background: rgba(0,0,0,.3); }
.cep-result-thumb--ph { display: flex; align-items: center; justify-content: center; color: var(--muted); }
.cep-result-body { flex: 1; min-width: 0; }
.cep-result-name { font-size: 13px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; }
.cep-result-src {
  font-size: 9px; text-transform: uppercase; letter-spacing: .5px; font-weight: 700;
  color: var(--pl-light); background: color-mix(in srgb, var(--pl) 15%, transparent);
  padding: 1px 6px; border-radius: 999px; flex-shrink: 0;
}
.cep-result-snippet {
  font-size: 11px; color: var(--muted); line-height: 1.4; margin-top: 2px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.cep-result-apply {
  flex-shrink: 0; padding: 7px 12px; border-radius: var(--radius-sm); min-width: 90px;
  background: rgba(255,255,255,.06); border: 1px solid var(--glass-border);
  color: var(--text); font-size: 12px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all .15s; display: inline-flex; align-items: center; justify-content: center;
}
.cep-result-apply:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 20%, transparent); border-color: var(--pl); color: #fff; }
.cep-result-apply:disabled { opacity: .6; cursor: wait; }

/* Artwork grid (mirrors the game editor: flex-column item, aspect-ratio on an
   INNER box so rows size correctly and tiles never overlap). */
.cep-cover-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 10px; max-height: 360px; overflow-y: auto; padding: 2px;
}
.cep-cover-grid--wide { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
.cep-cover-option { cursor: pointer; display: flex; flex-direction: column; gap: 4px; }
.cep-cover-option-img {
  position: relative; aspect-ratio: 3 / 4;
  border-radius: var(--radius-sm, 8px); overflow: hidden;
  border: 2px solid transparent; background: rgba(0,0,0,.3);
  transition: border-color .15s, box-shadow .15s, transform .15s;
}
.cep-cover-option-img.cep-art-hero { aspect-ratio: 16 / 9; }
.cep-cover-option-img.cep-art-logo { aspect-ratio: 16 / 9; background: rgba(0,0,0,.45); }
.cep-cover-option:hover .cep-cover-option-img { border-color: rgba(255,255,255,.3); box-shadow: 0 4px 20px rgba(0,0,0,.5); transform: translateY(-2px); }
.cep-cover-option.selected .cep-cover-option-img { border-color: var(--pl); box-shadow: 0 0 18px var(--pglow2, transparent); }
.cep-cover-option-img img { width: 100%; height: 100%; object-fit: cover; display: block; }
.cep-cover-option-img.cep-art-logo img { object-fit: contain; padding: 6px; }
.cep-cover-check {
  position: absolute; top: 4px; right: 4px; width: 18px; height: 18px;
  border-radius: 50%; background: var(--pl); color: #fff; font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.cep-cover-src { font-size: 9px; text-transform: uppercase; letter-spacing: .4px; font-weight: 700; color: var(--muted); text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

@media (max-width: 640px) {
  .cep-body { flex-direction: column; overflow-y: auto; }
  .cep-left { width: auto; border-right: none; border-bottom: 1px solid var(--glass-border); }
  .cep-cover-box { width: 120px; }
}
</style>
