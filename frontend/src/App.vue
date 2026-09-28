<script setup lang="ts">
import { session, sessionError, switchWorkspace, logout } from "@/services/session"
import "@/assets/identity.css"
import AppHeader from '@/components/common/AppHeader.vue'
</script>

<template>
  <div class="app">
    <template v-if="session">
      <AppHeader />
      <div class="account-bar">
        <label for="workspace-switch">Workspace</label>
        <select id="workspace-switch" class="workspace-select" :value="session.active_workspace_id" @change="switchWorkspace(Number(($event.target as HTMLSelectElement).value))">
          <option v-for="workspace in session.workspaces" :key="workspace.id" :value="workspace.id">{{ workspace.name }}</option>
        </select>
        <RouterLink to="/settings">{{ session.user.display_name }} · Settings</RouterLink>
        <button class="btn btn-secondary btn-sm" @click="logout">Log Out</button>
      </div>
      <p v-if="sessionError" class="identity-error" role="alert">{{ sessionError }}</p>
    </template>

    <main class="app-content">
      <RouterView :key="`${session?.active_workspace_id}-${$route.path}`" />
    </main>
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
