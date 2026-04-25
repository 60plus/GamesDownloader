<template>
  <div class="step-content">
    <div class="step-header">
      <div class="step-icon">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
        </svg>
      </div>
      <div>
        <h2 class="step-title">{{ t('setup.scrapers.title') }}</h2>
        <p class="step-subtitle">{{ t('setup.scrapers.subtitle') }}</p>
      </div>
    </div>

    <div class="scrapers-grid">
      <div
        v-for="scraper in scrapers"
        :key="scraper.key"
        class="scraper-card"
        :class="{ 'scraper-card--filled': form[scraper.key] }"
      >
        <div class="scraper-head">
          <img :src="scraper.icon" :alt="t(scraper.nameKey)" class="scraper-ico" />
          <div class="scraper-info">
            <div class="scraper-name">{{ t(scraper.nameKey) }}</div>
            <div class="scraper-desc">{{ t(scraper.descKey) }}</div>
          </div>
          <button
            v-if="canTest(scraper)"
            class="scraper-test-btn"
            :class="testResult[scraper.key]?.ok === true ? 'test--ok' : testResult[scraper.key]?.ok === false ? 'test--err' : ''"
            :disabled="testing === scraper.key"
            @click="testScraper(scraper)"
            :title="t('setup.scrapers.button.test_title')"
          >
            <span v-if="testing === scraper.key" class="spinner spinner--sm" />
            <svg v-else-if="testResult[scraper.key]?.ok === true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
            <svg v-else-if="testResult[scraper.key]?.ok === false" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
            {{ testing === scraper.key ? '' : testResult[scraper.key]?.ok === true ? t('setup.scrapers.button.test_ok') : testResult[scraper.key]?.ok === false ? t('setup.scrapers.button.test_failed') : t('setup.scrapers.button.test') }}
          </button>
        </div>

        <input
          v-model="form[scraper.key]"
          class="field-input"
          :type="scraper.secret ? 'password' : 'text'"
          :placeholder="t(scraper.placeholderKey)"
          @input="clearTestResult(scraper.key)"
        />
        <input
          v-if="scraper.extraKey"
          v-model="form[scraper.extraKey]"
          class="field-input"
          type="password"
          :placeholder="scraper.extraPlaceholderKey ? t(scraper.extraPlaceholderKey) : ''"
          @input="clearTestResult(scraper.key)"
        />

        <div v-if="testResult[scraper.key]?.message && testResult[scraper.key]?.ok === false" class="test-error-msg">
          {{ testResult[scraper.key]!.message }}
        </div>
      </div>
    </div>

    <div v-if="serverError" class="field-server-error">{{ serverError }}</div>

    <div class="step-actions">
      <button class="wizard-btn wizard-btn--ghost" @click="emit('skip')">
        {{ t('setup.scrapers.button.skip') }}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <button
        class="wizard-btn wizard-btn--primary"
        :disabled="!hasAnyKey || saving"
        @click="save"
      >
        <span v-if="saving" class="spinner" />
        <span v-else>{{ t('setup.scrapers.button.save') }}</span>
        <svg v-if="!saving" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const emit = defineEmits<{ next: []; skip: [] }>()

const saving = ref(false)
const serverError = ref('')
const testing = ref<string | null>(null)
const testResult = reactive<Record<string, { ok: boolean; message: string }>>({})

interface Scraper {
  key: string
  extraKey?: string
  nameKey: string
  descKey: string
  icon: string
  secret: boolean
  placeholderKey: string
  extraPlaceholderKey?: string
  scraperKey: string  // key for backend test endpoint
}

const scrapers: Scraper[] = [
  { key: 'igdb_client_id', extraKey: 'igdb_client_secret', nameKey: 'setup.scrapers.igdb.name', descKey: 'setup.scrapers.igdb.desc', icon: '/icons/igdb.ico', secret: false, placeholderKey: 'setup.scrapers.igdb.placeholder', extraPlaceholderKey: 'setup.scrapers.igdb.extra_placeholder', scraperKey: 'igdb' },
  { key: 'steamgriddb_api_key', nameKey: 'setup.scrapers.steamgriddb.name', descKey: 'setup.scrapers.steamgriddb.desc', icon: '/icons/steamgriddb.ico', secret: true, placeholderKey: 'setup.scrapers.steamgriddb.placeholder', scraperKey: 'steamgriddb' },
  { key: 'rawg_api_key', nameKey: 'setup.scrapers.rawg.name', descKey: 'setup.scrapers.rawg.desc', icon: '/icons/RAWG.ico', secret: true, placeholderKey: 'setup.scrapers.rawg.placeholder', scraperKey: 'rawg' },
  { key: 'screenscraper_username', extraKey: 'screenscraper_password', nameKey: 'setup.scrapers.screenscraper.name', descKey: 'setup.scrapers.screenscraper.desc', icon: '/icons/ScreenScraper.ico', secret: false, placeholderKey: 'setup.scrapers.screenscraper.placeholder', extraPlaceholderKey: 'setup.scrapers.screenscraper.extra_placeholder', scraperKey: 'screenscraper' },
]

const form = reactive<Record<string, string>>({})

const hasAnyKey = computed(() => scrapers.some(s => form[s.key]?.trim()))

function canTest(scraper: Scraper): boolean {
  return !!form[scraper.key]?.trim()
}

function clearTestResult(key: string) {
  delete testResult[key]
}

async function testScraper(scraper: Scraper) {
  testing.value = scraper.key
  delete testResult[scraper.key]
  try {
    await client.post('/setup/scrapers/test', {
      scraper: scraper.scraperKey,
      igdb_client_id: form['igdb_client_id'],
      igdb_client_secret: form['igdb_client_secret'],
      steamgriddb_api_key: form['steamgriddb_api_key'],
      rawg_api_key: form['rawg_api_key'],
      screenscraper_username: form['screenscraper_username'],
      screenscraper_password: form['screenscraper_password'],
    })
    testResult[scraper.key] = { ok: true, message: '' }
  } catch (e: any) {
    testResult[scraper.key] = {
      ok: false,
      message: e?.response?.data?.detail || t('setup.scrapers.error.test_failed'),
    }
  } finally {
    testing.value = null
  }
}

async function save() {
  saving.value = true
  serverError.value = ''
  try {
    await client.post('/setup/api-keys', form)
    emit('next')
  } catch (e: any) {
    serverError.value = e?.response?.data?.detail || t('setup.scrapers.error.save_failed')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.step-content { display: flex; flex-direction: column; gap: var(--space-5, 20px); }

.step-header { display: flex; align-items: flex-start; gap: var(--space-4, 16px); }
.step-icon {
  width: 42px; height: 42px; border-radius: 10px;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light); flex-shrink: 0;
}
.step-title { font-size: 20px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.step-subtitle { font-size: 13px; color: var(--muted); margin: 0; }

.scrapers-grid { display: flex; flex-direction: column; gap: var(--space-2, 8px); }

.scraper-card {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 12px 14px;
  display: flex; flex-direction: column; gap: var(--space-2, 8px);
  transition: border-color var(--transition);
}
.scraper-card--filled { border-color: color-mix(in srgb, var(--pl) 60%, transparent); }

.scraper-head { display: flex; align-items: center; gap: var(--space-3, 12px); }

.scraper-ico {
  width: 40px; height: 40px; object-fit: contain;
  border-radius: 6px; flex-shrink: 0;
  background: rgba(255,255,255,.04); padding: var(--space-1, 4px);
}

.scraper-info { flex: 1; min-width: 0; }
.scraper-name { font-size: 13px; font-weight: 700; color: var(--text); }
.scraper-desc { font-size: 11px; color: var(--muted); margin-top: 1px; }

.scraper-test-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.05);
  color: var(--muted); font-size: 11px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition); flex-shrink: 0;
  white-space: nowrap;
}
.scraper-test-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.scraper-test-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.scraper-test-btn.test--ok { border-color: #22c55e; color: #86efac; background: rgba(34,197,94,.1); }
.scraper-test-btn.test--err { border-color: #f87171; color: #fca5a5; background: rgba(248,113,113,.1); }

.test-error-msg {
  font-size: 11px; color: #f87171; padding: 0 2px;
}

.field-input {
  width: 100%; padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border); background: rgba(255,255,255,.04);
  color: var(--text); font-size: 13px; font-family: inherit; box-sizing: border-box;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.field-input:focus { outline: none; border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.field-input::placeholder { color: rgba(255,255,255,.25); }

.field-server-error {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(248,113,113,.1); border: 1px solid rgba(248,113,113,.3);
  color: #f87171; font-size: 13px;
}

.step-actions { display: flex; gap: 10px; padding-top: 4px; }

.spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
.spinner--sm { width: 10px; height: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
