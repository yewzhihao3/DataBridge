<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { identityRequest, session } from '@/services/session'
import { useTheme } from '@/composables/useTheme'
import { toast } from '@/services/toast'
type Member = { id: number; user_id: number; display_name: string; email: string; role: string }
type Invitation = { id: number; email: string; role: string; status: 'PENDING' | 'ACCEPTED' | 'EXPIRED'; created_at: string; expires_at: string; invited_by: string | null }
const tab = ref('Account'), error = ref(''), busy = ref(false)
const displayName = ref(session.value?.user.display_name ?? '')
const workspace = computed(() => session.value?.workspaces.find(w => w.id === session.value?.active_workspace_id))
const name = ref(workspace.value?.name ?? ''), newWorkspace = ref('')
const admin = computed(() => workspace.value?.role !== 'MEMBER')
const members = ref<Member[]>([]), email = ref(''), role = ref('MEMBER'), invitations = ref<Invitation[]>([])
const deletionName = ref('')
const currentPassword = ref(''), newPassword = ref('')
const events = ref<{ id: number; action: string; created_at: string }[]>([])
const { theme, mode } = useTheme()
async function run(action: () => Promise<void>) {
  error.value = ''; busy.value = true
  try { await action() } catch (e) { error.value = (e as Error).message; toast.error(error.value) }
  finally { busy.value = false }
}
async function loadMembers() { members.value = await identityRequest<Member[]>('/workspaces/current/members') }
async function loadInvitations() { if (admin.value) invitations.value = await identityRequest<Invitation[]>('/workspaces/current/invitations') }
async function saveAccount() { await run(async () => { session.value = await identityRequest('/auth/account', 'PATCH', { name: displayName.value }); toast.success('Account updated') }) }
async function password() { await run(async () => {
  session.value = await identityRequest('/auth/change-password', 'POST', { current_password: currentPassword.value, new_password: newPassword.value })
  currentPassword.value = ''; newPassword.value = ''
  toast.success('Password changed')
}) }
async function saveWorkspace() { await run(async () => {
  await identityRequest('/workspaces/current', 'PATCH', { name: name.value })
  if (workspace.value) workspace.value.name = name.value
  toast.success('Workspace updated')
}) }
async function createWorkspace() { await run(async () => {
  await identityRequest('/workspaces', 'POST', { name: newWorkspace.value }); toast.success('Workspace created'); window.location.assign('/')
}) }
async function deleteWorkspace() {
  if (!window.confirm('Permanently delete this workspace and all of its data?')) return
  await run(async () => { await identityRequest('/workspaces/current', 'DELETE', { name: deletionName.value }); window.location.assign('/login') })
}
async function invite() { await run(async () => {
  const result = await identityRequest<{ invitation_url: string }>('/workspaces/current/invitations', 'POST', { email: email.value, role: role.value })
  email.value = ''; role.value = 'MEMBER'; await navigator.clipboard.writeText(result.invitation_url); await loadInvitations(); toast.success('Invitation created and link copied')
}) }
async function copyInvite(invitation: Invitation) { await run(async () => { const result = await identityRequest<{ invitation_url: string }>(`/workspaces/current/invitations/${invitation.id}/regenerate`, 'POST'); await navigator.clipboard.writeText(result.invitation_url); await loadInvitations(); toast.success('Invitation link refreshed and copied') }) }
async function refreshInvitation(invitation: Invitation) { await copyInvite(invitation) }
async function changeRole(member: Member, value: string) { await run(async () => {
  await identityRequest(`/workspaces/current/members/${member.id}`, 'PATCH', { role: value }); await loadMembers(); toast.success('Member role updated')
}) }
async function remove(member: Member) {
  if (!window.confirm(`Remove ${member.display_name} from this workspace?`)) return
  await run(async () => { await identityRequest(`/workspaces/current/members/${member.id}`, 'DELETE'); await loadMembers(); toast.success('Member removed') })
}
onMounted(async () => {
  try {
    await loadMembers()
    await loadInvitations()
    if (admin.value) events.value = await identityRequest('/workspaces/current/audit')
  } catch (e) { error.value = (e as Error).message }
})
</script>
<template>
  <div class="settings-layout">
    <p class="eyebrow">YOUR DATABRIDGE</p><h1>Settings</h1>
    <nav class="settings-tabs" aria-label="Settings sections">
      <button v-for="item in ['Account', 'Workspace', 'Members', 'Appearance', ...(admin ? ['Audit'] : [])]" :key="item" class="btn" :class="tab === item ? 'btn-primary' : 'btn-secondary'" @click="tab = item">{{ item }}</button>
    </nav>
    <p v-if="error" class="identity-error" role="alert">{{ error }}</p>
    <section class="settings-panel">
      <template v-if="tab === 'Account'">
        <h2>Account</h2><p class="muted">{{ session?.user.email }}</p>
        <form @submit.prevent="saveAccount"><label>Display Name<input v-model="displayName" required maxlength="100"></label><button class="btn btn-primary" :disabled="busy">Save Account</button></form>
        <h2>Change password</h2><p class="muted">Changing your password signs out your other sessions.</p>
        <form @submit.prevent="password"><label>Current Password<input v-model="currentPassword" required type="password" autocomplete="current-password"></label><label>New Password<input v-model="newPassword" required type="password" minlength="12" maxlength="128" autocomplete="new-password"></label><button class="btn btn-primary" :disabled="busy">Change Password</button></form>
      </template>
      <template v-if="tab === 'Workspace'">
        <h2>Workspace</h2><p class="muted">{{ workspace?.slug }} · {{ workspace?.role }}</p>
        <form v-if="admin" @submit.prevent="saveWorkspace"><label>Workspace Name<input v-model="name" required maxlength="100"></label><button class="btn btn-primary" :disabled="busy">Save Workspace</button></form>
        <p v-else class="muted">An owner or administrator can change workspace settings.</p>
        <form v-if="workspace?.role === 'OWNER'" @submit.prevent="deleteWorkspace"><h2>Delete workspace</h2><p class="muted">This permanently deletes this workspace and its files, imports, templates, and audit history. Create another workspace first if this is your only one.</p><label>Type {{ workspace.name }} to confirm<input v-model="deletionName" required></label><button class="btn btn-secondary" :disabled="busy || deletionName !== workspace.name">Delete Workspace</button></form>
        <h2>Create another workspace</h2><form @submit.prevent="createWorkspace"><label>Workspace Name<input v-model="newWorkspace" required maxlength="100"></label><button class="btn btn-secondary" :disabled="busy">Create Workspace</button></form>
      </template>
      <template v-if="tab === 'Members'">
        <h2>Members</h2>
        <div v-for="member in members" :key="member.id" class="member-row">
          <div class="member-name"><strong>{{ member.display_name }}</strong><p class="muted">{{ member.email }}</p></div>
          <select v-if="admin && (member.role !== 'OWNER' || workspace?.role === 'OWNER')" :value="member.role" :aria-label="`Role for ${member.display_name}`" @change="changeRole(member, ($event.target as HTMLSelectElement).value)"><option v-if="workspace?.role === 'OWNER'" value="OWNER">Owner</option><option value="ADMIN">Admin</option><option value="MEMBER">Member</option></select>
          <span v-else>{{ member.role }}</span>
          <button v-if="admin && member.user_id !== session?.user.id && (member.role !== 'OWNER' || workspace?.role === 'OWNER')" class="btn btn-secondary" :disabled="busy" @click="remove(member)">Remove</button>
        </div>
        <template v-if="admin"><div class="invitation-heading"><h2>Invitations</h2><button class="btn btn-secondary" :disabled="busy" @click="loadInvitations">Refresh</button></div><div class="invitation-table"><div class="invitation-row invitation-columns"><strong>Email</strong><strong>Role</strong><strong>Status</strong><strong>Expires</strong><strong>Invited by</strong><strong>Actions</strong></div><div v-for="item in invitations" :key="item.id" class="invitation-row"><span>{{ item.email }}</span><span>{{ item.role }}</span><span class="invitation-status" :class="item.status.toLowerCase()">{{ item.status }}</span><span>{{ item.status === 'ACCEPTED' ? '—' : new Date(item.expires_at).toLocaleDateString() }}</span><span>{{ item.invited_by || '—' }}</span><span><button v-if="item.status === 'PENDING'" class="table-action" @click="refreshInvitation(item)">Refresh &amp; Copy</button><span v-else>—</span></span></div></div><form @submit.prevent="invite"><h2>Invite a teammate</h2><label>Email<input v-model="email" type="email" required></label><label>Role<select v-model="role"><option value="MEMBER">Member</option><option value="ADMIN">Admin</option></select></label><button class="btn btn-primary" :disabled="busy">Create Invitation</button></form></template>
      </template>
      <template v-if="tab === 'Appearance'"><h2>Appearance</h2><form @submit.prevent><label>Theme<select v-model="theme"><option value="orange">Orange</option><option value="blue">Blue</option><option value="emerald">Emerald</option></select></label><label>Appearance<select v-model="mode"><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label><p class="muted">Saved on this device.</p></form></template>
      <template v-if="tab === 'Audit'"><h2>Recent workspace activity</h2><p class="muted">Latest 100 events</p><div v-for="event in events" :key="event.id" class="member-row"><strong>{{ event.action.replaceAll('_', ' ') }}</strong><span class="muted">{{ event.created_at }}</span></div></template>
    </section>
  </div>
</template>
