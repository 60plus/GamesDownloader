<template>
  <component
    :is="type === 'toggle' ? 'label' : 'div'"
    class="ts-option"
    :class="{
      'ts-option--select': type === 'select',
      'ts-option--range': type === 'range',
      'ts-option--sub': sub,
      'ts-option--orb': orb,
      'ts-option--disabled': disabled,
    }"
    @mouseenter="setHint(ts(label), ts(hintBody ?? hint ?? ''))"
    @mouseleave="clearHint()"
  >
    <div class="ts-option-info">
      <span class="ts-option-name">{{ ts(label) }}</span>
      <span v-if="hint" class="ts-option-hint">{{ ts(hint) }}</span>
      <span v-if="unavailable" class="ts-option-na">{{ t('appearance.not_in_theme') }}</span>
    </div>

    <!-- Toggle pill -->
    <div
      v-if="type === 'toggle'"
      class="ts-pill"
      :class="{ on: !!modelValue }"
      @click="emit('update:modelValue', !modelValue)"
    >
      <div class="ts-pill-knob" />
    </div>

    <!-- Select chips -->
    <div v-else-if="type === 'select'" class="ts-chip-row">
      <button
        v-for="(opt, i) in options"
        :key="opt"
        class="ts-chip"
        :class="{ active: String(modelValue) === opt }"
        @click.stop="emit('update:modelValue', opt)"
      >
        {{ ts(optionLabels?.[i] ?? opt) }}
      </button>
    </div>

    <!-- Range slider -->
    <div v-else class="ts-range-wrap">
      <input
        type="range"
        :min="min"
        :max="max"
        :step="step"
        :value="Number(modelValue)"
        @input="emit('update:modelValue', +($event.target as HTMLInputElement).value)"
        class="ts-range"
      />
      <span class="ts-range-val">{{ modelValue }}{{ unit }}</span>
    </div>
  </component>
</template>

<script setup lang="ts">
/**
 * One row on the Appearance page: a name, a short hint, and a control.
 *
 * Every row looked the same but was written out three times - once for the
 * static orb settings, once for the motion ones, once for the rest of the
 * theme's own settings - so a fix to one of them missed the other two.
 * The three built-in switches (animations, orbs, orb motion) are the same row
 * with a value that lives in the store rather than in the theme, so they come
 * through here too and pass their value in from the outside.
 */
import { useSettingsHint } from '@/composables/useSettingsHint'
import { useI18n } from '@/i18n'

defineProps<{
  /** Translation key (or a ready string) for the row's name. */
  label: string
  /** Short line under the name. */
  hint?: string
  /** Body of the hover panel; falls back to `hint`. */
  hintBody?: string
  type: 'toggle' | 'select' | 'range'
  modelValue: unknown
  options?: string[]
  optionLabels?: string[]
  min?: number
  max?: number
  step?: number
  unit?: string
  /** Indented under the switch it depends on. */
  sub?: boolean
  /** Part of the ambient-orb group. */
  orb?: boolean
  /** Greyed out and click-through: the switch it depends on is off. */
  disabled?: boolean
  /** Show the "not drawn by this theme" badge. */
  unavailable?: boolean
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: unknown): void }>()

const { t } = useI18n()
const { setHint, clearHint } = useSettingsHint()

// Theme settings carry their own keys, which a plugin theme may leave
// untranslated - t() falls back to the raw string, so both work.
function ts(val: string): string { return t(val, val) }
</script>

<style scoped>
.ts-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4, 16px);
  padding: 12px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  cursor: pointer;
  transition: background var(--transition);
}
.ts-option:hover { background: var(--glass-highlight); }
.ts-option--sub {
  margin-left: 20px;
  border-left: 2px solid var(--glass-border);
  opacity: 1;
  transition: opacity var(--transition);
}
.ts-option--disabled {
  opacity: 0.4;
  pointer-events: none;
}
.ts-option--orb {
  border-left: 2px solid var(--glass-border);
}
.ts-option-info { display: flex; flex-direction: column; gap: 2px; }
.ts-option-name { font-size: var(--fs-md, 14px); font-weight: 600; color: var(--text); }
.ts-option-na { font-size: 11px; font-weight: 600; color: var(--pl, #a78bfa); opacity: .85; }
.ts-option-hint { font-size: var(--fs-sm, 12px); color: var(--muted); }

/* Range settings */
.ts-option--range {
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-2, 8px);
  cursor: default;
}
.ts-option--range:hover {
  background: var(--glass-bg);
}
.ts-range-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ts-range {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  border-radius: 2px;
  background: var(--glass-border);
  outline: none;
  cursor: pointer;
}
.ts-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  box-shadow: 0 0 8px var(--pglow2);
  cursor: pointer;
  transition: box-shadow var(--transition);
}
.ts-range::-webkit-slider-thumb:hover {
  box-shadow: 0 0 14px var(--pglow);
}
.ts-range-val {
  font-size: var(--fs-sm, 12px);
  font-weight: 700;
  color: var(--pl-light);
  min-width: 40px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* Select chips */
.ts-option--select {
  flex-direction: column;
  align-items: stretch;
  gap: var(--space-2, 8px);
  cursor: default;
}
.ts-option--select:hover { background: var(--glass-bg); }
.ts-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.ts-chip {
  padding: 4px 12px;
  border-radius: var(--radius-pill, 999px);
  border: 1px solid var(--glass-border);
  background: rgba(255,255,255,.05);
  color: var(--muted);
  font-size: var(--fs-sm, 12px);
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.ts-chip:hover { border-color: var(--pl); color: var(--text); }
.ts-chip.active {
  background: var(--pl-dim);
  border-color: var(--pl);
  color: var(--pl-light);
  box-shadow: 0 0 8px var(--pglow2);
}

/* Toggle pill */
.ts-pill {
  width: 40px;
  height: 22px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid var(--glass-border);
  flex-shrink: 0;
  position: relative;
  cursor: pointer;
  transition: all var(--transition);
}
.ts-pill.on {
  background: color-mix(in srgb, var(--pl) 40%, rgba(255,255,255,.1));
  border-color: color-mix(in srgb, var(--pl) 50%, transparent);
  box-shadow: 0 0 10px var(--pglow2);
}
.ts-pill-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(255,255,255,.4);
  transition: all var(--transition);
}
.ts-pill.on .ts-pill-knob {
  left: 21px;
  background: #fff;
}
</style>
