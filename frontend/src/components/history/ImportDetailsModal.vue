<script setup lang="ts">
import { ref } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code,
  Edit2,
  FileSpreadsheet,
  Loader2,
  Save,
  Trash2,
  X,
} from 'lucide-vue-next'

import type {
  ImportBatchDetail,
  InvoiceRecordRead,
  InvoiceRecordUpdate,
} from '@/types/api'

defineProps<{
  importBatch: ImportBatchDetail
  isDeleting?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'delete', batch: ImportBatchDetail): void
  (e: 'save-record', payload: { recordId: number; form: InvoiceRecordUpdate }): void
}>()

// ── Technical Disclosure State ──────────────────────────────────────────────
const showTechnicalDetails = ref(false)

// ── Edit Record State ───────────────────────────────────────────────────────
const editingRecordId = ref<number | null>(null)
const editForm = ref<InvoiceRecordUpdate>({})
const isSavingEdit = ref(false)
const editError = ref('')

function startEdit(record: InvoiceRecordRead) {
  editingRecordId.value = record.id
  editForm.value = {
    company_name: record.company_name,
    invoice_number: record.invoice_number,
    invoice_date: record.invoice_date ?? null,
    total_amount: record.total_amount ?? null,
    currency: record.currency ?? null,
  }
  editError.value = ''
}

function cancelEdit() {
  editingRecordId.value = null
  editForm.value = {}
  editError.value = ''
}

async function handleSaveRecord(recordId: number) {
  isSavingEdit.value = true
  editError.value = ''
  try {
    emit('save-record', { recordId, form: editForm.value })
    editingRecordId.value = null
    editForm.value = {}
  } catch (err: any) {
    editError.value = err.message || 'Failed to save changes.'
  } finally {
    isSavingEdit.value = false
  }
}

// ── Formatters (PRESENTATION ONLY) ──────────────────────────────────────────

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

function formatDateTime(dateStr?: string | null): string {
  if (!dateStr) return '—'
  const date = new Date(dateStr)
  if (isNaN(date.getTime())) return dateStr
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

function parseNumeric(val: any): number | null {
  if (val === null || val === undefined || val === '') return null
  if (typeof val === 'number') return isNaN(val) ? null : val
  if (typeof val === 'string') {
    const cleaned = val.trim().replace(/,/g, '')
    const parsed = Number(cleaned)
    return isNaN(parsed) ? null : parsed
  }
  return null
}

function formatNumber(val: number): string {
  return val.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatCurrency(val: any, currency?: string | null): string {
  const num = parseNumeric(val)
  if (num === null) return String(val ?? '—')
  const formatted = formatNumber(num)
  return currency ? `${currency} ${formatted}` : formatted
}

function friendlyLabel(key: string): string {
  const map: Record<string, string> = {
    due_date: 'Due Date',
    sub_total: 'Subtotal',
    subtotal: 'Subtotal',
    tax_rate: 'Tax Rate',
    tax_amount: 'Tax Amount',
    tax: 'Tax',
    total_amount: 'Total Amount',
    grand_total: 'Grand Total',
    invoice_date: 'Invoice Date',
    company_name: 'Company',
    invoice_number: 'Invoice Number',
    purchase_order_number: 'PO Number',
    po_number: 'PO Number',
    payment_terms: 'Payment Terms',
    shipping_amount: 'Shipping',
    discount: 'Discount',
  }
  return map[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function isDateValue(key: string, val: any): boolean {
  if (key.includes('date')) return true
  if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}/.test(val.trim())) return true
  return false
}

function isMoneyKey(key: string): boolean {
  const moneyKeys = [
    'sub_total',
    'subtotal',
    'tax',
    'tax_amount',
    'tax_rate',
    'total',
    'total_amount',
    'grand_total',
    'amount',
    'discount',
    'shipping_amount',
  ]
  return moneyKeys.includes(key.toLowerCase())
}

// ── Line Items Helpers ──────────────────────────────────────────────────────

function getLineItemColumns(record: InvoiceRecordRead) {
  const items = record.line_items || []
  if (items.length === 0) return []

  const hasQty = items.some((li) => li.quantity !== null && li.quantity !== undefined)
  const hasUnitPrice = items.some((li) => li.unit_price !== null && li.unit_price !== undefined)
  const hasTax = items.some((li) => li.tax_rate !== null || li.tax_amount !== null)
  const hasAmount = items.some((li) => li.amount !== null && li.amount !== undefined)

  const cols = [{ key: 'description', label: 'Description', numeric: false }]
  if (hasQty) cols.push({ key: 'quantity', label: 'Qty', numeric: true })
  if (hasUnitPrice) cols.push({ key: 'unit_price', label: 'Unit Price', numeric: true })
  if (hasTax) cols.push({ key: 'tax', label: 'Tax', numeric: true })
  if (hasAmount) cols.push({ key: 'amount', label: 'Amount', numeric: true })

  return cols
}

function formatLineItemCell(key: string, item: any, currency?: string | null): string {
  if (key === 'description') return item.description || '—'
  if (key === 'quantity') return item.quantity !== null && item.quantity !== undefined ? item.quantity.toLocaleString() : '—'
  if (key === 'unit_price') return item.unit_price !== null && item.unit_price !== undefined ? formatCurrency(item.unit_price, currency) : '—'
  if (key === 'tax') {
    if (item.tax_amount !== null && item.tax_amount !== undefined) return formatCurrency(item.tax_amount, currency)
    if (item.tax_rate !== null && item.tax_rate !== undefined) return `${item.tax_rate}%`
    return '—'
  }
  if (key === 'amount') return item.amount !== null && item.amount !== undefined ? formatCurrency(item.amount, currency) : '—'
  return '—'
}

// ── Custom Field Breakdown per Record ───────────────────────────────────────

function getRecordInfoFields(record: InvoiceRecordRead) {
  const entries: Array<{ key: string; label: string; value: string }> = []
  if (record.invoice_date) {
    entries.push({ key: 'invoice_date', label: 'Invoice Date', value: formatDate(record.invoice_date) })
  }
  if (record.currency) {
    entries.push({ key: 'currency', label: 'Currency', value: record.currency })
  }
  if (record.custom_fields) {
    for (const [key, val] of Object.entries(record.custom_fields)) {
      if (val === null || val === undefined) continue
      if (!isMoneyKey(key)) {
        const formattedVal = isDateValue(key, val) ? formatDate(String(val)) : String(val)
        entries.push({ key, label: friendlyLabel(key), value: formattedVal })
      }
    }
  }
  return entries
}

function getRecordMoneyFields(record: InvoiceRecordRead) {
  const entries: Array<{ key: string; label: string; value: string; isTotal: boolean }> = []

  if (record.custom_fields) {
    for (const [key, val] of Object.entries(record.custom_fields)) {
      if (val === null || val === undefined) continue
      if (isMoneyKey(key)) {
        const isTotal = ['total', 'total_amount', 'grand_total'].includes(key.toLowerCase())
        entries.push({
          key,
          label: friendlyLabel(key),
          value: formatCurrency(val, record.currency),
          isTotal,
        })
      }
    }
  }

  // Add canonical total_amount if explicitly non-null
  if (record.total_amount !== null && record.total_amount !== undefined) {
    entries.push({
      key: 'total_amount',
      label: 'Total Amount',
      value: formatCurrency(record.total_amount, record.currency),
      isTotal: true,
    })
  }

  return entries
}
</script>

<template>
  <div class="zen-modal-backdrop" @click.self="emit('close')">
    <div class="zen-modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <!-- ── Modal Header ─────────────────────────────────────────────── -->
      <header class="zen-modal-header">
        <div class="zen-header-main">
          <div class="zen-eyebrow">
            <FileSpreadsheet :size="14" />
            <span>IMPORT DETAILS</span>
          </div>

          <h2 id="modal-title" class="zen-filename" :title="importBatch.original_filename">
            {{ importBatch.original_filename }}
          </h2>

          <div class="zen-timestamp">
            Imported {{ formatDateTime(importBatch.imported_at) }}
          </div>

          <!-- Compact Batch Metadata Bar -->
          <div class="zen-meta-bar">
            <span class="zen-meta-chip">Batch #{{ importBatch.id }}</span>
            <span class="zen-meta-dot">•</span>
            <span class="zen-meta-chip">{{ importBatch.template_name }}</span>
            <span class="zen-meta-dot">•</span>
            <span class="zen-status-badge" :class="`status--${importBatch.status.toLowerCase()}`">
              {{ importBatch.status }}
            </span>
            <span v-if="importBatch.record_count > 0" class="zen-meta-chip">
              {{ importBatch.record_count }} record{{ importBatch.record_count > 1 ? 's' : '' }}
            </span>
            <span
              v-if="importBatch.warning_count > 0"
              class="zen-warning-chip"
            >
              <AlertTriangle :size="12" />
              {{ importBatch.warning_count }} warning{{ importBatch.warning_count > 1 ? 's' : '' }}
            </span>
          </div>
        </div>

        <button
          class="zen-close-btn"
          type="button"
          aria-label="Close dialog"
          @click="emit('close')"
        >
          <X :size="18" />
        </button>
      </header>

      <div class="zen-separator"></div>

      <!-- ── Modal Body ──────────────────────────────────────────────── -->
      <div class="zen-modal-body">
        <!-- Records List -->
        <div v-if="importBatch.invoice_records.length === 0" class="zen-empty-records">
          <p class="text-muted">No records available for this batch.</p>
        </div>

        <div v-else class="zen-records-list">
          <article
            v-for="record in importBatch.invoice_records"
            :key="record.id"
            class="zen-record-card"
          >
            <!-- ── EDIT FORM MODE ────────────────────────────────────── -->
            <div v-if="editingRecordId === record.id" class="zen-edit-form">
              <div class="edit-form-header">
                <h3>Edit Record #{{ record.id }}</h3>
                <span class="muted-text">Update canonical values</span>
              </div>

              <div v-if="editError" class="zen-notice zen-notice--error">
                <AlertCircle :size="14" />
                <span>{{ editError }}</span>
              </div>

              <div class="edit-form-grid">
                <label class="form-group">
                  <span>Company Name</span>
                  <input v-model="editForm.company_name" type="text" class="zen-input" />
                </label>

                <label class="form-group">
                  <span>Invoice Number</span>
                  <input v-model="editForm.invoice_number" type="text" class="zen-input" />
                </label>

                <label class="form-group">
                  <span>Invoice Date</span>
                  <input v-model="editForm.invoice_date" type="text" class="zen-input" placeholder="YYYY-MM-DD" />
                </label>

                <label class="form-group">
                  <span>Total Amount</span>
                  <input v-model.number="editForm.total_amount" type="number" step="0.01" class="zen-input" placeholder="0.00" />
                </label>

                <label class="form-group">
                  <span>Currency</span>
                  <input v-model="editForm.currency" type="text" class="zen-input" placeholder="e.g. MYR, USD" />
                </label>
              </div>

              <div class="edit-form-actions">
                <button
                  class="btn btn-secondary btn-small"
                  type="button"
                  :disabled="isSavingEdit"
                  @click="cancelEdit"
                >
                  Cancel
                </button>
                <button
                  class="btn btn-primary btn-small"
                  type="button"
                  :disabled="isSavingEdit"
                  @click="handleSaveRecord(record.id)"
                >
                  <Loader2 v-if="isSavingEdit" :size="13" class="animate-spin" />
                  <Save v-else :size="13" />
                  <span>{{ isSavingEdit ? 'Saving...' : 'Save Changes' }}</span>
                </button>
              </div>
            </div>

            <!-- ── VIEW MODE ─────────────────────────────────────────── -->
            <div v-else class="zen-record-view">
              <!-- Record Title Bar -->
              <div class="zen-record-header">
                <div>
                  <h3 class="zen-company-title">{{ record.company_name }}</h3>
                  <div class="zen-invoice-number">
                    Invoice {{ record.invoice_number }}
                    <span v-if="record.source_worksheet" class="zen-worksheet-tag">
                      {{ record.source_worksheet }}
                      <template v-if="record.source_row_number">#{{ record.source_row_number }}</template>
                    </span>
                  </div>
                </div>

                <button
                  class="btn btn-secondary btn-small"
                  type="button"
                  title="Edit Record"
                  @click="startEdit(record)"
                >
                  <Edit2 :size="13" />
                  <span>Edit</span>
                </button>
              </div>

              <!-- Record Details Section -->
              <div class="zen-details-block">
                <div class="zen-block-title">Invoice Details</div>
                <div class="zen-separator--subtle"></div>

                <div class="zen-details-grid">
                  <!-- Info Fields -->
                  <div class="zen-info-col">
                    <div
                      v-for="entry in getRecordInfoFields(record)"
                      :key="entry.key"
                      class="zen-detail-row"
                    >
                      <span class="zen-label">{{ entry.label }}</span>
                      <span class="zen-value">{{ entry.value }}</span>
                    </div>
                  </div>

                  <!-- Financial Summary Fields -->
                  <div v-if="getRecordMoneyFields(record).length > 0" class="zen-money-col">
                    <div
                      v-for="entry in getRecordMoneyFields(record)"
                      :key="entry.key"
                      class="zen-money-row"
                      :class="{ 'zen-money-row--total': entry.isTotal }"
                    >
                      <span class="zen-money-label">{{ entry.label }}</span>
                      <span class="zen-money-value">{{ entry.value }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Line Items Section -->
              <div v-if="record.line_items && record.line_items.length > 0" class="zen-line-items-block">
                <div class="line-items-header">
                  <div class="zen-block-title">Line Items</div>
                  <span class="zen-count-chip">{{ record.line_items.length }} item{{ record.line_items.length > 1 ? 's' : '' }}</span>
                </div>
                <div class="zen-separator--subtle"></div>

                <div class="line-items-table-wrapper">
                  <table class="zen-business-table" aria-label="Line items">
                    <thead>
                      <tr>
                        <th
                          v-for="col in getLineItemColumns(record)"
                          :key="col.key"
                          :class="{ 'col-numeric': col.numeric }"
                        >
                          {{ col.label }}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in record.line_items" :key="item.id">
                        <td
                          v-for="col in getLineItemColumns(record)"
                          :key="col.key"
                          :class="{ 'col-numeric': col.numeric }"
                        >
                          {{ formatLineItemCell(col.key, item, record.currency) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </article>
        </div>

        <!-- ── Validation Section ────────────────────────────────────── -->
        <div class="zen-validation-section">
          <div v-if="importBatch.validation_issues.length === 0" class="zen-validation-quiet">
            <CheckCircle2 :size="15" class="text-success" />
            <span>No validation issues</span>
          </div>

          <div v-else class="zen-validation-issues">
            <div class="zen-block-title text-warning">
              <AlertTriangle :size="15" />
              <span>Validation Issues ({{ importBatch.validation_issues.length }})</span>
            </div>
            <div class="issues-list">
              <div
                v-for="issue in importBatch.validation_issues"
                :key="issue.id"
                class="issue-card"
                :class="`issue-card--${issue.severity}`"
              >
                <div class="issue-main">
                  <strong class="issue-rule">{{ issue.rule_id }}</strong>
                  <span class="issue-msg">{{ issue.message }}</span>
                  <span v-if="issue.cell_ref" class="issue-ref mono">
                    {{ issue.worksheet ? `${issue.worksheet}!` : '' }}{{ issue.cell_ref }}
                  </span>
                </div>
                <span class="issue-severity-pill" :class="`pill--${issue.severity}`">
                  {{ issue.severity }}
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- ── Progressive Technical Disclosure ───────────────────────── -->
        <div v-if="importBatch.raw_data && Object.keys(importBatch.raw_data).length > 0" class="zen-technical-disclosure">
          <button
            class="disclosure-toggle"
            type="button"
            :aria-expanded="showTechnicalDetails"
            @click="showTechnicalDetails = !showTechnicalDetails"
          >
            <component :is="showTechnicalDetails ? ChevronDown : ChevronRight" :size="14" />
            <span>{{ showTechnicalDetails ? 'Hide' : 'Show' }} technical details</span>
          </button>

          <div v-if="showTechnicalDetails" class="technical-panel">
            <div class="technical-panel-title">
              <Code :size="13" />
              <span>Raw Sheet Formulas & Data</span>
            </div>
            <div class="raw-data-grid">
              <div
                v-for="(val, key) in importBatch.raw_data"
                :key="key"
                class="raw-item"
              >
                <span class="raw-key mono">{{ key }}:</span>
                <span class="raw-val mono">{{ val }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Modal Footer ────────────────────────────────────────────── -->
      <footer class="zen-modal-footer">
        <button
          class="btn btn-danger btn-small"
          type="button"
          :disabled="isDeleting"
          @click="emit('delete', importBatch)"
        >
          <Trash2 :size="14" />
          <span>Delete Import</span>
        </button>

        <button
          class="btn btn-secondary"
          type="button"
          @click="emit('close')"
        >
          Close
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
/* ── Modal Backdrop & Shell ───────────────────────────────────────── */

.zen-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: rgba(10, 14, 23, 0.75);
  backdrop-filter: blur(8px);
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.zen-modal {
  width: 100%;
  max-width: 820px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-surface, #141b2d);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
  border-radius: var(--radius-lg, 12px);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.4);
  overflow: hidden;
  animation: scaleIn 0.2s ease-out;
}

@keyframes scaleIn {
  from { transform: scale(0.97); opacity: 0; }
  to { transform: scale(1); opacity: 1; }
}

/* ── Modal Header ─────────────────────────────────────────────────── */

.zen-modal-header {
  padding: 1.5rem 1.75rem 1.25rem;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.zen-header-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.zen-eyebrow {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--accent-brand, #6366f1);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.zen-filename {
  margin: 0;
  color: var(--text-primary, #f8fafc);
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  word-break: break-all;
}

.zen-timestamp {
  color: var(--text-muted, #94a3b8);
  font-size: 0.82rem;
}

.zen-meta-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.4rem;
  font-size: 0.8rem;
}

.zen-meta-chip {
  color: var(--text-secondary, #cbd5e1);
  font-weight: 500;
}

.zen-meta-dot {
  color: var(--text-muted, #64748b);
  font-size: 0.7rem;
}

.zen-status-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.55rem;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.73rem;
  font-weight: 600;
  text-transform: capitalize;
  background: var(--bg-subtle, rgba(255, 255, 255, 0.05));
  color: var(--text-secondary, #cbd5e1);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
}

.status--imported,
.status--success,
.status--completed {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.2);
}

.status--failed,
.status--error {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.2);
}

.zen-warning-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.15rem 0.55rem;
  border-radius: var(--radius-full, 9999px);
  font-size: 0.73rem;
  font-weight: 600;
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.zen-close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: none;
  background: transparent;
  color: var(--text-muted, #94a3b8);
  border-radius: var(--radius-md, 6px);
  cursor: pointer;
  transition: all 0.15s ease;
}

.zen-close-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary, #f8fafc);
}

/* ── Dividers ─────────────────────────────────────────────────────── */

.zen-separator {
  height: 1px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.08));
  width: 100%;
}

.zen-separator--subtle {
  height: 1px;
  background: var(--border-subtle, rgba(255, 255, 255, 0.05));
  margin: 0.6rem 0 1rem;
}

/* ── Modal Body ───────────────────────────────────────────────────── */

.zen-modal-body {
  padding: 1.5rem 1.75rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* ── Record Card View ─────────────────────────────────────────────── */

.zen-records-list {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.zen-record-card {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 1.25rem 1.5rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-md, 8px);
}

.zen-record-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.zen-company-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary, #f8fafc);
  letter-spacing: -0.01em;
}

.zen-invoice-number {
  margin-top: 0.2rem;
  font-size: 0.88rem;
  color: var(--text-secondary, #cbd5e1);
  font-weight: 500;
}

.zen-worksheet-tag {
  margin-left: 0.4rem;
  padding: 0.1rem 0.4rem;
  background: rgba(255, 255, 255, 0.04);
  border-radius: var(--radius-sm, 4px);
  color: var(--text-muted, #94a3b8);
  font-size: 0.75rem;
  font-family: var(--font-mono, monospace);
}

/* ── Details Block ────────────────────────────────────────────────── */

.zen-block-title {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.zen-details-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.5rem;
}

@media (max-width: 640px) {
  .zen-details-grid {
    grid-template-columns: 1fr;
  }
}

.zen-info-col,
.zen-money-col {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.zen-detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.85rem;
}

.zen-label {
  color: var(--text-muted, #94a3b8);
}

.zen-value {
  color: var(--text-primary, #f8fafc);
  font-weight: 500;
}

.zen-money-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.85rem;
  padding: 0.2rem 0;
}

.zen-money-label {
  color: var(--text-secondary, #cbd5e1);
}

.zen-money-value {
  color: var(--text-primary, #f8fafc);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.zen-money-row--total {
  margin-top: 0.4rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
}

.zen-money-row--total .zen-money-label {
  font-weight: 700;
  color: var(--text-primary, #f8fafc);
}

.zen-money-row--total .zen-money-value {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--accent-brand, #6366f1);
}

/* ── Line Items Block ─────────────────────────────────────────────── */

.line-items-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.zen-count-chip {
  font-size: 0.75rem;
  padding: 0.1rem 0.5rem;
  border-radius: var(--radius-full, 9999px);
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-muted, #94a3b8);
  font-weight: 500;
}

.line-items-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-md, 6px);
}

.zen-business-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.zen-business-table th {
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-muted, #94a3b8);
  font-weight: 600;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.65rem 1rem;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  text-align: left;
}

.zen-business-table th.col-numeric {
  text-align: right;
}

.zen-business-table td {
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.04));
  color: var(--text-primary, #f8fafc);
}

.zen-business-table td.col-numeric {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.zen-business-table tr:last-child td {
  border-bottom: none;
}

/* ── Validation Section ───────────────────────────────────────────── */

.zen-validation-quiet {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(16, 185, 129, 0.05);
  border: 1px solid rgba(16, 185, 129, 0.15);
  border-radius: var(--radius-md, 6px);
  color: #34d399;
  font-size: 0.85rem;
  font-weight: 500;
}

.zen-validation-issues {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.issue-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-md, 6px);
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  font-size: 0.85rem;
}

.issue-card--warning {
  border-color: rgba(245, 158, 11, 0.25);
  background: rgba(245, 158, 11, 0.03);
}

.issue-card--error {
  border-color: rgba(239, 68, 68, 0.25);
  background: rgba(239, 68, 68, 0.03);
}

.issue-main {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.issue-rule {
  color: var(--text-primary, #f8fafc);
  font-size: 0.8rem;
}

.issue-msg {
  color: var(--text-secondary, #cbd5e1);
}

.issue-ref {
  font-size: 0.75rem;
  color: var(--text-muted, #94a3b8);
}

.issue-severity-pill {
  padding: 0.1rem 0.45rem;
  border-radius: var(--radius-sm, 4px);
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
}

.pill--warning {
  background: rgba(245, 158, 11, 0.15);
  color: #fbbf24;
}

.pill--error {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

.pill--info {
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
}

/* ── Technical Disclosure ─────────────────────────────────────────── */

.disclosure-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: transparent;
  border: none;
  color: var(--text-muted, #94a3b8);
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  padding: 0;
  transition: color 0.15s ease;
}

.disclosure-toggle:hover {
  color: var(--text-secondary, #cbd5e1);
}

.technical-panel {
  margin-top: 0.75rem;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
  border-radius: var(--radius-md, 6px);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.technical-panel-title {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-muted, #94a3b8);
  text-transform: uppercase;
}

.raw-data-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem 1rem;
}

@media (max-width: 640px) {
  .raw-data-grid {
    grid-template-columns: 1fr;
  }
}

.raw-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.78rem;
}

.raw-key {
  color: var(--text-muted, #64748b);
}

.raw-val {
  color: var(--text-secondary, #cbd5e1);
}

/* ── Inline Edit Form ─────────────────────────────────────────────── */

.zen-edit-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0.5rem 0;
}

.edit-form-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--text-primary, #f8fafc);
}

.muted-text {
  font-size: 0.8rem;
  color: var(--text-muted, #94a3b8);
}

.edit-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.form-group span {
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary, #cbd5e1);
}

.zen-input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--border-default, rgba(255, 255, 255, 0.12));
  border-radius: var(--radius-md, 6px);
  color: var(--text-primary, #f8fafc);
  font-size: 0.85rem;
  transition: border-color 0.15s ease;
}

.zen-input:focus {
  outline: none;
  border-color: var(--accent-brand, #6366f1);
}

.edit-form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.5rem;
}

.zen-notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  border-radius: var(--radius-md, 6px);
  font-size: 0.82rem;
}

.zen-notice--error {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

/* ── Modal Footer ─────────────────────────────────────────────────── */

.zen-modal-footer {
  padding: 1.25rem 1.75rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
  background: rgba(0, 0, 0, 0.15);
}
</style>
