import { ref } from 'vue'

export type ToastType = 'success' | 'info' | 'warning' | 'error'
export type Toast = { id: number; type: ToastType; message: string }
export const toasts = ref<Toast[]>([])
let nextId = 1
function push(type: ToastType, message: string, duration = type === 'error' || type === 'warning' ? 6000 : 4000) {
  const id = nextId++; toasts.value.push({ id, type, message })
  window.setTimeout(() => dismiss(id), duration)
}
function dismiss(id: number) { toasts.value = toasts.value.filter(toast => toast.id !== id) }
export const toast = { success: (message: string) => push('success', message), info: (message: string) => push('info', message), warning: (message: string) => push('warning', message), error: (message: string) => push('error', message), dismiss }
