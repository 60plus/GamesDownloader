<template>
  <!-- The game's manual, a PDF kept beside the game in its extras. Shared by
       every theme: Modern and Neon Horizon through the core ROM page, Classic
       through its layout, Vapor through the global registration in main.ts.

       Compact is the icon alone, for a row of icon buttons (Classic's, beside
       the cover): the host's own class styles it then, and the label moves to
       the tooltip and to what a screen reader announces. -->
  <button
    v-if="romId && available"
    type="button"
    :class="compact ? null : 'gd-manual-btn'"
    :title="t('detail.manual_hint')"
    :aria-label="t('detail.manual')"
    :disabled="opening"
    @click="openManual"
  >
    <svg :width="compact ? 16 : 14" :height="compact ? 16 : 14" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
         aria-hidden="true">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
    </svg>
    <span v-if="!compact">{{ t('detail.manual') }}</span>
  </button>
</template>

<script setup lang="ts">
import { ref } from "vue";
import client from "@/services/api/client";
import { useDialog } from "@/composables/useDialog";
import { useI18n } from "@/i18n";

const props = defineProps<{ romId?: number | null; available?: boolean; compact?: boolean }>();
const { t } = useI18n();
const { gdAlert } = useDialog();
const opening = ref(false);

// The manual lives in the ROM tree, which nothing serves by path, and opening
// it is a navigation - no Authorization header rides along. So the button asks
// for a short-lived ticket over the authenticated connection first and opens
// that, exactly as the ROM download does.
async function openManual(): Promise<void> {
  if (!props.romId || opening.value) return;
  opening.value = true;
  try {
    const { data } = await client.post(`/roms/${props.romId}/manual-ticket`);
    window.open(data.url, "_blank", "noopener");
  } catch {
    gdAlert(t("detail.manual_failed"));
  } finally {
    opening.value = false;
  }
}
</script>

<style scoped>
/* Glass, like the rest of the controls: the theme's own accent, mixed in. */
.gd-manual-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  padding: 8px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid color-mix(in srgb, var(--pl) 40%, transparent);
  background: color-mix(in srgb, var(--pl) 20%, transparent);
  color: var(--pl-light, #fff);
  font: inherit; font-size: 13px; font-weight: 600;
  transition: background .15s, border-color .15s, color .15s;
}
.gd-manual-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--pl) 30%, transparent);
  border-color: color-mix(in srgb, var(--pl) 55%, transparent);
  color: #fff;
}
.gd-manual-btn:disabled { opacity: .6; cursor: default; }
.gd-manual-btn:focus-visible {
  outline: 2px solid var(--pl-light, #fff);
  outline-offset: 2px;
}
</style>
