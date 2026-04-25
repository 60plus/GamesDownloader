<template>
  <v-text-field
    v-model="model"
    prepend-inner-icon="mdi-magnify"
    placeholder="Search games…"
    density="compact"
    variant="solo-filled"
    flat
    hide-details
    single-line
    clearable
    class="search-bar"
    style="max-width: 300px"
  />
</template>

<script setup lang="ts">
const model = defineModel<string>({ default: "" });
</script>

<style scoped>
.search-bar :deep(.v-field) {
  background: rgba(255, 255, 255, 0.06);
  border-radius: var(--radius-sm, 8px);
}
</style>
