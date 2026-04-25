<template>
  <v-layout class="main-layout">
    <!-- Top navbar -->
    <v-app-bar flat class="glass-navbar" density="compact">
      <template #prepend>
        <v-app-bar-title class="text-h6 font-weight-bold">
          GamesDownloaderV3
        </v-app-bar-title>
      </template>

      <!-- Nav tabs -->
      <v-tabs v-model="activeTab" class="ml-4" density="compact">
        <v-tab value="library" @click="$router.push('/library')">Library</v-tab>
        <v-tab value="requests" @click="$router.push('/requests')">Requests</v-tab>
      </v-tabs>

      <v-spacer />

      <!-- Search -->
      <search-bar v-model="searchQuery" class="mr-4" />

      <!-- User menu -->
      <user-menu />
    </v-app-bar>

    <!-- Main content -->
    <v-main>
      <v-container fluid class="pa-4">
        <router-view />
      </v-container>
    </v-main>

    <!-- Notifications -->
    <notification-snackbar />
  </v-layout>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useRoute } from "vue-router";
import { useSocketStore } from "@/stores/socket";
import SearchBar from "@/components/common/SearchBar.vue";
import UserMenu from "@/components/common/UserMenu.vue";
import NotificationSnackbar from "@/components/common/NotificationSnackbar.vue";

const route = useRoute();
const socketStore = useSocketStore();
const searchQuery = ref("");
const activeTab = ref("library");

// Connect WebSocket on layout mount
socketStore.connect();

// Sync active tab with route
watch(
  () => route.path,
  (path) => {
    if (path.startsWith("/library")) activeTab.value = "library";
    else if (path.startsWith("/requests")) activeTab.value = "requests";
  },
  { immediate: true }
);
</script>

<style scoped>
.main-layout {
  min-height: 100vh;
}

.glass-navbar {
  background: rgba(26, 26, 46, 0.8) !important;
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(124, 77, 255, 0.15);
}
</style>
