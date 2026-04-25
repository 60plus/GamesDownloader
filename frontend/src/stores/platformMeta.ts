import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/services/api/client'

export interface PlatformMeta {
  name: string
  color: string
  palette: string[]
  manufacturer: string
  release_year: string
  hardware_type: string
  cover_size: string
  descriptions: Record<string, string>
}

export const usePlatformMetaStore = defineStore('platformMeta', () => {
  const meta = ref<Record<string, PlatformMeta>>({})
  let _fetched = false

  async function fetchIfNeeded() {
    if (_fetched) return
    try {
      const { data } = await client.get('/roms/platforms/metadata')
      meta.value = data
      _fetched = true
    } catch {
      // silently ignore - metadata is enhancement only
    }
  }

  function getColor(fsSlug: string): string {
    return meta.value[fsSlug]?.color ?? ''
  }

  function getPalette(fsSlug: string): string[] {
    return meta.value[fsSlug]?.palette ?? []
  }

  function getDescription(fsSlug: string, lang = 'en'): string {
    const d = meta.value[fsSlug]?.descriptions
    if (!d) return ''
    return d[lang] ?? d['en'] ?? ''
  }

  return { meta, fetchIfNeeded, getColor, getPalette, getDescription }
})
