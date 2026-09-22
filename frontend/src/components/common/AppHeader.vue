<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { Database, FileSpreadsheet, History, Layers } from 'lucide-vue-next'

const route = useRoute()
const backendStatus = ref<'online' | 'offline' | 'checking'>('checking')
const appVersion = ref<string>('')

onMounted(async () => {
  try {
    const health = await api.checkHealth()
    backendStatus.value = health.status === 'ok' ? 'online' : 'offline'
    appVersion.value = health.version
  } catch {
    backendStatus.value = 'offline'
  }
})
</script>

<template>
  <header class="app-header">
    <div class="container header-content">
      <!-- Brand / Logo -->
      <router-link to="/" class="brand">
        <div class="logo-icon">
          <Database :size="22" class="text-accent" />
        </div>
        <div class="brand-text">
          <span class="brand-name">DataBridge</span>
          <span class="brand-tag">Data Ingestion Platform</span>
        </div>
      </router-link>

      <!-- Navigation Tabs -->
      <nav class="nav-links">
        <router-link
          to="/"
          class="nav-tab"
          :class="{ active: route.path === '/' }"
        >
          <FileSpreadsheet :size="18" />
          <span>Ingestion Studio</span>
        </router-link>

        <router-link
          to="/history"
          class="nav-tab"
          :class="{ active: route.path === '/history' }"
        >
          <History :size="18" />
          <span>Import History</span>
        </router-link>

        <router-link
          to="/templates"
          class="nav-tab"
          :class="{ active: route.path === '/templates' }"
        >
          <Layers :size="18" />
          <span>Templates</span>
        </router-link>
      </nav>

      <!-- System Health Indicator -->
      <div class="system-status">
        <div
          class="status-dot"
          :class="backendStatus"
          :title="`Backend is ${backendStatus}`"
        ></div>
        <span class="status-label">
          {{ backendStatus === 'online' ? `API Online ${appVersion ? 'v' + appVersion : ''}` : 'API Offline' }}
        </span>
      </div>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  background: rgba(17, 24, 39, 0.85);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 50;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 4.25rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.logo-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  background: var(--accent-brand-subtle);
  border: 1px solid rgba(99, 102, 241, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-brand);
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-name {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.brand-tag {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.nav-links {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--bg-app);
  padding: 0.3rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.nav-tab {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 1rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.nav-tab:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.nav-tab.active {
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--border-medium);
  box-shadow: var(--shadow-sm);
}

.system-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: var(--bg-card);
  padding: 0.35rem 0.75rem;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-subtle);
}

.status-dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
}

.status-dot.online {
  background-color: var(--status-success);
  box-shadow: 0 0 8px var(--status-success);
}

.status-dot.offline {
  background-color: var(--status-error);
  box-shadow: 0 0 8px var(--status-error);
}

.status-dot.checking {
  background-color: var(--status-warning);
}

.status-label {
  font-weight: 500;
}
</style>
