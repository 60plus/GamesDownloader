<template>
  <component
    :is="type === 'toggle' ? 'label' : 'div'"
    class="ap-option"
    :class="{
      'ap-option--range': type === 'range',
      'ap-option--select': type === 'segmented',
      'ap-option--disabled': isDisabled,
    }"
    @mouseenter="setHint(t(label), t(hintBody ?? hint))"
    @mouseleave="clearHint()"
  >
    <div class="ap-option-left">
      <div class="ap-option-icon">
        <slot name="icon" />
      </div>
      <div class="ap-option-info">
        <span class="ap-option-name">{{ t(label) }}</span>
        <span class="ap-option-hint">{{ t(hint) }}</span>
        <span v-if="!supported" class="ap-option-na">{{ t('appearance.not_in_theme') }}</span>
      </div>
    </div>

    <!-- Toggle pill -->
    <div
      v-if="type === 'toggle'"
      class="ap-pill"
      :class="{ on: !!modelValue }"
      @click="emit('update:modelValue', !modelValue)"
    >
      <div class="ap-pill-knob" />
    </div>

    <!-- Segmented control -->
    <div v-else-if="type === 'segmented'" class="ap-segmented">
      <button
        v-for="opt in options"
        :key="opt.id"
        class="ap-seg-btn"
        :class="{ active: String(modelValue) === opt.id }"
        :disabled="isDisabled"
        @click="emit('update:modelValue', opt.id)"
      >{{ opt.label }}</button>
    </div>

    <!-- Range slider -->
    <div v-else class="ap-range-wrap">
      <input
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="Number(modelValue)"
        @input="emit('update:modelValue', Number(($event.target as HTMLInputElement).value))"
        class="ap-range"
      />
      <span class="ap-range-val">{{ modelValue }}{{ unit }}</span>
    </div>
  </component>
</template>

<script setup lang="ts">
/**
 * One row on the Appearance page: an icon, a name, a short hint and a control.
 *
 * The nine rows were written out one by one, so each carried its own copy of
 * the "does this theme draw the effect at all" test - the grey-out class, the
 * badge and, where a row depends on another switch, a second condition on top.
 * Naming the effect once here keeps those three in step.
 */
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

const props = defineProps<{
  /** Name of the core effect this row switches, for the theme's own declaration. */
  effect?: string
  label: string
  hint: string
  /** Body of the hover panel; falls back to the short hint under the name. */
  hintBody?: string
  type: 'toggle' | 'range' | 'segmented'
  modelValue: unknown
  /** Segmented control choices. */
  options?: { id: string; label: string }[]
  min?: number
  max?: number
  step?: number
  unit?: string
  /** An extra condition on top of the theme's declaration, for a row that
   *  only means something while another switch is on. */
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: unknown): void }>()

const { t } = useI18n()
const themeStore = useThemeStore()
const { setHint, clearHint } = useSettingsHint()

const supported  = computed(() => !props.effect || themeStore.supportsEffect(props.effect))
const isDisabled = computed(() => props.disabled === true || !supported.value)
</script>

<style scoped>
.ap-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4, 16px);
  padding: 13px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  transition: background var(--transition);
  user-select: none;
}
.ap-option:hover { background: var(--glass-highlight); }

.ap-option-left {
  display: flex;
  align-items: center;
  gap: var(--space-3, 12px);
  flex: 1;
}

.ap-option-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm, 8px);
  background: rgba(255,255,255,.06);
  border: 1px solid var(--glass-border);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  flex-shrink: 0;
  transition: background var(--transition), color var(--transition), border-color var(--transition);
}
.ap-option:hover .ap-option-icon {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}

.ap-option-info { display: flex; flex-direction: column; gap: 2px; }
.ap-option-name { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); }
.ap-option-hint { font-size: var(--fs-sm, 12px); color: var(--muted); }
.ap-option-na {
  font-size: 11px; font-weight: 600; letter-spacing: .2px;
  color: var(--pl, #a78bfa); opacity: .85;
}
.ap-option--disabled { opacity: .45; pointer-events: none; }

/* ── Toggle pill ─────────────────────────────────────────────────────────── */
.ap-pill {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: rgba(255,255,255,.1);
  border: 1px solid var(--glass-border);
  flex-shrink: 0;
  position: relative;
  cursor: pointer;
  transition: all var(--transition);
}
.ap-pill.on {
  background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1));
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  box-shadow: 0 0 10px var(--pglow2);
}
.ap-pill-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255,255,255,.4);
  transition: all var(--transition);
}
.ap-pill.on .ap-pill-knob {
  left: 21px;
  background: #fff;
}

/* ── Range option ────────────────────────────────────────────────────────── */
.ap-option--range {
  cursor: default;
  align-items: center;
}
.ap-option--range:hover .ap-option-icon {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
}
.ap-range-wrap {
  display: flex; align-items: center; gap: 10px;
  flex-shrink: 0;
}
.ap-range {
  width: 140px;
  accent-color: var(--pl);
  cursor: pointer;
}
.ap-range-val {
  font-size: var(--fs-sm, 12px); font-weight: 700; color: var(--pl-light);
  min-width: 34px; text-align: right;
}

/* ── Segmented control ───────────────────────────────────────────────────── */
.ap-option--select { cursor: default; }
.ap-segmented {
  display: flex;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}
.ap-seg-btn {
  padding: 5px 12px;
  background: color-mix(in srgb, var(--pl) 12%, transparent); border: 1px solid color-mix(in srgb, var(--pl) 25%, transparent);
  color: var(--muted); font-size: var(--fs-sm, 12px); font-weight: 600;
  cursor: pointer; transition: all var(--transition); font-family: inherit;
  white-space: nowrap;
}
.ap-seg-btn + .ap-seg-btn { border-left: 1px solid var(--glass-border); }
.ap-seg-btn:hover:not(:disabled) { background: rgba(255,255,255,.1); color: var(--text); }
.ap-seg-btn.active { background: var(--pl-dim); color: var(--pl-light); }
.ap-seg-btn:disabled { cursor: not-allowed; }

/* ── Mobile ──────────────────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .ap-option { gap: 10px; padding: 10px 10px; }
  .ap-option-icon { width: 26px; height: 26px; border-radius: 6px; }
  .ap-option-icon :deep(svg) { width: 13px; height: 13px; }
  .ap-option-name { font-size: var(--fs-sm, 12px); }
  .ap-option-hint { font-size: var(--fs-xs, 10px); }
  .ap-option-left { gap: var(--space-2, 8px); }
  .ap-range { width: 100px; }
  .ap-range-val { font-size: 11px; min-width: 32px; }
  .ap-seg-btn { padding: 5px 8px; font-size: var(--fs-xs, 10px); }
}
</style>
