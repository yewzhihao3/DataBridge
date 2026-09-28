<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { ChartColumn, Database, Download, FileSpreadsheet, History, Layers, TableProperties } from 'lucide-vue-next'

const route = useRoute()
const { theme, mode } = useTheme()
const appearance = ref<HTMLDetailsElement | null>(null)
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
      <nav class="nav-links" aria-label="Main navigation">
        <router-link
          to="/"
          class="nav-tab"
          :class="{ active: route.path === '/' }"
        >
          <FileSpreadsheet :size="18" />
          <span>Ingest</span>
        </router-link>

        <router-link
          to="/templates"
          class="nav-tab"
          :class="{ active: route.path === '/templates' }"
        >
          <Layers :size="18" />
          <span>Templates</span>
        </router-link>

        <router-link
          to="/history"
          class="nav-tab"
          :class="{ active: route.path === '/history' }"
        >
          <History :size="18" />
          <span>History</span>
        </router-link>

        <router-link
          to="/explorer"
          class="nav-tab"
          :class="{ active: route.path.startsWith('/explorer') }"
        >
          <TableProperties :size="18" />
          <span>Explorer</span>
        </router-link>

        <router-link
          to="/exports"
          class="nav-tab"
          :class="{ active: route.path.startsWith('/exports') }"
        >
          <Download :size="18" />
          <span>Export</span>
        </router-link>
        <router-link to="/dashboard" class="nav-tab" :class="{ active: route.path === '/dashboard' }">
          <ChartColumn :size="18" />
          <span>Dashboard</span>
        </router-link>
      </nav>

      <!-- System Health Indicator -->
      <details ref="appearance" class="appearance" @keydown.esc="appearance?.removeAttribute('open')">
        <summary>Appearance</summary>
        <div class="appearance-panel">
          <label for="theme-family">Theme</label>
          <select id="theme-family" v-model="theme" class="custom-select">
            <option value="orange">Orange</option><option value="blue">Blue</option><option value="emerald">Emerald</option>
          </select>
          <label for="appearance-mode">Mode</label>
          <select id="appearance-mode" v-model="mode" class="custom-select">
            <option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option>
          </select>
        </div>
      </details>
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
  background: var(--bg-surface);
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
  gap: .8rem;
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
  border: 1px solid var(--accent-border);
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
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  text-decoration: underline;
  text-underline-offset: .35em;
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
}

.status-dot.offline {
  background-color: var(--status-error);
}

.status-dot.checking {
  background-color: var(--status-warning);
}

.status-label {
  font-weight: 500;
}
.appearance { position: relative; flex-shrink: 0; font-size: .8rem; }
.appearance summary { cursor: pointer; padding: .55rem; border: 1px solid var(--border-default); border-radius: var(--radius-sm); }
.appearance-panel { position: absolute; right: 0; top: calc(100% + .6rem); width: 210px; padding: 1rem; display: grid; gap: .5rem; border: 1px solid var(--border-default); background: var(--bg-surface); border-radius: var(--radius-md); box-shadow: var(--shadow); z-index: 60; }
.appearance-panel select { width: 100%; padding: .5rem; border: 1px solid var(--border-default); border-radius: var(--radius-sm); background: var(--bg-input); color: var(--text-primary); }
.nav-tab { white-space: nowrap; border: 1px solid transparent; padding-inline: .65rem; }
@media (max-width: 1450px) { .system-status { display: none; } }
/* Keep primary destinations reachable as the navigation grows. */
@media (max-width: 1200px) {
  .header-content { height: auto; min-height: 4.25rem; flex-wrap: wrap; padding-top: .6rem; padding-bottom: .6rem; gap: .7rem; }
  .nav-links { order: 3; width: 100%; min-width: 0; overflow-x: auto; }
  .nav-tab { flex-shrink: 0; }
}
</style>
