<template>
  <div class="wizard-shell">
    <!-- Ambient background (uses current theme/skin) -->
    <AmbientBackground />

    <div class="wizard-wrap">
      <!-- Header / stepper -->
      <div class="wizard-header">
        <div class="wizard-brand">
          <img src="/GDLOGO.png" alt="GamesDownloader" class="brand-logo" />
        </div>

        <div class="wizard-stepper">
          <template v-for="(step, idx) in STEPS" :key="step.key">
            <div
              class="stepper-step"
              :class="{
                'stepper-step--done':   setupStore.currentStep > idx + 1,
                'stepper-step--active': setupStore.currentStep === idx + 1,
              }"
            >
              <div class="stepper-dot">
                <svg v-if="setupStore.currentStep > idx + 1" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span v-else>{{ idx + 1 }}</span>
              </div>
              <span class="stepper-label">{{ step.label }}</span>
            </div>
            <div v-if="idx < STEPS.length - 1" class="stepper-connector" :class="{ 'stepper-connector--done': setupStore.currentStep > idx + 1 }" />
          </template>
        </div>
      </div>

      <!-- Card -->
      <div class="wizard-card">
        <transition :name="transitionName" mode="out-in">
          <component
            :is="currentStepComponent"
            :key="setupStore.currentStep"
            @next="() => goNext(true)"
            @skip="() => goNext(false)"
            @gog-connected="onGogConnected"
          />
        </transition>
      </div>

      <!-- Back / Skip All navigation -->
      <div v-if="showNav" class="wizard-nav">
        <button v-if="canGoBack" class="wizard-btn wizard-btn--ghost wizard-btn--nav" @click="goBack">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          {{ t('setup.nav.back') }}
        </button>
        <span class="wizard-nav-spacer" />
        <button v-if="canSkipAll" class="wizard-btn wizard-btn--ghost wizard-btn--nav" @click="skipAll">
          {{ t('setup.nav.skip_all') }}
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="5 12 19 12"/><polyline points="13 6 19 12 13 18"/>
          </svg>
        </button>
      </div>

      <!-- Step counter -->
      <div class="wizard-footer">
        {{ t('setup.footer.step_counter', { current: setupStore.currentStep, total: setupStore.totalSteps }) }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AmbientBackground from '@/components/common/AmbientBackground.vue'
import { useSetupStore } from '@/stores/setup'
import { useI18n } from '@/i18n'

const { t } = useI18n()
const router     = useRouter()
const setupStore = useSetupStore()

onMounted(async () => {
  const complete = await setupStore.checkStatus()
  if (complete) {
    router.replace({ name: 'home' })
    return
  }
  // Skip admin creation step if an admin already exists
  if (setupStore.hasAdmin && setupStore.currentStep === 1) {
    // Will auto-advance after welcome; handled in goNext
  }
})

const STEPS = computed(() => [
  { key: 'welcome',     label: t('setup.step.welcome')   },
  { key: 'admin',       label: t('setup.step.admin')     },
  { key: 'gog',         label: t('setup.step.gog')       },
  { key: 'scrapers',    label: t('setup.step.scrapers')  },
  { key: 'smtp',        label: t('setup.step.smtp')      },
  { key: 'app',         label: t('setup.step.settings')  },
  { key: 'complete',    label: t('setup.step.complete')  },
])

const stepComponents = [
  defineAsyncComponent(() => import('./steps/Step1Welcome.vue')),
  defineAsyncComponent(() => import('./steps/Step2Admin.vue')),
  defineAsyncComponent(() => import('./steps/Step3Gog.vue')),
  defineAsyncComponent(() => import('./steps/Step4Scrapers.vue')),
  defineAsyncComponent(() => import('./steps/Step5Smtp.vue')),
  defineAsyncComponent(() => import('./steps/Step6AppSettings.vue')),
  defineAsyncComponent(() => import('./steps/Step7Complete.vue')),
]

const currentStepComponent = computed(() => stepComponents[setupStore.currentStep - 1])

// ── Nav visibility ────────────────────────────────────────────────────────────
const canGoBack  = computed(() => setupStore.currentStep >= 4 && setupStore.currentStep <= 6)
const canSkipAll = computed(() => setupStore.currentStep >= 3 && setupStore.currentStep <= 6)
const showNav    = computed(() => canGoBack.value || canSkipAll.value)

const direction = ref<'forward' | 'back'>('forward')
const transitionName = computed(() => direction.value === 'forward' ? 'slide-next' : 'slide-prev')

function goNext(stepDone = true) {
  direction.value = 'forward'
  if (stepDone) setupStore.markDone(setupStore.currentStep)
  setupStore.nextStep()
  // Step 2 is admin creation - skip if admin already exists
  if (setupStore.currentStep === 2 && setupStore.hasAdmin) {
    setupStore.markDone(2)
    setupStore.nextStep()
  }
}

function goBack() {
  direction.value = 'back'
  setupStore.prevStep()
  // Skip admin step going backwards if admin already exists
  if (setupStore.currentStep === 2 && setupStore.hasAdmin) {
    setupStore.prevStep()
  }
}

function skipAll() {
  direction.value = 'forward'
  setupStore.goToStep(7)
}

function onGogConnected(success: boolean) {
  if (success) setupStore.markDone(3)
}
</script>

<style scoped>
/* ── Shell ────────────────────────────────────────────────────────────────── */
.wizard-shell {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--bg, #0d0d1a);
  isolation: isolate;
  z-index: 0;
}

.wizard-wrap {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-6, 24px);
  width: 100%;
  max-width: 560px;
  padding: 24px 16px;
  box-sizing: border-box;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
.wizard-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-5, 20px);
  width: 100%;
}

.brand-logo {
  height: 121px;
  filter: drop-shadow(0 0 10px var(--pglow)) drop-shadow(0 0 22px var(--pglow2));
}

/* ── Stepper ──────────────────────────────────────────────────────────────── */
.wizard-stepper {
  display: flex;
  align-items: center;
  gap: 0;
  width: 100%;
  overflow-x: auto;
  padding: 0 4px;
}
.wizard-stepper::-webkit-scrollbar { height: 0; }

.stepper-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.stepper-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--glass-border);
  background: rgba(255,255,255,.05);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  transition: all var(--transition);
}

.stepper-label {
  font-size: var(--fs-xs, 10px);
  font-weight: 600;
  color: var(--muted);
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: .05em;
  transition: color var(--transition);
}

.stepper-step--active .stepper-dot {
  border-color: var(--pl);
  background: var(--pl-dim);
  color: var(--pl-light);
  box-shadow: 0 0 10px var(--pglow);
}
.stepper-step--active .stepper-label { color: var(--pl-light); }

.stepper-step--done .stepper-dot {
  border-color: var(--pl);
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  color: #fff;
}
.stepper-step--done .stepper-label { color: var(--pl-light); }

.stepper-connector {
  flex: 1;
  height: 2px;
  background: var(--glass-border);
  min-width: 12px;
  margin-bottom: 20px;
  transition: background var(--transition);
}
.stepper-connector--done { background: color-mix(in srgb, var(--pl) 30%, transparent); }

/* ── Card ─────────────────────────────────────────────────────────────────── */
.wizard-card {
  width: 100%;
  background: var(--glass-bg);
  border: 1.5px solid var(--glass-border);
  border-radius: var(--radius);
  padding: 32px 36px;
  backdrop-filter: blur(var(--glass-blur-px, 22px)) saturate(var(--glass-sat, 180%));
  box-sizing: border-box;
}

/* ── Nav (Back / Skip All) ────────────────────────────────────────────────── */
.wizard-nav {
  display: flex;
  align-items: center;
  width: 100%;
  gap: var(--space-2, 8px);
}
.wizard-nav-spacer { flex: 1; }
.wizard-btn--nav {
  padding: 7px 14px;
  font-size: var(--fs-sm, 12px);
}

/* ── Footer ───────────────────────────────────────────────────────────────── */
.wizard-footer {
  font-size: 11px;
  color: var(--muted);
  opacity: 0.5;
}

/* ── Transitions ──────────────────────────────────────────────────────────── */
.slide-next-enter-active,
.slide-next-leave-active,
.slide-prev-enter-active,
.slide-prev-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.slide-next-enter-from { opacity: 0; transform: translateX(28px); }
.slide-next-leave-to   { opacity: 0; transform: translateX(-28px); }

.slide-prev-enter-from { opacity: 0; transform: translateX(-28px); }
.slide-prev-leave-to   { opacity: 0; transform: translateX(28px); }
</style>

<!-- Global wizard button styles (shared by all step components) -->
<style>
.wizard-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2, 8px);
  padding: 10px 20px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
  border: 1.5px solid transparent;
  text-decoration: none;
}

.wizard-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wizard-btn--primary {
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  border-color: var(--pl);
  color: #fff;
}
.wizard-btn--primary:not(:disabled):hover {
  background: var(--pl-light);
  border-color: var(--pl-light);
  box-shadow: 0 0 16px var(--pglow);
}

.wizard-btn--secondary {
  background: rgba(255,255,255,.06);
  border-color: var(--glass-border);
  color: var(--text);
}
.wizard-btn--secondary:not(:disabled):hover {
  background: var(--glass-highlight);
  border-color: var(--pl);
}

.wizard-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--muted);
}
.wizard-btn--ghost:hover {
  color: var(--text);
  border-color: var(--pl);
}
</style>
