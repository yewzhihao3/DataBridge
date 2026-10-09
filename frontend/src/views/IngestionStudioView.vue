<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Clock,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  Plus,
  RotateCcw,
  UploadCloud,
  X,
} from 'lucide-vue-next'
import { api } from '@/services/api'
import { toast } from '@/services/toast'
import {
  useIngestionQueue,
  formatBytes,
  type QueueEntry,
  type QueueStatus,
  type DocType,
  type FileFormat,
  MAX_QUEUE,
  MAX_FILE_MB,
} from '@/composables/useIngestionQueue'
import BatchImportReview from '@/components/ingestion/BatchImportReview.vue'
import type { ImportBatchListItem } from '@/types/api'

// ── Router ─────────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()

// ── Shared Queue State ─────────────────────────────────────────────────────
const {
  queue,
  activeBatch: batch,
  queueSummary,
  addFiles,
  removeEntry,
  clearCompleted,
  retryEntry,
  markFileImported,
} = useIngestionQueue()

const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

// ── Recent Activity ────────────────────────────────────────────────────────
const recentBatches = ref<ImportBatchListItem[]>([])
const recentLoading = ref(false)

async function loadRecent() {
  recentLoading.value = true
  try {
    recentBatches.value = await api.listImportBatches(0, 5)
  } catch {
    /* non-fatal */
  } finally {
    recentLoading.value = false
  }
}

// ── Drag & Drop ────────────────────────────────────────────────────────────
function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function onDragLeave(e: DragEvent) {
  if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
    isDragging.value = false
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  if (e.dataTransfer?.files?.length) {
    addFiles(e.dataTransfer.files)
  }
}

function onFileInputChange(e: Event) {
  const files = (e.target as HTMLInputElement).files
  if (files?.length) {
    addFiles(files)
    ;(e.target as HTMLInputElement).value = ''
  }
}

// ── Navigation to Dedicated Review Workspace ───────────────────────────────
function navigateReview(entry: QueueEntry) {
  if (entry.reviewPath) {
    router.push(entry.reviewPath)
  } else if (entry.format === 'xlsx' && entry.fileId) {
    if (entry.batchId) {
      router.push(`/history/batch/${entry.batchId}/file/${entry.fileId}/review`)
    } else {
      router.push(`/workbooks/${entry.fileId}/review`)
    }
  } else if (entry.documentId) {
    router.push(`/documents/${entry.documentId}/review`)
  }
}

async function handleRemoveEntry(entry: QueueEntry) {
  if (entry.batchId && entry.fileId) {
    try {
      await api.removeBatchFile(entry.batchId, entry.fileId)
    } catch {
      // non-fatal if backend batch is already updated
    }
  }
  removeEntry(entry.id)
}

// ── Batch Operations ───────────────────────────────────────────────────────
const batchBusy = ref(false)

async function importBatchReady() {
  if (!batch.value) return
  batchBusy.value = true
  try {
    batch.value = await api.importReadyFiles(batch.value.id)
    toast.success(`${batch.value.summary.imported} files imported successfully.`)
    if (batch.value.summary.failed) {
      toast.error(`${batch.value.summary.failed} file(s) failed import.`)
    }
    for (const file of batch.value.files) {
      if (file.status === 'imported') {
        markFileImported(file.source_file_id)
      }
    }
  } catch (err: any) {
    toast.error(err?.message || 'Batch import failed.')
  } finally {
    batchBusy.value = false
  }
}

async function removeBatchFile(fileId: number) {
  if (!batch.value) return
  try {
    batch.value = await api.removeBatchFile(batch.value.id, fileId)
    const entry = queue.value.find(e => e.fileId === fileId)
    if (entry) removeEntry(entry.id)
    toast.info('File removed from batch.')
  } catch (err: any) {
    toast.error(err?.message || 'Failed to remove file from batch.')
  }
}

async function retryBatch() {
  if (!batch.value) return
  batchBusy.value = true
  try {
    batch.value = await api.retryBatchAnalysis(batch.value.id)
    toast.info('Batch analysis retried.')
  } catch (err: any) {
    toast.error(err?.message || 'Failed to retry batch analysis.')
  } finally {
    batchBusy.value = false
  }
}

function openBatchReview(fileId: number) {
  if (!batch.value) return
  router.push(`/history/batch/${batch.value.id}/file/${fileId}/review`)
}

async function dismissBatch() {
  if (!batch.value) return
  const batchId = batch.value.id
  batch.value = null
  try {
    await api.deleteBatchImport(batchId)
  } catch {
    // non-fatal
  }
  toast.info('Batch review dismissed.')
}

// ── Mount ──────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Resume from batch deep-link (if navigated via history batch link)
  const sessionId = Number(route.params.sessionId || route.query.batchSession)
  if (sessionId) {
    try {
      batch.value = await api.getBatchImport(sessionId)
    } catch {
      toast.error('That batch session is no longer available.')
    }
  }

  await loadRecent()
})

// ── UI Labels & Helpers ────────────────────────────────────────────────────
const statusLabel: Record<QueueStatus, string> = {
  queued: 'Queued',
  uploading: 'Uploading',
  processing: 'Processing',
  ready: 'Ready',
  needs_review: 'Needs Review',
  imported: 'Imported',
  failed: 'Failed',
}

const typeLabel: Record<DocType, string> = {
  spreadsheet: 'Spreadsheet',
  invoice: 'Invoice',
  receipt: 'Receipt',
  unknown: 'Unknown',
}

function formatIcon(fmt: FileFormat) {
  if (fmt === 'xlsx') return FileSpreadsheet
  if (fmt === 'pdf') return FileText
  return FileImage
}
</script>

<template>
  <main class="ingestion-page container">
    <!-- ── Header ──────────────────────────────────────────────────────── -->
    <section class="page-header">
      <div class="page-header-content">
        <div class="eyebrow">
          <UploadCloud :size="16" />
          SMART INGESTION STUDIO
        </div>
        <h1>Smart Ingestion Studio</h1>
        <p class="page-description">
          Upload, manage, and process workbooks, invoices, and receipts in one central workspace.
        </p>
      </div>

      <div class="header-actions">
        <button
          v-if="queue.length"
          class="btn btn-secondary btn-small"
          type="button"
          @click="clearCompleted"
        >
          <RotateCcw :size="14" />
          Clear Completed
        </button>
      </div>
    </section>

    <!-- ── Universal Upload Zone ───────────────────────────────────────── -->
    <section
      class="upload-zone glass-card"
      :class="{ 'upload-zone--dragging': isDragging }"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <div class="upload-zone-inner" @click="fileInput?.click()">
        <div class="upload-icon-ring">
          <UploadCloud :size="32" />
        </div>
        <div class="upload-copy">
          <p class="upload-primary">Drag &amp; drop your files here</p>
          <p class="upload-secondary">Upload one file or multiple files at once.</p>
        </div>
        <div class="format-pills">
          <span class="format-pill xlsx">XLSX</span>
          <span class="format-pill pdf">PDF</span>
          <span class="format-pill img">JPG</span>
          <span class="format-pill img">PNG</span>
        </div>
        <button
          type="button"
          class="btn btn-primary browse-btn"
          :disabled="queue.length >= MAX_QUEUE"
          @click.stop="fileInput?.click()"
        >
          <Plus :size="16" />
          Browse Files
        </button>
        <p class="upload-limit">Up to {{ MAX_QUEUE }} files · {{ MAX_FILE_MB }} MB per file</p>
      </div>

      <input
        ref="fileInput"
        type="file"
        accept=".xlsx,.pdf,.jpg,.jpeg,.png,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/pdf,image/jpeg,image/png"
        multiple
        class="hidden-input"
        @change="onFileInputChange"
      />
    </section>

    <!-- ── Processing Summary Counters ─────────────────────────────────── -->
    <div v-if="queue.length" class="queue-summary">
      <div class="queue-stat">
        <span class="queue-stat-num">{{ queueSummary.total }}</span>
        <span class="queue-stat-label">Total</span>
      </div>
      <div v-if="queueSummary.uploading" class="queue-stat queue-stat--active">
        <span class="queue-stat-num">{{ queueSummary.uploading }}</span>
        <span class="queue-stat-label">Processing</span>
      </div>
      <div v-if="queueSummary.ready" class="queue-stat queue-stat--ready">
        <span class="queue-stat-num">{{ queueSummary.ready }}</span>
        <span class="queue-stat-label">Ready</span>
      </div>
      <div v-if="queueSummary.needsReview" class="queue-stat queue-stat--review">
        <span class="queue-stat-num">{{ queueSummary.needsReview }}</span>
        <span class="queue-stat-label">Needs Review</span>
      </div>
      <div v-if="queueSummary.imported" class="queue-stat queue-stat--success">
        <span class="queue-stat-num">{{ queueSummary.imported }}</span>
        <span class="queue-stat-label">Imported</span>
      </div>
      <div v-if="queueSummary.failed" class="queue-stat queue-stat--error">
        <span class="queue-stat-num">{{ queueSummary.failed }}</span>
        <span class="queue-stat-label">Failed</span>
      </div>
    </div>

    <!-- ── Upload Queue ────────────────────────────────────────────────── -->
    <section v-if="queue.length" class="glass-card queue-card">
      <div class="queue-header">
        <h2 class="queue-title">Upload Queue</h2>
        <span class="queue-count">{{ queue.length }} file{{ queue.length !== 1 ? 's' : '' }}</span>
      </div>

      <div class="queue-list">
        <div
          v-for="entry in queue"
          :key="entry.id"
          class="queue-row"
          :class="`queue-row--${entry.status}`"
        >
          <!-- Format icon -->
          <div class="queue-file-icon">
            <component :is="formatIcon(entry.format)" :size="20" />
          </div>

          <!-- File info -->
          <div class="queue-file-info">
            <span class="queue-filename" :title="entry.name">{{ entry.name }}</span>
            <div class="queue-meta">
              <span class="format-badge">{{ entry.format.toUpperCase() }}</span>
              <span class="type-badge">{{ typeLabel[entry.suggestedType] }}</span>
              <span class="size-badge">{{ formatBytes(entry.size) }}</span>
            </div>
            <p v-if="entry.error" class="queue-error">{{ entry.error }}</p>
          </div>

          <!-- Status badge -->
          <div class="queue-status-col">
            <div class="queue-status-badge" :class="`status-${entry.status}`">
              <Loader2
                v-if="entry.status === 'uploading' || entry.status === 'processing'"
                :size="12"
                class="animate-spin"
              />
              <CheckCircle2
                v-else-if="entry.status === 'ready' || entry.status === 'imported'"
                :size="12"
              />
              <AlertCircle v-else-if="entry.status === 'failed'" :size="12" />
              <AlertTriangle v-else-if="entry.status === 'needs_review'" :size="12" />
              <Clock v-else-if="entry.status === 'queued'" :size="12" />
              {{ statusLabel[entry.status] }}
            </div>
          </div>

          <!-- Actions -->
          <div class="queue-actions">
            <button
              v-if="entry.status === 'failed' && entry.file"
              class="btn btn-sm btn-secondary retry-btn"
              title="Retry upload"
              @click="retryEntry(entry.id)"
            >
              <RotateCcw :size="12" />
              Retry
            </button>
            <button
              v-else-if="entry.status === 'needs_review' || entry.status === 'ready'"
              class="btn btn-sm btn-primary review-link"
              @click="navigateReview(entry)"
            >
              {{ entry.status === 'ready' ? 'Preview' : 'Review' }}
              <ChevronRight :size="14" />
            </button>
            <button
              v-else-if="entry.status === 'imported'"
              class="btn btn-sm btn-ghost review-link"
              title="View review workspace"
              @click="navigateReview(entry)"
            >
              View
              <ChevronRight :size="14" />
            </button>

            <button
              v-if="entry.status !== 'uploading' && entry.status !== 'processing'"
              class="btn-icon remove-btn"
              :title="`Remove ${entry.name}`"
              @click="handleRemoveEntry(entry)"
            >
              <X :size="14" />
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- ── Batch Import Review (if active batch session exists) ────────── -->
    <BatchImportReview
      v-if="batch"
      :batch="batch"
      :busy="batchBusy"
      @import="importBatchReady"
      @remove="removeBatchFile"
      @retry="retryBatch"
      @review="openBatchReview"
      @dismiss="dismissBatch"
    />

    <!-- ── Recent Activity ─────────────────────────────────────────────── -->
    <section class="glass-card recent-card">
      <div class="recent-header">
        <h2 class="recent-title">Recent Activity</h2>
        <router-link to="/history" class="btn btn-ghost btn-sm">View History</router-link>
      </div>

      <div v-if="recentLoading" class="recent-loading">
        <Loader2 :size="18" class="animate-spin" />
        <span>Loading recent activity…</span>
      </div>

      <p v-else-if="!recentBatches.length" class="recent-empty">
        No imports yet. Upload files above to get started.
      </p>

      <div v-else class="recent-list">
        <div v-for="b in recentBatches" :key="b.id" class="recent-row">
          <div class="recent-info">
            <span class="recent-filename">{{ b.original_filename }}</span>
            <div class="recent-meta">
              <span>{{ b.record_count }} records</span>
              <span v-if="b.warning_count" class="recent-warn">· {{ b.warning_count }} warnings</span>
              <span class="recent-date">· {{ new Date(b.imported_at).toLocaleDateString() }}</span>
            </div>
          </div>
          <router-link to="/history" class="btn btn-ghost btn-sm">
            History
            <ChevronRight :size="13" />
          </router-link>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────── */
.ingestion-page {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  padding-block: 2rem;
  max-width: 1300px;
  margin-inline: auto;
}

/* ── Page Header ─────────────────────────────────────────────────── */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.page-header-content {
  min-width: 0;
}

.eyebrow {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.4rem;
  color: var(--accent-brand);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-header h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.85rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.page-description {
  max-width: 600px;
  margin-top: 0.4rem;
  color: var(--text-secondary);
  font-size: 0.92rem;
  line-height: 1.6;
}

.header-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}

/* ── Upload Zone ─────────────────────────────────────────────────── */
.upload-zone {
  border: 2px dashed var(--border-subtle);
  border-radius: var(--radius-lg, 16px);
  padding: 2.25rem 1.5rem;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--bg-card, rgba(255, 255, 255, 0.02));
}

.upload-zone:hover,
.upload-zone--dragging {
  border-color: var(--accent-brand);
  background: var(--accent-brand-subtle, rgba(249, 115, 22, 0.05));
}

.upload-zone-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.upload-icon-ring {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--accent-brand-subtle, rgba(249, 115, 22, 0.1));
  color: var(--accent-brand);
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-primary {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.upload-secondary {
  margin: 0.2rem 0 0 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.format-pills {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.format-pill {
  font-size: 0.7rem;
  font-weight: 700;
  padding: 0.15rem 0.55rem;
  border-radius: 4px;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.06));
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}

.browse-btn {
  margin-top: 0.25rem;
}

.upload-limit {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.hidden-input {
  display: none;
}

/* ── Queue Summary ───────────────────────────────────────────────── */
.queue-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 0.75rem;
}

.queue-stat {
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md, 8px);
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.queue-stat-num {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--text-primary);
}

.queue-stat-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  text-transform: uppercase;
  font-weight: 700;
  letter-spacing: 0.05em;
}

.queue-stat--active .queue-stat-num {
  color: var(--accent-brand);
}

.queue-stat--ready .queue-stat-num {
  color: #22c55e;
}

.queue-stat--review .queue-stat-num {
  color: #f59e0b;
}

.queue-stat--success .queue-stat-num {
  color: #22c55e;
}

.queue-stat--error .queue-stat-num {
  color: #ef4444;
}

/* ── Queue Card ──────────────────────────────────────────────────── */
.queue-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.queue-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}

.queue-count {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
}

.queue-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.queue-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md, 8px);
  background: var(--bg-subtle, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--border-subtle);
  transition: background 0.15s ease;
}

.queue-row:hover {
  background: var(--bg-card-hover, rgba(255, 255, 255, 0.05));
}

.queue-file-icon {
  color: var(--accent-brand);
  flex-shrink: 0;
}

.queue-file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.queue-filename {
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.queue-meta {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.72rem;
}

.format-badge,
.type-badge,
.size-badge {
  color: var(--text-muted);
}

.queue-error {
  margin: 0.2rem 0 0 0;
  font-size: 0.75rem;
  color: #ef4444;
}

.queue-status-col {
  flex-shrink: 0;
}

.queue-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.05);
}

.status-ready,
.status-imported {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.12);
}

.status-needs_review {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
}

.status-failed {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
}

.status-uploading,
.status-processing {
  color: var(--accent-brand);
  background: rgba(249, 115, 22, 0.12);
}

.queue-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
}

.review-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.35rem;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
}

/* ── Recent Activity ─────────────────────────────────────────────── */
.recent-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.recent-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.recent-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
}

.recent-empty {
  color: var(--text-muted);
  font-size: 0.88rem;
  margin: 0;
}

.recent-loading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.recent-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.6rem 0.8rem;
  border-radius: 6px;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.02));
  border: 1px solid var(--border-subtle);
}

.recent-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.recent-filename {
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--text-primary);
}

.recent-meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.recent-warn {
  color: #f59e0b;
}
</style>
