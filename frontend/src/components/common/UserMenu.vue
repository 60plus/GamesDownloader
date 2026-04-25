<template>
  <v-menu offset-y>
    <template #activator="{ props }">
      <v-btn icon v-bind="props" size="small">
        <v-avatar size="32" color="primary">
          <span class="text-body-2">{{ initials }}</span>
        </v-avatar>
      </v-btn>
    </template>
    <v-list density="compact" class="glass-menu">
      <v-list-item @click="$router.push('/settings')">
        <template #prepend><v-icon>mdi-cog</v-icon></template>
        <v-list-item-title>Settings</v-list-item-title>
      </v-list-item>
      <v-divider />
      <v-list-item @click="handleLogout">
        <template #prepend><v-icon>mdi-logout</v-icon></template>
        <v-list-item-title>Logout</v-list-item-title>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

const initials = computed(() => {
  const name = (auth.user?.username as string) || "?";
  return name.slice(0, 2).toUpperCase();
});

function handleLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.glass-menu {
  background: rgba(26, 26, 46, 0.95) !important;
  backdrop-filter: blur(12px);
}
</style>
