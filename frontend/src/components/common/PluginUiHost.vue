<template>
  <LibraryMetadataPanel
    v-if="meta"
    :game="metaGame"
    :api-prefix="meta.apiPrefix"
    @close="closeMetadataEditor()"
    @saved="onGameSaved"
  />
  <CollectionMetadataPanel
    v-if="coll"
    :collection="collObject"
    @close="closeCollectionEditor()"
    @updated="onCollectionUpdated"
    @deleted="onCollectionDeleted"
  />
  <EmulationRomMetadataPanel
    v-if="romReq"
    :rom="romObject"
    @close="closeRomMetadataEditor()"
    @saved="onRomSaved"
  />
  <!-- Add a file to a game, for skins that draw their own game page. -->
  <Teleport to="body">
    <div v-if="addFileGame" class="puh-backdrop" @mousedown.self="closeAddFileDialog()">
      <div class="puh-dialog glass" role="dialog" :aria-label="t('detail.add_file')">
        <div class="puh-head">
          <span class="puh-title">{{ t('detail.add_file_to', { title: addFileGame.title || '' }) }}</span>
          <button class="puh-close" :title="t('common.close')" @click="closeAddFileDialog()">&times;</button>
        </div>
        <AddFileForm :game-id="addFileGame?.id" @added="onFileAdded" />
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import CollectionMetadataPanel from '@/components/collections/CollectionMetadataPanel.vue'
import EmulationRomMetadataPanel from '@/views/emulation/EmulationRomMetadataPanel.vue'
import AddFileForm from '@/components/games/AddFileForm.vue'
import { useI18n } from '@/i18n'
import {
  pluginUiState,
  closeMetadataEditor,
  closeCollectionEditor,
  closeRomMetadataEditor,
  closeAddFileDialog,
} from '@/lib/pluginUi'

const { t } = useI18n()
const addFileGame = computed(() => pluginUiState.addFileDialog?.game)

// Stays open for the next file; the page is told so it can show the new one,
// and so is anything following the snapshot+event pattern.
function onFileAdded() {
  const req = pluginUiState.addFileDialog
  req?.onAdded?.()
  document.documentElement.dispatchEvent(new CustomEvent('gd-game-updated', {
    detail: { id: addFileGame.value?.id },
  }))
}

const meta = computed(() => pluginUiState.metadataEditor)
const coll = computed(() => pluginUiState.collectionEditor)
const romReq = computed(() => pluginUiState.romEditor)
// The panels type their props loosely (LibGame / any); the requests carry
// plain dicts from the API, so hand them over untyped.
const metaGame   = computed<any>(() => pluginUiState.metadataEditor?.game)
const collObject = computed<any>(() => pluginUiState.collectionEditor?.collection)
const romObject  = computed<any>(() => pluginUiState.romEditor?.rom)

function onRomSaved() {
  const req = pluginUiState.romEditor
  const romId = romObject.value?.id
  // The ROM panel is single-shot: Modern closes it right after a save too.
  pluginUiState.romEditor = null
  req?.onSaved?.()
  document.documentElement.dispatchEvent(new CustomEvent('gd-rom-updated', {
    detail: { id: romId },
  }))
}

function onGameSaved(data: Record<string, unknown>) {
  const req = pluginUiState.metadataEditor
  req?.onSaved?.(data)
  document.documentElement.dispatchEvent(new CustomEvent('gd-game-updated', {
    detail: { id: metaGame.value?.id, apiPrefix: req?.apiPrefix },
  }))
}

function onCollectionUpdated() {
  const req = pluginUiState.collectionEditor
  req?.onUpdated?.()
  document.documentElement.dispatchEvent(new CustomEvent('gd-collection-updated', {
    detail: { slug: collObject.value?.slug },
  }))
}

function onCollectionDeleted(slug: string) {
  const req = pluginUiState.collectionEditor
  pluginUiState.collectionEditor = null
  req?.onDeleted?.(slug)
  document.documentElement.dispatchEvent(new CustomEvent('gd-collection-updated', {
    detail: { slug, deleted: true },
  }))
}
</script>

<style scoped>
.puh-backdrop {
  position: fixed; inset: 0; z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; background: rgba(0,0,0,.55); backdrop-filter: blur(4px);
}
.puh-dialog {
  width: min(640px, 100%); padding: 16px 18px; border-radius: var(--radius, 12px);
  display: flex; flex-direction: column; gap: 12px;
  background: var(--glass-bg, #1a1a2e);
  border: 1px solid var(--glass-border, rgba(255,255,255,.12));
  box-shadow: 0 24px 64px rgba(0,0,0,.55);
}
.puh-head { display: flex; align-items: center; gap: 8px; }
.puh-title { font-size: var(--fs-md, 14px); font-weight: 700; color: var(--text); }
.puh-close {
  margin-left: auto; background: none; border: none; cursor: pointer;
  color: var(--muted); font-size: 20px; line-height: 1;
}
</style>
