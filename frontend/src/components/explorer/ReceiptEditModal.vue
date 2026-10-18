<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  AlertCircle,
  AlertTriangle,
  Building2,
  Calendar,
  ChevronDown,
  ChevronUp,
  CreditCard,
  DollarSign,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Plus,
  Receipt,
  RotateCcw,
  Trash2,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'

import { api } from '@/services/api'
import { toast } from '@/services/toast'
import type {
  ReceiptDetailResponse,
  ReceiptLineItemRead,
  ReceiptRecordUpdate,
} from '@/types/api'

const props = defineProps<{
  receipt: ReceiptDetailResponse | null
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'saved', updated: ReceiptDetailResponse): void
}>()

// ── State ────────────────────────────────────────────────────────────────────
const isSaving = ref(false)
const saveError = ref('')
const previewLoading = ref(false)
const previewBlobUrl = ref<string | null>(null)
const zoomLevel = ref(1)
const isPreviewCollapsed = ref(false)
const isLineItemsCollapsed = ref(false)

// Form State
interface EditableLineItem {
  id?: number | null
  description: string
  quantity: string
  unit_price: string
  tax_rate: string
  tax_amount: string
  amount: string
}

const form = reactive({
  merchant_name: '',
  receipt_number: '',
  transaction_date: '',
  transaction_time: '',
  currency: '',
  direction: 'unclassified' as 'expense' | 'income' | 'unclassified',
  subtotal: '',
  tax_amount: '',
  total_amount: '',
  payment_method: '',
  store_address: '',
  cashier: '',
  branch: '',
  cash_paid: '',
  change_amount: '',
  line_items: [] as EditableLineItem[],
})

// Original snapshot to detect dirty state
const initialSnapshot = ref<string>('')

// Populate form when receipt prop changes
watch(
  () => [props.receipt, props.isOpen] as const,
  async ([newReceipt, open]) => {
    if (open && newReceipt) {
      saveError.value = ''
      zoomLevel.value = 1

      form.merchant_name = newReceipt.merchant_name || ''
      form.receipt_number = newReceipt.receipt_number || ''
      form.transaction_date = newReceipt.transaction_date || ''
      form.transaction_time = newReceipt.transaction_time || ''
      form.currency = newReceipt.currency || ''
      form.direction = (newReceipt.direction as any) || 'unclassified'
      form.subtotal = newReceipt.subtotal !== null && newReceipt.subtotal !== undefined ? String(newReceipt.subtotal) : ''
      form.tax_amount = newReceipt.tax_amount !== null && newReceipt.tax_amount !== undefined ? String(newReceipt.tax_amount) : ''
      form.total_amount = newReceipt.total_amount !== null && newReceipt.total_amount !== undefined ? String(newReceipt.total_amount) : ''
      form.payment_method = newReceipt.payment_method || ''
      form.store_address = newReceipt.store_address || ''
      form.cashier = newReceipt.cashier || ''
      form.branch = newReceipt.branch || ''
      form.cash_paid = newReceipt.cash_paid !== null && newReceipt.cash_paid !== undefined ? String(newReceipt.cash_paid) : ''
      form.change_amount = newReceipt.change_amount !== null && newReceipt.change_amount !== undefined ? String(newReceipt.change_amount) : ''

      form.line_items = (newReceipt.line_items || []).map((li: ReceiptLineItemRead) => ({
        id: li.id,
        description: li.description || '',
        quantity: li.quantity !== null && li.quantity !== undefined ? String(li.quantity) : '',
        unit_price: li.unit_price !== null && li.unit_price !== undefined ? String(li.unit_price) : '',
        tax_rate: li.tax_rate !== null && li.tax_rate !== undefined ? String(li.tax_rate) : '',
        tax_amount: li.tax_amount !== null && li.tax_amount !== undefined ? String(li.tax_amount) : '',
        amount: li.amount !== null && li.amount !== undefined ? String(li.amount) : '',
      }))

      initialSnapshot.value = JSON.stringify(form)

      // Load preview document if source file is present
      const sourceFileId = newReceipt.batch?.source_file_id
      if (sourceFileId) {
        await loadPreview(sourceFileId)
      } else {
        cleanupPreview()
      }
    } else if (!open) {
      cleanupPreview()
    }
  },
  { immediate: true },
)

function cleanupPreview() {
  if (previewBlobUrl.value) {
    URL.revokeObjectURL(previewBlobUrl.value)
    previewBlobUrl.value = null
  }
}

onBeforeUnmount(() => {
  cleanupPreview()
})

async function loadPreview(sourceId: number) {
  previewLoading.value = true
  cleanupPreview()
  try {
    const blob = await api.getDocumentPreview(sourceId)
    previewBlobUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    console.warn('Failed to load authenticated preview blob:', err)
  } finally {
    previewLoading.value = false
  }
}

// ── Computed & Validation ───────────────────────────────────────────────────

const isPdf = computed(() => {
  const media = props.receipt?.batch?.source_media_type || ''
  return media.includes('pdf') || props.receipt?.batch?.source_filename?.toLowerCase().endsWith('.pdf')
})

const isDirty = computed(() => {
  if (!initialSnapshot.value) return false
  return JSON.stringify(form) !== initialSnapshot.value
})

const parsedSubtotal = computed(() => {
  const v = parseFloat(form.subtotal)
  return isNaN(v) ? null : v
})

const parsedTax = computed(() => {
  const v = parseFloat(form.tax_amount)
  return isNaN(v) ? null : v
})

const parsedTotal = computed(() => {
  const v = parseFloat(form.total_amount)
  return isNaN(v) ? null : v
})

const parsedCashPaid = computed(() => {
  const v = parseFloat(form.cash_paid)
  return isNaN(v) ? null : v
})

const calculatedLineItemsSum = computed(() => {
  let sum = 0
  let hasValid = false
  for (const li of form.line_items) {
    const amt = parseFloat(li.amount)
    if (!isNaN(amt)) {
      sum += amt
      hasValid = true
    }
  }
  return hasValid ? Math.round(sum * 100) / 100 : null
})

const calculatedExpectedTotal = computed(() => {
  if (parsedSubtotal.value !== null && parsedTax.value !== null) {
    return Math.round((parsedSubtotal.value + parsedTax.value) * 100) / 100
  }
  return null
})

const calculatedExpectedChange = computed(() => {
  if (parsedCashPaid.value !== null && parsedTotal.value !== null) {
    const diff = parsedCashPaid.value - parsedTotal.value
    return diff >= 0 ? Math.round(diff * 100) / 100 : null
  }
  return null
})

// Validation Severities
const validationErrors = computed<string[]>(() => {
  const errors: string[] = []
  if (!form.merchant_name.trim()) {
    errors.push('Merchant name is required.')
  }
  for (let i = 0; i < form.line_items.length; i++) {
    const li = form.line_items[i]
    if (li.quantity) {
      const q = parseFloat(li.quantity)
      if (isNaN(q) || q < 0) {
        errors.push(`Line item #${i + 1} has an invalid quantity.`)
      }
    }
    if (li.unit_price) {
      const p = parseFloat(li.unit_price)
      if (isNaN(p) || p < 0) {
        errors.push(`Line item #${i + 1} has an invalid unit price.`)
      }
    }
  }
  return errors
})

const validationWarnings = computed<string[]>(() => {
  const warnings: string[] = []

  // Check sum of line items vs subtotal
  if (calculatedLineItemsSum.value !== null && parsedSubtotal.value !== null) {
    if (Math.abs(calculatedLineItemsSum.value - parsedSubtotal.value) > 0.05) {
      warnings.push(
        `Sum of line items (${form.currency || ''} ${calculatedLineItemsSum.value.toFixed(2)}) differs from Subtotal (${form.currency || ''} ${parsedSubtotal.value.toFixed(2)}).`,
      )
    }
  }

  // Check subtotal + tax vs total
  if (calculatedExpectedTotal.value !== null && parsedTotal.value !== null) {
    if (Math.abs(calculatedExpectedTotal.value - parsedTotal.value) > 0.05) {
      warnings.push(
        `Subtotal + Tax (${form.currency || ''} ${calculatedExpectedTotal.value.toFixed(2)}) differs from Total Amount (${form.currency || ''} ${parsedTotal.value.toFixed(2)}).`,
      )
    }
  }

  // Check change calculation
  if (calculatedExpectedChange.value !== null && form.change_amount) {
    const enteredChange = parseFloat(form.change_amount)
    if (!isNaN(enteredChange) && Math.abs(calculatedExpectedChange.value - enteredChange) > 0.05) {
      warnings.push(
        `Calculated change (Cash Paid - Total = ${form.currency || ''} ${calculatedExpectedChange.value.toFixed(2)}) differs from entered Change Amount.`,
      )
    }
  }

  return warnings
})

// ── Zoom Controls ───────────────────────────────────────────────────────────

function zoomIn() {
  if (zoomLevel.value < 2.5) {
    zoomLevel.value = Math.min(2.5, Math.round((zoomLevel.value + 0.25) * 100) / 100)
  }
}

function zoomOut() {
  if (zoomLevel.value > 0.5) {
    zoomLevel.value = Math.max(0.5, Math.round((zoomLevel.value - 0.25) * 100) / 100)
  }
}

function resetZoom() {
  zoomLevel.value = 1
}

function openOriginalTab() {
  const sourceId = props.receipt?.batch?.source_file_id
  if (sourceId) {
    window.open(`/api/v1/documents/${sourceId}/preview`, '_blank', 'noopener,noreferrer')
  }
}

async function downloadOriginalDocument() {
  const sourceId = props.receipt?.batch?.source_file_id
  if (!sourceId) return
  try {
    const blob = await api.downloadDocument(sourceId)
    const filename = props.receipt?.batch?.source_filename || `receipt_source_${sourceId}`
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Document download started')
  } catch (err: any) {
    toast.error(err.message || 'Failed to download original document.')
  }
}

// ── Line Item Operations ────────────────────────────────────────────────────

function addLineItem() {
  form.line_items.push({
    id: null,
    description: '',
    quantity: '1',
    unit_price: '',
    tax_rate: '',
    tax_amount: '',
    amount: '',
  })
}

function removeLineItem(index: number) {
  form.line_items.splice(index, 1)
}

function onLineItemQuantityPriceChange(item: EditableLineItem) {
  const q = parseFloat(item.quantity)
  const p = parseFloat(item.unit_price)
  if (!isNaN(q) && !isNaN(p)) {
    item.amount = (Math.round(q * p * 100) / 100).toFixed(2)
  }
}

// ── Close & Save Handlers ───────────────────────────────────────────────────

function handleClose() {
  if (isDirty.value) {
    const confirmDiscard = window.confirm(
      'You have unsaved changes in this receipt editor. Discard changes?',
    )
    if (!confirmDiscard) return
  }
  emit('close')
}

async function handleSave() {
  if (!props.receipt) return
  if (validationErrors.value.length > 0) {
    saveError.value = validationErrors.value[0]
    return
  }

  isSaving.value = true
  saveError.value = ''

  try {
    const payload: ReceiptRecordUpdate = {
      merchant_name: form.merchant_name.trim(),
      receipt_number: form.receipt_number.trim(),
      transaction_date: form.transaction_date || null,
      transaction_time: form.transaction_time.trim() || null,
      currency: form.currency.trim().toUpperCase() || null,
      direction: form.direction,
      subtotal: form.subtotal !== '' ? (parseFloat(form.subtotal) as any) : null,
      tax_amount: form.tax_amount !== '' ? (parseFloat(form.tax_amount) as any) : null,
      total_amount: form.total_amount !== '' ? (parseFloat(form.total_amount) as any) : null,
      payment_method: form.payment_method.trim() || null,
      store_address: form.store_address.trim() || null,
      cashier: form.cashier.trim() || null,
      branch: form.branch.trim() || null,
      cash_paid: form.cash_paid !== '' ? (parseFloat(form.cash_paid) as any) : null,
      change_amount: form.change_amount !== '' ? (parseFloat(form.change_amount) as any) : null,
      line_items: form.line_items.map((li) => ({
        id: li.id ?? null,
        description: li.description.trim() || null,
        quantity: li.quantity !== '' ? (parseFloat(li.quantity) as any) : null,
        unit_price: li.unit_price !== '' ? (parseFloat(li.unit_price) as any) : null,
        tax_rate: li.tax_rate !== '' ? (parseFloat(li.tax_rate) as any) : null,
        tax_amount: li.tax_amount !== '' ? (parseFloat(li.tax_amount) as any) : null,
        amount: li.amount !== '' ? (parseFloat(li.amount) as any) : null,
      })),
    }

    const updated = await api.updateDataExplorerReceipt(props.receipt.id, payload)
    toast.success('Receipt updated successfully')
    emit('saved', updated)
    emit('close')
  } catch (err: any) {
    saveError.value = err?.message || 'Failed to update receipt.'
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen && receipt"
      class="zen-modal-overlay"
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="receipt-edit-modal-title"
    @click.self="handleClose"
    @keydown.esc="handleClose"
  >
    <div class="zen-modal-dialog">
      <!-- Modal Header -->
      <header class="zen-dialog-header">
        <div class="header-left">
          <div class="flex items-center gap-2">
            <Receipt :size="20" class="text-accent-brand" />
            <h2 id="receipt-edit-modal-title" class="dialog-title">
              Receipt Editing Workspace
            </h2>
            <span class="badge badge-workspace">ID #{{ receipt.id }}</span>
          </div>
          <p class="dialog-subtitle">
            Review original extraction evidence and make post-import accounting corrections.
          </p>
        </div>

        <button
          type="button"
          class="btn-close-dialog"
          aria-label="Close receipt editor"
          @click="handleClose"
        >
          <X :size="18" />
        </button>
      </header>

      <!-- Modal Body (Two-Column Split Workspace) -->
      <div class="zen-dialog-body">
        <div class="workspace-split-container">
          <!-- ── Left Panel: Original Receipt Document ── -->
          <aside class="original-preview-panel" :class="{ collapsed: isPreviewCollapsed }">
            <div class="preview-panel-header">
              <div class="preview-title-group">
                <FileText :size="16" class="text-secondary" />
                <span class="preview-title">Original Receipt</span>
                <span v-if="receipt.batch?.source_filename" class="preview-filename-badge" :title="receipt.batch.source_filename">
                  {{ receipt.batch.source_filename }}
                </span>
              </div>

              <div class="preview-toolbar">
                <div class="zoom-controls">
                  <button
                    type="button"
                    class="btn-tool"
                    title="Zoom In"
                    :disabled="zoomLevel >= 2.5"
                    @click="zoomIn"
                  >
                    <ZoomIn :size="14" />
                  </button>
                  <span class="zoom-indicator">{{ Math.round(zoomLevel * 100) }}%</span>
                  <button
                    type="button"
                    class="btn-tool"
                    title="Zoom Out"
                    :disabled="zoomLevel <= 0.5"
                    @click="zoomOut"
                  >
                    <ZoomOut :size="14" />
                  </button>
                  <button
                    type="button"
                    class="btn-tool"
                    title="Reset Zoom"
                    @click="resetZoom"
                  >
                    <RotateCcw :size="14" />
                  </button>
                </div>

                <button
                  type="button"
                  class="btn-tool"
                  title="Open source preview in new tab"
                  @click="openOriginalTab"
                >
                  <ExternalLink :size="14" />
                </button>
                <button
                  type="button"
                  class="btn-tool"
                  title="Download original file"
                  @click="downloadOriginalDocument"
                >
                  <Download :size="14" />
                </button>
              </div>
            </div>

            <!-- Preview Viewport -->
            <div class="preview-viewport">
              <div v-if="previewLoading" class="preview-loading-state">
                <Loader2 class="animate-spin" :size="28" />
                <span>Loading original receipt…</span>
              </div>

              <div v-else-if="previewBlobUrl" class="preview-canvas" :style="{ transform: `scale(${zoomLevel})` }">
                <iframe
                  v-if="isPdf"
                  :src="previewBlobUrl"
                  title="Original PDF receipt"
                  class="preview-iframe"
                />
                <img
                  v-else
                  :src="previewBlobUrl"
                  alt="Original receipt image"
                  class="preview-image"
                />
              </div>

              <div v-else class="preview-fallback-state">
                <FileText :size="40" class="text-muted" />
                <p>Preview document unavailable</p>
                <button
                  v-if="receipt.batch?.source_file_id"
                  type="button"
                  class="btn btn-secondary btn-small"
                  @click="loadPreview(receipt.batch.source_file_id)"
                >
                  Retry Loading
                </button>
              </div>
            </div>

            <div class="preview-footer-note">
              <span>Original OCR extraction evidence and raw source files remain preserved.</span>
            </div>
          </aside>

          <!-- ── Right Panel: Editable Receipt Fields ── -->
          <main class="editor-fields-panel">
            <!-- Validation & Warning Alerts -->
            <div v-if="validationErrors.length" class="editor-alert alert-danger" role="alert">
              <AlertCircle :size="16" class="alert-icon" />
              <div>
                <strong>Blocking Errors</strong>
                <ul>
                  <li v-for="err in validationErrors" :key="err">{{ err }}</li>
                </ul>
              </div>
            </div>

            <div v-if="validationWarnings.length" class="editor-alert alert-warning" role="alert">
              <AlertTriangle :size="16" class="alert-icon" />
              <div>
                <strong>Arithmetic Discrepancies (Non-blocking)</strong>
                <ul>
                  <li v-for="warn in validationWarnings" :key="warn">{{ warn }}</li>
                </ul>
              </div>
            </div>

            <div v-if="saveError" class="editor-alert alert-danger" role="alert">
              <AlertCircle :size="16" class="alert-icon" />
              <div>{{ saveError }}</div>
            </div>

            <!-- Section 1 — Merchant Information -->
            <section class="form-section glass-card">
              <div class="section-header">
                <Building2 :size="16" class="section-icon" />
                <div>
                  <h3 class="section-title">Merchant Information</h3>
                  <p class="section-desc">Store identifier, cashier, and location details.</p>
                </div>
              </div>

              <div class="fields-grid grid-2">
                <label class="input-field required">
                  <span class="field-label">Merchant Name *</span>
                  <input
                    v-model="form.merchant_name"
                    type="text"
                    placeholder="e.g. Village Grocer"
                    required
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Receipt / Invoice Number</span>
                  <input
                    v-model="form.receipt_number"
                    type="text"
                    placeholder="e.g. REC-2026-0042"
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Store Branch</span>
                  <input
                    v-model="form.branch"
                    type="text"
                    placeholder="e.g. Bangsar Village II"
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Cashier</span>
                  <input
                    v-model="form.cashier"
                    type="text"
                    placeholder="e.g. Alex M."
                  />
                </label>

                <label class="input-field col-span-2">
                  <span class="field-label">Store Address</span>
                  <input
                    v-model="form.store_address"
                    type="text"
                    placeholder="e.g. 1 Jalan Telawi 1, Bangsar Baru, 59100 Kuala Lumpur"
                  />
                </label>
              </div>
            </section>

            <!-- Section 2 — Transaction Information -->
            <section class="form-section glass-card">
              <div class="section-header">
                <Calendar :size="16" class="section-icon" />
                <div>
                  <h3 class="section-title">Transaction Information</h3>
                  <p class="section-desc">Date, time, currency, and payment channel.</p>
                </div>
              </div>

              <div class="fields-grid grid-4">
                <label class="input-field">
                  <span class="field-label">Transaction Date</span>
                  <input
                    v-model="form.transaction_date"
                    type="date"
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Transaction Time</span>
                  <input
                    v-model="form.transaction_time"
                    type="text"
                    placeholder="14:32:00"
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Currency</span>
                  <input
                    v-model="form.currency"
                    type="text"
                    placeholder="USD / MYR / EUR"
                    maxlength="10"
                  />
                </label>

                <label class="input-field">
                  <span class="field-label">Payment Method</span>
                  <input
                    v-model="form.payment_method"
                    type="text"
                    placeholder="Cash, Visa, TNG, etc."
                  />
                </label>
              </div>
            </section>

            <!-- Section 3 — Financial Direction -->
            <section class="form-section glass-card">
              <div class="section-header">
                <CreditCard :size="16" class="section-icon" />
                <div>
                  <h3 class="section-title">Financial Direction</h3>
                  <p class="section-desc">Accounting classification for financial dashboards and audits.</p>
                </div>
              </div>

              <div class="direction-selector" role="radiogroup" aria-label="Receipt financial direction">
                <label
                  class="direction-card-option"
                  :class="{ selected: form.direction === 'expense' }"
                >
                  <input
                    type="radio"
                    v-model="form.direction"
                    value="expense"
                    class="sr-only"
                  />
                  <div class="dir-dot dot-expense" />
                  <div class="dir-info">
                    <span class="dir-name">Expense</span>
                    <span class="dir-desc">Retail purchase, vendor disbursement, or business cost</span>
                  </div>
                </label>

                <label
                  class="direction-card-option"
                  :class="{ selected: form.direction === 'income' }"
                >
                  <input
                    type="radio"
                    v-model="form.direction"
                    value="income"
                    class="sr-only"
                  />
                  <div class="dir-dot dot-income" />
                  <div class="dir-info">
                    <span class="dir-name">Income</span>
                    <span class="dir-desc">Cash sale, customer refund credit, or retail revenue</span>
                  </div>
                </label>

                <label
                  class="direction-card-option"
                  :class="{ selected: form.direction === 'unclassified' }"
                >
                  <input
                    type="radio"
                    v-model="form.direction"
                    value="unclassified"
                    class="sr-only"
                  />
                  <div class="dir-dot dot-unclassified" />
                  <div class="dir-info">
                    <span class="dir-name">Unclassified</span>
                    <span class="dir-desc">Default neutral context; direction pending categorization</span>
                  </div>
                </label>
              </div>
            </section>

            <!-- Section 4 — Financial Amounts -->
            <section class="form-section glass-card">
              <div class="section-header">
                <DollarSign :size="16" class="section-icon" />
                <div>
                  <h3 class="section-title">Financial Amounts</h3>
                  <p class="section-desc">Subtotal, tax, cash paid, and change totals.</p>
                </div>
              </div>

              <div class="fields-grid grid-3">
                <label class="input-field">
                  <span class="field-label">Subtotal</span>
                  <div class="input-currency-wrapper">
                    <span class="curr-prefix">{{ form.currency || '$' }}</span>
                    <input
                      v-model="form.subtotal"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                    />
                  </div>
                </label>

                <label class="input-field">
                  <span class="field-label">Tax Amount</span>
                  <div class="input-currency-wrapper">
                    <span class="curr-prefix">{{ form.currency || '$' }}</span>
                    <input
                      v-model="form.tax_amount"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                    />
                  </div>
                </label>

                <label class="input-field highlight-field">
                  <span class="field-label">Total Amount</span>
                  <div class="input-currency-wrapper">
                    <span class="curr-prefix">{{ form.currency || '$' }}</span>
                    <input
                      v-model="form.total_amount"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      class="total-input"
                    />
                  </div>
                </label>

                <label class="input-field">
                  <span class="field-label">Cash Paid</span>
                  <div class="input-currency-wrapper">
                    <span class="curr-prefix">{{ form.currency || '$' }}</span>
                    <input
                      v-model="form.cash_paid"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                    />
                  </div>
                </label>

                <label class="input-field">
                  <span class="field-label">Change Amount</span>
                  <div class="input-currency-wrapper">
                    <span class="curr-prefix">{{ form.currency || '$' }}</span>
                    <input
                      v-model="form.change_amount"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                    />
                  </div>
                </label>

                <!-- Live Arithmetic Helper Card -->
                <div class="arithmetic-helper-box">
                  <span class="helper-label">Reconciliation Check</span>
                  <div class="helper-row">
                    <span>Lines Sum:</span>
                    <strong>{{ form.currency || '' }} {{ calculatedLineItemsSum !== null ? calculatedLineItemsSum.toFixed(2) : '—' }}</strong>
                  </div>
                  <div class="helper-row">
                    <span>Expected Total:</span>
                    <strong>{{ form.currency || '' }} {{ calculatedExpectedTotal !== null ? calculatedExpectedTotal.toFixed(2) : '—' }}</strong>
                  </div>
                </div>
              </div>
            </section>

            <!-- Section 5 — Line Items -->
            <section class="form-section glass-card">
              <div class="section-header line-items-header">
                <div class="flex items-center gap-2">
                  <Receipt :size="16" class="section-icon" />
                  <div>
                    <h3 class="section-title">Line Items ({{ form.line_items.length }})</h3>
                    <p class="section-desc">Itemized products, service charges, quantities, and pricing.</p>
                  </div>
                </div>

                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    class="btn btn-secondary btn-small"
                    @click="addLineItem"
                  >
                    <Plus :size="13" />
                    <span>Add Item</span>
                  </button>
                  <button
                    type="button"
                    class="btn-toggle-section"
                    :title="isLineItemsCollapsed ? 'Expand line items' : 'Collapse line items'"
                    @click="isLineItemsCollapsed = !isLineItemsCollapsed"
                  >
                    <ChevronUp v-if="!isLineItemsCollapsed" :size="15" />
                    <ChevronDown v-else :size="15" />
                  </button>
                </div>
              </div>

              <div v-if="!isLineItemsCollapsed" class="line-items-table-wrapper">
                <div v-if="form.line_items.length === 0" class="empty-line-items">
                  <p>No line items recorded for this receipt.</p>
                  <button type="button" class="btn btn-secondary btn-small" @click="addLineItem">
                    <Plus :size="13" />
                    Add First Line Item
                  </button>
                </div>

                <table v-else class="line-items-table">
                  <thead>
                    <tr>
                      <th class="th-num">#</th>
                      <th class="th-desc">Description</th>
                      <th class="th-qty">Qty</th>
                      <th class="th-price">Unit Price</th>
                      <th class="th-tax">Tax</th>
                      <th class="th-total">Total Amount</th>
                      <th class="th-action"></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(item, idx) in form.line_items" :key="item.id ?? `new-${idx}`">
                      <td class="td-num">
                        <span class="row-num-badge">{{ idx + 1 }}</span>
                      </td>
                      <td class="td-desc">
                        <input
                          v-model="item.description"
                          type="text"
                          placeholder="Item name / description"
                          class="table-input"
                        />
                      </td>
                      <td class="td-qty">
                        <input
                          v-model="item.quantity"
                          type="number"
                          step="0.001"
                          placeholder="1"
                          class="table-input mono"
                          @input="onLineItemQuantityPriceChange(item)"
                        />
                      </td>
                      <td class="td-price">
                        <input
                          v-model="item.unit_price"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          class="table-input mono"
                          @input="onLineItemQuantityPriceChange(item)"
                        />
                      </td>
                      <td class="td-tax">
                        <input
                          v-model="item.tax_amount"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          class="table-input mono"
                        />
                      </td>
                      <td class="td-total">
                        <input
                          v-model="item.amount"
                          type="number"
                          step="0.01"
                          placeholder="0.00"
                          class="table-input mono total-col"
                        />
                      </td>
                      <td class="td-action">
                        <button
                          type="button"
                          class="btn-remove-line"
                          title="Remove this line item"
                          @click="removeLineItem(idx)"
                        >
                          <Trash2 :size="14" />
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </main>
        </div>
      </div>

      <!-- Modal Sticky Footer -->
      <footer class="zen-dialog-footer">
        <div class="footer-left-status">
          <span v-if="isDirty" class="dirty-indicator">
            <span class="dirty-dot" />
            Unsaved changes
          </span>
          <span v-else class="clean-indicator">
            All changes saved
          </span>
        </div>

        <div class="footer-actions">
          <button
            type="button"
            class="btn-cancel"
            :disabled="isSaving"
            @click="handleClose"
          >
            Cancel
          </button>

          <button
            type="button"
            class="btn-save-primary"
            :disabled="isSaving || validationErrors.length > 0"
            @click="handleSave"
          >
            <Loader2 v-if="isSaving" :size="15" class="animate-spin" />
            <span>{{ isSaving ? 'Saving Corrections…' : 'Save Changes' }}</span>
          </button>
        </div>
      </footer>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.zen-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay, rgba(0, 0, 0, 0.75));
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1050;
  padding: 1.5rem;
}

.zen-modal-dialog {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg, 10px);
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6);
  width: 100%;
  max-width: 96rem;
  height: 92vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
.zen-dialog-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 1.25rem 1.75rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-elevated);
}

.dialog-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
}

.badge-workspace {
  background: var(--accent-soft);
  color: var(--accent-brand);
  border: 1px solid var(--accent-border);
  font-family: var(--font-mono);
  font-size: 0.72rem;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
}

.dialog-subtitle {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.btn-close-dialog {
  color: var(--text-muted);
  background: transparent;
  border: none;
  padding: 0.35rem;
  border-radius: var(--radius-sm, 4px);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-close-dialog:hover {
  color: var(--text-primary);
  background: var(--border-default);
}

/* Body / Split View */
.zen-dialog-body {
  flex: 1;
  overflow: hidden;
  display: flex;
}

.workspace-split-container {
  display: flex;
  width: 100%;
  height: 100%;
}

/* Left Panel */
.original-preview-panel {
  width: 44%;
  border-right: 1px solid var(--border-default);
  background: var(--bg-subtle, #0b0f17);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.preview-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-default);
}

.preview-title-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.preview-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.preview-filename-badge {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.zoom-controls {
  display: flex;
  align-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 4px;
}

.btn-tool {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.3rem 0.45rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s;
}

.btn-tool:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--border-default);
}

.btn-tool:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.zoom-indicator {
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  padding: 0 0.25rem;
}

.preview-viewport {
  flex: 1;
  overflow: auto;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(0, 0, 0, 0.4);
}

.preview-canvas {
  transform-origin: center top;
  transition: transform 0.2s cubic-bezier(0.2, 0, 0, 1);
  max-width: 100%;
}

.preview-image {
  max-width: 100%;
  border-radius: 4px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
  display: block;
}

.preview-iframe {
  width: 700px;
  height: 800px;
  border: none;
  border-radius: 4px;
  background: #fff;
}

.preview-loading-state,
.preview-fallback-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.preview-footer-note {
  padding: 0.5rem 1rem;
  border-top: 1px solid var(--border-default);
  background: var(--bg-elevated);
  font-size: 0.72rem;
  color: var(--text-muted);
}

/* Right Panel */
.editor-fields-panel {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Alerts */
.editor-alert {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.875rem 1rem;
  border-radius: var(--radius-md, 6px);
  font-size: 0.82rem;
}

.editor-alert ul {
  margin: 0.35rem 0 0;
  padding-left: 1.25rem;
}

.alert-danger {
  background: var(--status-error-bg, rgba(239, 68, 68, 0.12));
  border: 1px solid var(--status-error, #ef4444);
  color: #ef4444;
}

.alert-warning {
  background: var(--status-warning-bg, rgba(245, 158, 11, 0.12));
  border: 1px solid var(--status-warning-border, #f59e0b);
  color: #f59e0b;
}

/* Sections */
.form-section {
  padding: 1.25rem 1.5rem;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 8px);
  background: var(--bg-elevated);
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  margin-bottom: 1.25rem;
}

.section-icon {
  color: var(--accent-brand);
  margin-top: 0.15rem;
}

.section-title {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.section-desc {
  margin: 0.15rem 0 0;
  font-size: 0.76rem;
  color: var(--text-secondary);
}

/* Fields Grid */
.fields-grid {
  display: grid;
  gap: 1rem;
}

.grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.grid-4 {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.col-span-2 {
  grid-column: span 2 / span 2;
}

.input-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.field-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.input-field input {
  padding: 0.55rem 0.75rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 4px);
  color: var(--text-primary);
  font-size: 0.85rem;
  transition: all 0.15s ease;
}

.input-field input:focus {
  outline: none;
  border-color: var(--accent-brand);
  box-shadow: 0 0 0 1px var(--accent-brand);
}

.input-currency-wrapper {
  display: flex;
  align-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 4px);
  overflow: hidden;
}

.curr-prefix {
  padding: 0 0.6rem;
  font-size: 0.8rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
  background: var(--bg-elevated);
  border-right: 1px solid var(--border-default);
}

.input-currency-wrapper input {
  flex: 1;
  border: none;
  background: transparent;
  font-family: var(--font-mono);
}

.highlight-field .input-currency-wrapper {
  border-color: var(--status-success-border, #10b981);
}

.total-input {
  font-weight: 700;
  color: var(--status-success, #10b981) !important;
}

.arithmetic-helper-box {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm, 4px);
  padding: 0.6rem 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.74rem;
}

.helper-label {
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  font-size: 0.68rem;
  letter-spacing: 0.04em;
}

.helper-row {
  display: flex;
  justify-content: space-between;
  color: var(--text-secondary);
}

.helper-row strong {
  font-family: var(--font-mono);
  color: var(--text-primary);
}

/* Direction Cards */
.direction-selector {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.85rem;
}

.direction-card-option {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding: 0.85rem 1rem;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md, 6px);
  background: var(--bg-surface);
  cursor: pointer;
  transition: all 0.2s ease;
}

.direction-card-option:hover {
  border-color: var(--border-medium);
  background: var(--bg-elevated);
}

.direction-card-option.selected {
  border-color: var(--accent-brand);
  background: var(--accent-soft);
  box-shadow: 0 0 0 1px var(--accent-brand);
}

.dir-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 0.25rem;
  flex-shrink: 0;
}

.dot-expense { background: #ef4444; }
.dot-income { background: #10b981; }
.dot-unclassified { background: var(--text-muted); }

.dir-info {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.dir-name {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
}

.dir-desc {
  font-size: 0.72rem;
  color: var(--text-secondary);
  line-height: 1.35;
}

/* Line Items */
.line-items-header {
  justify-content: space-between;
  margin-bottom: 0.85rem;
}

.btn-toggle-section {
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  color: var(--text-secondary);
  padding: 0.25rem;
  cursor: pointer;
}

.line-items-table-wrapper {
  overflow-x: auto;
}

.line-items-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.line-items-table th {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--border-default);
  color: var(--text-muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.line-items-table td {
  padding: 0.45rem 0.5rem;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.th-num { width: 36px; text-align: center; }
.th-desc { min-width: 200px; }
.th-qty { width: 85px; }
.th-price { width: 105px; }
.th-tax { width: 95px; }
.th-total { width: 115px; }
.th-action { width: 36px; text-align: center; }

.table-input {
  width: 100%;
  padding: 0.4rem 0.55rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 3px;
  color: var(--text-primary);
  font-size: 0.8rem;
}

.table-input.mono {
  font-family: var(--font-mono);
}

.table-input.total-col {
  font-weight: 600;
}

.row-num-badge {
  display: inline-block;
  font-size: 0.7rem;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.btn-remove-line {
  background: transparent;
  border: none;
  color: var(--text-muted);
  padding: 0.25rem;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.15s;
}

.btn-remove-line:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.empty-line-items {
  text-align: center;
  padding: 1.5rem;
  color: var(--text-muted);
  font-size: 0.82rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

/* Footer */
.zen-dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.75rem;
  border-top: 1px solid var(--border-default);
  background: var(--bg-elevated);
}

.footer-left-status {
  font-size: 0.78rem;
}

.dirty-indicator {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: #f59e0b;
  font-weight: 500;
}

.dirty-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
}

.clean-indicator {
  color: var(--text-muted);
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-cancel {
  padding: 0.55rem 1.25rem;
  font-size: 0.84rem;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm, 5px);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-cancel:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--border-default);
}

.btn-save-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.55rem 1.35rem;
  font-size: 0.84rem;
  font-weight: 600;
  color: #fff;
  background: var(--accent-brand);
  border: 1px solid var(--accent-brand);
  border-radius: var(--radius-sm, 5px);
  cursor: pointer;
  transition: all 0.15s;
}

.btn-save-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.btn-save-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* Responsive */
@media (max-width: 1024px) {
  .workspace-split-container {
    flex-direction: column;
  }
  .original-preview-panel {
    width: 100%;
    height: 340px;
    border-right: none;
    border-bottom: 1px solid var(--border-default);
  }
  .editor-fields-panel {
    padding: 1.25rem;
  }
  .grid-4, .grid-3 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .direction-selector {
    grid-template-columns: 1fr;
  }
}
</style>
