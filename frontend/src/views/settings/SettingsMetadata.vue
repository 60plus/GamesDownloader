<template>
  <div class="sm-root">
    <div class="sm-header">
      <div class="sm-icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>
        </svg>
      </div>
      <div>
        <div class="sm-title">{{ t('metadata.title') }}</div>
        <div class="sm-subtitle">{{ t('metadata.subtitle') }}</div>
      </div>
    </div>

    <div v-if="loading" class="sm-loading">
      <span class="spinner" /> {{ t('common.loading') }}
    </div>

    <template v-else>
      <div class="scrapers-list">
        <div
          v-for="scraper in scrapers"
          :key="scraper.key"
          class="scraper-card"
          :class="{ 'scraper-card--filled': form[scraper.key] }"
        >
          <div class="scraper-head">
            <img :src="scraper.icon" :alt="scraper.name" class="scraper-ico" />
            <div class="scraper-info">
              <div class="scraper-name">{{ scraper.name }}</div>
              <div class="scraper-desc">{{ scraper.desc }}</div>
            </div>
            <button
              v-if="canTest(scraper)"
              class="scraper-test-btn"
              :class="testResult[scraper.key]?.ok === true ? 'test--ok' : testResult[scraper.key]?.ok === false ? 'test--err' : ''"
              :disabled="testing === scraper.key"
              @click="testScraper(scraper)"
              :title="t('metadata.test_connection')"
            >
              <span v-if="testing === scraper.key" class="spinner spinner--sm" />
              <svg v-else-if="testResult[scraper.key]?.ok === true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              <svg v-else-if="testResult[scraper.key]?.ok === false" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
              {{ testing === scraper.key ? '' : testResult[scraper.key]?.ok === true ? t('metadata.test_ok') : testResult[scraper.key]?.ok === false ? t('metadata.test_failed') : t('metadata.test_btn') }}
            </button>
          </div>

          <input
            v-model="form[scraper.key]"
            class="field-input"
            :type="scraper.secret ? 'password' : 'text'"
            :placeholder="scraper.placeholder"
            @input="clearTestResult(scraper.key)"
          />
          <input
            v-if="scraper.extraKey"
            v-model="form[scraper.extraKey]"
            class="field-input"
            type="password"
            :placeholder="scraper.extraPlaceholder"
            @input="clearTestResult(scraper.key)"
          />

          <template v-if="scraper.devFields">
            <div class="dev-creds-label">{{ t('metadata.dev_creds') }}</div>
            <div class="dev-creds-row">
              <input
                v-model="form['screenscraper_devid']"
                class="field-input"
                type="text"
                :placeholder="t('metadata.dev_id')"
                @input="clearTestResult(scraper.key)"
              />
              <input
                v-model="form['screenscraper_devpassword']"
                class="field-input"
                type="password"
                :placeholder="t('metadata.dev_password')"
                @input="clearTestResult(scraper.key)"
              />
            </div>
          </template>

          <div v-if="testResult[scraper.key]?.ok === false && testResult[scraper.key]?.message" class="test-error-msg">
            {{ testResult[scraper.key]!.message }}
          </div>
        </div>
      </div>

      <div v-if="serverError" class="field-server-error">{{ serverError }}</div>
      <div v-if="savedOk" class="field-ok">{{ t('metadata.saved') }}</div>

      <div class="sm-actions">
        <button class="action-btn action-btn--primary" :disabled="saving" @click="save">
          <span v-if="saving" class="spinner" />
          <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          {{ t('metadata.save_changes') }}
        </button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import client from '@/services/api/client'
import { useI18n } from '@/i18n'

const { t } = useI18n()

const loading = ref(true)
const saving = ref(false)
const savedOk = ref(false)
const serverError = ref('')
const testing = ref<string | null>(null)
const testResult = reactive<Record<string, { ok: boolean; message: string }>>({})

interface Scraper {
  key: string
  extraKey?: string
  name: string
  desc: string
  icon: string
  secret: boolean
  placeholder: string
  extraPlaceholder?: string
  scraperKey: string
  devFields?: boolean   // ScreenScraper - shows extra devid/devpassword inputs
}

const scrapers: Scraper[] = [
  { key: 'igdb_client_id', extraKey: 'igdb_client_secret', name: 'IGDB', desc: t('metadata.igdb_desc'), icon: '/icons/igdb.ico', secret: false, placeholder: 'Client ID', extraPlaceholder: 'Client Secret', scraperKey: 'igdb' },
  { key: 'steamgriddb_api_key', name: 'SteamGridDB', desc: t('metadata.steamgriddb_desc'), icon: '/icons/steamgriddb.ico', secret: true, placeholder: 'API Key', scraperKey: 'steamgriddb' },
  { key: 'rawg_api_key', name: 'RAWG', desc: t('metadata.rawg_desc'), icon: '/icons/RAWG.ico', secret: true, placeholder: 'API Key', scraperKey: 'rawg' },
  { key: 'screenscraper_username', extraKey: 'screenscraper_password', name: 'ScreenScraper', desc: t('metadata.screenscraper_desc'), icon: '/icons/ScreenScraper.ico', secret: false, placeholder: 'Username', extraPlaceholder: 'Password', scraperKey: 'screenscraper', devFields: true },
]

const form = reactive<Record<string, string>>({})

onMounted(async () => {
  try {
    const data = await client.get('/settings/scrapers').then(r => r.data)
    for (const k of Object.keys(data)) {
      form[k] = data[k] || ''
    }
  } catch {
    // ignore load errors
  } finally {
    loading.value = false
  }
})

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
    await client.post('/settings/scrapers/test', {
      scraper: scraper.scraperKey,
      igdb_client_id: form['igdb_client_id'],
      igdb_client_secret: form['igdb_client_secret'],
      steamgriddb_api_key: form['steamgriddb_api_key'],
      rawg_api_key: form['rawg_api_key'],
      screenscraper_username: form['screenscraper_username'],
      screenscraper_password: form['screenscraper_password'],
      screenscraper_devid: form['screenscraper_devid'] || null,
      screenscraper_devpassword: form['screenscraper_devpassword'] || null,
    })
    testResult[scraper.key] = { ok: true, message: '' }
  } catch (e: any) {
    testResult[scraper.key] = {
      ok: false,
      message: e?.response?.data?.detail || t('metadata.connection_failed'),
    }
  } finally {
    testing.value = null
  }
}

async function save() {
  saving.value = true
  serverError.value = ''
  savedOk.value = false
  try {
    await client.post('/settings/scrapers', form)
    savedOk.value = true
    setTimeout(() => { savedOk.value = false }, 3000)
  } catch (e: any) {
    serverError.value = e?.response?.data?.detail || t('metadata.save_failed')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.sm-root { display: flex; flex-direction: column; gap: var(--space-5, 20px); }

.sm-header { display: flex; align-items: flex-start; gap: 14px; }
.sm-icon {
  width: 38px; height: 38px; border-radius: 9px; flex-shrink: 0;
  background: var(--pl-dim); border: 1px solid var(--pl);
  display: flex; align-items: center; justify-content: center;
  color: var(--pl-light);
}
.sm-title { font-size: 17px; font-weight: 700; color: var(--text); margin-bottom: 2px; }
.sm-subtitle { font-size: var(--fs-sm, 12px); color: var(--muted); line-height: 1.5; }

.sm-loading {
  display: flex; align-items: center; gap: var(--space-2, 8px);
  font-size: 13px; color: var(--muted); padding: 8px 0;
}

.scrapers-list { display: flex; flex-direction: column; gap: var(--space-2, 8px); }

.scraper-card {
  background: var(--glass-bg); border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm); padding: 12px 14px;
  display: flex; flex-direction: column; gap: var(--space-2, 8px);
  transition: border-color var(--transition);
}
.scraper-card--filled { border-color: color-mix(in srgb, var(--pl) 60%, transparent); }

.scraper-head { display: flex; align-items: center; gap: var(--space-3, 12px); }

.scraper-ico {
  width: 36px; height: 36px; object-fit: contain;
  border-radius: 6px; flex-shrink: 0;
  background: rgba(255,255,255,.04); padding: var(--space-1, 4px);
}

.scraper-info { flex: 1; min-width: 0; }
.scraper-name { font-size: 13px; font-weight: 700; color: var(--text); }
.scraper-desc { font-size: 11px; color: var(--muted); margin-top: 1px; }

.scraper-test-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 10px; border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent); background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--muted); font-size: 11px; font-weight: 600; font-family: inherit;
  cursor: pointer; transition: all var(--transition); flex-shrink: 0;
  white-space: nowrap;
}
.scraper-test-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.scraper-test-btn:disabled { opacity: .5; cursor: not-allowed; }
.scraper-test-btn.test--ok { border-color: #22c55e; color: #86efac; background: rgba(34,197,94,.1); }
.scraper-test-btn.test--err { border-color: #f87171; color: #fca5a5; background: rgba(248,113,113,.1); }

.test-error-msg { font-size: 11px; color: #f87171; padding: 0 2px; }

.dev-creds-label {
  font-size: 11px; color: var(--muted); padding: 2px 0 0;
  opacity: .7;
}
.dev-creds-row {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-2, 8px);
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
.field-ok {
  padding: 10px 14px; border-radius: var(--radius-sm);
  background: rgba(34,197,94,.08); border: 1px solid rgba(34,197,94,.25);
  color: #86efac; font-size: 13px;
}

.sm-actions { display: flex; gap: 10px; }

.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius-sm); font-size: 13px;
  font-weight: 600; cursor: pointer; border: 1px solid var(--glass-border);
  font-family: inherit; transition: all var(--transition);
  background: rgba(255,255,255,.05); color: var(--muted);
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.action-btn:not(:disabled):hover { border-color: var(--pl); color: var(--text); }
.action-btn--primary {
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  border-color: color-mix(in srgb, var(--pl) 40%, transparent);
  color: var(--pl-light);
}
.action-btn--primary:not(:disabled):hover { background: color-mix(in srgb, var(--pl) 30%, transparent); opacity: 1; border-color: color-mix(in srgb, var(--pl) 50%, transparent); color: #fff; }

.spinner {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
  animation: spin .7s linear infinite; display: inline-block;
}
.spinner--sm { width: 10px; height: 10px; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
