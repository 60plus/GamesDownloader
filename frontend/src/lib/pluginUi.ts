/**
 * Shared-editor bridge for plugin themes (window.__GD__.ui).
 *
 * A compiled theme plugin can render its own game / collection detail pages,
 * but the metadata editors (LibraryMetadataPanel, CollectionMetadataPanel)
 * stay core components - they are far too large to reimplement per theme and
 * plugin metadata tabs (registerMetadataTab) mount inside them. This module
 * lets a theme open those editors imperatively; PluginUiHost (mounted once in
 * App.vue) renders whatever is requested here.
 *
 * Events: besides the optional callbacks, every save/update also dispatches a
 * DOM CustomEvent on document.documentElement ('gd-game-updated' /
 * 'gd-collection-updated') so themes that follow the snapshot+event pattern
 * (Pinia reactivity does not cross the compiled-plugin boundary) can refetch.
 */

import { reactive } from 'vue'

export interface MetadataEditorRequest {
  /** Full game dict (the same shape the detail endpoints return). */
  game: Record<string, unknown>
  /** '/library/games' (default) or '/gog/library/games'. */
  apiPrefix?: string
  onSaved?: (data: Record<string, unknown>) => void
  onClosed?: () => void
}

export interface CollectionEditorRequest {
  /** Loaded collection object; openCollectionEditor can resolve it from a slug. */
  collection: Record<string, unknown>
  onUpdated?: () => void
  onDeleted?: (slug: string) => void
  onClosed?: () => void
}

export interface RomEditorRequest {
  /** Full ROM dict (the same shape GET /roms/{id} returns). */
  rom: Record<string, unknown>
  onSaved?: () => void
  onClosed?: () => void
}

export const pluginUiState = reactive({
  metadataEditor: null as MetadataEditorRequest | null,
  collectionEditor: null as CollectionEditorRequest | null,
  romEditor: null as RomEditorRequest | null,
})

export function openMetadataEditor(req: MetadataEditorRequest): void {
  if (!req || !req.game) return
  pluginUiState.metadataEditor = { apiPrefix: '/library/games', ...req }
}

/** Accepts a loaded collection object or its slug (resolved via the store). */
export async function openCollectionEditor(
  target: Record<string, unknown> | string,
  opts: Omit<CollectionEditorRequest, 'collection'> = {},
): Promise<void> {
  let collection: Record<string, unknown> | null = null
  if (typeof target === 'string') {
    const { useCollectionsStore } = await import('@/stores/collections')
    collection = (await useCollectionsStore().get(target)) as Record<string, unknown> | null
  } else {
    collection = target
  }
  if (!collection) return
  pluginUiState.collectionEditor = { collection, ...opts }
}

export function openRomMetadataEditor(req: RomEditorRequest): void {
  if (!req || !req.rom) return
  pluginUiState.romEditor = { ...req }
}

export function closeMetadataEditor(): void {
  const req = pluginUiState.metadataEditor
  pluginUiState.metadataEditor = null
  req?.onClosed?.()
}

export function closeRomMetadataEditor(): void {
  const req = pluginUiState.romEditor
  pluginUiState.romEditor = null
  req?.onClosed?.()
}

export function closeCollectionEditor(): void {
  const req = pluginUiState.collectionEditor
  pluginUiState.collectionEditor = null
  req?.onClosed?.()
}
