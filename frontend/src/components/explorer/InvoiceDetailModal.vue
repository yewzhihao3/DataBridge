<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  Calendar,
  Edit2,
  FileSpreadsheet,
  Layers,
  Loader2,
  Save,
  Tag,
  X,
} from 'lucide-vue-next'

import type {
  InvoiceDetailResponse,
  InvoiceRecordUpdate,
} from '@/types/api'

const props = defineProps<{
  invoice: InvoiceDetailResponse
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', payload: { invoiceId: number; form: InvoiceRecordUpdate }): void
}>()

// ── Edit Record State ───────────────────────────────────────────────────────
const isEditing = ref(false)
const editForm = ref<InvoiceRecordUpdate>({})
const isSaving = ref(false)
const editError = ref('')

watch(
  () => props.invoice,
  (newInv) => {
    if (newInv) {
      editForm.value = {
        company_name: newInv.company_name,
        invoice_number: newInv.invoice_number,
        invoice_date: newInv.invoice_date ?? null,
        total_amount: newInv.total_amount == null ? null : Number(newInv.total_amount),
        currency: newInv.currency ?? null,
      }
      isEditing.value = false
      editError.value = ''
    }
  },
  { immediate: true },
)

function startEdit() {
  editForm.value = {
    company_name: props.invoice.company_name,
    invoice_number: props.invoice.invoice_number,
    invoice_date: props.invoice.invoice_date ?? null,
    total_amount: props.invoice.total_amount == null ? null : Number(props.invoice.total_amount),
    currency: props.invoice.currency ?? null,
  }
  isEditing.value = true
  editError.value = ''
}

function cancelEdit() {
  isEditing.value = false
  editError.value = ''
}

async function handleSave() {
  isSaving.value = true
  editError.value = ''
  try {
    emit('save', {
      invoiceId: props.invoice.id,
      form: editForm.value,
    })
    isEditing.value = false
  } catch (err: any) {
    editError.value = err.message || 'Failed to save changes.'
  } finally {
    isSaving.value = false
  }
}

// ── Presentation Helpers ────────────────────────────────────────────────────

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

function formatQuantity(val: any): string {
  const num = parseNumeric(val)
  if (num === null) return '—'
  return num.toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function formatTax(rate: any, amt: any, currency?: string | null): string {
  if (amt !== null && amt !== undefined) {
    return formatCurrency(amt, currency)
  }
  if (rate !== null && rate !== undefined) {
    const num = parseNumeric(rate)
    if (num !== null) {
      const pct = num <= 1 && num > 0 ? num * 100 : num
      return `${pct}%`
    }
    return `${rate}%`
  }
  return '—'
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
    sku_code: 'SKU Code',
    notes: 'Notes',
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
    'total',
    'total_amount',
    'grand_total',
    'amount',
    'discount',
    'shipping_amount',
  ]
  return moneyKeys.includes(key.toLowerCase())
}

const customFieldsList = computed(() => {
  if (!props.invoice.custom_fields) return []
  return Object.entries(props.invoice.custom_fields)
    .filter(([_, val]) => val !== null && val !== undefined && val !== '')
    .map(([key, val]) => {
      let displayValue = String(val)
      if (isMoneyKey(key)) {
        displayValue = formatCurrency(val, props.invoice.currency)
      } else if (isDateValue(key, val)) {
        displayValue = formatDate(String(val))
      }
      return {
        key,
        label: friendlyLabel(key),
        value: displayValue,
        isMoney: isMoneyKey(key),
      }
    })
})

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    emit('close')
  }
}
</script>

<template>
  <div
    v-if="isOpen"
    class="zen-modal-backdrop"
    @click.self="emit('close')"
    @keydown="handleKeydown"
  >
    <div
      class="zen-modal"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="'invoice-detail-title'"
    >
      <!-- Modal Header -->
      <header class="zen-modal-header">
        <div class="zen-header-main">
          <div class="zen-eyebrow">
            <FileSpreadsheet :size="14" />
            <span>INVOICE RECORD</span>
          </div>

          <h2 id="invoice-detail-title" class="zen-title">
            {{ invoice.company_name }}
          </h2>

          <div class="zen-meta-bar">
            <span class="zen-meta-chip font-mono">{{ invoice.invoice_number }}</span>
            <span class="zen-meta-dot">•</span>
            <span class="zen-meta-chip">
              <Calendar :size="13" />
              {{ formatDate(invoice.invoice_date) }}
            </span>
            <span v-if="invoice.currency" class="zen-meta-chip zen-currency-chip">
              {{ invoice.currency }}
            </span>
            <span class="zen-meta-dot">•</span>
            <span class="zen-meta-chip">
              {{ invoice.line_items.length }} line item{{ invoice.line_items.length !== 1 ? 's' : '' }}
            </span>
          </div>
        </div>

        <div class="zen-header-actions">
          <button
            v-if="!isEditing"
            type="button"
            class="btn-zen-secondary"
            @click="startEdit"
            aria-label="Edit invoice details"
          >
            <Edit2 :size="14" />
            <span>Edit</span>
          </button>
          <button
            type="button"
            class="btn-close-zen"
            @click="emit('close')"
            aria-label="Close modal"
          >
            <X :size="18" />
          </button>
        </div>
      </header>

      <!-- Modal Body -->
      <div class="zen-modal-body">
        <!-- Edit Form Mode -->
        <div v-if="isEditing" class="zen-edit-section">
          <div class="zen-section-title">
            <Edit2 :size="16" />
            <span>Edit Canonical Invoice Header</span>
          </div>

          <div v-if="editError" class="zen-alert zen-alert-error" role="alert">
            <AlertCircle :size="16" />
            <span>{{ editError }}</span>
          </div>

          <div class="zen-form-grid">
            <div class="zen-form-group">
              <label for="edit-company">Company Name</label>
              <input
                id="edit-company"
                v-model="editForm.company_name"
                type="text"
                class="zen-input"
                required
              />
            </div>

            <div class="zen-form-group">
              <label for="edit-invoice-num">Invoice Number</label>
              <input
                id="edit-invoice-num"
                v-model="editForm.invoice_number"
                type="text"
                class="zen-input"
                required
              />
            </div>

            <div class="zen-form-group">
              <label for="edit-date">Invoice Date</label>
              <input
                id="edit-date"
                v-model="editForm.invoice_date"
                type="date"
                class="zen-input"
              />
            </div>

            <div class="zen-form-group">
              <label for="edit-currency">Currency</label>
              <input
                id="edit-currency"
                v-model="editForm.currency"
                type="text"
                class="zen-input"
                placeholder="MYR, USD, EUR..."
              />
            </div>

            <div class="zen-form-group">
              <label for="edit-total">Total Amount</label>
              <input
                id="edit-total"
                v-model="editForm.total_amount"
                type="number"
                step="0.01"
                class="zen-input"
              />
            </div>
          </div>

          <div class="zen-edit-actions">
            <button
              type="button"
              class="btn-zen-secondary"
              @click="cancelEdit"
              :disabled="isSaving"
            >
              Cancel
            </button>
            <button
              type="button"
              class="btn-zen-primary"
              @click="handleSave"
              :disabled="isSaving"
            >
              <Loader2 v-if="isSaving" :size="14" class="spin" />
              <Save v-else :size="14" />
              <span>{{ isSaving ? 'Saving...' : 'Save Changes' }}</span>
            </button>
          </div>
        </div>

        <!-- Overview Cards -->
        <div class="zen-summary-cards">
          <div class="zen-card">
            <span class="zen-card-label">Company</span>
            <span class="zen-card-value font-medium">{{ invoice.company_name }}</span>
          </div>
          <div class="zen-card">
            <span class="zen-card-label">Invoice Number</span>
            <span class="zen-card-value font-mono">{{ invoice.invoice_number }}</span>
          </div>
          <div class="zen-card">
            <span class="zen-card-label">Invoice Date</span>
            <span class="zen-card-value">{{ formatDate(invoice.invoice_date) }}</span>
          </div>
          <div class="zen-card highlight-card">
            <span class="zen-card-label">Total Amount</span>
            <span class="zen-card-value font-mono total-value">
              {{ formatCurrency(invoice.total_amount, invoice.currency) }}
            </span>
          </div>
        </div>

        <!-- Additional Custom Fields -->
        <div v-if="customFieldsList.length > 0" class="zen-custom-fields-section">
          <h3 class="zen-section-heading">
            <Tag :size="15" />
            <span>Additional Fields</span>
          </h3>
          <div class="zen-custom-fields-grid">
            <div
              v-for="item in customFieldsList"
              :key="item.key"
              class="zen-field-tile"
            >
              <span class="zen-field-label">{{ item.label }}</span>
              <span class="zen-field-val" :class="{ 'font-mono': item.isMoney }">
                {{ item.value }}
              </span>
            </div>
          </div>
        </div>

        <!-- Line Items Section -->
        <div class="zen-line-items-section">
          <div class="zen-section-header">
            <h3 class="zen-section-heading">
              <Layers :size="15" />
              <span>Line Items ({{ invoice.line_items.length }})</span>
            </h3>
          </div>

          <div v-if="invoice.line_items.length === 0" class="zen-empty-inline">
            <span>No line items attached to this invoice.</span>
          </div>

          <div v-else class="zen-table-wrapper">
            <table class="zen-table">
              <thead>
                <tr>
                  <th class="th-num">#</th>
                  <th class="th-desc">Description</th>
                  <th class="th-right">Qty</th>
                  <th class="th-right">Unit Price</th>
                  <th class="th-right">Tax</th>
                  <th class="th-right">Amount</th>
                  <th class="th-custom">Details</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in invoice.line_items" :key="item.id || idx">
                  <td class="td-num">{{ item.source_row_number || idx + 1 }}</td>
                  <td class="td-desc">
                    <span class="item-description">{{ item.description || '—' }}</span>
                  </td>
                  <td class="td-right font-mono">{{ formatQuantity(item.quantity) }}</td>
                  <td class="td-right font-mono">{{ formatCurrency(item.unit_price, invoice.currency) }}</td>
                  <td class="td-right font-mono">{{ formatTax(item.tax_rate, item.tax_amount, invoice.currency) }}</td>
                  <td class="td-right font-mono font-medium">{{ formatCurrency(item.amount, invoice.currency) }}</td>
                  <td class="td-custom">
                    <div v-if="item.custom_fields && Object.keys(item.custom_fields).length > 0" class="line-custom-tags">
                      <span
                        v-for="(val, k) in item.custom_fields"
                        :key="k"
                        class="zen-pill"
                        :title="`${friendlyLabel(String(k))}: ${val}`"
                      >
                        {{ friendlyLabel(String(k)) }}: {{ val }}
                      </span>
                    </div>
                    <span v-else class="text-muted">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Provenance Footer Bar -->
        <div v-if="invoice.batch" class="zen-provenance-box">
          <div class="zen-provenance-item">
            <span class="prov-label">Source File</span>
            <span class="prov-val">{{ invoice.batch.source_filename }}</span>
          </div>
          <div class="zen-provenance-item">
            <span class="prov-label">Template</span>
            <span class="prov-val">{{ invoice.batch.template_name }}</span>
          </div>
          <div class="zen-provenance-item">
            <span class="prov-label">Worksheet</span>
            <span class="prov-val font-mono">{{ invoice.source_worksheet }}</span>
          </div>
          <div class="zen-provenance-item">
            <span class="prov-label">Imported At</span>
            <span class="prov-val">{{ formatDateTime(invoice.batch.imported_at) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.zen-modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 1.5rem;
  overflow-y: auto;
}

.zen-modal {
  background: var(--bg-card);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 960px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modalFadeIn 0.2s ease-out;
}

@keyframes modalFadeIn {
  from {
    opacity: 0;
    transform: scale(0.97);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.zen-modal-header {
  padding: 1.5rem 1.75rem 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  background: var(--bg-subtle);
}

.zen-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--accent-brand);
  margin-bottom: 0.35rem;
}

.zen-title {
  margin: 0 0 0.5rem;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text-primary);
}

.zen-meta-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.zen-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.zen-currency-chip {
  background: var(--bg-app);
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-xs);
  border: 1px solid var(--border-subtle);
  font-weight: 600;
  color: var(--text-primary);
}

.zen-meta-dot {
  color: var(--text-muted);
}

.zen-header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-close-zen {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.4rem;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.btn-close-zen:hover {
  color: var(--text-primary);
  background: var(--bg-card);
}

.zen-modal-body {
  padding: 1.75rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

/* Edit Mode */
.zen-edit-section {
  background: var(--bg-subtle);
  border: 1px solid var(--accent-brand-subtle);
  border-radius: var(--radius-md);
  padding: 1.25rem;
}

.zen-section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--accent-brand);
  margin-bottom: 1rem;
}

.zen-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.zen-form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.zen-form-group label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.zen-input {
  background: var(--bg-card);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  color: var(--text-primary);
}

.zen-input:focus {
  outline: none;
  border-color: var(--accent-brand);
}

.zen-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.25rem;
}

/* Summary Cards */
.zen-summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
}

.zen-card {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.zen-card-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.zen-card-value {
  font-size: 1rem;
  color: var(--text-primary);
  word-break: break-word;
}

.highlight-card {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.total-value {
  color: var(--accent-brand);
  font-weight: 700;
  font-size: 1.15rem;
}

/* Custom Fields */
.zen-section-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 0.85rem;
}

.zen-custom-fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 0.75rem;
}

.zen-field-tile {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0.65rem 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.zen-field-label {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 500;
}

.zen-field-val {
  font-size: 0.88rem;
  color: var(--text-primary);
  font-weight: 500;
}

/* Line Items Table */
.zen-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.zen-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.85rem;
}

.zen-table th {
  background: var(--bg-subtle);
  padding: 0.75rem 1rem;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-subtle);
}

.zen-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.zen-table tr:last-child td {
  border-bottom: none;
}

.th-num, .td-num {
  width: 40px;
  color: var(--text-muted);
  font-size: 0.78rem;
}

.th-right, .td-right {
  text-align: right;
  white-space: nowrap;
}

.item-description {
  font-weight: 500;
  color: var(--text-primary);
}

.line-custom-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.zen-pill {
  font-size: 0.7rem;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
}

/* Provenance */
.zen-provenance-box {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 1rem;
  padding: 1rem 1.25rem;
  background: var(--bg-subtle);
  border-radius: var(--radius-md);
  border: 1px dashed var(--border-subtle);
}

.zen-provenance-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.prov-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--text-muted);
  font-weight: 600;
}

.prov-val {
  font-size: 0.82rem;
  color: var(--text-secondary);
  word-break: break-all;
}

/* Buttons */
.btn-zen-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--accent-brand);
  color: var(--on-accent);
  border: none;
  padding: 0.45rem 0.9rem;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-zen-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-zen-secondary {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--bg-card);
  color: var(--text-secondary);
  border: 1px solid var(--border-medium);
  padding: 0.45rem 0.9rem;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-zen-secondary:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.font-mono {
  font-family: var(--font-mono, monospace);
}

.font-medium {
  font-weight: 500;
}

.text-muted {
  color: var(--text-muted);
}
</style>
