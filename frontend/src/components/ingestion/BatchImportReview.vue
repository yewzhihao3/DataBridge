<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckCircle2, ChevronDown, ChevronRight, ChevronUp, RotateCcw, Trash2, X } from 'lucide-vue-next'
import type { BatchImportDetail } from '@/types/api'

const props = defineProps<{ batch: BatchImportDetail; busy: boolean }>()
const emit = defineEmits<{
  (e: 'import'): void
  (e: 'remove', id: number): void
  (e: 'retry'): void
  (e: 'review', id: number): void
  (e: 'dismiss'): void
}>()

const filter = ref('all')
const isTableExpanded = ref(false)
const visible = computed(() =>
  filter.value === 'all'
    ? props.batch.files
    : props.batch.files.filter(file => file.status === filter.value)
)
</script>

<template>
  <section class="glass-card batch-review">
    <div class="batch-head">
      <div>
        <h2>Batch Review #{{ batch.id }}</h2>
        <p>
          {{ batch.summary.imported }} imported · {{ batch.summary.ready }} ready · {{ batch.summary.review }} need review ·
          {{ batch.summary.duplicate }} duplicate · {{ batch.summary.failed }} failed
        </p>
      </div>
      <div class="batch-actions">
        <button
          v-if="batch.summary.ready"
          class="btn btn-primary btn-sm"
          :disabled="busy"
          @click="emit('import')"
        >
          <CheckCircle2 :size="14" />
          Import {{ batch.summary.ready }} Ready Files
        </button>
        <button
          type="button"
          class="btn btn-secondary btn-sm"
          @click="isTableExpanded = !isTableExpanded"
        >
          <component :is="isTableExpanded ? ChevronUp : ChevronDown" :size="14" />
          {{ isTableExpanded ? 'Hide Details' : 'View File Details' }}
        </button>
        <button
          class="btn btn-ghost btn-sm"
          :disabled="busy"
          title="Dismiss this batch review"
          @click="emit('dismiss')"
        >
          <X :size="14" />
          Dismiss Batch
        </button>
      </div>
    </div>

    <div v-if="isTableExpanded">
      <div class="filters" role="group" aria-label="Batch status filters">
        <button
          v-for="item in ['all', 'ready', 'review', 'duplicate', 'failed', 'imported']"
          :key="item"
          :class="{ active: filter === item }"
          @click="filter = item"
        >
          {{ item === 'all' ? 'All' : item }}
        </button>
      </div>

      <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>File</th>
            <th>Detected type</th>
            <th>Template / Method</th>
            <th>Status</th>
            <th>Issues</th>
            <th class="actions-header">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="file in visible" :key="file.id">
            <td class="file-name-cell">{{ file.filename }}</td>
            <td>{{ file.detected_type || '—' }}</td>
            <td>{{ file.template_name || file.processing_method || '—' }}</td>
            <td>
              <span class="status" :class="file.status">
                {{ file.status === 'review' ? 'Needs review' : file.status }}
              </span>
            </td>
            <td>
              {{
                file.status === 'review' && file.error_message?.includes('warning')
                  ? 'Warnings require confirmation before import.'
                  : file.error_message || file.issues.map(i => i.message).join(' ') || '—'
              }}
            </td>
            <td class="action-cell">
              <button
                v-if="file.status === 'review' || file.status === 'ready'"
                class="btn btn-primary btn-sm"
                :disabled="busy"
                @click="emit('review', file.source_file_id)"
              >
                {{ file.status === 'ready' ? 'Preview' : 'Review' }}
                <ChevronRight :size="13" />
              </button>
              <button
                v-if="file.status !== 'skipped'"
                class="btn btn-secondary btn-sm remove-file-btn"
                :disabled="busy"
                title="Remove file from this batch"
                @click="emit('remove', file.source_file_id)"
              >
                <Trash2 :size="13" />
                Remove
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <div v-if="batch.summary.failed" class="batch-footer">
      <button class="btn btn-secondary btn-sm" :disabled="busy" @click="emit('retry')">
        <RotateCcw :size="13" />
        Retry failed analysis
      </button>
    </div>
  </section>
</template>

<style scoped>
.batch-review {
  padding: 1.5rem;
  display: grid;
  gap: 1rem;
}

.batch-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  flex-wrap: wrap;
}

.batch-head h2,
.batch-head p {
  margin: 0;
}

.batch-head p {
  color: var(--text-secondary);
  margin-top: 0.35rem;
  font-size: 0.88rem;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.filters {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.filters button {
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--border-subtle);
  border-radius: 99px;
  color: var(--text-secondary);
  background: none;
  font-size: 0.8rem;
  cursor: pointer;
  text-transform: capitalize;
}

.filters .active {
  background: var(--accent-brand-subtle);
  color: var(--accent-brand);
  border-color: var(--accent-brand);
  font-weight: 600;
}

.table-wrap {
  overflow: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}

th,
td {
  text-align: left;
  padding: 0.75rem;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

th {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.actions-header {
  text-align: right;
}

.file-name-cell {
  font-weight: 600;
  color: var(--text-primary);
}

.action-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.remove-file-btn {
  color: var(--status-error, #ef4444);
}

.remove-file-btn:hover {
  background: rgba(239, 68, 68, 0.1);
}

.status {
  font-weight: 700;
  text-transform: uppercase;
  font-size: 0.72rem;
  letter-spacing: 0.04em;
}

.ready,
.imported {
  color: var(--status-success, #22c55e);
}

.review,
.duplicate {
  color: var(--status-warning, #f59e0b);
}

.failed {
  color: var(--status-error, #ef4444);
}

.skipped {
  color: var(--text-muted);
}

.batch-footer {
  display: flex;
  justify-content: flex-start;
}

@media (max-width: 650px) {
  .batch-head {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
