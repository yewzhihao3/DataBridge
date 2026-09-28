import { ref } from 'vue'

export interface Workspace { id: number; name: string; slug: string; role: 'OWNER' | 'ADMIN' | 'MEMBER' }
export interface SessionState {
  user: { id: number; email: string; display_name: string }
  workspaces: Workspace[]
  active_workspace_id: number
  csrf_token: string
}
export const session = ref<SessionState | null>(null)
export const sessionError = ref('')
let restoration: Promise<void> | undefined

export function sessionHeaders(): Record<string, string> {
  return session.value ? { 'X-CSRF-Token': session.value.csrf_token, 'X-Workspace-ID': String(session.value.active_workspace_id) } : {}
}

export async function identityRequest<T = SessionState>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method, credentials: 'include', headers: { 'Content-Type': 'application/json', ...sessionHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = response.status === 204 ? null : await response.json()
  if (!response.ok) {
    if (response.status === 401) session.value = null
    throw new Error(typeof data?.detail === 'string' ? data.detail : 'Please check your details and try again.')
  }
  return data as T
}

export function restoreSession() {
  return restoration ??= identityRequest('/auth/me').then(value => { session.value = value }).catch(() => { session.value = null })
}

export async function logout() {
  sessionError.value = ''
  try {
    await identityRequest('/auth/logout', 'POST')
    session.value = null
    window.location.assign('/login')
  } catch (error) {
    if (!session.value) window.location.assign('/login')
    else sessionError.value = (error as Error).message
  }
}

export async function switchWorkspace(id: number) {
  sessionError.value = ''
  try {
    await identityRequest(`/workspaces/${id}/switch`, 'POST')
    // Full document reload clears workflow drafts, requests, modals and all caches.
    window.location.assign('/')
  } catch (error) { sessionError.value = (error as Error).message }
}
