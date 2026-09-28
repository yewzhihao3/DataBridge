<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { identityRequest, session } from '@/services/session'
import { useTheme } from '@/composables/useTheme'
type Member = { id: number; user_id: number; display_name: string; email: string; role: string }
const tab = ref('Account'), error = ref(''), message = ref(''), busy = ref(false)
const displayName = ref(session.value?.user.display_name ?? '')
const workspace = computed(() => session.value?.workspaces.find(w => w.id === session.value?.active_workspace_id))
const name = ref(workspace.value?.name ?? ''), newWorkspace = ref('')
const admin = computed(() => workspace.value?.role !== 'MEMBER')
const members = ref<Member[]>([]), email = ref(''), role = ref('MEMBER'), invitation = ref('')
const deletionName = ref('')
const currentPassword = ref(''), newPassword = ref('')
const events = ref<{ id: number; action: string; created_at: string }[]>([])
const { theme, mode } = useTheme()
async function run(action: () => Promise<void>) {
  error.value = ''; message.value = ''; busy.value = true
  try { await action(); message.value = 'Saved successfully.' } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
async function loadMembers() { members.value = await identityRequest<Member[]>('/workspaces/current/members') }
async function saveAccount() { await run(async () => { session.value = await identityRequest('/auth/account', 'PATCH', { name: displayName.value }) }) }
async function password() { await run(async () => {
  session.value = await identityRequest('/auth/change-password', 'POST', { current_password: currentPassword.value, new_password: newPassword.value })
  currentPassword.value = ''; newPassword.value = ''
}) }
async function saveWorkspace() { await run(async () => {
  await identityRequest('/workspaces/current', 'PATCH', { name: name.value })
  if (workspace.value) workspace.value.name = name.value
}) }
async function createWorkspace() { await run(async () => {
  await identityRequest('/workspaces', 'POST', { name: newWorkspace.value }); window.location.assign('/')
}) }
async function deleteWorkspace() {
  if (!window.confirm('Permanently delete this workspace and all of its data?')) return
  await run(async () => { await identityRequest('/workspaces/current', 'DELETE', { name: deletionName.value }); window.location.assign('/login') })
}
async function invite() { await run(async () => {
  const result = await identityRequest<{ invitation_url: string }>('/workspaces/current/invitations', 'POST', { email: email.value, role: role.value })
  invitation.value = result.invitation_url
}) }
async function copyInvite() { await run(async () => { await navigator.clipboard.writeText(invitation.value) }); message.value = 'Invitation link copied.' }
async function changeRole(member: Member, value: string) { await run(async () => {
  await identityRequest(`/workspaces/current/members/${member.id}`, 'PATCH', { role: value }); await loadMembers()
}) }
async function remove(member: Member) {
  if (!window.confirm(`Remove ${member.display_name} from this workspace?`)) return
  await run(async () => { await identityRequest(`/workspaces/current/members/${member.id}`, 'DELETE'); await loadMembers() })
}
onMounted(async () => {
  try {
    await loadMembers()
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
    <p v-if="error" class="identity-error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
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
        <form v-if="admin" @submit.prevent="invite"><h2>Invite a teammate</h2><label>Email<input v-model="email" type="email" required></label><label>Role<select v-model="role"><option value="MEMBER">Member</option><option value="ADMIN">Admin</option></select></label><button class="btn btn-primary" :disabled="busy">Create Invitation</button></form>
        <div v-if="invitation"><label>Invitation link<input :value="invitation" readonly @focus="($event.target as HTMLInputElement).select()"></label><button class="btn btn-secondary" @click="copyInvite">Copy Link</button><p class="muted">Share this link with the invited teammate. It expires in seven days.</p></div>
      </template>
      <template v-if="tab === 'Appearance'"><h2>Appearance</h2><form @submit.prevent><label>Theme<select v-model="theme"><option value="orange">Orange</option><option value="blue">Blue</option><option value="emerald">Emerald</option></select></label><label>Appearance<select v-model="mode"><option value="light">Light</option><option value="dark">Dark</option><option value="system">System</option></select></label><p class="muted">Saved on this device.</p></form></template>
      <template v-if="tab === 'Audit'"><h2>Recent workspace activity</h2><p class="muted">Latest 100 events</p><div v-for="event in events" :key="event.id" class="member-row"><strong>{{ event.action.replaceAll('_', ' ') }}</strong><span class="muted">{{ event.created_at }}</span></div></template>
    </section>
  </div>
</template>
