<script setup lang="ts">
import { computed, ref } from 'vue'
import type { BatchImportDetail } from '@/types/api'
const props = defineProps<{ batch: BatchImportDetail; busy: boolean }>()
const emit = defineEmits<{ (e: 'import'): void; (e: 'remove', id: number): void; (e: 'retry'): void; (e: 'review', id: number): void }>()
const filter = ref('all')
const visible = computed(() => filter.value === 'all' ? props.batch.files : props.batch.files.filter(file => file.status === filter.value))
</script>
<template>
  <section class="glass-card batch-review">
    <div class="batch-head"><div><h2>Batch review</h2><p>{{ batch.summary.imported }} imported · {{ batch.summary.review }} need review · {{ batch.summary.duplicate }} duplicate · {{ batch.summary.failed }} failed</p></div><button class="btn btn-primary" :disabled="busy || !batch.summary.ready" @click="emit('import')">Import {{ batch.summary.ready }} Ready Files</button></div>
    <div class="filters" role="group" aria-label="Batch status filters"><button v-for="item in ['all','ready','review','duplicate','failed','imported']" :key="item" :class="{ active: filter === item }" @click="filter = item">{{ item === 'all' ? 'All' : item }}</button></div>
    <div class="table-wrap"><table><thead><tr><th>File</th><th>Detected type</th><th>Processing method</th><th>Status</th><th>Issues</th><th></th></tr></thead><tbody><tr v-for="file in visible" :key="file.id"><td>{{ file.filename }}</td><td>{{ file.detected_type || '—' }}</td><td>{{ file.template_name || file.processing_method || '—' }}</td><td><span class="status" :class="file.status">{{ file.status === 'review' ? 'Needs review' : file.status }}</span></td><td>{{ file.status === 'review' && file.error_message?.includes('warning') ? 'Warnings require confirmation before import.' : file.error_message || file.issues.map(i => i.message).join(' ') || '—' }}</td><td><button v-if="file.status === 'review'" class="btn btn-primary btn-sm" :disabled="busy" @click="emit('review', file.source_file_id)">Review</button><button v-else-if="!['imported','skipped'].includes(file.status)" class="btn btn-secondary btn-sm" :disabled="busy" @click="emit('remove', file.source_file_id)">Remove</button></td></tr></tbody></table></div>
    <button v-if="batch.summary.failed" class="btn btn-secondary" :disabled="busy" @click="emit('retry')">Retry analysis</button>
  </section>
</template>
<style scoped>
.batch-review{padding:1.5rem;display:grid;gap:1rem}.batch-head{display:flex;justify-content:space-between;gap:1rem;align-items:center}.batch-head h2,.batch-head p{margin:0}.batch-head p{color:var(--text-secondary);margin-top:.35rem}.filters{display:flex;gap:.5rem;flex-wrap:wrap}.filters button{padding:.35rem .7rem;border:1px solid var(--border-subtle);border-radius:99px;color:var(--text-secondary)}.filters .active{background:var(--accent-brand-subtle);color:var(--accent-brand);border-color:var(--accent-brand)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:.88rem}th,td{text-align:left;padding:.75rem;border-bottom:1px solid var(--border-subtle);vertical-align:top}th{color:var(--text-muted)}.status{font-weight:700;text-transform:uppercase;font-size:.72rem}.ready,.imported{color:var(--status-success)}.review,.duplicate{color:var(--status-warning)}.failed{color:var(--status-error)}@media(max-width:650px){.batch-head{align-items:stretch;flex-direction:column}}
</style>
