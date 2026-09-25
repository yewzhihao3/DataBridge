<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Loader2,
  RotateCcw,
  UploadCloud,
  FileText,
} from 'lucide-vue-next'

import FileUploadCard from '@/components/ingestion/FileUploadCard.vue'
import TemplateSelectorCard from '@/components/ingestion/TemplateSelectorCard.vue'
import ExtractionPreviewTable from '@/components/ingestion/ExtractionPreviewTable.vue'
import { useImportWorkflow } from '@/composables/useImportWorkflow'

const {
  currentStep,
  uploadedFile,
  isUploading,
  uploadError,

  templates,
  selectedTemplateId,
  isLoadingTemplates,
  templateError,

  previewResult,
  isExtracting,
  extractError,

  isConfirming,
  confirmError,
  confirmedBatch,
  userAcknowledgedWarnings,

  hasValidationErrors,
  warningCount,
  canConfirm,

  handleFileUpload,
  runExtraction,
  confirmImport,
  resetWorkflow,
} = useImportWorkflow()

const workflowSteps = [
  { number: 1, label: 'Upload' },
  { number: 2, label: 'Template' },
  { number: 3, label: 'Preview' },
  { number: 4, label: 'Confirmation' },
]

/** Extract company name from preview header fields (if present) */
const previewCompanyName = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find((f) => f.field_name === 'company_name')
  return f?.normalized_value ? String(f.normalized_value) : null
})

/** Extract invoice number from preview header fields (if present) */
const previewInvoiceNumber = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find((f) => f.field_name === 'invoice_number')
  return f?.normalized_value ? String(f.normalized_value) : null
})

/** Overall status text for the preview header */
const overallStatusText = computed(() => {
  if (!previewResult.value) return ''
  if (hasValidationErrors.value) {
    return `${previewResult.value.error_count} validation error${previewResult.value.error_count !== 1 ? 's' : ''}`
  }
  if (warningCount.value > 0) {
    return `${warningCount.value} warning${warningCount.value !== 1 ? 's' : ''}`
  }
  return 'Ready to import'
})
</script>

<template>
  <main class="ingestion-page container">
    <!-- Page Header -->
    <section class="page-header">
      <div class="page-header-content">
        <div class="eyebrow">
          <UploadCloud :size="16" />
          DATA INGESTION
        </div>

        <h1>Ingestion Studio</h1>

        <p class="page-description">
          Upload, inspect, validate, and import business data from Excel
          workbooks.
        </p>
      </div>

      <button
        v-if="currentStep > 1"
        class="btn btn-secondary"
        type="button"
        @click="resetWorkflow"
      >
        <RotateCcw :size="16" />
        Start Over
      </button>
    </section>

    <!-- Workflow Progress -->
    <section class="workflow-progress glass-card">
      <div
        v-for="step in workflowSteps"
        :key="step.number"
        class="progress-step"
        :class="{
          active: currentStep === step.number,
          completed: currentStep > step.number,
        }"
      >
        <div class="progress-number">
          <CheckCircle2
            v-if="currentStep > step.number"
            :size="17"
          />

          <span v-else>
            {{ step.number }}
          </span>
        </div>

        <span class="progress-label">
          {{ step.label }}
        </span>
      </div>
    </section>

    <!-- Step 1: File Upload -->
    <FileUploadCard
      :uploaded-file="uploadedFile"
      :is-uploading="isUploading"
      :error="uploadError"
      @file-selected="handleFileUpload"
      @reset="resetWorkflow"
    />

    <!-- Step 2: Template Selection -->
    <TemplateSelectorCard
      v-if="currentStep >= 2 && uploadedFile"
      :templates="templates"
      :selected-template-id="selectedTemplateId"
      :uploaded-file="uploadedFile"
      :is-loading="isLoadingTemplates"
      :is-extracting="isExtracting"
      :error="templateError || extractError"
      @update:selected-template-id="selectedTemplateId = $event"
      @extract="runExtraction"
    />

    <!-- Step 3: Extraction Preview -->
    <section
      v-if="currentStep >= 3 && previewResult"
      class="preview-section"
    >
      <!-- Zen Data Preview Header -->
      <div class="zen-preview-header">
        <div class="zen-preview-identity">
          <div class="eyebrow">
            <FileText :size="16" />
            EXTRACTION PREVIEW
          </div>

          <h2 v-if="previewCompanyName || previewInvoiceNumber">
            <span v-if="previewCompanyName">{{ previewCompanyName }}</span>
            <span
              v-if="previewCompanyName && previewInvoiceNumber"
              class="zen-invoice-number"
            >
              {{ previewInvoiceNumber }}
            </span>
            <span v-else-if="previewInvoiceNumber">
              Invoice {{ previewInvoiceNumber }}
            </span>
          </h2>
          <h2 v-else>Extraction Preview</h2>

          <p>
            Review the extracted values before confirming the import.
          </p>
        </div>

        <div class="zen-preview-status-wrap">
          <div
            class="zen-overall-status"
            :class="{
              'zen-overall-status--success': !hasValidationErrors && warningCount === 0,
              'zen-overall-status--warning': !hasValidationErrors && warningCount > 0,
              'zen-overall-status--error': hasValidationErrors,
            }"
          >
            <CheckCircle2
              v-if="!hasValidationErrors && warningCount === 0"
              :size="16"
            />
            <AlertTriangle
              v-else-if="!hasValidationErrors && warningCount > 0"
              :size="16"
            />
            <AlertCircle
              v-else
              :size="16"
            />
            <span>{{ overallStatusText }}</span>
          </div>
        </div>
      </div>

      <!-- Extraction Table -->
      <ExtractionPreviewTable
        :fields="previewResult.fields"
        :target-worksheet="previewResult.target_worksheet"
        :is-multi-record="previewResult.is_multi_record"
        :records="previewResult.records"
        :has-line-items="previewResult.has_line_items"
        :line-items="previewResult.line_items"
      />

      <!-- Validation Issues -->
      <div
        v-if="previewResult.validation_report.issues.length > 0"
        class="glass-card issues-card"
      >
        <div class="card-heading">
          <AlertTriangle :size="20" />
          <h3>Validation Issues</h3>
        </div>

        <div class="issues-list">
          <div
            v-for="(issue, index) in previewResult.validation_report.issues"
            :key="`${issue.rule_id}-${index}`"
            class="issue-item"
            :class="`issue-${issue.severity}`"
          >
            <AlertCircle :size="17" />

            <div class="issue-content">
              <strong>
                {{ issue.rule_id }}

                <span v-if="issue.field_name">
                  — {{ issue.field_name }}
                </span>
              </strong>

              <p>
                {{ issue.message }}
              </p>

              <small v-if="issue.cell_ref">
                Cell:
                {{ issue.worksheet }}!{{ issue.cell_ref }}
              </small>
            </div>
          </div>
        </div>
      </div>

      <!-- Extraction Errors -->
      <div
        v-if="previewResult.errors.length > 0"
        class="glass-card issues-card"
      >
        <div class="card-heading error-text">
          <AlertCircle :size="20" />
          <h3>Extraction Errors</h3>
        </div>

        <div class="issues-list">
          <div
            v-for="(error, index) in previewResult.errors"
            :key="`${error.error_type}-${index}`"
            class="issue-item issue-error"
          >
            <AlertCircle :size="17" />

            <div class="issue-content">
              <strong>
                {{ error.error_type }}
              </strong>

              <p>
                {{ error.message }}
              </p>

              <small v-if="error.cell_ref">
                Cell:
                {{ error.worksheet }}!{{ error.cell_ref }}
              </small>
            </div>
          </div>
        </div>
      </div>

      <!-- Confirmation Panel -->
      <div class="glass-card confirmation-card">
        <div class="card-heading">
          <CheckCircle2 :size="20" />
          <h3>Confirm Import</h3>
        </div>

        <!-- Validation Error Notice -->
        <div
          v-if="hasValidationErrors"
          class="notice notice-error"
        >
          <AlertCircle :size="18" />

          <div>
            <strong>Import is blocked</strong>

            <p>
              Please resolve the validation errors before
              confirming this import.
            </p>
          </div>
        </div>

        <!-- Warning Notice -->
        <div
          v-else-if="warningCount > 0"
          class="notice notice-warning"
        >
          <AlertTriangle :size="18" />

          <div>
            <strong>
              Warnings require acknowledgment
            </strong>

            <p>
              Review the warnings before proceeding with
              the import.
            </p>
          </div>
        </div>

        <!-- Warning Acknowledgment -->
        <label
          v-if="warningCount > 0 && !hasValidationErrors"
          class="acknowledgment-checkbox"
        >
          <input
            v-model="userAcknowledgedWarnings"
            type="checkbox"
          />

          <span>
            I have reviewed and acknowledge the validation
            warnings.
          </span>
        </label>

        <!-- Confirmation Error -->
        <div
          v-if="confirmError"
          class="notice notice-error"
        >
          <AlertCircle :size="18" />

          <p>
            {{ confirmError }}
          </p>
        </div>

        <!-- Confirmation Actions -->
        <div class="confirmation-actions">
          <button
            class="btn btn-secondary"
            type="button"
            :disabled="isConfirming"
            @click="resetWorkflow"
          >
            Cancel
          </button>

          <button
            class="btn btn-primary"
            type="button"
            :disabled="!canConfirm || isConfirming"
            @click="confirmImport"
          >
            <Loader2
              v-if="isConfirming"
              class="animate-spin"
              :size="17"
            />

            <span v-else>
              Confirm Import
            </span>
          </button>
        </div>
      </div>
    </section>

    <!-- Step 4: Successful Import -->
    <section
      v-if="currentStep === 4 && confirmedBatch"
      class="glass-card success-card"
    >
      <CheckCircle2
        :size="48"
        class="success-icon"
      />

      <div class="eyebrow success-eyebrow">
        <CheckCircle2 :size="15" />
        IMPORT COMPLETE
      </div>

      <h2>
        Import Completed Successfully
      </h2>

      <p>
        Your workbook has been validated and imported
        successfully.
      </p>

      <!-- Import Details -->
      <div class="success-details">
        <div class="success-detail-item">
          <span>Batch ID</span>
          <strong>
            #{{ confirmedBatch.id }}
          </strong>
        </div>

        <div class="success-detail-item">
          <span>Records Imported</span>
          <strong>
            {{ confirmedBatch.record_count }}
          </strong>
        </div>

        <div class="success-detail-item">
          <span>Warnings</span>
          <strong>
            {{ confirmedBatch.warning_count }}
          </strong>
        </div>

        <div class="success-detail-item">
          <span>Status</span>
          <strong class="success-text">
            {{ confirmedBatch.status }}
          </strong>
        </div>
      </div>

      <button
        class="btn btn-primary"
        type="button"
        @click="resetWorkflow"
      >
        Import Another File
      </button>
    </section>
  </main>
</template>

<style scoped>
.ingestion-page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  padding-top: 2rem;
  padding-bottom: 2rem;
}

/* Page Header */

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.page-header-content {
  min-width: 0;
}

.eyebrow {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.5rem;

  color: var(--accent-brand);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-header h1 {
  margin: 0;

  color: var(--text-primary);
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.page-description {
  max-width: 650px;
  margin-top: 0.5rem;

  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.7;
}

/* Workflow Progress */

.workflow-progress {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;

  padding: 1rem 1.5rem;

  border: 1px solid var(--border-default);
  background: var(--bg-card);
}

.progress-step {
  display: flex;
  align-items: center;
  gap: 0.6rem;

  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 600;

  transition:
    color 0.2s ease,
    transform 0.2s ease;
}

.progress-number {
  display: flex;
  align-items: center;
  justify-content: center;

  width: 2rem;
  height: 2rem;

  border: 1px solid var(--border-medium);
  border-radius: var(--radius-full);

  color: var(--text-muted);
  font-size: 0.8rem;

  transition:
    background 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.progress-step.active {
  color: var(--accent-brand);
}

.progress-step.active .progress-number {
  border-color: var(--accent-brand);
  background: var(--accent-brand-subtle);
  color: var(--accent-brand);
}

.progress-step.completed {
  color: var(--status-success);
}

.progress-step.completed .progress-number {
  border-color: var(--status-success);
  background: var(--status-success-bg);
  color: var(--status-success);
}

/* Preview Section */

.preview-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Zen Preview Header */

.zen-preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.zen-preview-identity h2 {
  margin: 0;

  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.zen-invoice-number {
  display: inline-block;
  margin-left: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0;
}

.zen-preview-identity p {
  max-width: 700px;
  margin-top: 0.4rem;

  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.6;
}

.zen-preview-status-wrap {
  flex-shrink: 0;
  padding-top: 0.25rem;
}

.zen-overall-status {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.85rem;
  border-radius: var(--radius-full);
  font-size: 0.82rem;
  font-weight: 600;
}

.zen-overall-status--success {
  color: var(--status-success);
  background: var(--status-success-bg);
  border: 1px solid var(--status-success-border);
}

.zen-overall-status--warning {
  color: var(--status-warning);
  background: var(--status-warning-bg);
  border: 1px solid var(--status-warning-border);
}

.zen-overall-status--error {
  color: var(--status-error);
  background: var(--status-error-bg);
  border: 1px solid var(--status-error-border);
}

/* Text Colors */

.success-text {
  color: var(--status-success) !important;
}

.warning-text {
  color: var(--status-warning) !important;
}

.error-text {
  color: var(--status-error) !important;
}

/* Issue and Confirmation Cards */

.issues-card,
.confirmation-card {
  padding: 1.5rem;
}

.card-heading {
  display: flex;
  align-items: center;
  gap: 0.6rem;

  margin-bottom: 1rem;

  color: var(--text-primary);
}

.card-heading h3 {
  margin: 0;

  font-size: 1rem;
  font-weight: 700;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.issue-item {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;

  padding: 0.85rem;

  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
}

.issue-error {
  border-color: var(--status-error-border);
  background: var(--status-error-bg);
  color: var(--status-error);
}

.issue-warning {
  border-color: var(--status-warning-border);
  background: var(--status-warning-bg);
  color: var(--status-warning);
}

.issue-info {
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.issue-content {
  min-width: 0;
}

.issue-content strong {
  color: inherit;
  font-size: 0.85rem;
  font-weight: 700;
}

.issue-content p {
  margin-top: 0.25rem;

  color: var(--text-primary);
  font-size: 0.85rem;
  line-height: 1.5;
}

.issue-content small {
  display: block;
  margin-top: 0.3rem;

  color: var(--text-muted);
  font-size: 0.75rem;
}

/* Notices */

.notice {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;

  padding: 1rem;

  border-radius: var(--radius-sm);

  font-size: 0.85rem;
  line-height: 1.5;
}

.notice strong {
  display: block;
  margin-bottom: 0.25rem;
}

.notice p {
  margin: 0;
}

.notice-error {
  border: 1px solid var(--status-error-border);
  background: var(--status-error-bg);
  color: var(--status-error);
}

.notice-warning {
  border: 1px solid var(--status-warning-border);
  background: var(--status-warning-bg);
  color: var(--status-warning);
}

/* Warning Acknowledgment */

.acknowledgment-checkbox {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;

  margin-top: 1rem;

  color: var(--text-secondary);
  font-size: 0.85rem;
  line-height: 1.5;

  cursor: pointer;
}

.acknowledgment-checkbox input {
  flex-shrink: 0;
  margin-top: 0.2rem;

  accent-color: var(--accent-brand);
}

/* Confirmation Actions */

.confirmation-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;

  margin-top: 1.25rem;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

/* Success Card */

.success-card {
  display: flex;
  flex-direction: column;
  align-items: center;

  padding: 2.5rem 1.5rem;

  text-align: center;
}

.success-icon {
  margin-bottom: 1rem;
  color: var(--status-success);
}

.success-eyebrow {
  margin-bottom: 0.75rem;
  color: var(--status-success);
}

.success-card h2 {
  margin: 0;

  color: var(--text-primary);
  font-size: 1.5rem;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.success-card > p {
  max-width: 500px;
  margin-top: 0.5rem;

  color: var(--text-secondary);
  font-size: 0.9rem;
  line-height: 1.6;
}

/* Success Details */

.success-details {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;

  width: 100%;
  max-width: 500px;

  margin: 1.5rem 0;
}

.success-detail-item {
  padding: 1rem;

  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);

  background: var(--bg-subtle);
}

.success-detail-item span,
.success-detail-item strong {
  display: block;
}

.success-detail-item span {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.success-detail-item strong {
  margin-top: 0.25rem;

  color: var(--text-primary);
  font-size: 0.95rem;
}

/* Loading Animation */

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

/* Responsive Layout */

@media (max-width: 768px) {
  .ingestion-page {
    padding-top: 1rem;
    padding-bottom: 1rem;
  }

  .page-header {
    flex-direction: column;
  }

  .page-header h1 {
    font-size: 1.7rem;
  }

  .zen-preview-header {
    flex-direction: column;
    gap: 0.75rem;
  }

  .zen-preview-identity h2 {
    font-size: 1.25rem;
  }

  .workflow-progress {
    justify-content: flex-start;
    overflow-x: auto;
  }

  .progress-step {
    flex-shrink: 0;
  }

  .progress-label {
    white-space: nowrap;
  }
}

@media (max-width: 520px) {
  .success-details {
    grid-template-columns: 1fr;
  }

  .confirmation-actions {
    flex-direction: column-reverse;
  }

  .confirmation-actions .btn {
    width: 100%;
  }
}
</style>