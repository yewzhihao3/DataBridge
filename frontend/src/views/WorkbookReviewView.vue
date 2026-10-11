<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  FileSpreadsheet,
  Loader2,
  RotateCcw,
  TrendingDown,
  TrendingUp,
  HelpCircle,
} from 'lucide-vue-next'
import { api } from '@/services/api'
import { toast } from '@/services/toast'
import { reviewedTemplateId } from '@/composables/useSuggestionDraft'
import { useImportWorkflow } from '@/composables/useImportWorkflow'
import { useIngestionQueue, type QueueEntry } from '@/composables/useIngestionQueue'
import SmartSuggestionsCard from '@/components/ingestion/SmartSuggestionsCard.vue'
import TemplateSelectorCard from '@/components/ingestion/TemplateSelectorCard.vue'
import ExtractionPreviewTable from '@/components/ingestion/ExtractionPreviewTable.vue'
import type {
  BatchImportDetail,
  BatchImportFile,
  ImportBatchDetail,
  RowDirectionOverride,
} from '@/types/api'

const route = useRoute()
const router = useRouter()

// ── Ingestion Queue Context ────────────────────────────────────────────────
const { queue, markFileImported } = useIngestionQueue()

// ── Import Workflow ────────────────────────────────────────────────────────
const {
  currentStep,
  uploadedFile,
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
  runExtraction,
  confirmImport,
  loadTemplates,
  resetWorkflow,
} = useImportWorkflow()

// ── Local State ────────────────────────────────────────────────────────────
const templateChoice = ref<'smart' | 'manual'>('smart')
const isLoadingFile = ref(false)
const loadError = ref<string | null>(null)

// ── Financial Direction State ──────────────────────────────────────────────
type InvoiceDirection = 'sales' | 'purchase' | 'unclassified'
const bulkDirection = ref<InvoiceDirection>('unclassified')
// Map of source_row_number → per-row direction override
const rowDirectionOverrides = ref<Map<number, InvoiceDirection>>(new Map())

const isMultiRecord = computed(() =>
  Boolean(previewResult.value?.is_multi_record && (previewResult.value?.records?.length ?? 0) > 1),
)

const rowDirectionsList = computed((): RowDirectionOverride[] => {
  const overrides: RowDirectionOverride[] = []
  for (const [rowNum, dir] of rowDirectionOverrides.value.entries()) {
    if (dir !== bulkDirection.value) {
      overrides.push({ source_row_number: rowNum, direction: dir })
    }
  }
  return overrides
})

function effectiveRowDirection(rowNum: number): InvoiceDirection {
  return rowDirectionOverrides.value.get(rowNum) ?? bulkDirection.value
}

function setRowDirection(rowNum: number, dir: InvoiceDirection) {
  const map = new Map(rowDirectionOverrides.value)
  map.set(rowNum, dir)
  rowDirectionOverrides.value = map
}

function clearRowOverrides() {
  rowDirectionOverrides.value = new Map()
}



// Batch context (if routed via batch session)
const batchSessionId = computed<number | null>(() => {
  const sid = route.params.sessionId || route.query.batchSession
  return sid ? Number(sid) : null
})
const batchDetail = ref<BatchImportDetail | null>(null)
const batchFile = ref<BatchImportFile | null>(null)

// ── Current File Identification ────────────────────────────────────────────
const currentFileId = computed<number>(() => {
  return Number(route.params.fileId)
})

const currentQueueEntry = computed<QueueEntry | undefined>(() => {
  return queue.value.find(e => e.fileId === currentFileId.value)
})

const fileDisplayName = computed<string>(() => {
  return (
    currentQueueEntry.value?.name ||
    batchFile.value?.filename ||
    uploadedFile.value?.original_name ||
    `Workbook #${currentFileId.value}`
  )
})

// ── Queue Navigation ───────────────────────────────────────────────────────
const reviewableEntries = computed(() => {
  return queue.value.filter(
    e => (e.status === 'needs_review' || e.status === 'ready' || e.status === 'imported') && e.reviewPath
  )
})

const currentIndex = computed(() => {
  return reviewableEntries.value.findIndex(e => e.fileId === currentFileId.value)
})

const prevEntry = computed(() => {
  if (currentIndex.value > 0) {
    return reviewableEntries.value[currentIndex.value - 1]
  }
  return null
})

const nextEntry = computed(() => {
  if (currentIndex.value >= 0 && currentIndex.value < reviewableEntries.value.length - 1) {
    return reviewableEntries.value[currentIndex.value + 1]
  }
  return null
})

function goToEntry(entry: QueueEntry) {
  if (entry.reviewPath) {
    router.push(entry.reviewPath)
  }
}

// ── Summary Metrics ────────────────────────────────────────────────────────
const previewCompanyName = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find(f => f.field_name === 'company_name')
  return f?.normalized_value ? String(f.normalized_value) : null
})

const previewInvoiceNumber = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find(f => f.field_name === 'invoice_number')
  return f?.normalized_value ? String(f.normalized_value) : null
})

const previewInvoiceDate = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find(f => f.field_name === 'invoice_date')
  return f?.normalized_value ? String(f.normalized_value) : null
})

const previewCurrency = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find(f => f.field_name === 'currency')
  return f?.normalized_value ? String(f.normalized_value) : null
})

const previewTotalAmount = computed(() => {
  if (!previewResult.value) return null
  const f = previewResult.value.fields.find(f => f.field_name === 'total_amount')
  return f?.normalized_value ? String(f.normalized_value) : null
})

const overallStatusText = computed(() => {
  if (!previewResult.value) return ''
  if (hasValidationErrors.value) {
    const errCount = previewResult.value.error_count ?? 1
    return `${errCount} validation error${errCount !== 1 ? 's' : ''}`
  }
  if (warningCount.value > 0) {
    return `${warningCount.value} warning${warningCount.value !== 1 ? 's' : ''}`
  }
  return 'Ready to import'
})

// ── Handlers ───────────────────────────────────────────────────────────────
function selectSuggestedTemplate(id: number) {
  selectedTemplateId.value = id
  templateChoice.value = 'smart'
}

/**
 * Persists the selected template to the batch file record (if in batch mode),
 * then runs the extraction preview. This ensures the backend has the correct
 * template_id before calling the review endpoint.
 */
async function handleExtract() {
  if (batchSessionId.value && selectedTemplateId.value) {
    try {
      await api.assignBatchTemplate(batchSessionId.value, currentFileId.value, selectedTemplateId.value)
    } catch {
      // Non-fatal — proceed with extraction anyway (template_id passed as query param)
    }
  }
  await runExtraction()
}

async function handleConfirm() {
  const directionOptions = {
    direction: bulkDirection.value,
    row_directions: rowDirectionsList.value.length > 0 ? rowDirectionsList.value : undefined,
  }

  if (batchSessionId.value) {
    // Batch file confirmation
    isConfirming.value = true
    confirmError.value = null
    try {
      const updated = await api.acceptBatchWarnings(
        batchSessionId.value,
        currentFileId.value,
        directionOptions,
      )
      batchDetail.value = updated
      markFileImported(currentFileId.value)
      currentStep.value = 4
      confirmedBatch.value = {
        id: batchSessionId.value,
        source_file_id: currentFileId.value,
        original_filename: fileDisplayName.value,
        template_id: selectedTemplateId.value || 0,
        template_name: templates.value.find(t => t.id === selectedTemplateId.value)?.name || 'Mapped Template',
        status: 'imported',
        record_count: previewResult.value?.records?.length || 1,
        warning_count: warningCount.value,
        imported_at: new Date().toISOString(),
        invoice_records: [],
        validation_issues: [],
      } as ImportBatchDetail
      toast.success('File imported successfully.')
    } catch (err: any) {
      const msg = err?.message || 'Failed to confirm batch file import.'
      confirmError.value = msg
      toast.error(msg)
    } finally {
      isConfirming.value = false
    }
  } else {
    // Single file confirmation — pass direction options into the workflow
    await confirmImport(directionOptions)
    if (confirmedBatch.value) {
      markFileImported(currentFileId.value)
      toast.success('Workbook imported successfully.')
    }
  }
}

// ── Lifecycle & Restoration ────────────────────────────────────────────────
async function initWorkbookReview() {
  const fileId = currentFileId.value
  if (!fileId || Number.isNaN(fileId)) {
    loadError.value = 'Invalid or missing file ID.'
    return
  }

  // ── Always reset workflow state when switching to a new file ──────────────
  // This prevents stale success screens, old previewResults, and stale
  // confirmedBatch from a previous file bleeding into the current one.
  resetWorkflow()
  templateChoice.value = 'smart'
  batchDetail.value = null
  batchFile.value = null
  loadError.value = null
  bulkDirection.value = 'unclassified'
  rowDirectionOverrides.value = new Map()

  isLoadingFile.value = true

  try {
    // 1. Load templates list WITHOUT auto-selecting (we select explicitly below)
    await loadTemplates()
    // After loadTemplates, the composable may have auto-selected templates[0].
    // We override that immediately so it's null until we explicitly assign.
    selectedTemplateId.value = null

    // 2. Reconstruct or verify uploadedFile
    const restored = await api.getFile(fileId)
    uploadedFile.value = restored

    // 3. If part of a batch session, load batch context and restore template
    if (batchSessionId.value) {
      try {
        batchDetail.value = await api.getBatchImport(batchSessionId.value)
        batchFile.value = batchDetail.value.files.find(f => f.source_file_id === fileId) || null
        if (batchFile.value?.template_id) {
          selectedTemplateId.value = batchFile.value.template_id
        }
      } catch {
        // Non-fatal if batch details cannot be fetched
      }
    }

    // 4. Restore an explicitly reviewed template (from suggestion draft) if present
    if (reviewedTemplateId.value !== null) {
      selectedTemplateId.value = reviewedTemplateId.value
      reviewedTemplateId.value = null
    }

    // 5. If we have a template selected, try to load a pre-existing batch review
    if (batchSessionId.value && selectedTemplateId.value) {
      try {
        previewResult.value = await api.getBatchReview(batchSessionId.value, fileId, selectedTemplateId.value)
        currentStep.value = 3
      } catch {
        // Fall back to template selection step
        currentStep.value = 2
      }
    } else {
      // No template assigned yet — stay on mapping/selection step
      currentStep.value = 2
    }
  } catch (err: any) {
    loadError.value = err?.message || 'Unable to load workbook review data.'
  } finally {
    isLoadingFile.value = false
  }
}

watch(
  () => route.params.fileId,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      initWorkbookReview()
    }
  }
)

onMounted(() => {
  initWorkbookReview()
})
</script>

<template>
  <main class="workbook-review container">
    <!-- ── Zen Header ──────────────────────────────────────────────────── -->
    <header class="review-header glass-card">
      <div class="header-top">
        <router-link to="/" class="back-link">
          <ArrowLeft :size="16" />
          Back to Ingestion
        </router-link>

        <!-- Queue Pagination / Navigation -->
        <div v-if="reviewableEntries.length > 1" class="queue-nav">
          <button
            class="queue-nav-btn"
            :disabled="!prevEntry"
            title="Previous file in queue"
            @click="prevEntry && goToEntry(prevEntry)"
          >
            <ArrowLeft :size="14" />
            Previous
          </button>
          <span class="queue-nav-counter">
            {{ currentIndex >= 0 ? currentIndex + 1 : '—' }} of {{ reviewableEntries.length }}
          </span>
          <button
            class="queue-nav-btn"
            :disabled="!nextEntry"
            title="Next file in queue"
            @click="nextEntry && goToEntry(nextEntry)"
          >
            Next
            <ArrowRight :size="14" />
          </button>
        </div>
      </div>

      <div class="header-main">
        <div class="file-identity">
          <div class="eyebrow">
            <FileSpreadsheet :size="15" />
            WORKBOOK REVIEW WORKSPACE
          </div>
          <h1>{{ fileDisplayName }}</h1>
          <p class="file-subtitle">
            Map columns, preview extracted records, inspect validation issues, and confirm import.
          </p>
        </div>

        <div class="file-badges">
          <span class="badge badge-neutral">XLSX</span>
          <span v-if="uploadedFile?.sheet_names?.length" class="badge badge-neutral">
            {{ uploadedFile.sheet_names.length }} Sheet{{ uploadedFile.sheet_names.length !== 1 ? 's' : '' }}
          </span>
          <span
            v-if="currentQueueEntry"
            class="badge"
            :class="{
              'badge-success': currentQueueEntry.status === 'imported' || currentQueueEntry.status === 'ready',
              'badge-warning': currentQueueEntry.status === 'needs_review',
              'badge-error': currentQueueEntry.status === 'failed',
            }"
          >
            {{ currentQueueEntry.status === 'needs_review' ? 'Needs Review' : currentQueueEntry.status }}
          </span>
        </div>
      </div>
    </header>

    <!-- ── Loading State ───────────────────────────────────────────────── -->
    <section v-if="isLoadingFile" class="glass-card state-card">
      <Loader2 :size="28" class="animate-spin" />
      <p>Loading workbook inspection and mapping data…</p>
    </section>

    <!-- ── Error State ─────────────────────────────────────────────────── -->
    <section v-else-if="loadError" class="glass-card state-card error-card">
      <AlertTriangle :size="32" class="error-icon" />
      <h2>Unable to Load Workbook</h2>
      <p>{{ loadError }}</p>
      <div class="state-actions">
        <router-link to="/" class="btn btn-secondary">
          <ArrowLeft :size="14" />
          Return to Queue
        </router-link>
        <button class="btn btn-primary" @click="initWorkbookReview">
          <RotateCcw :size="14" />
          Retry
        </button>
      </div>
    </section>

    <!-- ── Main Workspace ──────────────────────────────────────────────── -->
    <div v-else class="workspace-content">
      <!-- ── Step 1: Mapping & Template Selection ──────────────────────── -->
      <section v-if="currentStep <= 2 && uploadedFile" class="mapping-section">
        <SmartSuggestionsCard
          v-if="templateChoice === 'smart'"
          :file-id="uploadedFile.id"
          :disabled="isExtracting"
          @select="selectSuggestedTemplate"
          @manual="templateChoice = 'manual'"
        />

        <TemplateSelectorCard
          :templates="templates"
          :selected-template-id="selectedTemplateId"
          :uploaded-file="uploadedFile"
          :is-loading="isLoadingTemplates"
          :is-extracting="isExtracting"
          :error="templateError || extractError"
          :compact="templateChoice === 'smart' && Boolean(selectedTemplateId)"
          @update:selected-template-id="selectedTemplateId = $event"
          @change="templateChoice = 'manual'"
          @extract="handleExtract"
        />
      </section>

      <!-- ── Step 2 & 3: Extraction Preview & Validation ────────────────── -->
      <section v-if="currentStep >= 3 && previewResult" class="preview-section">
        <!-- Zen Invoice Summary Card -->
        <article class="glass-card summary-card">
          <div class="summary-header">
            <div>
              <span class="summary-eyebrow">EXTRACTED INVOICE SUMMARY</span>
              <h2 v-if="previewCompanyName || previewInvoiceNumber">
                <span v-if="previewCompanyName">{{ previewCompanyName }}</span>
                <span v-if="previewInvoiceNumber" class="summary-inv-num">
                  {{ previewInvoiceNumber }}
                </span>
              </h2>
              <h2 v-else>Extraction Preview</h2>
            </div>

            <div
              class="zen-overall-status"
              :class="{
                'zen-overall-status--success': !hasValidationErrors && warningCount === 0,
                'zen-overall-status--warning': !hasValidationErrors && warningCount > 0,
                'zen-overall-status--error': hasValidationErrors,
              }"
            >
              <CheckCircle2 v-if="!hasValidationErrors && warningCount === 0" :size="16" />
              <AlertTriangle v-else-if="!hasValidationErrors && warningCount > 0" :size="16" />
              <AlertCircle v-else :size="16" />
              <span>{{ overallStatusText }}</span>
            </div>
          </div>

          <div class="summary-grid">
            <div class="summary-field">
              <span class="field-label">Company</span>
              <strong class="field-value">{{ previewCompanyName || '—' }}</strong>
            </div>
            <div class="summary-field">
              <span class="field-label">Invoice Number</span>
              <strong class="field-value font-mono">{{ previewInvoiceNumber || '—' }}</strong>
            </div>
            <div class="summary-field">
              <span class="field-label">Invoice Date</span>
              <strong class="field-value">{{ previewInvoiceDate || '—' }}</strong>
            </div>
            <div class="summary-field">
              <span class="field-label">Currency</span>
              <strong class="field-value">{{ previewCurrency || '—' }}</strong>
            </div>
            <div class="summary-field">
              <span class="field-label">Total Amount</span>
              <strong class="field-value highlight font-mono">
                {{ previewTotalAmount ? `${previewCurrency || ''} ${previewTotalAmount}` : '—' }}
              </strong>
            </div>
          </div>
        </article>

        <!-- Line Items Table -->
        <ExtractionPreviewTable
          :fields="previewResult.fields"
          :target-worksheet="previewResult.target_worksheet"
          :is-multi-record="previewResult.is_multi_record"
          :records="previewResult.records"
          :has-line-items="previewResult.has_line_items"
          :line-items="previewResult.line_items"
        />

        <!-- Validation Issues Card -->
        <div
          v-if="previewResult.validation_report?.issues?.length"
          class="glass-card issues-card"
        >
          <div class="card-heading">
            <AlertTriangle :size="20" class="warning-icon" />
            <h3>Validation Issues ({{ previewResult.validation_report.issues.length }})</h3>
          </div>
          <div class="issues-list">
            <div
              v-for="(issue, index) in previewResult.validation_report.issues"
              :key="`${issue.rule_id}-${index}`"
              class="issue-item"
              :class="`issue-${issue.severity}`"
            >
              <AlertCircle :size="16" />
              <div class="issue-content">
                <strong
                  >{{ issue.rule_id }}<span v-if="issue.field_name"> — {{ issue.field_name }}</span></strong
                >
                <p>{{ issue.message }}</p>
                <small v-if="issue.cell_ref">Cell: {{ issue.worksheet }}!{{ issue.cell_ref }}</small>
              </div>
            </div>
          </div>
        </div>

        <!-- Extraction Errors Card -->
        <div v-if="previewResult.errors?.length" class="glass-card issues-card">
          <div class="card-heading error-heading">
            <AlertCircle :size="20" />
            <h3>Extraction Errors ({{ previewResult.errors.length }})</h3>
          </div>
          <div class="issues-list">
            <div
              v-for="(error, index) in previewResult.errors"
              :key="`${error.error_type}-${index}`"
              class="issue-item issue-error"
            >
              <AlertCircle :size="16" />
              <div class="issue-content">
                <strong>{{ error.error_type }}</strong>
                <p>{{ error.message }}</p>
                <small v-if="error.cell_ref">Cell: {{ error.worksheet }}!{{ error.cell_ref }}</small>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Financial Direction Classification Card ────────────────── -->
        <div class="glass-card direction-card">
          <div class="direction-card-header">
            <div class="direction-card-title">
              <TrendingUp :size="18" class="direction-icon" />
              <div>
                <span class="direction-eyebrow">FINANCIAL DIRECTION</span>
                <p class="direction-desc">
                  Classify these invoices to power direction-aware dashboard analytics.
                </p>
              </div>
            </div>
          </div>

          <!-- Bulk direction picker -->
          <div class="direction-bulk-row">
            <span class="bulk-label">
              {{ isMultiRecord ? 'Default for all records:' : 'Classification:' }}
            </span>
            <div class="direction-pill-group">
              <button
                v-for="opt in ([
                  { value: 'sales', label: 'Sales (AR)', icon: 'TrendingUp' },
                  { value: 'purchase', label: 'Purchase (AP)', icon: 'TrendingDown' },
                  { value: 'unclassified', label: 'Unclassified', icon: 'HelpCircle' },
                ] as const)"
                :key="opt.value"
                type="button"
                class="direction-pill"
                :class="{
                  'direction-pill--sales': opt.value === 'sales' && bulkDirection === opt.value,
                  'direction-pill--purchase': opt.value === 'purchase' && bulkDirection === opt.value,
                  'direction-pill--unclassified': opt.value === 'unclassified' && bulkDirection === opt.value,
                  'direction-pill--active': bulkDirection === opt.value,
                }"
                @click="bulkDirection = opt.value; clearRowOverrides()"
              >
                <TrendingUp v-if="opt.value === 'sales'" :size="13" />
                <TrendingDown v-else-if="opt.value === 'purchase'" :size="13" />
                <HelpCircle v-else :size="13" />
                {{ opt.label }}
              </button>
            </div>
          </div>

          <!-- Per-row overrides (only for multi-record workbooks) -->
          <div v-if="isMultiRecord && previewResult?.records?.length" class="direction-row-overrides">
            <div class="row-overrides-header">
              <span class="row-overrides-label">Per-record overrides</span>
              <button
                v-if="rowDirectionsList.length > 0"
                type="button"
                class="btn-reset-overrides"
                @click="clearRowOverrides"
              >
                Reset all to default
              </button>
            </div>
            <div class="row-overrides-table-wrapper">
              <table class="row-overrides-table">
                <thead>
                  <tr>
                    <th class="rot-row">Row</th>
                    <th class="rot-company">Company</th>
                    <th class="rot-invnum">Invoice #</th>
                    <th class="rot-direction">Direction</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="rec in previewResult.records"
                    :key="rec.source_row_number"
                    :class="{ 'row-overridden': rowDirectionOverrides.has(rec.source_row_number) && rowDirectionOverrides.get(rec.source_row_number) !== bulkDirection }"
                  >
                    <td class="rot-row">{{ rec.source_row_number }}</td>
                    <td class="rot-company">
                      {{ rec.normalized_data?.company_name || '—' }}
                    </td>
                    <td class="rot-invnum font-mono">
                      {{ rec.normalized_data?.invoice_number || '—' }}
                    </td>
                    <td class="rot-direction">
                      <div class="direction-inline-pills">
                        <button
                          v-for="opt in (['sales', 'purchase', 'unclassified'] as const)"
                          :key="opt"
                          type="button"
                          class="direction-inline-pill"
                          :class="{
                            'dip--sales': opt === 'sales' && effectiveRowDirection(rec.source_row_number) === opt,
                            'dip--purchase': opt === 'purchase' && effectiveRowDirection(rec.source_row_number) === opt,
                            'dip--unclassified': opt === 'unclassified' && effectiveRowDirection(rec.source_row_number) === opt,
                            'dip--active': effectiveRowDirection(rec.source_row_number) === opt,
                          }"
                          @click="setRowDirection(rec.source_row_number, opt)"
                        >
                          {{ opt === 'sales' ? 'Sales' : opt === 'purchase' ? 'Purchase' : 'Unclassified' }}
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- ── Sticky Bottom Confirmation Bar ──────────────────────────── -->
        <aside class="sticky-confirm-bar glass-card">
          <div class="confirm-bar-left">
            <div
              class="confirm-status-pill"
              :class="{
                'pill-success': !hasValidationErrors && warningCount === 0,
                'pill-warning': !hasValidationErrors && warningCount > 0,
                'pill-error': hasValidationErrors,
              }"
            >
              <CheckCircle2 v-if="!hasValidationErrors && warningCount === 0" :size="15" />
              <AlertTriangle v-else-if="!hasValidationErrors && warningCount > 0" :size="15" />
              <AlertCircle v-else :size="15" />
              <span>{{ overallStatusText }}</span>
            </div>

            <label
              v-if="warningCount > 0 && !hasValidationErrors"
              class="warning-ack-checkbox"
            >
              <input v-model="userAcknowledgedWarnings" type="checkbox" />
              <span>I acknowledge the {{ warningCount }} validation warning(s).</span>
            </label>
          </div>

          <div class="confirm-bar-actions">
            <button
              class="btn btn-secondary btn-small"
              :disabled="isConfirming"
              @click="currentStep = 2"
            >
              Change Mapping
            </button>

            <button
              class="btn btn-primary btn-small"
              :disabled="!canConfirm || isConfirming"
              @click="handleConfirm"
            >
              <Loader2 v-if="isConfirming" class="animate-spin" :size="15" />
              <span v-else>Confirm Import</span>
            </button>
          </div>
        </aside>
      </section>

      <!-- ── Step 4: Import Success Screen ─────────────────────────────── -->
      <section v-if="currentStep === 4 && confirmedBatch" class="glass-card success-card">
        <CheckCircle2 :size="48" class="success-icon" />
        <div class="eyebrow success-eyebrow">
          <CheckCircle2 :size="15" />
          IMPORT COMPLETE
        </div>
        <h2>Workbook Imported Successfully</h2>
        <p class="success-desc">
          Your file has been verified, normalized, and saved to the persistent database.
        </p>

        <div class="success-metrics">
          <div class="metric-box">
            <span class="metric-label">Batch ID</span>
            <strong>#{{ confirmedBatch.id }}</strong>
          </div>
          <div class="metric-box">
            <span class="metric-label">Records</span>
            <strong>{{ confirmedBatch.record_count }}</strong>
          </div>
          <div class="metric-box">
            <span class="metric-label">Warnings</span>
            <strong>{{ confirmedBatch.warning_count }}</strong>
          </div>
          <div class="metric-box">
            <span class="metric-label">Status</span>
            <strong class="success-text">{{ confirmedBatch.status }}</strong>
          </div>
        </div>

        <div class="success-actions">
          <router-link to="/" class="btn btn-secondary">
            Return to Ingestion Studio
          </router-link>
          <button
            v-if="nextEntry"
            class="btn btn-primary"
            @click="goToEntry(nextEntry)"
          >
            Review Next File
            <ChevronRight :size="16" />
          </button>
          <router-link v-else to="/history" class="btn btn-primary">
            View in History
            <ChevronRight :size="16" />
          </router-link>
        </div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.workbook-review {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  padding-block: 2rem;
  max-width: 1400px;
  margin-inline: auto;
}

/* ── Header ──────────────────────────────────────────────────────── */
.review-header {
  padding: 1.5rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.back-link {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.88rem;
  font-weight: 600;
  text-decoration: none;
  transition: color 0.15s ease;
}

.back-link:hover {
  color: var(--accent-brand);
}

.queue-nav {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--border-subtle);
  border-radius: 9999px;
  padding: 0.25rem 0.5rem;
}

.queue-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.2rem 0.5rem;
  border-radius: 9999px;
  transition: background 0.15s ease, color 0.15s ease;
}

.queue-nav-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-primary);
}

.queue-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.queue-nav-counter {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted);
  padding-inline: 0.25rem;
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.file-identity {
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

.file-identity h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.75rem;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.file-subtitle {
  margin: 0.35rem 0 0 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.file-badges {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

/* ── State Cards ─────────────────────────────────────────────────── */
.state-card {
  padding: 3rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1rem;
}

.error-card {
  border-color: rgba(239, 68, 68, 0.4);
}

.error-icon {
  color: #ef4444;
}

.state-actions {
  display: flex;
  gap: 0.75rem;
  margin-top: 1rem;
}

/* ── Main Workspace ──────────────────────────────────────────────── */
.workspace-content {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.mapping-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.preview-section {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* ── Summary Card ────────────────────────────────────────────────── */
.summary-card {
  padding: 1.5rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  flex-wrap: wrap;
}

.summary-eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.summary-header h2 {
  margin: 0.25rem 0 0 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text-primary);
}

.summary-inv-num {
  margin-left: 0.5rem;
  font-family: var(--font-mono, monospace);
  font-size: 0.9em;
  color: var(--accent-brand);
}

.zen-overall-status {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.8rem;
  font-weight: 700;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.06));
}

.zen-overall-status--success {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.zen-overall-status--warning {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}

.zen-overall-status--error {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border-subtle);
}

.summary-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.field-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.field-value {
  font-size: 0.95rem;
  color: var(--text-primary);
}

.field-value.highlight {
  color: var(--accent-brand);
  font-weight: 700;
}

.font-mono {
  font-family: var(--font-mono, monospace);
}

/* ── Issues & Errors Cards ───────────────────────────────────────── */
.issues-card {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.card-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.card-heading h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.warning-icon {
  color: #f59e0b;
}

.error-heading {
  color: #ef4444;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.issue-item {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.75rem 1rem;
  border-radius: 8px;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.03));
  border-left: 3px solid transparent;
}

.issue-warning {
  border-left-color: #f59e0b;
  color: #f59e0b;
}

.issue-error {
  border-left-color: #ef4444;
  color: #ef4444;
}

.issue-content {
  color: var(--text-primary);
  font-size: 0.85rem;
}

.issue-content p {
  margin: 0.2rem 0;
  color: var(--text-secondary);
}

.issue-content small {
  color: var(--text-muted);
  font-family: var(--font-mono, monospace);
}

/* ── Sticky Bottom Confirmation Bar ─────────────────────────────── */
.sticky-confirm-bar {
  position: sticky;
  bottom: 1.5rem;
  z-index: 20;
  padding: 1rem 1.75rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-focus, rgba(249, 115, 22, 0.4));
  backdrop-filter: blur(12px);
}

.confirm-bar-left {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  flex-wrap: wrap;
}

.confirm-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  font-weight: 700;
  padding: 0.3rem 0.65rem;
  border-radius: 9999px;
}

.pill-success {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.pill-warning {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.pill-error {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.warning-ack-checkbox {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.warning-ack-checkbox input {
  accent-color: var(--accent-brand);
  width: 15px;
  height: 15px;
  cursor: pointer;
}

.confirm-bar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

/* ── Success Screen ──────────────────────────────────────────────── */
.success-card {
  padding: 3.5rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1.25rem;
}

.success-icon {
  color: #22c55e;
}

.success-eyebrow {
  color: #22c55e;
}

.success-card h2 {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.success-desc {
  max-width: 500px;
  color: var(--text-secondary);
  margin: 0;
}

.success-metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.5rem;
  margin-top: 1rem;
  margin-bottom: 1rem;
  width: 100%;
  max-width: 600px;
}

.metric-box {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 1rem;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.04));
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
}

.metric-label {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
}

.success-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
}

/* ── Direction Classification Card ───────────────────────────────── */
.direction-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.direction-card-header {
  display: flex;
  align-items: flex-start;
}

.direction-card-title {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
}

.direction-icon {
  color: var(--accent-brand);
  flex-shrink: 0;
  margin-top: 2px;
}

.direction-eyebrow {
  display: block;
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--accent-brand);
  margin-bottom: 0.2rem;
}

.direction-desc {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.direction-bulk-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.bulk-label {
  font-size: 0.83rem;
  font-weight: 600;
  color: var(--text-secondary);
  white-space: nowrap;
}

.direction-pill-group {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.direction-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.85rem;
  border-radius: 9999px;
  border: 1.5px solid var(--border-medium);
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.direction-pill:hover:not(.direction-pill--active) {
  border-color: var(--accent-brand);
  color: var(--accent-brand);
  background: var(--accent-soft, rgba(99, 102, 241, 0.06));
}

.direction-pill--active {
  border-color: currentColor;
}

.direction-pill--sales.direction-pill--active {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.4);
}

.direction-pill--purchase.direction-pill--active {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.4);
}

.direction-pill--unclassified.direction-pill--active {
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-muted);
  border-color: var(--border-medium);
}

/* Per-row overrides */
.direction-row-overrides {
  border-top: 1px solid var(--border-subtle);
  padding-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.row-overrides-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.row-overrides-label {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.btn-reset-overrides {
  font-size: 0.75rem;
  color: var(--accent-brand);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
  font-weight: 600;
  text-decoration: underline;
  text-decoration-color: transparent;
  transition: text-decoration-color 0.15s;
}

.btn-reset-overrides:hover {
  text-decoration-color: var(--accent-brand);
}

.row-overrides-table-wrapper {
  overflow-x: auto;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.row-overrides-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.83rem;
}

.row-overrides-table th {
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.row-overrides-table td {
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

.row-overrides-table tbody tr:last-child td {
  border-bottom: none;
}

.row-overrides-table tbody tr.row-overridden {
  background: rgba(99, 102, 241, 0.04);
}

.rot-row { width: 60px; color: var(--text-muted); }
.rot-company { min-width: 140px; }
.rot-invnum { min-width: 120px; font-family: monospace; }
.rot-direction { width: auto; }

.direction-inline-pills {
  display: flex;
  gap: 0.3rem;
  flex-wrap: nowrap;
}

.direction-inline-pill {
  padding: 0.2rem 0.55rem;
  border-radius: 9999px;
  border: 1px solid var(--border-subtle);
  background: transparent;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.12s ease;
}

.direction-inline-pill:hover:not(.dip--active) {
  border-color: var(--accent-brand);
  color: var(--accent-brand);
}

.dip--sales.dip--active {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
  border-color: rgba(34, 197, 94, 0.5);
}

.dip--purchase.dip--active {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-color: rgba(239, 68, 68, 0.5);
}

.dip--unclassified.dip--active {
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-muted);
  border-color: var(--border-medium);
}
</style>
