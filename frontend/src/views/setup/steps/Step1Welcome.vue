<template>
  <div class="step-content">
    <!-- Language picker -->
    <div class="welcome-lang-row">
      <label class="welcome-lang-label">{{ t('setup.welcome.language_label') }}</label>
      <select
        class="welcome-lang-select"
        :value="locale"
        @change="setLocale(($event.target as HTMLSelectElement).value)"
      >
        <option v-for="lang in SUPPORTED" :key="lang.code" :value="lang.code">
          {{ lang.flag }} {{ lang.name }}
        </option>
      </select>
    </div>

    <h2 class="step-title">{{ t('setup.welcome.title') }}</h2>
    <p class="step-desc">{{ t('setup.welcome.description') }}</p>
    <div class="step-checklist">
      <div v-for="item in checklist" :key="item.key" class="check-item">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="check-icon">
          <polyline points="20 6 9 17 4 12"/>
        </svg>
        <span>{{ t(item.key) }}</span>
      </div>
    </div>
    <button class="wizard-btn wizard-btn--primary" @click="emit('next')">
      {{ t('setup.welcome.button') }}
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n'

const { t, locale, setLocale, SUPPORTED } = useI18n()
const emit = defineEmits<{ next: [] }>()

const checklist = [
  { key: 'setup.welcome.checklist.admin' },
  { key: 'setup.welcome.checklist.gog' },
  { key: 'setup.welcome.checklist.scrapers' },
  { key: 'setup.welcome.checklist.smtp' },
  { key: 'setup.welcome.checklist.settings' },
]
</script>

<style scoped>
.step-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 18px;
  padding: 8px 0;
}

.welcome-lang-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  max-width: 380px;
  justify-content: center;
}
.welcome-lang-label {
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .05em;
}
.welcome-lang-select {
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(255,255,255,.1));
  background: rgba(255,255,255,.04);
  color: var(--text, #fff);
  font-size: var(--fs-md, 14px);
  font-family: inherit;
  cursor: pointer;
  outline: none;
  transition: border-color var(--transition);
}
.welcome-lang-select:focus { border-color: var(--pl); box-shadow: 0 0 0 3px var(--pl-dim); }
.welcome-lang-select option { background: var(--bg2, #0a0a1a); color: var(--text, #fff); }

.step-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

.step-desc {
  font-size: var(--fs-md, 14px);
  color: var(--muted);
  line-height: 1.7;
  max-width: 400px;
  margin: 0;
}

.step-checklist {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  padding: 18px 24px;
  width: 100%;
  max-width: 380px;
}

.check-item {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text);
}

.check-icon {
  color: var(--pl-light);
  flex-shrink: 0;
}
</style>
