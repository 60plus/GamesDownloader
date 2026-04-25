<template>
  <div class="notification-stack">
    <v-snackbar
      v-for="n in notifications"
      :key="n.id"
      :model-value="true"
      :color="n.type"
      :timeout="n.timeout"
      location="bottom right"
      @update:model-value="remove(n.id)"
    >
      {{ n.message }}
      <template #actions>
        <v-btn variant="text" size="small" @click="remove(n.id)">Close</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { useNotifications } from "@/composables/useNotifications";

const { notifications, remove } = useNotifications();
</script>
