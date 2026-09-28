<script setup lang="ts">
import { session, sessionError } from "@/services/session"
import "@/assets/identity.css"
import AppHeader from '@/components/common/AppHeader.vue'
import ToastHost from '@/components/common/ToastHost.vue'
</script>

<template>
  <div class="app">
    <template v-if="session">
      <AppHeader />
      <p v-if="sessionError" class="identity-error" role="alert">{{ sessionError }}</p>
    </template>

    <main class="app-content">
      <RouterView :key="`${session?.active_workspace_id}-${$route.path}`" />
    </main>
    <ToastHost />
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  background-color: var(--bg-app);
}

.app-content {
  width: 100%;
}
</style>
