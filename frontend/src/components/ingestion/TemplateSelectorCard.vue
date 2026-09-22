<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, FileCheck, Layers, Loader2 } from 'lucide-vue-next'
import type { SourceFileUploadResponse, TemplateSummary } from '@/types/api'

const props = defineProps<{
  templates: TemplateSummary[]
  selectedTemplateId: number | null
  uploadedFile: SourceFileUploadResponse | null
  isLoading: boolean
  isExtracting: boolean
  error: string | null
}>()

const emit = defineEmits<{
  (e: 'update:selectedTemplateId', id: number): void
  (e: 'extract'): void
}>()

const selectedTemplate = computed<TemplateSummary | null>(() => {
  return (
    props.templates.find(
      (template) => template.id === props.selectedTemplateId,
    ) ?? null
  )
})

/**
 * Some upload API responses may not include sheet_names.
 * Normalize the value before using array methods such as includes().
 */
const uploadedSheetNames = computed<string[]>(() => {
  const sheetNames = props.uploadedFile?.sheet_names

  return Array.isArray(sheetNames) ? sheetNames : []
})

const isWorksheetMatched = computed<boolean>(() => {
  const templateWorksheet = selectedTemplate.value?.worksheet

  if (!templateWorksheet || !props.uploadedFile) {
    return false
  }

  return uploadedSheetNames.value.includes(templateWorksheet)
})

function onTemplateChange(event: Event) {
  const target = event.target as HTMLSelectElement
  const templateId = Number(target.value)

  if (Number.isFinite(templateId) && templateId > 0) {
    emit('update:selectedTemplateId', templateId)
  }
}

function onExtract() {
  if (
    !props.uploadedFile ||
    props.selectedTemplateId === null ||
    props.isExtracting
  ) {
    return
  }

  emit('extract')
}
</script>

<template>
  <div class="glass-card template-card">
    <div class="card-header">
      <div class="step-indicator">
        <span class="step-number">2</span>
      </div>

      <div class="header-titles">
        <h2 class="card-title">Select Extraction Template</h2>
        <p class="card-subtitle">
          Choose a template matching your spreadsheet layout
        </p>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="isLoading" class="loading-state">
      <Loader2 class="animate-spin text-accent" :size="24" />
      <span>Loading templates...</span>
    </div>

    <!-- Empty State -->
    <div v-else-if="templates.length === 0" class="empty-state">
      <Layers :size="32" class="text-muted" />
      <span class="empty-text">
        No templates available. Please create a template first.
      </span>

      <router-link to="/templates" class="btn btn-secondary btn-sm">
        Go to Templates
      </router-link>
    </div>

    <!-- Template Selection -->
    <div v-else class="template-selector-body">
      <div class="form-group">
        <label class="form-label" for="template-select">
          Template Layout
        </label>

        <select
          id="template-select"
          class="custom-select"
          :value="selectedTemplateId ?? ''"
          :disabled="isExtracting"
          @change="onTemplateChange"
        >
          <option disabled value="">
            Select a template
          </option>

          <option
            v-for="template in templates"
            :key="template.id"
            :value="template.id"
          >
            {{ template.name }} (Target Sheet: "{{ template.worksheet }}",
            {{ template.mapping_count }} mapped fields)
          </option>
        </select>
      </div>

      <!-- Selected Template Details -->
      <div v-if="selectedTemplate" class="template-details">
        <div class="detail-row">
          <span class="detail-label">Target Worksheet:</span>

          <div class="detail-value-wrapper">
            <span class="detail-value mono">
              {{ selectedTemplate.worksheet }}
            </span>

            <span
              v-if="isWorksheetMatched"
              class="match-badge matched"
              title="Sheet found in uploaded workbook"
            >
              <FileCheck :size="12" />
              <span>Sheet Found</span>
            </span>

            <span
              v-else
              class="match-badge mismatched"
              title="Sheet not found in uploaded file"
            >
              Warning: Worksheet not found in file
            </span>
          </div>
        </div>

        <div class="detail-row">
          <span class="detail-label">Mapped Fields:</span>
          <span class="detail-value">
            {{ selectedTemplate.mapping_count }} fields
          </span>
        </div>

        <div
          v-if="selectedTemplate.description"
          class="detail-row detail-row-top"
        >
          <span class="detail-label">Description:</span>
          <span class="detail-value text-secondary">
            {{ selectedTemplate.description }}
          </span>
        </div>
      </div>

      <!-- Action Button -->
      <div class="action-row">
        <button
          type="button"
          class="btn btn-primary btn-extract"
          :disabled="
            selectedTemplateId === null ||
            isExtracting ||
            !uploadedFile
          "
          @click="onExtract"
        >
          <Loader2
            v-if="isExtracting"
            class="animate-spin"
            :size="18"
          />

          <template v-else>
            <span>Run Extraction Preview</span>
            <ArrowRight :size="18" />
          </template>
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner" role="alert">
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<style scoped>
.template-card {
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
  flex-shrink: 0;
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

.header-titles {
  min-width: 0;
}

.card-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
}

.card-subtitle {
  margin-top: 0.2rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.template-selector-body {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-label {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.custom-select {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 0.75rem 1rem;
  border: 1px solid var(--border-medium, #475569);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-input, #0f172a) !important;
  color: var(--text-primary, #f8fafc) !important;
  font-family: inherit;
  font-size: 0.9rem;
  line-height: 1.4;
  cursor: pointer;
  outline: none;
  color-scheme: dark;
  transition:
    border-color var(--transition-fast),
    box-shadow var(--transition-fast),
    background var(--transition-fast);
}

.custom-select:focus {
  border-color: var(--border-focus, var(--accent-brand));
  box-shadow: 0 0 0 3px var(--accent-brand-subtle);
}

.custom-select:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.custom-select option {
  background: var(--bg-card, #111827);
  color: var(--text-primary, #f8fafc);
}

.template-details {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
}

.detail-row-top {
  align-items: flex-start;
}

.detail-label {
  flex: 0 0 8.5rem;
  font-weight: 600;
  color: var(--text-muted);
}

.detail-value-wrapper {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.65rem;
  min-width: 0;
}

.detail-value {
  color: var(--text-primary);
  font-weight: 500;
  overflow-wrap: anywhere;
}

.match-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 600;
}

.match-badge.matched {
  background: var(--status-success-bg);
  color: var(--status-success);
}

.match-badge.mismatched {
  background: var(--status-warning-bg);
  color: var(--status-warning);
}

.action-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.5rem;
}

.btn-extract {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1.5rem;
  font-size: 0.95rem;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 2rem;
  color: var(--text-secondary);
  text-align: center;
}

.empty-text {
  max-width: 28rem;
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
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 640px) {
  .template-card {
    padding: 1.25rem;
  }

  .detail-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.35rem;
  }

  .detail-label {
    flex-basis: auto;
  }

  .action-row {
    justify-content: stretch;
  }

  .btn-extract {
    width: 100%;
  }
}
</style>
