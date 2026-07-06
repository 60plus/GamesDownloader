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
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LibraryMetadataPanel from '@/components/games/LibraryMetadataPanel.vue'
import CollectionMetadataPanel from '@/components/collections/CollectionMetadataPanel.vue'
import EmulationRomMetadataPanel from '@/views/emulation/EmulationRomMetadataPanel.vue'
import {
  pluginUiState,
  closeMetadataEditor,
  closeCollectionEditor,
  closeRomMetadataEditor,
} from '@/lib/pluginUi'

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
