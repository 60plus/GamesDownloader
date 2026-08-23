<!--
  The little Windows, Apple or Linux mark that sits beside a requirements
  heading. The three glyphs were written out four times over, so a change to
  one of them meant finding the other three.

  Sizing stays with the caller: the GOG detail view draws it large next to a
  per-OS card, everywhere else it is a label-sized mark. The root element keeps
  the gd-req-os-icon class the existing scoped rules already target.
-->
<template>
  <img
    v-if="os === 'linux'"
    src="/icons/os-linux.svg"
    :width="size"
    :height="size"
    alt="Linux"
    class="gd-req-os-icon"
  />
  <svg
    v-else
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="currentColor"
    class="gd-req-os-icon"
    :class="os === 'mac' ? 'gd-req-os-icon--mac' : 'gd-req-os-icon--win'"
  >
    <path
      v-if="os === 'mac'"
      d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z"
    />
    <path
      v-else
      d="M3,12V6.75L9,5.43V11.91L3,12M20,3V11.76L11,12.97V5.38L20,3M3,13L9,13.18V19.83L3,18.35V13M20,13.21V21.72L11,20.5V13.12L20,13.21Z"
    />
  </svg>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ os: 'win' | 'mac' | 'linux'; size?: number }>(), { size: 14 })
</script>
