import { computed, ref, watch } from 'vue'
type Theme = 'orange' | 'blue' | 'emerald'
type Mode = 'light' | 'dark' | 'system'
const root = document.documentElement
const theme = ref<Theme>((root.dataset.theme as Theme) || 'orange')
const mode = ref<Mode>((root.dataset.appearance as Mode) || 'dark')
const media = matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
const resolvedMode = computed(() => mode.value === 'system' ? (systemDark.value ? 'dark' : 'light') : mode.value)
media.addEventListener('change', event => { systemDark.value = event.matches })
watch([theme, mode, resolvedMode], () => {
  root.dataset.theme = theme.value
  root.dataset.mode = resolvedMode.value
  root.dataset.appearance = mode.value
  try { localStorage.setItem('databridge.appearance', JSON.stringify({ theme: theme.value, mode: mode.value })) } catch { /* Preference still works in memory. */ }
}, { immediate: true })
export const useTheme = () => ({ theme, mode, resolvedMode })
