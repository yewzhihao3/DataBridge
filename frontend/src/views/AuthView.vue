<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { identityRequest, session } from '@/services/session'
import { useTheme } from '@/composables/useTheme'
const route = useRoute(), router = useRouter()
const registering = computed(() => route.path === '/register')
const step = ref(1), busy = ref(false), error = ref('')
const displayName = ref(''), email = ref(''), password = ref(''), workspaceName = ref('')
const { theme, mode } = useTheme()
async function submit() {
  if (registering.value && step.value === 1) { step.value = 2; return }
  busy.value = true; error.value = ''
  try {
    session.value = await identityRequest(registering.value ? '/auth/register' : '/auth/login', 'POST', {
      email: email.value, password: password.value,
      ...(registering.value ? { display_name: displayName.value, workspace_name: workspaceName.value } : {}),
    })
    password.value = ''
    await router.replace(route.hash ? `/invite${route.hash}` : '/')
  } catch (e) { error.value = (e as Error).message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="identity-page">
    <div class="identity-brand">DataBridge <span>Workspace intelligence starts here.</span></div>
    <section class="identity-card">
      <p class="eyebrow">{{ registering ? `STEP ${step} OF 2` : 'WELCOME BACK' }}</p>
      <h1>{{ registering ? (step === 1 ? 'Your Account' : 'Your Workspace') : 'Log in to DataBridge' }}</h1>
      <p class="muted">{{ registering ? 'Bring your team and spreadsheet workflows together.' : 'Continue working with your team’s data.' }}</p>
      <form @submit.prevent="submit">
        <template v-if="!registering || step === 1">
          <label v-if="registering">Display Name<input v-model="displayName" required maxlength="100" autocomplete="name"></label>
          <label>Email<input v-model="email" required type="email" maxlength="254" autocomplete="email"></label>
          <label>Password<input v-model="password" required type="password" :minlength="registering ? 12 : 1" maxlength="128" :autocomplete="registering ? 'new-password' : 'current-password'"></label>
          <small v-if="registering" class="muted">Use at least 12 characters.</small>
        </template>
        <template v-else>
          <label>Workspace Name<input v-model="workspaceName" required maxlength="100" placeholder="Northstar Office Solutions" autofocus></label>
          <small class="muted">Use your company, department, or team name.</small>
        </template>
        <p v-if="error" class="identity-error" role="alert">{{ error }}</p>
        <button class="btn btn-primary" :disabled="busy">{{ busy ? 'Please wait…' : registering ? (step === 1 ? 'Continue' : 'Create Account') : 'Log In' }}</button>
        <button v-if="registering && step === 2" type="button" class="btn btn-secondary" @click="step = 1">Back</button>
      </form>
      <p class="muted">{{ registering ? 'Already have an account?' : 'New to DataBridge?' }} <RouterLink :to="`${registering ? '/login' : '/register'}${route.hash}`">{{ registering ? 'Log in' : 'Create an account' }}</RouterLink></p>
    </section>
    <div class="identity-appearance">
      <label>Theme<select v-model="theme"><option value="orange">Orange</option><option value="blue">Blue</option><option value="emerald">Emerald</option></select></label>
      <label>Appearance<select v-model="mode"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
    </div>
  </div>
</template>
