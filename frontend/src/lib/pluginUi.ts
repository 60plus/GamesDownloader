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

export interface AddFileRequest {
  /** The game the file goes into; `id` is what is sent, `title` heads the dialog. */
  game: { id: number | string; title?: string }
  /** After a file landed, so the page can refetch its file list. */
  onAdded?: () => void
  onClosed?: () => void
}

export interface RomAddFileRequest {
  /** The ROM the file goes beside. `platform_fs_slug` lets it take a further
   *  disc too; without it the dialog offers extras, mods and the manual. */
  rom: { id: number; title?: string; platform_fs_slug?: string | null }
  /** After a file landed, so the page can refetch the ROM and its files. */
  onAdded?: () => void
  onClosed?: () => void
}

export const pluginUiState = reactive({
  metadataEditor: null as MetadataEditorRequest | null,
  collectionEditor: null as CollectionEditorRequest | null,
  romEditor: null as RomEditorRequest | null,
  addFileDialog: null as AddFileRequest | null,
  romAddFileDialog: null as RomAddFileRequest | null,
})

/** Open the "add a file to this ROM game" dialog (1.0.36): an extra, a mod, the
 *  manual or a further disc, by administrators and uploaders alike. The form is
 *  the core's, so every skin sends the same request and shows the same refusal.
 *  It stays open after a file lands, for the next one. */
export function openRomAddFileDialog(req: RomAddFileRequest): void {
  if (!req || !req.rom || !req.rom.id) return
  pluginUiState.romAddFileDialog = { ...req }
}

export function closeRomAddFileDialog(): void {
  const req = pluginUiState.romAddFileDialog
  pluginUiState.romAddFileDialog = null
  req?.onClosed?.()
}

/** Open the "add a file to this game" dialog (1.0.35). For a skin that draws its
 *  own game page: an uploader may add a file to any game it can see, and the
 *  form is the core's, so every skin sends the same request and shows the same
 *  refusal. The dialog stays open after a file lands, for the next one. */
export function openAddFileDialog(req: AddFileRequest): void {
  if (!req || !req.game || !req.game.id) return
  pluginUiState.addFileDialog = { ...req }
}

export function closeAddFileDialog(): void {
  const req = pluginUiState.addFileDialog
  pluginUiState.addFileDialog = null
  req?.onClosed?.()
}

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
