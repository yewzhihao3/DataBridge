<script setup lang="ts">
import { ref } from 'vue'
import { CheckCircle2, FileCode, FileSpreadsheet, Loader2, UploadCloud } from 'lucide-vue-next'
import type { SourceFileUploadResponse } from '@/types/api'

const props = defineProps<{
  uploadedFile: SourceFileUploadResponse | null
  isUploading: boolean
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'file-selected', file: File): void
  (e: 'reset'): void
}>()

const isDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
    handleFile(e.dataTransfer.files[0])
  }
}

function onFileInputChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files && target.files.length > 0) {
    handleFile(target.files[0])
  }
}

function handleFile(file: File) {
  if (!file.name.endsWith('.xlsx')) {
    alert('Please upload a valid Microsoft Excel (.xlsx) file.')
    return
  }
  emit('file-selected', file)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
}
</script>

<template>
  <div class="glass-card upload-card">
    <div class="card-header">
      <div class="step-indicator">
        <span class="step-number">1</span>
      </div>
      <div>
        <h2 class="card-title">Source File Upload & Inspection</h2>
        <p class="card-subtitle">Upload an Excel (.xlsx) invoice workbook for inspection</p>
      </div>
    </div>

    <!-- Upload Dropzone (When no file uploaded) -->
    <div
      v-if="!uploadedFile"
      class="dropzone"
      :class="{ dragging: isDragging, loading: isUploading }"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
      @click="fileInput?.click()"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".xlsx"
        class="hidden-input"
        @change="onFileInputChange"
      />

      <div v-if="isUploading" class="upload-state">
        <Loader2 class="animate-spin text-accent" :size="38" />
        <span class="upload-text">Streaming file, calculating SHA-256 & inspecting sheets...</span>
      </div>

      <div v-else class="upload-state">
        <div class="icon-circle">
          <UploadCloud :size="32" />
        </div>
        <span class="upload-text primary-text">Click or drag & drop an Excel file</span>
        <span class="upload-hint">Supports .xlsx workbooks up to 10 MB</span>
      </div>
    </div>

    <!-- Uploaded File Summary -->
    <div v-else class="file-summary">
      <div class="file-main-info">
        <div class="file-icon-box">
          <FileSpreadsheet :size="28" class="text-success" />
        </div>
        <div class="file-meta">
          <span class="file-name">{{ uploadedFile.original_name }}</span>
          <div class="meta-row">
            <span class="file-size">{{ formatBytes(uploadedFile.file_size_bytes) }}</span>
            <span class="bullet">•</span>
           <span class="file-checksum mono"
              :title="`SHA-256: ${uploadedFile.checksum_sha256 || 'Unavailable'}`">
              SHA-256:
              {{ uploadedFile.checksum_sha256?.slice(0, 12) || 'Unavailable' }}...
          </span>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" @click="$emit('reset')">
          Change File
        </button>
      </div>

      <!-- Inspected Sheets Pills -->
      <div class="sheets-container">
        <span class="sheets-label">Inspected Worksheets:</span>
        <div class="sheets-grid">
          <div
            v-for="sheet in uploadedFile.worksheet_info"
            :key="sheet.name"
            class="sheet-pill"
            :class="{ hidden: sheet.is_hidden }"
          >
            <span class="sheet-name">{{ sheet.name }}</span>
            <span v-if="sheet.has_formulas" class="formula-tag" title="Formulas detected">
              <FileCode :size="12" />
              <span>fx</span>
            </span>
            <span v-if="sheet.is_hidden" class="hidden-tag">Hidden</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Error Message -->
    <div v-if="error" class="error-banner">
      <span class="error-text">{{ error }}</span>
    </div>
  </div>
</template>

<style scoped>
.upload-card {
  padding: 1.75rem;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.step-indicator {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--radius-full);
  background: var(--accent-brand-subtle);
  border: 1px solid var(--accent-brand);
  color: var(--accent-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.95rem;
}

.card-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-subtitle {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.dropzone {
  border: 2px dashed var(--border-medium);
  border-radius: var(--radius-md);
  padding: 2.5rem 1.5rem;
  text-align: center;
  cursor: pointer;
  background: rgba(15, 23, 42, 0.4);
  transition: all var(--transition-fast);
}

.dropzone:hover,
.dropzone.dragging {
  border-color: var(--accent-brand);
  background: var(--accent-brand-subtle);
}

.hidden-input {
  display: none;
}

.upload-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.icon-circle {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-full);
  background: var(--bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
}

.primary-text {
  font-weight: 600;
  color: var(--text-primary);
}

.upload-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.file-summary {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  background: var(--bg-subtle);
  padding: 1.25rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.file-main-info {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.file-icon-box {
  width: 3rem;
  height: 3rem;
  border-radius: var(--radius-md);
  background: var(--status-success-bg);
  border: 1px solid var(--status-success-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.file-meta {
  flex: 1;
}

.file-name {
  font-weight: 700;
  font-size: 1rem;
  color: var(--text-primary);
  display: block;
}

.meta-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin-top: 0.2rem;
}

.bullet {
  color: var(--text-muted);
}

.file-checksum {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.sheets-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid var(--border-subtle);
  padding-top: 0.85rem;
}

.sheets-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sheets-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.sheet-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-primary);
}

.formula-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.15rem;
  font-size: 0.7rem;
  color: var(--accent-cyan);
  background: var(--accent-cyan-subtle);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}

.hidden-tag {
  font-size: 0.7rem;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}

.error-banner {
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  background: var(--status-error-bg);
  border: 1px solid var(--status-error-border);
  border-radius: var(--radius-sm);
  color: var(--status-error);
  font-size: 0.85rem;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
