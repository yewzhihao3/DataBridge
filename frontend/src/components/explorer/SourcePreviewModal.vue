<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import {
  X,
  FileSpreadsheet,
  Download,
  AlertCircle,
  ExternalLink,
  FileText,
  Layers,
} from 'lucide-vue-next'
import { api } from '@/services/api'
import type { WorksheetPreviewResponse } from '@/types/api'

const props = defineProps<{
  isOpen: boolean
  sourceFileId?: number | null
  filename?: string | null
  mediaType?: string | null
  initialWorksheet?: string | null
  batchId?: number | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const isLoading = ref(false)
const error = ref('')
const availableSheets = ref<string[]>([])
const selectedSheet = ref('')
const previewRows = ref<any[][]>([])
const previewMeta = ref<{ totalRows: number; totalCols: number } | null>(null)
const isDownloading = ref(false)
const downloadMessage = ref('')

const isDocument = computed(() => {
  if (props.mediaType) {
    return props.mediaType.startsWith('image/') || props.mediaType === 'application/pdf'
  }
  if (props.filename) {
    const ext = props.filename.toLowerCase().split('.').pop()
    if (ext && ['pdf', 'jpg', 'jpeg', 'png', 'webp'].includes(ext)) return true
    if (ext === 'xlsx') return false
  }
  if (props.initialWorksheet === 'Document') return true
  return false
})

const documentBlobUrl = ref<string | null>(null)
const documentMediaType = ref<string | null>(null)

const isImage = computed(() => {
  if (documentMediaType.value) {
    return documentMediaType.value.startsWith('image/')
  }
  if (props.mediaType) {
    return props.mediaType.startsWith('image/')
  }
  if (props.filename) {
    const ext = props.filename.toLowerCase().split('.').pop()
    if (ext && ['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp'].includes(ext)) return true
  }
  return false
})

watch(
  () => [props.isOpen, props.sourceFileId, props.initialWorksheet],
  async ([open]) => {
    if (!open || !props.sourceFileId) {
      resetState()
      return
    }
    await initializePreview()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (documentBlobUrl.value) {
    URL.revokeObjectURL(documentBlobUrl.value)
    documentBlobUrl.value = null
  }
})

function resetState() {
  if (documentBlobUrl.value) {
    URL.revokeObjectURL(documentBlobUrl.value)
    documentBlobUrl.value = null
  }
  documentMediaType.value = null
  isLoading.value = false
  error.value = ''
  availableSheets.value = []
  selectedSheet.value = ''
  previewRows.value = []
  previewMeta.value = null
  isDownloading.value = false
  downloadMessage.value = ''
}

async function initializePreview() {
  if (!props.sourceFileId) return
  resetState()

  // If document (PDF / image), fetch authenticated binary and display via managed blob URL
  if (isDocument.value) {
    isLoading.value = true
    try {
      const blob = await api.getDocumentPreview(props.sourceFileId)
      documentMediaType.value = blob.type || props.mediaType || null
      documentBlobUrl.value = URL.createObjectURL(blob)
    } catch (err: any) {
      error.value = 'Preview is unavailable for this document. You can download the original file instead.'
    } finally {
      isLoading.value = false
    }
    return
  }

  isLoading.value = true
  try {
    const fileInfo = await api.getFile(props.sourceFileId)
    availableSheets.value = fileInfo.sheet_names || []

    const candidate = props.initialWorksheet?.trim() || ''
    if (candidate && candidate !== 'Document' && availableSheets.value.includes(candidate)) {
      selectedSheet.value = candidate
      await loadSheetPreview(candidate)
    } else if (availableSheets.value.length === 1 && candidate === '') {
      // If exactly 1 worksheet and no metadata was given, use that single worksheet
      selectedSheet.value = availableSheets.value[0]
      await loadSheetPreview(availableSheets.value[0])
    } else if (availableSheets.value.length > 0) {
      // Multiple worksheets exist and no valid source sheet can be determined
      error.value = 'Select a worksheet to preview.'
      isLoading.value = false
    } else {
      error.value = 'Preview is unavailable. Download the original file instead.'
      isLoading.value = false
    }
  } catch (err: any) {
    isLoading.value = false
    if (err.message && err.message.includes('404')) {
      error.value = 'This source file is no longer available.'
    } else {
      error.value = 'Preview is unavailable. Download the original file instead.'
    }
  }
}

async function loadSheetPreview(sheetName: string) {
  if (!props.sourceFileId || !sheetName) return
  isLoading.value = true
  error.value = ''
  try {
    const preview: WorksheetPreviewResponse = await api.getFilePreview(
      props.sourceFileId,
      sheetName,
      25,
      15,
    )
    previewRows.value = preview.rows || []
    previewMeta.value = {
      totalRows: preview.total_rows_returned,
      totalCols: preview.total_cols_returned,
    }
  } catch (err: any) {
    previewRows.value = []
    previewMeta.value = null
    if (err.message && err.message.includes('404')) {
      error.value = 'This source file is no longer available.'
    } else {
      error.value = 'Preview is unavailable. Download the original file instead.'
    }
  } finally {
    isLoading.value = false
  }
}

async function handleSheetChange(event: Event) {
  const target = event.target as HTMLSelectElement
  const sheet = target.value
  selectedSheet.value = sheet
  if (sheet) {
    await loadSheetPreview(sheet)
  } else {
    previewRows.value = []
    previewMeta.value = null
    error.value = 'Select a worksheet to preview.'
  }
}

async function handleDownload() {
  if (!props.sourceFileId) return
  isDownloading.value = true
  downloadMessage.value = ''
  try {
    const name = props.filename || `source_${props.sourceFileId}.xlsx`
    await api.downloadSourceFile(props.sourceFileId, name)
    downloadMessage.value = 'Download started.'
    setTimeout(() => {
      downloadMessage.value = ''
    }, 4000)
  } catch (err: any) {
    error.value = err.message || 'Failed to download file.'
  } finally {
    isDownloading.value = false
  }
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="zen-modal-overlay"
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="source-preview-modal-title"
    @click="onBackdropClick"
    @keydown.esc="emit('close')"
  >
    <div class="zen-modal-container">
      <!-- Modal Header -->
      <div class="zen-modal-header">
        <div class="header-titles">
          <div class="flex items-center gap-2">
            <component
              :is="isDocument ? FileText : FileSpreadsheet"
              :size="20"
              class="header-icon"
            />
            <h2 id="source-preview-modal-title" class="text-lg font-semibold text-main">
              {{ isDocument ? 'Source Document Preview' : 'Source Workbook Preview' }}
            </h2>
            <span v-if="batchId" class="batch-badge">
              Batch #{{ batchId }}
            </span>
          </div>
          <span class="text-xs text-subtle font-mono mt-0.5 truncate max-w-md">
            {{ filename || (isDocument ? 'Document' : 'Workbook') }}
          </span>
        </div>

        <div class="header-actions">
          <button
            type="button"
            class="btn-zen-download"
            :disabled="isDownloading || !sourceFileId"
            title="Download original source file"
            @click="handleDownload"
          >
            <Download :size="14" />
            <span>{{ isDownloading ? 'Downloading...' : 'Download File' }}</span>
          </button>
          <button
            type="button"
            class="btn-close"
            aria-label="Close source preview modal"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </div>
      </div>

      <!-- Controls Bar for Excel Worksheets -->
      <div v-if="!isDocument" class="zen-controls-bar">
        <div class="sheet-selector-group">
          <label for="worksheet-select" class="selector-label">
            <Layers :size="14" />
            <span>Worksheet:</span>
          </label>
          <select
            id="worksheet-select"
            class="zen-sheet-select"
            :value="selectedSheet"
            :disabled="isLoading || availableSheets.length === 0"
            @change="handleSheetChange"
          >
            <option value="" disabled>-- Select a worksheet to preview --</option>
            <option
              v-for="sheet in availableSheets"
              :key="sheet"
              :value="sheet"
            >
              {{ sheet }}
            </option>
          </select>
        </div>

        <div v-if="previewMeta" class="preview-metrics">
          <span>Showing bounded preview ({{ previewMeta.totalRows }} rows &times; {{ previewMeta.totalCols }} cols)</span>
        </div>
      </div>

      <!-- Modal Body -->
      <div class="zen-modal-body">
        <!-- Notification Message -->
        <div v-if="downloadMessage" class="feedback-banner banner-info">
          <span>{{ downloadMessage }}</span>
        </div>

        <!-- Document Preview (PDF or Image) -->
        <div v-if="isDocument" class="document-preview-container">
          <!-- Loading State -->
          <div v-if="isLoading" class="preview-loading">
            <div class="spinner" />
            <p>Loading document preview...</p>
          </div>

          <!-- Error / Fallback State -->
          <div v-else-if="error" class="feedback-banner banner-warning">
            <AlertCircle :size="18" class="banner-icon" />
            <div class="banner-content">
              <p class="banner-text">{{ error }}</p>
              <div class="banner-action mt-2">
                <button
                  type="button"
                  class="btn-zen-download"
                  @click="handleDownload"
                >
                  <Download :size="14" />
                  <span>Download Original File</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Image Preview -->
          <div v-else-if="isImage && documentBlobUrl" class="document-image-wrap">
            <img
              :src="documentBlobUrl"
              class="document-preview-img"
              :alt="filename || 'Document preview'"
            />
          </div>

          <!-- PDF or Embed Preview -->
          <div v-else-if="documentBlobUrl" class="document-frame-wrap">
            <iframe
              :src="documentBlobUrl"
              class="document-iframe"
              title="Document Source Preview"
            />
          </div>

          <!-- Document Actions Footer -->
          <div class="document-actions-footer">
            <a
              v-if="documentBlobUrl"
              :href="documentBlobUrl"
              target="_blank"
              rel="noopener noreferrer"
              class="btn-open-tab"
            >
              <ExternalLink :size="14" />
              <span>Open in New Tab</span>
            </a>
            <button
              type="button"
              class="btn-zen-secondary"
              @click="handleDownload"
            >
              <Download :size="14" />
              <span>Download Original</span>
            </button>
          </div>
        </div>

        <!-- Excel Worksheet Preview Grid -->
        <div v-else class="sheet-preview-container">
          <!-- Loading State -->
          <div v-if="isLoading" class="preview-loading">
            <div class="spinner" />
            <p>Loading worksheet preview...</p>
          </div>

          <!-- User Feedback Error / Advisory State -->
          <div v-else-if="error" class="feedback-banner banner-warning">
            <AlertCircle :size="18" class="banner-icon" />
            <div class="banner-content">
              <p class="banner-text">{{ error }}</p>
              <div v-if="error.includes('Download') || error.includes('unavailable')" class="banner-action mt-2">
                <button
                  type="button"
                  class="btn-zen-primary btn-sm"
                  :disabled="isDownloading"
                  @click="handleDownload"
                >
                  <Download :size="13" />
                  <span>Download Original File</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Empty Grid State -->
          <div
            v-else-if="previewRows.length === 0 && !isLoading"
            class="empty-preview"
          >
            <p>No tabular data found in worksheet "{{ selectedSheet }}".</p>
          </div>

          <!-- Data Grid Table -->
          <div v-else class="zen-grid-table-wrapper">
            <table class="zen-preview-grid">
              <thead>
                <tr>
                  <th class="th-index">#</th>
                  <th
                    v-for="(header, cIdx) in (previewRows[0] || [])"
                    :key="cIdx"
                    class="th-grid-col"
                  >
                    {{ header !== null && header !== undefined && String(header).trim() !== '' ? String(header) : `Col ${cIdx + 1}` }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(row, rIdx) in previewRows.slice(1)"
                  :key="rIdx"
                  class="preview-grid-row"
                >
                  <td class="td-index">{{ rIdx + 2 }}</td>
                  <td
                    v-for="(cell, cIdx) in row"
                    :key="cIdx"
                    class="td-grid-cell"
                    :title="cell !== null && cell !== undefined ? String(cell) : ''"
                  >
                    {{ cell !== null && cell !== undefined ? String(cell) : '—' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="zen-modal-footer">
        <div class="footer-left">
          <span v-if="selectedSheet && !isDocument" class="active-sheet-info">
            Worksheet: <strong>{{ selectedSheet }}</strong>
          </span>
        </div>
        <div class="footer-right">
          <button
            type="button"
            class="btn-zen-secondary"
            @click="emit('close')"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.zen-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay, rgba(15, 23, 42, 0.6));
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2500;
  padding: 1.25rem;
}

.zen-modal-container {
  background: var(--bg-surface, #ffffff);
  border-radius: 0.625rem;
  box-shadow: var(--shadow-lg, 0 20px 25px -5px rgba(0, 0, 0, 0.1));
  border: 1px solid var(--border-medium, #cbd5e1);
  width: 100%;
  max-width: 1100px;
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.zen-modal-header {
  padding: 1rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-subtle, #e2e8f0);
  background: var(--bg-card, #ffffff);
}

.header-titles {
  display: flex;
  flex-direction: column;
}

.header-icon {
  color: var(--accent-primary, #2563eb);
}

.text-main {
  color: var(--text-primary, #0f172a);
}

.text-subtle {
  color: var(--text-muted, #64748b);
}

.batch-badge {
  font-size: 0.7rem;
  padding: 0.15rem 0.5rem;
  background: var(--bg-elevated, #f1f5f9);
  color: var(--text-muted, #64748b);
  border-radius: 9999px;
  font-weight: 500;
  border: 1px solid var(--border-subtle, #e2e8f0);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-zen-download {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 0.375rem;
  background: var(--bg-surface, #ffffff);
  border: 1px solid var(--border-medium, #cbd5e1);
  color: var(--text-primary, #0f172a);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-zen-download:hover:not(:disabled) {
  background: var(--bg-elevated, #f8fafc);
  border-color: var(--border-strong, #94a3b8);
}

.btn-zen-download:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.375rem;
  border: 1px solid transparent;
  color: var(--text-muted, #64748b);
  background: transparent;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-close:hover {
  background: var(--bg-elevated, #f1f5f9);
  color: var(--text-primary, #0f172a);
}

.zen-controls-bar {
  padding: 0.625rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  background: var(--bg-subtle, #f8fafc);
  border-bottom: 1px solid var(--border-subtle, #e2e8f0);
}

.sheet-selector-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.selector-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-secondary, #475569);
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.zen-sheet-select {
  padding: 0.35rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  border: 1px solid var(--border-medium, #cbd5e1);
  background: var(--bg-surface, #ffffff);
  color: var(--text-primary, #0f172a);
  min-width: 240px;
  cursor: pointer;
}

.zen-sheet-select:focus {
  outline: none;
  border-color: var(--accent-primary, #2563eb);
}

.preview-metrics {
  font-size: 0.75rem;
  color: var(--text-muted, #64748b);
}

.zen-modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
  min-height: 280px;
  display: flex;
  flex-direction: column;
}

.feedback-banner {
  padding: 0.875rem 1rem;
  border-radius: 0.375rem;
  display: flex;
  align-items: flex-start;
  gap: 0.625rem;
  margin-bottom: 1rem;
  font-size: 0.8125rem;
}

.banner-warning {
  background: var(--bg-warning, #fefce8);
  border: 1px solid var(--border-warning, #fef08a);
  color: var(--text-warning, #854d0e);
}

.banner-info {
  background: var(--bg-info, #eff6ff);
  border: 1px solid var(--border-info, #bfdbfe);
  color: var(--text-info, #1e40af);
}

.banner-icon {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.banner-content {
  flex: 1;
}

.banner-text {
  margin: 0;
  font-weight: 500;
}

.document-preview-container {
  display: flex;
  flex-direction: column;
  height: 520px;
}

.document-frame-wrap {
  flex: 1;
  border: 1px solid var(--border-subtle, #e2e8f0);
  border-radius: 0.375rem;
  overflow: hidden;
  background: #f8fafc;
}

.document-image-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--border-subtle, #e2e8f0);
  border-radius: 0.375rem;
  overflow: auto;
  background: #0f172a;
  padding: 1rem;
}

.document-preview-img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  border-radius: 0.25rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4);
}

.document-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

.document-actions-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.75rem;
}

.btn-open-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--accent-primary, #2563eb);
  text-decoration: none;
  border-radius: 0.375rem;
  border: 1px solid var(--border-medium, #cbd5e1);
  background: var(--bg-surface, #ffffff);
  transition: all 0.15s ease;
}

.btn-open-tab:hover {
  background: var(--bg-elevated, #f8fafc);
}

.sheet-preview-container {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.preview-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 1rem;
  color: var(--text-muted, #64748b);
  font-size: 0.875rem;
  gap: 0.75rem;
}

.spinner {
  width: 1.75rem;
  height: 1.75rem;
  border: 2px solid var(--border-subtle, #e2e8f0);
  border-top-color: var(--accent-primary, #2563eb);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4rem 1rem;
  color: var(--text-muted, #64748b);
  font-size: 0.875rem;
}

.zen-grid-table-wrapper {
  overflow: auto;
  max-height: 520px;
  border: 1px solid var(--border-subtle, #e2e8f0);
  border-radius: 0.375rem;
}

.zen-preview-grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.75rem;
  font-family: var(--font-mono, monospace);
  white-space: nowrap;
}

.zen-preview-grid th,
.zen-preview-grid td {
  padding: 0.4rem 0.625rem;
  border-bottom: 1px solid var(--border-subtle, #e2e8f0);
  border-right: 1px solid var(--border-subtle, #e2e8f0);
  text-align: left;
}

.zen-preview-grid thead th {
  position: sticky;
  top: 0;
  background: var(--bg-subtle, #f8fafc);
  color: var(--text-secondary, #475569);
  font-weight: 600;
  z-index: 10;
  box-shadow: 0 1px 0 var(--border-subtle, #e2e8f0);
}

.th-index,
.td-index {
  width: 3rem;
  text-align: center !important;
  color: var(--text-muted, #94a3b8);
  background: var(--bg-subtle, #f8fafc);
  user-select: none;
}

.preview-grid-row:hover td {
  background: var(--bg-elevated, #f8fafc);
}

.td-grid-cell {
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary, #0f172a);
}

.zen-modal-footer {
  padding: 0.75rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--border-subtle, #e2e8f0);
  background: var(--bg-card, #ffffff);
}

.active-sheet-info {
  font-size: 0.75rem;
  color: var(--text-muted, #64748b);
}

.btn-zen-secondary {
  padding: 0.4rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  border: 1px solid var(--border-medium, #cbd5e1);
  background: var(--bg-surface, #ffffff);
  color: var(--text-secondary, #475569);
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-zen-secondary:hover {
  background: var(--bg-elevated, #f1f5f9);
  color: var(--text-primary, #0f172a);
}

.btn-zen-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.4rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 0.375rem;
  border: 1px solid var(--accent-primary, #2563eb);
  background: var(--accent-primary, #2563eb);
  color: #ffffff;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-zen-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-sm {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}
</style>
