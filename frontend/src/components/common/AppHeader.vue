<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { logout, session, switchWorkspace } from '@/services/session'
import { ChartColumn, Database, Download, FileSpreadsheet, History, Layers, TableProperties } from 'lucide-vue-next'

const route = useRoute()
const userMenu = ref<HTMLDetailsElement | null>(null)
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
function closeOnOutsideClick(event: MouseEvent) {
  if (userMenu.value && !userMenu.value.contains(event.target as Node)) userMenu.value.removeAttribute('open')
}
onMounted(() => document.addEventListener('click', closeOnOutsideClick))
onBeforeUnmount(() => document.removeEventListener('click', closeOnOutsideClick))
</script>

<template>
  <header class="app-header">
    <div class="container header-content">
      <router-link to="/" class="brand">
        <div class="logo-icon">
          <Database :size="22" class="text-accent" />
        </div>
        <div class="brand-text">
          <span class="brand-name">DataBridge</span>
        </div>
      </router-link>

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

      <div class="system-status">
        <div
          class="status-dot"
          :class="backendStatus"
          :title="`Backend is ${backendStatus}`"
        ></div>
      </div>
      <div v-if="session" class="header-actions">
        <label class="sr-only" for="workspace-switch">Workspace</label>
        <select id="workspace-switch" class="workspace-select" :value="session.active_workspace_id" @change="switchWorkspace(Number(($event.target as HTMLSelectElement).value))">
          <option v-for="workspace in session.workspaces" :key="workspace.id" :value="workspace.id">{{ workspace.name }}</option>
        </select>
        <details ref="userMenu" class="user-menu" @keydown.esc="userMenu?.removeAttribute('open')">
          <summary :aria-label="`Account menu for ${session.user.display_name}`">{{ session.user.display_name }} <span aria-hidden="true">▾</span></summary>
          <div class="user-menu-panel" role="menu">
            <strong>{{ session.user.display_name }}</strong><span>{{ session.user.email }}</span>
            <hr><router-link to="/settings" role="menuitem" @click="userMenu?.removeAttribute('open')">Settings</router-link>
            <button role="menuitem" @click="logout">Log Out</button>
          </div>
        </details>
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
  flex-shrink: 0;
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

.header-actions { margin-left: auto; display: flex; align-items: center; gap: .5rem; min-width: 0; }
.user-menu { position: relative; flex-shrink: 0; }
.user-menu summary { list-style: none; cursor: pointer; padding: .55rem .7rem; border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); color: var(--text-primary); font-weight: 600; white-space: nowrap; }
.user-menu summary::-webkit-details-marker { display: none; }
.user-menu-panel { position: absolute; right: 0; top: calc(100% + .5rem); width: 230px; padding: .85rem; display: grid; gap: .45rem; border: 1px solid var(--border-default); background: var(--bg-surface); border-radius: var(--radius-md); box-shadow: var(--shadow); z-index: 60; }
.user-menu-panel span { color: var(--text-muted); font-size: .82rem; overflow-wrap: anywhere; }.user-menu-panel hr { width: 100%; border: 0; border-top: 1px solid var(--border-subtle); margin: .25rem 0; }.user-menu-panel a, .user-menu-panel button { text-align: left; padding: .55rem; border-radius: var(--radius-sm); color: var(--text-primary); font: inherit; }.user-menu-panel a:hover, .user-menu-panel button:hover { background: var(--bg-elevated); }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
.nav-tab { white-space: nowrap; border: 1px solid transparent; padding-inline: .65rem; }
@media (max-width: 1450px) { .system-status { display: none; } }
/* Keep primary destinations reachable as the navigation grows. */
@media (max-width: 1200px) {
  .header-content { height: auto; min-height: 4.25rem; flex-wrap: wrap; padding-top: .6rem; padding-bottom: .6rem; gap: .7rem; }
  .nav-links { order: 3; width: 100%; min-width: 0; overflow-x: auto; }
  .nav-tab { flex-shrink: 0; }
}
@media (max-width: 600px) { .header-content { padding-inline: 1rem; } .brand-text { display: none; } .workspace-select { max-width: 150px; } .user-menu summary { max-width: 115px; overflow: hidden; text-overflow: ellipsis; } }
</style>
