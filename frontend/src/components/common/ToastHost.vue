<script setup lang="ts">
import { toasts, toast } from '@/services/toast'
</script>
<template><div class="toast-host" aria-live="polite" aria-relevant="additions"><div v-for="item in toasts" :key="item.id" class="toast" :class="item.type" :role="item.type === 'error' ? 'alert' : 'status'"><span>{{ item.message }}</span><button type="button" :aria-label="`Dismiss: ${item.message}`" @click="toast.dismiss(item.id)">×</button></div></div></template>
<style scoped>
.toast-host { position: fixed; right: 1.25rem; bottom: 1.25rem; display: grid; gap: .65rem; width: min(360px, calc(100vw - 2rem)); z-index: 200; pointer-events: none; }.toast { pointer-events: auto; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 1rem; background: var(--bg-surface); border: 1px solid var(--border-subtle); border-left: 4px solid var(--info); color: var(--text-primary); border-radius: var(--radius-md); box-shadow: var(--shadow); }.toast.success { border-left-color: var(--success); }.toast.warning { border-left-color: var(--warning); }.toast.error { border-left-color: var(--danger); }.toast button { color: var(--text-primary); font-size: 1.35rem; line-height: 1; padding: .1rem .3rem; } @media(max-width: 600px) { .toast-host { left: 1rem; right: 1rem; bottom: 1rem; width: auto; } }
</style>
