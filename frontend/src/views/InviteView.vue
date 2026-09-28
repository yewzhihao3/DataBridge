<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { identityRequest, session } from '@/services/session'
const route = useRoute(), router = useRouter(), error = ref(''), busy = ref(false)
async function accept() {
  busy.value = true; error.value = ''
  try {
    session.value = await identityRequest('/workspaces/invitations/accept', 'POST', { token: route.hash.slice(1) })
    await router.replace('/')
    window.location.reload()
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>
<template>
  <div class="identity-page"><section class="identity-card">
    <p class="eyebrow">DATABRIDGE INVITATION</p><h1>Join your workspace</h1>
    <p class="muted">Sign in with the email address your team invited. Invitations expire after seven days.</p>
    <template v-if="session"><p>Signed in as {{ session.user.email }}</p><button class="btn btn-primary" :disabled="busy" @click="accept">Accept Invitation</button></template>
    <template v-else><RouterLink class="btn btn-primary" :to="`/login${route.hash}`">Log In</RouterLink> <RouterLink class="btn btn-secondary" :to="`/register${route.hash}`">Create an Account</RouterLink></template>
    <p v-if="error" class="identity-error" role="alert">{{ error }}</p>
  </section></div>
</template>
