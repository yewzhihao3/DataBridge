<script setup lang="ts">
import AppHeader from '@/components/common/AppHeader.vue'
</script>

<template>
  <div class="app">
    <AppHeader />

    <main class="app-content">
      <RouterView />
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