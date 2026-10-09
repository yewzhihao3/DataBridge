<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  FileText,
  Info,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  ArrowLeft,
  ArrowRight,
  Trash2,
  ZoomIn,
} from 'lucide-vue-next'
import { api } from '@/services/api'
import { toast } from '@/services/toast'
import { useIngestionQueue } from '@/composables/useIngestionQueue'
import type { DocumentDetail, DocumentLineItem } from '@/types/api'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const { queue, markDocumentConfirmed } = useIngestionQueue()

const reviewableEntries = computed(() => {
  return queue.value.filter(
    (e) => (e.status === 'needs_review' || e.status === 'ready' || e.status === 'imported') && e.reviewPath
  )
})

const currentIndex = computed(() => {
  return reviewableEntries.value.findIndex((e) => e.documentId === id)
})

const prevEntry = computed(() => {
  if (currentIndex.value > 0) return reviewableEntries.value[currentIndex.value - 1]
  return null
})

const nextEntry = computed(() => {
  if (currentIndex.value >= 0 && currentIndex.value < reviewableEntries.value.length - 1) {
    return reviewableEntries.value[currentIndex.value + 1]
  }
  return null
})

function goToEntry(entry: any) {
  if (entry.reviewPath) router.push(entry.reviewPath)
}

const detail = ref<DocumentDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const previewUrl = ref('')
const showExtendedDetails = ref(false)
const reprocessMode = ref<'auto' | 'vision_only' | 'local_ocr'>('auto')
const showAiNotes = ref(false)

const form = reactive({
  company_name: '',
  invoice_number: '',
  invoice_date: '',
  merchant_name: '',
  receipt_number: '',
  transaction_date: '',
  transaction_time: '',
  subtotal: '',
  tax_amount: '',
  total_amount: '',
  currency: '',
  payment_method: '',
  store_address: '',
  cash_paid: '',
  change_amount: '',
  service_charge: '',
  discount_amount: '',
  rounding_adjustment: '',
  line_items: [] as DocumentLineItem[],
})

const isReceipt = computed(() => detail.value?.document_type === 'receipt')
const confidence = (name: string) => detail.value?.fields[name]?.confidence || 'low'
const source = (name: string) => detail.value?.fields[name]?.text || ''
const isPdf = computed(() => previewUrl.value.includes('application/pdf'))

const providerInfo = computed(() => {
  if (!detail.value) return { label: 'Processing Engine', type: 'unknown', icon: Cpu, badgeClass: 'badge-muted' }
  const prov = detail.value.provider || ''
  if (prov.startsWith('deepseek_vision')) {
    const model = prov.replace('deepseek_vision:', '') || 'deepseek'
    return {
      label: `AI Vision (${model})`,
      type: 'ai',
      icon: Sparkles,
      badgeClass: 'badge-ai',
      method: detail.value.processing_method,
    }
  }
  if (prov === 'tesseract') {
    return {
      label: 'Local OCR (Tesseract)',
      type: 'ocr',
      icon: Cpu,
      badgeClass: 'badge-ocr',
      method: detail.value.processing_method,
    }
  }
  if (prov === 'pypdf') {
    return {
      label: 'Native PDF (pypdf)',
      type: 'native',
      icon: FileText,
      badgeClass: 'badge-native',
      method: detail.value.processing_method,
    }
  }
  if (prov.includes('+')) {
    return {
      label: 'Mixed PDF (OCR + Native)',
      type: 'mixed',
      icon: Layers,
      badgeClass: 'badge-mixed',
      method: detail.value.processing_method,
    }
  }
  return {
    label: prov,
    type: 'custom',
    icon: Cpu,
    badgeClass: 'badge-muted',
    method: detail.value.processing_method,
  }
})

const fallbackNotice = computed(() => {
  if (!detail.value) return null
  const fallbackWarning = detail.value.warnings.find((w) =>
    w.toLowerCase().includes('fell back to local ocr') || w.toLowerCase().includes('fell back to local'),
  )
  if (fallbackWarning) {
    return {
      title: 'AI Vision Fallback Active',
      body: 'AI Vision extraction was unavailable or encountered an error. DataBridge gracefully fell back to the local Tesseract OCR engine. Please verify the extracted fields below.',
    }
  }
  return null
})

const ocrNotice = computed(() => {
  if (!detail.value) return null
  if (detail.value.ocr_status === 'provider_unavailable') {
    return {
      title: 'Image OCR is not available in this environment.',
      body: 'Tesseract OCR could not be found. Install Tesseract or configure DeepSeek Vision.',
    }
  }
  if (detail.value.ocr_status === 'failed' && !fallbackNotice.value) {
    return {
      title: 'DataBridge could not extract text from this document.',
      body: detail.value.error_message || 'Retry extraction or enter details manually.',
    }
  }
  if (detail.value.ocr_status === 'unsupported') {
    return {
      title: 'This PDF appears to contain scanned pages and could not be read as text.',
      body: detail.value.ocr_message || 'Image-based PDF OCR is processing.',
    }
  }
  return null
})

const calculatedLineItemTotal = computed(() => {
  let sum = 0
  let hasValid = false
  for (const item of form.line_items) {
    const val = parseFloat(String(item.amount || '0'))
    if (!isNaN(val) && val > 0) {
      sum += val
      hasValid = true
    }
  }
  return hasValid ? sum.toFixed(2) : null
})

const lineItemSumMismatch = computed(() => {
  if (!calculatedLineItemTotal.value || !form.subtotal) return false
  const subtotalVal = parseFloat(form.subtotal)
  const calcVal = parseFloat(calculatedLineItemTotal.value)
  if (isNaN(subtotalVal) || isNaN(calcVal)) return false
  return Math.abs(subtotalVal - calcVal) > 0.05
})

function apply(result: DocumentDetail) {
  detail.value = result
  const keys = [
    'company_name',
    'invoice_number',
    'invoice_date',
    'merchant_name',
    'receipt_number',
    'transaction_date',
    'transaction_time',
    'subtotal',
    'tax_amount',
    'total_amount',
    'currency',
    'payment_method',
    'store_address',
    'cash_paid',
    'change_amount',
    'service_charge',
    'discount_amount',
    'rounding_adjustment',
  ] as const

  for (const key of keys) {
    form[key] = (result.fields[key]?.value || '') as any
  }
  form.line_items = (result.line_items || []).map((row) => ({ ...row }))
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [result, blob] = await Promise.all([api.getDocument(id), api.getDocumentPreview(id)])
    apply(result)
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = URL.createObjectURL(blob)
  } catch (e: any) {
    error.value = e.message || 'Could not load this document.'
  } finally {
    loading.value = false
  }
}

async function changeType(event: Event) {
  const type = (event.target as HTMLSelectElement).value as 'invoice' | 'receipt'
  saving.value = true
  try {
    apply(await api.parseDocumentAs(id, type))
    toast.success(`Parsed as ${type}`)
  } catch (e: any) {
    toast.error(e.message || 'Could not change document type')
  } finally {
    saving.value = false
  }
}

async function reprocess() {
  if (!confirm(`Reprocess using '${reprocessMode.value}' mode? Your current unsaved edits will be refreshed.`)) {
    return
  }
  saving.value = true
  try {
    const updated = await api.reprocessDocument(id, reprocessMode.value)
    apply(updated)
    toast.success(`Document reprocessed via ${reprocessMode.value}`)
  } catch (e: any) {
    toast.error(e.message || 'Could not reprocess document')
  } finally {
    saving.value = false
  }
}

async function confirmImport() {
  const missing = isReceipt.value
    ? !form.merchant_name.trim()
    : !form.company_name.trim() || !form.invoice_number.trim()

  if (missing) {
    error.value = isReceipt.value
      ? 'Merchant name is required before import.'
      : 'Company name and invoice number are required before import.'
    return
  }

  saving.value = true
  error.value = ''
  try {
    await api.confirmDocument(id, {
      ...form,
      document_type: detail.value?.document_type,
      total_amount: form.total_amount || null,
      subtotal: form.subtotal || null,
      tax_amount: form.tax_amount || null,
      invoice_date: form.invoice_date || null,
      transaction_date: form.transaction_date || null,
      currency: form.currency || null,
      cash_paid: form.cash_paid || null,
      change_amount: form.change_amount || null,
      service_charge: form.service_charge || null,
      discount_amount: form.discount_amount || null,
      rounding_adjustment: form.rounding_adjustment || null,
      payment_method: form.payment_method || null,
      store_address: form.store_address || null,
    })
    markDocumentConfirmed(id)
    toast.success(`${isReceipt.value ? 'Receipt' : 'Invoice'} imported successfully`)
    if (nextEntry.value) {
      router.push(nextEntry.value.reviewPath!)
    } else {
      router.push('/history')
    }
  } catch (e: any) {
    error.value = e.message || 'Import could not be confirmed.'
    if (error.value.toLowerCase().includes('duplicate')) {
      toast.warning(`Possible duplicate ${isReceipt.value ? 'receipt' : 'invoice'}`)
    }
  } finally {
    saving.value = false
  }
}

function addLine() {
  form.line_items.push({
    description: '',
    quantity: '1',
    unit_price: '',
    tax_rate: null,
    tax_amount: null,
    amount: '',
  })
}

function calculateItemAmount(line: DocumentLineItem) {
  if (line.quantity && line.unit_price && !line.amount) {
    const q = parseFloat(String(line.quantity))
    const p = parseFloat(String(line.unit_price))
    if (!isNaN(q) && !isNaN(p)) {
      line.amount = (q * p).toFixed(2)
    }
  }
}

onMounted(load)
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})
</script>

<template>
  <main class="document-review container">
    <header class="review-header glass-card">
      <div class="header-top">
        <router-link to="/" class="back-link">
          <ArrowLeft :size="16" />
          Back to Ingestion
        </router-link>

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
        <div>
          <p class="eyebrow">DOCUMENT INGESTION & AUDIT</p>
          <h1>Review Document</h1>
          <p class="header-sub">Verify and correct extracted fields before confirming into system records.</p>
        </div>
        <div class="type-controls">
          <label>
            Document type
            <select :value="detail?.document_type" :disabled="saving" @change="changeType">
              <option value="invoice">Invoice</option>
              <option value="receipt">Receipt</option>
            </select>
          </label>
          <span class="status">{{ detail?.status?.replace('_', ' ') || 'Loading' }}</span>
        </div>
      </div>
    </header>

    <section v-if="loading" class="glass-card loading">
      <Loader2 class="animate-spin" :size="24" />
      <span>Loading extraction & document preview…</span>
    </section>

    <section v-else-if="error && !detail" class="glass-card notice error">
      <AlertTriangle :size="20" />
      <div>
        <strong>Failed to load document</strong>
        <p>{{ error }}</p>
      </div>
      <button class="btn btn-secondary" @click="load">Retry</button>
    </section>

    <section v-else-if="detail" class="review-grid">
      <!-- Left Column: Document Preview -->
      <article class="glass-card preview">
        <div class="preview-header">
          <h2>Original Document</h2>
          <div :class="['engine-badge', providerInfo.badgeClass]">
            <component :is="providerInfo.icon" :size="14" />
            <span>{{ providerInfo.label }}</span>
          </div>
        </div>

        <iframe v-if="isPdf" :src="previewUrl" title="Document preview" />
        <img v-else :src="previewUrl" alt="Uploaded document preview" />

        <p class="muted">
          <ZoomIn :size="14" />
          <span>Native zoom & pan available. Processed via <code>{{ detail.processing_method }}</code>.</span>
        </p>
      </article>

      <!-- Right Column: Extracted Values Form -->
      <article class="glass-card form">
        <div class="form-heading">
          <div>
            <h2>
              Extracted {{ isReceipt ? 'Receipt' : detail.document_type === 'invoice' ? 'Invoice' : 'Document' }}
            </h2>
            <p>Review confidence flags and edit fields directly.</p>
          </div>

          <div class="reprocess-group">
            <select v-model="reprocessMode" :disabled="saving" class="mode-select" title="Extraction engine mode">
              <option value="auto">Auto (AI / OCR)</option>
              <option value="vision_only">Vision AI Only</option>
              <option value="local_ocr">Local OCR Only</option>
            </select>
            <button class="btn btn-secondary reprocess-btn" :disabled="saving" @click="reprocess">
              <RefreshCw :size="14" :class="{ 'animate-spin': saving }" />
              <span>Reprocess</span>
            </button>
          </div>
        </div>

        <!-- Fallback Warning Notice -->
        <div v-if="fallbackNotice" class="notice fallback-banner">
          <AlertTriangle :size="20" />
          <div>
            <strong>{{ fallbackNotice.title }}</strong>
            <p>{{ fallbackNotice.body }}</p>
          </div>
        </div>

        <!-- OCR Error Notice -->
        <div v-if="ocrNotice" class="notice warning">
          <AlertTriangle :size="18" />
          <div>
            <strong>{{ ocrNotice.title }}</strong>
            <p>{{ ocrNotice.body }}</p>
          </div>
        </div>

        <!-- Structured Validation Items (severity-categorized) -->
        <div v-if="detail.validation_items?.length" class="validation-summary">
          <div v-if="detail.validation_items.filter(i => i.severity === 'error').length" class="notice v-error">
            <AlertCircle :size="18" class="notice-icon" />
            <div>
              <strong>Action Required</strong>
              <ul>
                <li v-for="item in detail.validation_items.filter(i => i.severity === 'error')" :key="item.message">
                  {{ item.message }}<span v-if="item.details" class="v-detail"> — {{ item.details }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div v-if="detail.validation_items.filter(i => i.severity === 'warning').length" class="notice v-warning">
            <AlertTriangle :size="18" class="notice-icon" />
            <div>
              <strong>Needs Attention</strong>
              <ul>
                <li v-for="item in detail.validation_items.filter(i => i.severity === 'warning')" :key="item.message">
                  {{ item.message }}<span v-if="item.details" class="v-detail"> — {{ item.details }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div v-if="detail.validation_items.filter(i => i.severity === 'info').length" class="notice v-info">
            <Info :size="18" class="notice-icon" />
            <div>
              <strong>Information</strong>
              <ul>
                <li v-for="item in detail.validation_items.filter(i => i.severity === 'info')" :key="item.message">
                  {{ item.message }}<span v-if="item.details" class="v-detail"> — {{ item.details }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div v-if="detail.validation_items.filter(i => i.severity === 'success').length" class="notice v-success">
            <CheckCircle2 :size="18" class="notice-icon" />
            <div>
              <strong>Validated</strong>
              <ul>
                <li v-for="item in detail.validation_items.filter(i => i.severity === 'success')" :key="item.message">
                  {{ item.message }}
                </li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Legacy flat warnings fallback (no structured items) -->
        <div v-else-if="detail.warnings.length" class="notice v-warning">
          <AlertTriangle :size="18" />
          <div>
            <strong>Needs Review &amp; Verification</strong>
            <ul>
              <li v-for="warning in detail.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </div>
        </div>

        <!-- AI Notes (collapsible) -->
        <div v-if="detail.ai_notes?.length" class="ai-notes-section">
          <button type="button" class="btn-toggle" @click="showAiNotes = !showAiNotes">
            <Bot :size="14" />
            <span>AI Extraction Notes ({{ detail.ai_notes.length }})</span>
            <ChevronUp v-if="showAiNotes" :size="14" />
            <ChevronDown v-else :size="14" />
          </button>
          <div v-if="showAiNotes" class="ai-notes-body">
            <p v-for="note in detail.ai_notes" :key="note" class="ai-note">{{ note }}</p>
          </div>
        </div>

        <!-- Line Item Reconciliation Mismatch Live Warning -->
        <div v-if="lineItemSumMismatch" class="notice warning">
          <AlertTriangle :size="18" />
          <div>
            <strong>Arithmetic Discrepancy</strong>
            <p>
              Calculated sum of line items ({{ form.currency || '' }} {{ calculatedLineItemTotal }}) does not match the
              subtotal ({{ form.currency || '' }} {{ form.subtotal }}).
            </p>
          </div>
        </div>

        <div v-if="error" class="notice error">
          <AlertTriangle :size="18" />
          <div>{{ error }}</div>
        </div>

        <!-- Receipt Form Fields -->
        <div v-if="isReceipt" class="fields-section">
          <div class="fields">
            <label :class="`confidence-${confidence('merchant_name')}`">
              <span class="field-label">
                Merchant name
                <em :class="`pill-${confidence('merchant_name')}`">{{ confidence('merchant_name') }}</em>
              </span>
              <input v-model="form.merchant_name" placeholder="e.g. Petronas Dagangan" />
              <small v-if="source('merchant_name')">Source: {{ source('merchant_name') }}</small>
            </label>

            <label :class="`confidence-${confidence('receipt_number')}`">
              <span class="field-label">
                Receipt / Txn #
                <em :class="`pill-${confidence('receipt_number')}`">{{ confidence('receipt_number') }}</em>
              </span>
              <input v-model="form.receipt_number" placeholder="e.g. TXN-100234" />
              <small v-if="source('receipt_number')">Source: {{ source('receipt_number') }}</small>
            </label>

            <label :class="`confidence-${confidence('transaction_date')}`">
              <span class="field-label">
                Transaction date
                <em :class="`pill-${confidence('transaction_date')}`">{{ confidence('transaction_date') }}</em>
              </span>
              <input v-model="form.transaction_date" type="date" />
            </label>

            <label>
              <span class="field-label">Transaction time</span>
              <input v-model="form.transaction_time" placeholder="HH:MM (e.g. 14:35)" />
            </label>

            <label :class="`confidence-${confidence('currency')}`">
              <span class="field-label">
                Currency
                <em :class="`pill-${confidence('currency')}`">{{ confidence('currency') }}</em>
              </span>
              <input v-model="form.currency" placeholder="MYR, USD, SGD, EUR" />
            </label>

            <label>
              <span class="field-label">Subtotal</span>
              <input v-model="form.subtotal" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label>
              <span class="field-label">Tax amount (SST / GST)</span>
              <input v-model="form.tax_amount" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label :class="`confidence-${confidence('total_amount')}`">
              <span class="field-label">
                Total amount
                <em :class="`pill-${confidence('total_amount')}`">{{ confidence('total_amount') }}</em>
              </span>
              <input v-model="form.total_amount" type="number" step="0.01" placeholder="0.00" />
            </label>
          </div>

          <!-- Collapsible Extended Receipt Metadata -->
          <div class="extended-toggle">
            <button type="button" class="btn-toggle" @click="showExtendedDetails = !showExtendedDetails">
              <span>Additional Receipt Information (Address, Payment, Rounding)</span>
              <ChevronUp v-if="showExtendedDetails" :size="16" />
              <ChevronDown v-else :size="16" />
            </button>
          </div>

          <div v-if="showExtendedDetails" class="fields extended-fields">
            <label class="full-width">
              <span class="field-label">Store / Merchant Address</span>
              <input v-model="form.store_address" placeholder="Store address or branch location" />
            </label>

            <label>
              <span class="field-label">Payment Method</span>
              <input v-model="form.payment_method" placeholder="Cash, Credit Card, Touch 'n Go, etc." />
            </label>

            <label>
              <span class="field-label">Cash Paid</span>
              <input v-model="form.cash_paid" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label>
              <span class="field-label">Change Amount</span>
              <input v-model="form.change_amount" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label>
              <span class="field-label">Rounding Adjustment</span>
              <input v-model="form.rounding_adjustment" type="number" step="0.01" placeholder="e.g. -0.02" />
            </label>

            <label>
              <span class="field-label">Service Charge</span>
              <input v-model="form.service_charge" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label>
              <span class="field-label">Discount Amount</span>
              <input v-model="form.discount_amount" type="number" step="0.01" placeholder="0.00" />
            </label>
          </div>
        </div>

        <!-- Invoice Form Fields -->
        <div v-else class="fields">
          <label
            v-for="item in [
              ['company_name', 'Company name'],
              ['invoice_number', 'Invoice number'],
              ['invoice_date', 'Invoice date'],
              ['currency', 'Currency'],
              ['total_amount', 'Total amount'],
            ]"
            :key="item[0]"
            :class="`confidence-${confidence(item[0])}`"
          >
            <span class="field-label">
              {{ item[1] }}
              <em :class="`pill-${confidence(item[0])}`">{{ confidence(item[0]) }}</em>
            </span>
            <input
              v-model="form[item[0] as 'company_name']"
              :type="item[0] === 'invoice_date' ? 'date' : item[0] === 'total_amount' ? 'number' : 'text'"
            />
            <small v-if="source(item[0])">Source: {{ source(item[0]) }}</small>
          </label>
        </div>

        <!-- Line Items Section -->
        <div class="line-items-section">
          <div class="line-items-header">
            <h3>Line Items ({{ form.line_items.length }})</h3>
            <span v-if="calculatedLineItemTotal" class="calculated-sum">
              Sum: {{ form.currency || '' }} {{ calculatedLineItemTotal }}
            </span>
          </div>

          <p v-if="!form.line_items.length" class="muted">
            No itemized rows detected. You can import the document header or add line items manually below.
          </p>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Description</th>
                  <th style="width: 80px">Qty</th>
                  <th style="width: 100px">Unit Price</th>
                  <th style="width: 80px">Tax %</th>
                  <th style="width: 90px">Tax Amt</th>
                  <th style="width: 110px">Amount</th>
                  <th style="width: 40px"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in form.line_items" :key="index">
                  <td>
                    <input v-model="line.description" placeholder="Item description" />
                  </td>
                  <td>
                    <input
                      v-model="line.quantity"
                      type="number"
                      step="any"
                      placeholder="1"
                      @input="calculateItemAmount(line)"
                    />
                  </td>
                  <td>
                    <input
                      v-model="line.unit_price"
                      type="number"
                      step="0.01"
                      placeholder="0.00"
                      @input="calculateItemAmount(line)"
                    />
                  </td>
                  <td>
                    <input v-model="line.tax_rate" type="number" step="0.1" placeholder="%" />
                  </td>
                  <td>
                    <input v-model="line.tax_amount" type="number" step="0.01" placeholder="0.00" />
                  </td>
                  <td>
                    <input v-model="line.amount" type="number" step="0.01" placeholder="0.00" />
                  </td>
                  <td>
                    <button
                      class="btn-icon delete-btn"
                      title="Remove line item"
                      aria-label="Delete line item"
                      @click="form.line_items.splice(index, 1)"
                    >
                      <Trash2 :size="14" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Action Buttons -->
        <div class="actions">
          <button class="btn btn-secondary" @click="addLine">
            <Plus :size="16" />
            <span>Add Line Item</span>
          </button>
          <button class="btn btn-primary" :disabled="saving" @click="confirmImport">
            <Loader2 v-if="saving" class="animate-spin" :size="16" />
            <CheckCircle2 v-else :size="16" />
            <span>Confirm & Import</span>
          </button>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.document-review {
  padding-block: 2rem;
}

.document-review header,
.form-heading,
.actions,
.type-controls,
.preview-header,
.line-items-header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.type-controls {
  align-items: center;
}

.type-controls label {
  display: grid;
  gap: 0.25rem;
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.type-controls select,
.mode-select {
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.85rem;
}

.reprocess-group {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.reprocess-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.75rem;
}

.eyebrow {
  color: var(--accent-brand);
  font-weight: 700;
  font-size: 0.75rem;
  letter-spacing: 0.08em;
}

.document-review h1,
.document-review h2,
.document-review h3 {
  margin: 0.2rem 0;
}

.document-review header p,
.muted {
  color: var(--text-secondary);
}

.status {
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  background: var(--status-warning-bg);
  color: var(--status-warning);
  text-transform: capitalize;
  font-size: 0.8rem;
  font-weight: 600;
}

.review-grid {
  display: grid;
  grid-template-columns: minmax(320px, 1fr) minmax(460px, 1.3fr);
  gap: 1.5rem;
  margin-top: 1.5rem;
}

.preview,
.form,
.loading {
  padding: 1.25rem;
}

.preview iframe,
.preview img {
  width: 100%;
  height: 68vh;
  border: 0;
  object-fit: contain;
  background: var(--bg-subtle);
  margin-top: 1rem;
  border-radius: var(--radius-sm);
}

.preview .muted {
  display: flex;
  gap: 0.4rem;
  align-items: center;
  margin-top: 0.75rem;
  font-size: 0.8rem;
}

.engine-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}

.badge-ai {
  background: rgba(147, 51, 234, 0.12);
  color: #a855f7;
  border: 1px solid rgba(147, 51, 234, 0.25);
}

.badge-ocr {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  border: 1px solid rgba(59, 130, 246, 0.25);
}

.badge-native {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.badge-mixed {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.badge-muted {
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.notice {
  padding: 0.85rem 1rem;
  margin: 1rem 0;
  border-radius: var(--radius-sm);
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  font-size: 0.88rem;
}

.notice ul {
  margin: 0.3rem 0 0 1.2rem;
  padding: 0;
}

.warning {
  background: var(--status-warning-bg);
  color: var(--status-warning);
  border: 1px solid var(--status-warning-border);
}

.fallback-banner {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.error {
  background: var(--status-error-bg);
  color: var(--status-error);
  border: 1px solid var(--status-error-border);
}

/* ── Severity-band validation notices ─────────────────────────── */
.validation-summary {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 0.75rem 0;
}

.validation-summary .notice {
  margin: 0;
}

.v-error {
  background: var(--status-error-bg);
  color: var(--status-error);
  border: 1px solid var(--status-error-border);
}

.v-warning {
  background: var(--status-warning-bg);
  color: var(--status-warning);
  border: 1px solid var(--status-warning-border);
}

.v-info {
  background: rgba(59, 130, 246, 0.08);
  color: #60a5fa;
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.v-success {
  background: rgba(16, 185, 129, 0.08);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.notice-icon {
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.v-detail {
  opacity: 0.75;
  font-size: 0.82em;
}

/* ── AI Notes section ─────────────────────────────────────────── */
.ai-notes-section {
  margin-top: 0.75rem;
}

.ai-notes-body {
  margin-top: 0.5rem;
  padding: 0.75rem 1rem;
  background: rgba(147, 51, 234, 0.05);
  border: 1px solid rgba(147, 51, 234, 0.15);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.ai-note {
  font-size: 0.82rem;
  color: #a78bfa;
  margin: 0;
  padding-left: 0.5rem;
  border-left: 2px solid rgba(167, 139, 250, 0.4);
}


.fields-section {
  margin-top: 1rem;
}

.fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.9rem;
}

.full-width {
  grid-column: 1 / -1;
}

.fields label {
  display: grid;
  gap: 0.3rem;
}

.field-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.pill-high,
.pill-medium,
.pill-low {
  font-style: normal;
  text-transform: uppercase;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
}

.pill-high {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.pill-medium {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.pill-low {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.fields input,
table input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  color: var(--text-primary);
  font-size: 0.88rem;
}

.confidence-low input {
  border-color: rgba(239, 68, 68, 0.6);
  background: rgba(239, 68, 68, 0.03);
}

.confidence-medium input {
  border-color: rgba(245, 158, 11, 0.6);
  background: rgba(245, 158, 11, 0.03);
}

small {
  color: var(--text-muted);
  font-size: 0.72rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.extended-toggle {
  margin-top: 1rem;
}

.btn-toggle {
  background: none;
  border: none;
  color: var(--accent-brand);
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0;
}

.extended-fields {
  margin-top: 0.75rem;
  padding: 0.85rem;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
}

.line-items-section {
  margin-top: 1.5rem;
}

.calculated-sum {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent-brand);
}

.table-wrap {
  overflow-x: auto;
  margin-top: 0.5rem;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: 0.4rem;
  text-align: left;
}

th {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-weight: 600;
}

.btn-icon {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.35rem;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.delete-btn:hover {
  color: var(--status-error);
  background: var(--status-error-bg);
}

.actions {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-subtle);
  align-items: center;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 850px) {
  .review-grid {
    grid-template-columns: 1fr;
  }
  .preview iframe,
  .preview img {
    height: 48vh;
  }
  .fields {
    grid-template-columns: 1fr;
  }
  .document-review header {
    flex-direction: column;
  }
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 0.75rem;
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

.header-sub {
  color: var(--text-secondary);
  margin: 0.35rem 0 0 0;
  font-size: 0.9rem;
}

</style>
