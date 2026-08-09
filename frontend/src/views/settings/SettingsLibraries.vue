<template>
  <div class="lib-settings">
    <!-- ── Admin: library management (create / enable / reorder / access) ── -->
    <template v-if="isAdmin">
    <div class="ls-head">
      <div class="ls-title">{{ t('libraries.title') }}</div>
      <div class="ls-desc">{{ t('libraries.desc') }}</div>
      <div class="ls-warn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        <span>{{ t('libraries.desc_warn') }}</span>
      </div>
    </div>

    <div v-if="loading" class="ls-loading">{{ t('common.loading') }}</div>

    <div v-else class="ls-list">
      <div v-for="(lib, i) in items" :key="lib.slug" class="ls-item">
        <div
          class="ls-row"
          :class="{ 'ls-row--off': !lib.enabled, 'ls-row--editing': editingSlug === lib.slug }"
          @mouseenter="setHint(lib.name, t(lib.is_builtin ? 'libraries.hint_builtin' : 'libraries.hint_collection'))"
          @mouseleave="clearHint()"
        >
          <div class="ls-reorder">
            <button class="ls-arrow" :disabled="i === 0" @click="move(i, -1)" :aria-label="t('libraries.move_up')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <button class="ls-arrow" :disabled="i === items.length - 1" @click="move(i, 1)" :aria-label="t('libraries.move_down')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>

          <span class="ls-swatch" :style="{ background: lib.color || 'var(--pl)' }" />
          <LibraryIcon :icon="lib.icon" :color="lib.color" :size="26" :alt="lib.name" class="ls-icon" />

          <div class="ls-info">
            <span class="ls-name">{{ lib.name }}</span>
            <span class="ls-kind">
              {{ t('libraries.kind_' + lib.kind, lib.kind) }}
              <span v-if="lib.is_builtin"> &middot; {{ t('libraries.builtin') }}</span>
              <span v-if="lib.storage_folder"> &middot; /{{ lib.storage_folder }}</span>
            </span>
          </div>

          <button class="ls-edit" :class="{ on: editingSlug === lib.slug }" :title="t('libraries.edit')" @click="editingSlug === lib.slug ? cancelEdit() : startEdit(lib)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>
          </button>

          <button
            v-if="!lib.is_builtin && !lib.catalog_id"
            class="ls-del"
            :title="t('libraries.delete')"
            @click="removeLib(lib)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          </button>

          <div class="ls-pill" :class="{ on: lib.enabled }" @click="toggle(lib)" role="switch" :aria-checked="lib.enabled">
            <div class="ls-pill-knob" />
          </div>
        </div>

        <!-- Inline editor: colour + icon (built-in picker or upload); name only for collections -->
        <div v-if="editingSlug === lib.slug" class="ls-editor">
          <div class="ls-ed-row">
            <input
              v-if="!lib.is_builtin"
              v-model="editForm.name"
              class="ls-input"
              :placeholder="t('libraries.new_name')"
              maxlength="60"
            />
            <input v-model="editForm.color" type="color" class="ls-color" @mouseenter="setHint(t('libraries.new_color'), t('hint.lib_color'))" @mouseleave="clearHint()" />
            <label class="ls-upload-btn" @mouseenter="setHint(t('libraries.icon_upload'), t('libraries.icon_upload_hint'))" @mouseleave="clearHint()">
              <input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onEditFile($event)" />
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              <span>{{ editFileName || t('libraries.icon_upload') }}</span>
            </label>
          </div>
          <div class="ls-ed-label">{{ t('libraries.icon') }}</div>
          <LibraryIconPicker v-model="editForm.icon" :color="editForm.color" @hover="onIconHover" />

          <!-- A store is a plugin's to create and manage, never a hand-made
               shelf, so there is no store toggle here. -->
          <template v-if="defaultFeedEligible(lib)">
            <div class="ls-ed-label">{{ t('libraries.behaviour') }}</div>
            <label
              v-if="defaultFeedEligible(lib)"
              class="ls-folder"
              @mouseenter="setHint(t('libraries.adds_to_default'), t('libraries.adds_to_default_hint'))"
              @mouseleave="clearHint()"
            >
              <input type="checkbox" v-model="editForm.adds_to_default_library" />
              <span>{{ t('libraries.adds_to_default') }}</span>
            </label>
          </template>

          <template v-if="accessEligible(lib)">
            <div class="ls-ed-label">{{ t('libraries.access') }}</div>
            <div class="ls-access-seg">
              <button type="button" :class="{ active: editAccess.visibility === 'public' }" @click="editAccess.visibility = 'public'">{{ t('libraries.access_everyone') }}</button>
              <button type="button" :class="{ active: editAccess.visibility === 'restricted' }" @click="editAccess.visibility = 'restricted'">{{ t('libraries.access_restricted') }}</button>
            </div>
            <div v-if="editAccess.visibility === 'restricted'" class="ls-access-users">
              <div class="ls-access-hint">{{ t('libraries.access_hint') }}</div>
              <label v-for="u in users" :key="u.id" class="ls-access-user">
                <input
                  type="checkbox"
                  :checked="u.role === 'admin' || editAccess.userIds.includes(u.id)"
                  :disabled="u.role === 'admin'"
                  @change="toggleAccessUser(u.id)"
                />
                <span class="ls-access-name">{{ u.username }}</span>
                <span class="ls-access-role">{{ u.role }}</span>
              </label>
              <span v-if="!users.length" class="ls-access-hint">{{ t('libraries.access_no_users') }}</span>
            </div>
          </template>

          <div v-if="editError" class="ls-error">{{ editError }}</div>
          <div class="ls-ed-actions">
            <button class="ls-ed-cancel" @click="cancelEdit">{{ t('common.cancel') }}</button>
            <button class="ls-ed-save" :disabled="editSaving" @click="saveEdit(lib)">{{ editSaving ? t('common.loading') : t('common.save') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Create a new collection -->
    <div
      v-if="!loading"
      class="ls-create"
      @mouseenter="setHint(t('libraries.new'), t('libraries.hint_new'))"
      @mouseleave="clearHint()"
    >
      <div class="ls-create-title">{{ t('libraries.new') }}</div>
      <div class="ls-create-row">
        <input
          v-model="newName"
          class="ls-input"
          :placeholder="t('libraries.new_name')"
          maxlength="60"
          @keyup.enter="create"
        />
        <input v-model="newColor" type="color" class="ls-color" @mouseenter="setHint(t('libraries.new_color'), t('hint.lib_color'))" @mouseleave="clearHint()" />
        <button class="ls-create-btn" :disabled="!newName.trim() || creating" @click="create">
          {{ creating ? t('common.loading') : t('libraries.create') }}
        </button>
      </div>

      <div class="ls-ed-label">{{ t('libraries.icon') }}</div>
      <LibraryIconPicker v-model="newIcon" :color="newColor" @hover="onIconHover" />

      <!-- A collections container holds no game files, so it has no scan folder. -->
      <label v-if="!newIsCollection" class="ls-folder">
        <input type="checkbox" v-model="newFolder" />
        <span>{{ t('libraries.new_folder') }}</span>
      </label>
      <label class="ls-folder" @mouseenter="setHint(t('libraries.new_is_collection'), t('libraries.new_is_collection_hint'))" @mouseleave="clearHint()">
        <input type="checkbox" v-model="newIsCollection" @change="onNewCollectionToggle" />
        <span>{{ t('libraries.new_is_collection') }}</span>
      </label>
      <!-- No store toggle: a store is created by a plugin catalogue, not by
           hand. This describes how the library behaves once it holds something,
           which a container of collections never does. -->
      <label v-if="!newIsCollection" class="ls-folder" @mouseenter="setHint(t('libraries.adds_to_default'), t('libraries.adds_to_default_hint'))" @mouseleave="clearHint()">
        <input type="checkbox" v-model="newAddsToDefault" />
        <span>{{ t('libraries.adds_to_default') }}</span>
      </label>
      <label class="ls-upload-btn ls-upload-btn--inline" @mouseenter="setHint(t('libraries.icon_upload'), t('libraries.icon_upload_hint'))" @mouseleave="clearHint()">
        <input type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onNewFile($event)" />
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        <span>{{ newFileName || t('libraries.icon_upload') }}</span>
      </label>
      <div v-if="createError" class="ls-error">{{ createError }}</div>
    </div>

    <div v-if="!loading" class="ls-foot">{{ t('libraries.foot') }}</div>
    </template>

    <!-- ── Everyone: my home / navigation view ──────────────────────────── -->
    <!-- The active theme may ship its own editor for the blocks below. When it
         claims one, Settings stands down rather than offering a second place to
         change the same thing. -->
    <div v-if="!isSettingManaged('libraryVisibility')" class="ls-section">
      <div class="ls-sec-title">{{ t('appearance.lib_visibility') }}</div>
      <div class="ls-sec-desc">{{ t('appearance.lib_visibility_desc') }}</div>
      <div class="ls-vis-list">
        <div
          v-for="(lib, i) in libsStore.enabled"
          :key="lib.slug"
          class="ls-vis-row"
          @mouseenter="setHint(lib.name, t('hint.lib_order'))"
          @mouseleave="clearHint()"
        >
          <div class="ls-reorder">
            <button class="ls-arrow" :disabled="i === 0" @click="moveVis(i, -1)" :aria-label="t('libraries.move_up')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <button class="ls-arrow" :disabled="i === libsStore.enabled.length - 1" @click="moveVis(i, 1)" :aria-label="t('libraries.move_down')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
          <LibraryIcon :icon="lib.icon" :color="lib.color" :size="20" :alt="lib.name" />
          <span class="ls-vis-name">{{ lib.name }}</span>
          <span class="ls-vis-kind">{{ t('libraries.kind_' + lib.kind, lib.kind) }}</span>
          <div class="ls-pill" :class="{ on: !themeStore.isLibraryHidden(lib.slug) }" @click="themeStore.toggleHiddenLibrary(lib.slug)" role="switch" :aria-checked="!themeStore.isLibraryHidden(lib.slug)">
            <div class="ls-pill-knob" />
          </div>
        </div>
        <span v-if="!libsStore.enabled.length" class="ls-sec-desc" style="margin:0;">{{ t('appearance.lib_visibility_empty') }}</span>
      </div>
    </div>

    <!-- Recently-added picker (per theme; themes with a home feed only) -->
    <div v-if="themeStore.currentLayout !== 'classic' && !isSettingManaged('recentLibraries')" class="ls-section">
      <div class="ls-sec-title">{{ t('appearance.recent_libs') }}</div>
      <div class="ls-sec-desc">{{ t('appearance.recent_libs_desc') }}</div>
      <div
        class="ls-recent-list"
        @mouseenter="setHint(t('appearance.recent_libs'), t('hint.recent_libs'))"
        @mouseleave="clearHint()"
      >
        <label v-for="lib in recentLibs" :key="lib.slug" class="ls-recent-item">
          <input type="checkbox" :checked="isRecentChecked(lib.slug)" @change="toggleRecent(lib.slug)" />
          <LibraryIcon :icon="lib.icon" :color="lib.color" :size="16" :alt="lib.name" />
          <span>{{ lib.name }}</span>
        </label>
        <span v-if="!recentLibs.length" class="ls-sec-desc" style="margin:0;">{{ t('appearance.recent_libs_empty') }}</span>
      </div>
    </div>

    <!-- Theme home sections (only when the active theme registered any) -->
    <div v-if="themeHomeSections.length && !isSettingManaged('homeSections')" class="ls-section">
      <div class="ls-sec-title">{{ t('appearance.home_sections') }}</div>
      <div class="ls-sec-desc">{{ t('appearance.home_sections_desc') }}</div>
      <div
        class="ls-recent-list"
        @mouseenter="setHint(t('appearance.home_sections'), t('hint.home_sections'))"
        @mouseleave="clearHint()"
      >
        <div v-for="(s, i) in orderedHomeSections" :key="s.id" class="ls-sec-row">
          <!-- Only for sections the theme actually lays out through
               homeSections.order(). A theme that pins a section to one spot
               declares orderable: false, and offering arrows there would save a
               preference nothing ever reads. -->
          <div v-if="s.orderable !== false" class="ls-reorder">
            <button class="ls-arrow" :disabled="i === 0" @click="moveSection(i, -1)" :aria-label="t('libraries.move_up')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
            </button>
            <button class="ls-arrow" :disabled="i === orderedHomeSections.length - 1" @click="moveSection(i, 1)" :aria-label="t('libraries.move_down')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
          </div>
          <div v-else class="ls-reorder ls-reorder--none" aria-hidden="true" />
          <label class="ls-recent-item">
            <input type="checkbox" :checked="!themeStore.isHomeSectionHidden(s.id)" @change="themeStore.toggleHomeSection(s.id)" />
            <span>{{ t(s.label, s.label) }}</span>
          </label>
          <!-- Switches this section declared for itself (e.g. which side a
               Vapor rail's big card sits on). -->
          <label v-for="o in (s.options || [])" :key="o.id" class="ls-recent-item ls-sec-opt">
            <input
              type="checkbox"
              :checked="themeStore.isHomeSectionOptionOn(s.id, o.id, !!o.default)"
              @change="themeStore.setHomeSectionOption(s.id, o.id, ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ t(o.label, o.label) }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import client from '@/services/api/client'
import { useLibrariesStore } from '@/stores/libraries'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useDialog } from '@/composables/useDialog'
import { useI18n } from '@/i18n'
import LibraryIcon from '@/components/common/LibraryIcon.vue'
import LibraryIconPicker from '@/components/common/LibraryIconPicker.vue'
import { getHomeSections, isSettingManaged } from '@/themes'
import type { LibraryInfo } from '@/stores/libraries'

const { t } = useI18n()
const { setHint, clearHint } = useSettingsHint()
const { gdConfirm } = useDialog()
const libsStore = useLibrariesStore()
const themeStore = useThemeStore()
const auth = useAuthStore()

// Management UI (list / create / access) is admin-only; the per-user sections
// below (visibility + recently-added) are shown to everyone.
const isAdmin = computed(() => auth.user?.role === 'admin')

// Show the hovered icon's name in the settings-hint panel (not a native tooltip).
function onIconHover(name: string | null) {
  if (name) setHint(t('libraries.icon'), name)
  else clearHint()
}

// Home sections the ACTIVE theme registered (empty for themes without extras).
const themeHomeSections = computed(() => getHomeSections())
// Shown in this user's chosen order; sections they never moved keep the theme's.
const orderedHomeSections = computed(() => {
  const byId = new Map(themeHomeSections.value.map(s => [s.id, s]))
  return themeStore.orderHomeSections(themeHomeSections.value.map(s => s.id))
    .map(id => byId.get(id)!)
    .filter(Boolean)
})
// Reorder by swapping the two adjacent ids in the displayed order, like the
// library list above.
function moveSection(i: number, dir: number) {
  const order = orderedHomeSections.value.map(s => s.id)
  const j = i + dir
  if (j < 0 || j >= order.length) return
  const tmp = order[i]; order[i] = order[j]; order[j] = tmp
  themeStore.setHomeSectionOrder(order)
}

// Per-user "recently added" picker (per theme). Couch has no home feed.
const recentLibs = computed(() => libsStore.visible.filter(l => l.kind !== 'couch'))
function isRecentChecked(slug: string): boolean {
  const sel = themeStore.getRecentLibraries()
  return !sel || sel.includes(slug)
}
function toggleRecent(slug: string) {
  const sel = themeStore.getRecentLibraries()
  const all = recentLibs.value.map(l => l.slug)
  let next: string[]
  if (!sel) next = all.filter(s => s !== slug)
  else if (sel.includes(slug)) next = sel.filter(s => s !== slug)
  else next = [...sel, slug]
  themeStore.setRecentLibraries(next)
}

// Per-user library order: reorder by capturing the current displayed order
// (already in effective order) and swapping the two adjacent slugs.
function moveVis(i: number, dir: number) {
  const order = libsStore.enabled.map(l => l.slug)
  const j = i + dir
  if (j < 0 || j >= order.length) return
  const tmp = order[i]; order[i] = order[j]; order[j] = tmp
  themeStore.setLibraryOrder(order)
}

const items = ref<LibraryInfo[]>([])
const loading = ref(true)

const newName = ref('')
const newColor = ref('#7c3aed')
const newFolder = ref(false)
const newIsCollection = ref(false)
const newAddsToDefault = ref(false)
const newIcon = ref('builtin:folder')
const newIconFile = ref<File | null>(null)
const newFileName = ref('')
const creating = ref(false)
const createError = ref('')

// Inline editor (per-row): colour + icon for any library, name for collections.
const editingSlug = ref('')
const editForm = ref<{
  name: string; color: string; icon: string
  adds_to_default_library: boolean
}>({ name: '', color: '#7c3aed', icon: 'builtin:folder', adds_to_default_library: false })
const editFile = ref<File | null>(null)
const editFileName = ref('')
const editError = ref('')
const editSaving = ref(false)

// Per-user access (only user libraries / custom / GOG can be restricted).
const ACL_KINDS = ['gog', 'custom', 'custom_lib']
const users = ref<{ id: number; username: string; role: string }[]>([])
const editAccess = ref<{ visibility: string; userIds: number[] }>({ visibility: 'public', userIds: [] })

function accessEligible(lib: LibraryInfo): boolean {
  return ACL_KINDS.includes(lib.kind)
}

// Only a membership-driven user library can feed the default one - "games" IS
// the default library, and the ROM shelves do not use membership at all.
function defaultFeedEligible(lib: LibraryInfo): boolean {
  return lib.kind === 'custom_lib'
}
function toggleAccessUser(id: number) {
  const a = editAccess.value.userIds
  editAccess.value.userIds = a.includes(id) ? a.filter(x => x !== id) : [...a, id]
}
async function fetchUsers() {
  try {
    const { data } = await client.get('/users')
    users.value = (Array.isArray(data) ? data : []).map((u: any) => ({
      id: u.id, username: u.username, role: String(u.role || '').toLowerCase(),
    }))
  } catch { /* not permitted or unavailable - access UI just shows no users */ }
}

function onNewFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] || null
  newIconFile.value = f
  newFileName.value = f ? f.name : ''
}

async function startEdit(lib: LibraryInfo) {
  editingSlug.value = lib.slug
  editForm.value = {
    name: lib.name, color: lib.color || '#7c3aed', icon: lib.icon || 'builtin:folder',
    adds_to_default_library: !!lib.adds_to_default_library,
  }
  editFile.value = null; editFileName.value = ''; editError.value = ''
  editAccess.value = { visibility: 'public', userIds: [] }
  if (accessEligible(lib)) {
    try {
      const { data } = await client.get(`/libraries/${lib.slug}/access`)
      editAccess.value = {
        visibility: data?.visibility || 'public',
        userIds: Array.isArray(data?.user_ids) ? data.user_ids : [],
      }
    } catch { /* ignore - defaults to public */ }
  }
}
function cancelEdit() {
  editingSlug.value = ''
  editFile.value = null; editFileName.value = ''; editError.value = ''
}
function onEditFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] || null
  editFile.value = f
  editFileName.value = f ? f.name : ''
}

async function uploadIcon(slug: string, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  await client.post(`/libraries/${slug}/icon`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
}

async function saveEdit(lib: LibraryInfo) {
  if (editSaving.value) return
  editSaving.value = true
  editError.value = ''
  try {
    const body: Record<string, unknown> = { color: editForm.value.color, icon: editForm.value.icon }
    if (!lib.is_builtin) body.name = editForm.value.name
    if (defaultFeedEligible(lib)) {
      body.adds_to_default_library = editForm.value.adds_to_default_library
    }
    await client.patch(`/libraries/${lib.slug}`, body)
    if (accessEligible(lib)) {
      await client.put(`/libraries/${lib.slug}/access`, {
        visibility: editAccess.value.visibility,
        user_ids: editAccess.value.userIds,
      })
    }
    if (editFile.value) await uploadIcon(lib.slug, editFile.value)  // overrides icon with the upload
    cancelEdit()
    await load()
    libsStore.fetch()
  } catch (e: any) {
    editError.value = e?.response?.data?.detail || t('libraries.create_failed')
  } finally {
    editSaving.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await client.get('/libraries/all')
    if (Array.isArray(data)) {
      items.value = (data as LibraryInfo[]).sort((a, b) => a.sort_order - b.sort_order)
    }
  } catch { /* ignore */ } finally {
    loading.value = false
  }
}

async function toggle(lib: LibraryInfo) {
  const next = !lib.enabled
  lib.enabled = next
  try {
    await client.patch(`/libraries/${lib.slug}`, { enabled: next })
    libsStore.fetch()
  } catch {
    lib.enabled = !next
  }
}

async function move(i: number, dir: number) {
  const j = i + dir
  if (j < 0 || j >= items.value.length) return
  const a = items.value[i]
  const b = items.value[j]
  const tmp = a.sort_order; a.sort_order = b.sort_order; b.sort_order = tmp
  items.value.sort((x, y) => x.sort_order - y.sort_order)
  try {
    await Promise.all([
      client.patch(`/libraries/${a.slug}`, { sort_order: a.sort_order }),
      client.patch(`/libraries/${b.slug}`, { sort_order: b.sort_order }),
    ])
    libsStore.fetch()
  } catch { /* best-effort */ }
}

function onNewCollectionToggle() {
  // Default a collections container to the layers icon, a regular library to the
  // folder icon (only while the icon is still one of those defaults - keep a pick).
  if (newIcon.value === 'builtin:folder' || newIcon.value === 'builtin:layers') {
    newIcon.value = newIsCollection.value ? 'builtin:layers' : 'builtin:folder'
  }
}

async function create() {
  const name = newName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    if (newIsCollection.value) {
      // A Collections container is a library (kind 'collections') that holds
      // collections of games - no scan folder, but it still gets a chosen icon.
      const { data } = await client.post('/libraries', {
        name, color: newColor.value, icon: newIcon.value, is_collection: true,
      })
      if (newIconFile.value && data?.slug) await uploadIcon(data.slug, newIconFile.value)
    } else {
      const { data } = await client.post('/libraries', {
        name, color: newColor.value, icon: newIcon.value, create_folder: newFolder.value,
        adds_to_default_library: newAddsToDefault.value,
      })
      if (newIconFile.value && data?.slug) await uploadIcon(data.slug, newIconFile.value)
    }
    newName.value = ''
    newFolder.value = false
    newIsCollection.value = false
    newAddsToDefault.value = false
    newIcon.value = 'builtin:folder'
    newIconFile.value = null
    newFileName.value = ''
    await load()
    libsStore.fetch()
  } catch (e: any) {
    createError.value = e?.response?.data?.detail || t('libraries.create_failed')
  } finally {
    creating.value = false
  }
}

async function removeLib(lib: LibraryInfo) {
  const ok = await gdConfirm(t('libraries.delete_confirm', { name: lib.name }), { title: t('libraries.delete'), danger: true })
  if (!ok) return
  try {
    await client.delete(`/libraries/${lib.slug}`)
    await load()
    libsStore.fetch()
  } catch { /* ignore */ }
}

onMounted(() => {
  libsStore.fetch()                       // for the per-user sections (all users)
  if (isAdmin.value) { load(); fetchUsers() }   // admin management list + access
})
</script>

<style scoped>
.lib-settings { max-width: 640px; }

.ls-head { margin-bottom: 18px; }
.ls-title { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); }
.ls-desc { font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 4px; line-height: 1.5; }
.ls-warn {
  display: flex; align-items: center; gap: 8px;
  margin-top: 10px; padding: 9px 12px;
  font-size: var(--fs-sm, 12px); font-weight: 600; color: #fbbf24; line-height: 1.45;
  background: rgba(251, 191, 36, .08);
  border: 1px solid rgba(251, 191, 36, .28);
  border-radius: var(--radius-sm, 8px);
}
.ls-warn svg { flex-shrink: 0; }

.ls-loading { color: var(--muted); font-size: var(--fs-sm, 12px); padding: 16px 0; }

.ls-list { display: flex; flex-direction: column; gap: 8px; }

.ls-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm, 8px);
  background: rgba(255, 255, 255, .03);
  transition: opacity var(--transition), border-color var(--transition);
}
.ls-row--off { opacity: .5; }

.ls-reorder { display: flex; flex-direction: column; gap: 2px; }
/* Holds the column so a theme without reordering keeps its labels aligned with
   one that has it. */
.ls-reorder--none { width: 20px; }
.ls-arrow {
  display: flex; align-items: center; justify-content: center;
  width: 20px; height: 16px;
  border: none; background: none; color: var(--muted);
  cursor: pointer; border-radius: 3px;
}
.ls-arrow:not(:disabled):hover { color: var(--text); background: var(--glass-highlight); }
.ls-arrow:disabled { opacity: .25; cursor: not-allowed; }

.ls-swatch { width: 10px; height: 30px; border-radius: 3px; flex-shrink: 0; }
.ls-icon { width: 26px; height: 26px; object-fit: contain; border-radius: 6px; flex-shrink: 0; }

.ls-info { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.ls-name { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); }
.ls-kind { font-size: var(--fs-xs, 11px); color: var(--muted); }

.ls-del {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 6px);
  background: none; color: var(--muted); cursor: pointer;
  transition: all var(--transition);
}
.ls-del:hover { color: #f87171; border-color: color-mix(in srgb, #f87171 45%, transparent); background: rgba(248,113,113,.08); }

/* Edit button */
.ls-edit {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 6px);
  background: none; color: var(--muted); cursor: pointer;
  transition: all var(--transition);
}
.ls-edit:hover, .ls-edit.on { color: var(--pl-light); border-color: var(--pl); background: var(--pl-dim); }

/* Inline editor */
.ls-item { display: flex; flex-direction: column; }
.ls-row--editing { border-color: color-mix(in srgb, var(--pl) 45%, transparent); border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.ls-editor {
  display: flex; flex-direction: column; gap: 10px;
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--pl) 45%, transparent);
  border-top: none;
  border-radius: 0 0 var(--radius-sm, 8px) var(--radius-sm, 8px);
  background: rgba(255,255,255,.02);
}
.ls-ed-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.ls-ed-label { font-size: var(--fs-xs, 11px); font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.ls-ed-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 4px; }
.ls-ed-cancel, .ls-ed-save {
  padding: 7px 16px; font: inherit; font-size: var(--fs-sm, 13px); font-weight: 600;
  border-radius: var(--radius-xs, 6px); cursor: pointer;
}
.ls-ed-cancel { color: var(--muted); background: none; border: 1px solid var(--glass-border); }
.ls-ed-cancel:hover { color: var(--text); background: var(--glass-highlight); }
.ls-ed-save {
  color: var(--text);
  background: color-mix(in srgb, var(--pl) 22%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
}
.ls-ed-save:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 32%, transparent); }
.ls-ed-save:disabled { opacity: .5; cursor: not-allowed; }

/* Upload button (editor + create) */
.ls-upload-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 12px; font-size: var(--fs-sm, 12px); color: var(--muted);
  border: 1px dashed var(--glass-border); border-radius: var(--radius-xs, 6px);
  background: rgba(255,255,255,.03); cursor: pointer; max-width: 100%;
  transition: all var(--transition);
}
.ls-upload-btn:hover { color: var(--text); border-color: var(--pl); }
.ls-upload-btn span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ls-upload-btn--inline { margin-top: 10px; }

/* Access control */
.ls-access-seg {
  display: flex; width: fit-content;
  border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 6px); overflow: hidden;
}
.ls-access-seg button {
  padding: 6px 16px; font: inherit; font-size: var(--fs-sm, 12px); font-weight: 600;
  background: color-mix(in srgb, var(--pl) 10%, transparent); border: none; color: var(--muted); cursor: pointer;
  transition: all var(--transition);
}
.ls-access-seg button + button { border-left: 1px solid var(--glass-border); }
.ls-access-seg button:hover { color: var(--text); }
.ls-access-seg button.active { background: var(--pl-dim); color: var(--pl-light); }
.ls-access-users { display: flex; flex-direction: column; gap: 2px; margin-top: 2px; max-height: 240px; overflow-y: auto; }
.ls-access-hint { font-size: var(--fs-xs, 11px); color: var(--muted); margin-bottom: 4px; line-height: 1.5; }
.ls-access-user { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm, 13px); color: var(--text); cursor: pointer; padding: 3px 2px; }
.ls-access-user input { cursor: pointer; }
.ls-access-user input:disabled { cursor: not-allowed; }
.ls-access-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ls-access-role { font-size: var(--fs-xs, 10px); color: var(--muted); text-transform: capitalize; flex-shrink: 0; }

/* Per-user sections (visibility + recently added), shown to everyone */
.ls-section { margin-top: 28px; padding-top: 22px; border-top: 1px solid var(--glass-border); }
.lib-settings > .ls-section:first-child { margin-top: 0; padding-top: 0; border-top: none; }
.ls-sec-title { font-size: var(--fs-lg, 16px); font-weight: 700; color: var(--text); }
.ls-sec-desc { font-size: var(--fs-sm, 12px); color: var(--muted); margin-top: 4px; line-height: 1.5; }
.ls-vis-list { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.ls-vis-row {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  border: 1px solid var(--glass-border); border-radius: var(--radius-sm, 8px);
  background: rgba(255, 255, 255, .03);
}
.ls-vis-name { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ls-vis-kind { font-size: var(--fs-xs, 11px); color: var(--muted); flex-shrink: 0; }
.ls-recent-list { display: flex; flex-wrap: wrap; gap: 16px; margin-top: 12px; padding: 4px 2px; }
.ls-recent-item { display: flex; align-items: center; gap: 7px; cursor: pointer; font-size: var(--fs-sm, 13px); color: var(--text); }
/* Home sections carry reorder arrows, so each is a row rather than a bare
   checkbox - the arrows need somewhere to sit. */
.ls-sec-row { display: flex; align-items: center; gap: 8px; }
/* A section's own switches sit beside it, dimmer - they qualify the section
   rather than standing next to it as an equal. */
.ls-sec-opt { opacity: .62; font-size: var(--fs-xs, 12px); }
.ls-sec-opt:hover { opacity: 1; }

/* Glass toggle */
.ls-pill {
  position: relative; width: 42px; height: 24px; border-radius: 999px;
  background: color-mix(in srgb, var(--text, #fff) 12%, transparent);
  border: 1px solid var(--glass-border); cursor: pointer;
  transition: background var(--transition), border-color var(--transition); flex-shrink: 0;
}
.ls-pill.on {
  background: color-mix(in srgb, var(--pl, #7c3aed) 30%, transparent);
  border-color: color-mix(in srgb, var(--pl, #7c3aed) 45%, transparent);
}
.ls-pill-knob {
  position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
  background: var(--text, #fff); transition: transform var(--transition);
}
.ls-pill.on .ls-pill-knob { transform: translateX(18px); }

/* Create */
.ls-create {
  margin-top: 18px; padding: 14px;
  border: 1px dashed var(--glass-border); border-radius: var(--radius-sm, 8px);
}
.ls-create-title { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); margin-bottom: 10px; }
.ls-create-row { display: flex; gap: 8px; align-items: center; }
.ls-input {
  flex: 1; min-width: 0; padding: 8px 10px;
  border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 6px);
  background: rgba(255,255,255,.04); color: var(--text); font: inherit; font-size: var(--fs-sm, 13px);
}
.ls-input:focus { outline: none; border-color: var(--pl); }
.ls-color { width: 38px; height: 36px; padding: 2px; border: 1px solid var(--glass-border); border-radius: var(--radius-xs, 6px); background: none; cursor: pointer; }
.ls-create-btn {
  padding: 8px 16px; font: inherit; font-size: var(--fs-sm, 13px); font-weight: 600;
  color: var(--text);
  background: color-mix(in srgb, var(--pl, #7c3aed) 22%, transparent);
  border: 1px solid color-mix(in srgb, var(--pl, #7c3aed) 40%, transparent);
  border-radius: var(--radius-xs, 6px); cursor: pointer; white-space: nowrap;
}
.ls-create-btn:not(:disabled):hover { background: color-mix(in srgb, var(--pl, #7c3aed) 32%, transparent); }
.ls-create-btn:disabled { opacity: .5; cursor: not-allowed; }
.ls-folder { display: flex; align-items: center; gap: 7px; margin-top: 10px; font-size: var(--fs-sm, 12px); color: var(--muted); cursor: pointer; }
.ls-error { color: #f87171; font-size: var(--fs-sm, 12px); margin-top: 8px; }

.ls-foot { font-size: var(--fs-xs, 11px); color: var(--muted); margin-top: 14px; line-height: 1.5; opacity: .8; }
</style>
