<template>
  <button
    v-if="translatorAvailable"
    class="gd-translate-btn"
    :class="{ 'gd-translate-btn--loading': loading }"
    :disabled="loading || !text"
    :title="`Translate ${fromFlag} ${fromLang.toUpperCase()} to ${toFlag} ${toLang.toUpperCase()}`"
    @click="doTranslate"
  >
    <div v-if="loading" class="gd-translate-spinner" />
    <template v-else>
      <span class="gd-translate-flag">{{ fromFlag }}</span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
      <span class="gd-translate-flag">{{ toFlag }}</span>
    </template>
  </button>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import client from '@/services/api/client'

const props = defineProps<{
  text: string
}>()

const emit = defineEmits<{
  translated: [text: string]
}>()

const loading = ref(false)
const translatorAvailable = ref(false)
const fromLang = ref('en')
const toLang = ref('pl')

const FLAG_MAP: Record<string, string> = {
  en: '\u{1F1EC}\u{1F1E7}', pl: '\u{1F1F5}\u{1F1F1}', de: '\u{1F1E9}\u{1F1EA}',
  fr: '\u{1F1EB}\u{1F1F7}', es: '\u{1F1EA}\u{1F1F8}', it: '\u{1F1EE}\u{1F1F9}',
  pt: '\u{1F1F5}\u{1F1F9}', ru: '\u{1F1F7}\u{1F1FA}', ja: '\u{1F1EF}\u{1F1F5}',
  ko: '\u{1F1F0}\u{1F1F7}', zh: '\u{1F1E8}\u{1F1F3}', cs: '\u{1F1E8}\u{1F1FF}',
  sk: '\u{1F1F8}\u{1F1F0}', nl: '\u{1F1F3}\u{1F1F1}', sv: '\u{1F1F8}\u{1F1EA}',
  da: '\u{1F1E9}\u{1F1F0}', no: '\u{1F1F3}\u{1F1F4}', fi: '\u{1F1EB}\u{1F1EE}',
  hu: '\u{1F1ED}\u{1F1FA}', ro: '\u{1F1F7}\u{1F1F4}', bg: '\u{1F1E7}\u{1F1EC}',
  hr: '\u{1F1ED}\u{1F1F7}', uk: '\u{1F1FA}\u{1F1E6}', ar: '\u{1F1F8}\u{1F1E6}',
  tr: '\u{1F1F9}\u{1F1F7}', auto: '\u{1F310}',
}

const fromFlag = ref(FLAG_MAP['en'])
const toFlag = ref(FLAG_MAP['pl'])

onMounted(async () => {
  try {
    const { data } = await client.get('/plugins')
    const translator = (data as any[]).find(
      (p: any) => p.plugin_id === 'gd3-translator' && p.enabled
    )
    if (translator) {
      translatorAvailable.value = true
      // Read config
      try {
        const { data: cfg } = await client.get('/plugins/gd3-translator/config')
        if (cfg?.config) {
          const c = typeof cfg.config === 'string' ? JSON.parse(cfg.config) : cfg.config
          fromLang.value = c.from_lang || 'en'
          toLang.value = c.to_lang || 'pl'
          fromFlag.value = FLAG_MAP[fromLang.value] || '\u{1F310}'
          toFlag.value = FLAG_MAP[toLang.value] || '\u{1F310}'
        }
      } catch { /* use defaults */ }
    }
  } catch { /* plugin system not available */ }
})

async function doTranslate() {
  if (!props.text || loading.value) return
  loading.value = true
  try {
    const { data } = await client.post('/plugins/translate', {
      text: props.text,
      from_lang: fromLang.value,
      to_lang: toLang.value,
    })
    if (data.ok && data.text) {
      emit('translated', data.text)
    }
  } catch (e) {
    console.error('Translation failed:', e)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.gd-translate-btn {
  display: inline-flex; align-items: center; gap: var(--space-1, 4px);
  padding: 4px 10px; border-radius: 6px;
  background: rgba(99, 102, 241, .15);
  border: 1px solid rgba(99, 102, 241, .3);
  color: rgba(99, 102, 241, .9);
  font-size: var(--fs-sm, 12px); font-weight: 600;
  cursor: pointer; transition: all .15s;
  vertical-align: middle;
}
.gd-translate-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, .25);
  border-color: rgba(99, 102, 241, .5);
}
.gd-translate-btn:disabled {
  opacity: .4; cursor: default;
}
.gd-translate-btn--loading {
  min-width: 60px; justify-content: center;
}
.gd-translate-flag { font-size: var(--fs-md, 14px); line-height: 1; }
.gd-translate-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(99, 102, 241, .2);
  border-top-color: rgba(99, 102, 241, .8);
  border-radius: 50%;
  animation: gd-tspin .6s linear infinite;
}
@keyframes gd-tspin { to { transform: rotate(360deg); } }
</style>
