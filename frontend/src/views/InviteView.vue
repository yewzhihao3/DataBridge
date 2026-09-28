<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { identityRequest, logout, session } from '@/services/session'
const route = useRoute(), router = useRouter(), error = ref(''), busy = ref(false)
const invitation = ref<{ email: string; workspace_name: string | null } | null>(null)
const token = computed(() => route.hash.slice(1))
const wrongAccount = computed(() => !!session.value && !!invitation.value && session.value.user.email !== invitation.value.email)
onMounted(async () => {
  if (!token.value) { error.value = 'Invitation link is invalid.'; return }
  try { invitation.value = await identityRequest('/workspaces/invitations/preview', 'POST', { token: token.value }) }
  catch (e) { error.value = (e as Error).message }
})
async function accept() {
  busy.value = true; error.value = ''
  try {
    session.value = await identityRequest('/workspaces/invitations/accept', 'POST', { token: token.value })
    await router.replace('/')
    window.location.reload()
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
async function switchAccount() { await logout() }
</script>
<template>
  <div class="identity-page"><section class="identity-card">
    <p class="eyebrow">DATABRIDGE INVITATION</p><h1>Join your workspace</h1>
    <p class="muted">Sign in with the email address your team invited. Invitations expire after seven days.</p>
    <div v-if="invitation" class="invite-details"><span>You've been invited to join:</span><strong>{{ invitation.workspace_name || 'a DataBridge workspace' }}</strong></div>
    <template v-if="session && wrongAccount"><div class="invite-details"><span>This invitation was sent to:</span><strong>{{ invitation?.email }}</strong><span>You're currently signed in as:</span><strong>{{ session.user.email }}</strong></div><button class="btn btn-primary" @click="switchAccount">Switch Account</button></template>
    <template v-else-if="session"><div class="invite-details"><span>Signed in as:</span><strong>{{ session.user.email }}</strong></div><button class="btn btn-primary" :disabled="busy || !invitation" @click="accept">Accept Invitation</button></template>
    <template v-else><RouterLink class="btn btn-primary" :to="`/login${route.hash}`">Log In</RouterLink> <RouterLink class="btn btn-secondary" :to="`/register${route.hash}`">Create an Account</RouterLink></template>
    <p v-if="error" class="identity-error" role="alert">{{ error }}</p>
  </section></div>
</template>
