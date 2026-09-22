<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Info,
} from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    status: 'success' | 'warning' | 'error' | 'info' | 'empty_optional' | 'imported' | string
    label?: string
    showIcon?: boolean
  }>(),
  {
    showIcon: true,
  }
)

const badgeClass = computed(() => {
  switch (props.status) {
    case 'success':
    case 'imported':
      return 'badge-success'
    case 'warning':
      return 'badge-warning'
    case 'error':
      return 'badge-error'
    case 'info':
      return 'badge-info'
    case 'empty_optional':
    default:
      return 'badge-neutral'
  }
})

const displayLabel = computed(() => {
  if (props.label) return props.label
  switch (props.status) {
    case 'empty_optional':
      return 'Optional (Empty)'
    default:
      return props.status.charAt(0).toUpperCase() + props.status.slice(1)
  }
})
</script>

<template>
  <span class="badge" :class="badgeClass">
    <template v-if="showIcon">
      <CheckCircle2 v-if="status === 'success' || status === 'imported'" :size="12" />
      <AlertTriangle v-else-if="status === 'warning'" :size="12" />
      <AlertCircle v-else-if="status === 'error'" :size="12" />
      <Info v-else-if="status === 'info'" :size="12" />
      <HelpCircle v-else-if="status === 'empty_optional'" :size="12" />
    </template>
    <span>{{ displayLabel }}</span>
  </span>
</template>
