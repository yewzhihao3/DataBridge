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
  ExternalLink,
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

const originalFilename = computed(() => {
  return detail.value?.original_filename || reviewableEntries.value.find((e) => e.documentId === id)?.name || ''
})

// â”€â”€ Duplicate conflict state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const duplicateConflict = ref<{
  message: string
  recordId: number | null
  docType: string | null
  docNumber?: string | null
  counterparty?: string | null
  date?: string | null
  amount?: string | null
  currency?: string | null
  reason?: string | null
} | null>(null)

const form = reactive({
  company_name: '',
  invoice_number: '',
  invoice_date: '',
  direction: 'unclassified',
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

function formatDirectionLabel(dir: string): string {
  if (dir === 'sales') return 'Sales (AR)'
  if (dir === 'purchase') return 'Purchase (AP)'
  if (dir === 'expense') return 'Expense'
  if (dir === 'income') return 'Income'
  return 'Unclassified'
}

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
  form.direction = 'unclassified'
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

  duplicateConflict.value = null
  saving.value = true
  error.value = ''
  try {
    await api.confirmDocument(id, {
      ...form,
      direction: form.direction || 'unclassified',
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
    if (e?.isDuplicateConflict) {
      const cleanMsg = (e.message || 'A possible duplicate record already exists.')
        .replace(/Set acknowledge_duplicate=true to confirm\.?/gi, '')
        .trim()
      duplicateConflict.value = {
        message: cleanMsg,
        recordId: e.duplicateRecordId ?? null,
        docType: e.duplicateDocumentType ?? (isReceipt.value ? 'receipt' : 'invoice'),
        docNumber: e.duplicateDocNumber || (isReceipt.value ? form.receipt_number : form.invoice_number) || null,
        counterparty: e.duplicateCounterparty || (isReceipt.value ? form.merchant_name : form.company_name) || null,
        date: e.duplicateDate || (isReceipt.value ? form.transaction_date : form.invoice_date) || null,
        amount: e.duplicateAmount || form.total_amount || null,
        currency: e.duplicateCurrency || form.currency || null,
        reason: cleanMsg,
      }
    } else {
      error.value = e.message || 'Import could not be confirmed.'
    }
  } finally {
    saving.value = false
  }
}

function cancelDuplicateWarning() {
  duplicateConflict.value = null
  error.value = ''
}

function viewExisting() {
  if (!duplicateConflict.value?.recordId) return
  const docType = duplicateConflict.value.docType || (isReceipt.value ? 'receipt' : 'invoice')
  const tab = docType === 'invoice' ? 'invoices' : 'receipts'
  const routeUrl = router.resolve({
    path: '/explorer',
    query: {
      tab,
      recordId: String(duplicateConflict.value.recordId),
      docType,
    },
  })
  window.open(routeUrl.href, '_blank')
}

async function acknowledgeImport() {
  const missing = isReceipt.value
    ? !form.merchant_name.trim()
    : !form.company_name.trim() || !form.invoice_number.trim()

  if (missing) {
    error.value = isReceipt.value
      ? 'Merchant name is required before import.'
      : 'Company name and invoice number are required before import.'
    return
  }
  duplicateConflict.value = null
  saving.value = true
  error.value = ''
  try {
    await api.confirmDocument(id, {
      ...form,
      direction: form.direction || 'unclassified',
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
      acknowledge_duplicate: true,
    })
    markDocumentConfirmed(id)
    toast.success(`${isReceipt.value ? 'Receipt' : 'Invoice'} imported (duplicate acknowledged)`)
    if (nextEntry.value) {
      router.push(nextEntry.value.reviewPath!)
    } else {
      router.push('/history')
    }
  } catch (e: any) {
    error.value = e.message || 'Import could not be confirmed.'
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

    <!-- â”€â”€ Page Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <header class="review-header">
      <div class="header-row-top">
        <router-link to="/" class="back-link">
          <ArrowLeft :size="15" />
          Back to Ingestion
        </router-link>

        <div v-if="reviewableEntries.length > 1" class="queue-nav">
          <button class="queue-nav-btn" :disabled="!prevEntry" @click="prevEntry && goToEntry(prevEntry)">
            <ArrowLeft :size="13" /> Prev
          </button>
          <span class="queue-nav-counter">{{ currentIndex >= 0 ? currentIndex + 1 : 'â€”' }} / {{ reviewableEntries.length }}</span>
          <button class="queue-nav-btn" :disabled="!nextEntry" @click="nextEntry && goToEntry(nextEntry)">
            Next <ArrowRight :size="13" />
          </button>
        </div>
      </div>

      <div class="header-row-main">
        <div class="header-identity">
          <h1 class="header-title">Review Document</h1>
          <p v-if="originalFilename" class="header-filename">
            <FileText :size="13" />
            {{ originalFilename }}
          </p>
          <p v-else class="header-sub">Verify and correct extracted fields before confirming into system records.</p>
        </div>

        <div class="header-controls">
          <div class="doc-type-group">
            <span class="control-label">Document type</span>
            <select :value="detail?.document_type" :disabled="saving" @change="changeType" class="type-select">
              <option value="invoice">Invoice</option>
              <option value="receipt">Receipt</option>
            </select>
          </div>
          <span v-if="detail" class="status-pill">{{ detail.status.replace(/_/g, ' ') }}</span>
        </div>
      </div>
    </header>

    <!-- â”€â”€ Loading state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <div v-if="loading" class="state-card loading">
      <Loader2 class="animate-spin" :size="22" />
      <span>Loading extraction & document previewâ€¦</span>
    </div>

    <!-- â”€â”€ Error state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <div v-else-if="error && !detail" class="state-card notice-error">
      <AlertTriangle :size="20" />
      <div>
        <strong>Failed to load document</strong>
        <p>{{ error }}</p>
      </div>
      <button class="btn btn-secondary" @click="load">Retry</button>
    </div>

    <!-- â”€â”€ Main review split â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
    <section v-else-if="detail" class="review-grid">

      <!-- Left: Document Preview -->
      <aside class="pane pane-preview">
        <div class="pane-header">
          <h2 class="pane-title">Original Document</h2>
          <div :class="['engine-badge', providerInfo.badgeClass]">
            <component :is="providerInfo.icon" :size="13" />
            <span>{{ providerInfo.label }}</span>
          </div>
        </div>

        <div class="preview-viewport">
          <iframe v-if="isPdf" :src="previewUrl" title="Document preview" />
          <img v-else :src="previewUrl" alt="Uploaded document preview" />
        </div>

        <p class="preview-hint">
          <ZoomIn :size="13" />
          Native zoom & pan available Â· <code>{{ detail.processing_method }}</code>
        </p>
      </aside>

      <!-- Right: Extracted Form -->
      <div class="pane pane-form">

        <!-- Form header -->
        <div class="pane-header">
          <div>
            <h2 class="pane-title">
              Extracted {{ isReceipt ? 'Receipt' : detail.document_type === 'invoice' ? 'Invoice' : 'Document' }}
            </h2>
            <p class="pane-sub">Review confidence flags and edit fields directly.</p>
          </div>
          <div class="reprocess-group">
            <select v-model="reprocessMode" :disabled="saving" class="mode-select">
              <option value="auto">Auto (AI / OCR)</option>
              <option value="vision_only">Vision AI Only</option>
              <option value="local_ocr">Local OCR Only</option>
            </select>
            <button class="btn btn-secondary" :disabled="saving" @click="reprocess">
              <RefreshCw :size="13" :class="{ 'animate-spin': saving }" />
              Reprocess
            </button>
          </div>
        </div>

        <!-- â”€â”€ Notices area â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <div class="notices-stack" v-if="fallbackNotice || ocrNotice || detail.validation_items?.length || detail.warnings.length || lineItemSumMismatch || error || detail.ai_notes?.length">

          <div v-if="fallbackNotice" class="notice notice-warn">
            <AlertTriangle :size="16" class="notice-icon" />
            <div class="notice-body"><strong>{{ fallbackNotice.title }}</strong><p>{{ fallbackNotice.body }}</p></div>
          </div>

          <div v-if="ocrNotice" class="notice notice-warn">
            <AlertTriangle :size="16" class="notice-icon" />
            <div class="notice-body"><strong>{{ ocrNotice.title }}</strong><p>{{ ocrNotice.body }}</p></div>
          </div>

          <!-- Structured validation -->
          <template v-if="detail.validation_items?.length">
            <div v-if="detail.validation_items.filter(i => i.severity === 'error').length" class="notice notice-error">
              <AlertCircle :size="16" class="notice-icon" />
              <div class="notice-body">
                <strong>Action Required</strong>
                <ul>
                  <li v-for="item in detail.validation_items.filter(i => i.severity === 'error')" :key="item.message">
                    {{ item.message }}<span v-if="item.details" class="v-detail"> â€” {{ item.details }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-if="detail.validation_items.filter(i => i.severity === 'warning').length" class="notice notice-warn">
              <AlertTriangle :size="16" class="notice-icon" />
              <div class="notice-body">
                <strong>Needs Attention</strong>
                <ul>
                  <li v-for="item in detail.validation_items.filter(i => i.severity === 'warning')" :key="item.message">
                    {{ item.message }}<span v-if="item.details" class="v-detail"> â€” {{ item.details }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-if="detail.validation_items.filter(i => i.severity === 'info').length" class="notice notice-info">
              <Info :size="16" class="notice-icon" />
              <div class="notice-body">
                <strong>Information</strong>
                <ul>
                  <li v-for="item in detail.validation_items.filter(i => i.severity === 'info')" :key="item.message">
                    {{ item.message }}<span v-if="item.details" class="v-detail"> â€” {{ item.details }}</span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-if="detail.validation_items.filter(i => i.severity === 'success').length" class="notice notice-success">
              <CheckCircle2 :size="16" class="notice-icon" />
              <div class="notice-body">
                <strong>Validated</strong>
                <ul>
                  <li v-for="item in detail.validation_items.filter(i => i.severity === 'success')" :key="item.message">{{ item.message }}</li>
                </ul>
              </div>
            </div>
          </template>

          <!-- Legacy flat warnings -->
          <div v-else-if="detail.warnings.length" class="notice notice-warn">
            <AlertTriangle :size="16" class="notice-icon" />
            <div class="notice-body">
              <strong>Needs Review & Verification</strong>
              <ul><li v-for="w in detail.warnings" :key="w">{{ w }}</li></ul>
            </div>
          </div>

          <!-- AI Notes -->
          <div v-if="detail.ai_notes?.length" class="notice notice-ai">
            <Bot :size="16" class="notice-icon" />
            <div class="notice-body" style="flex:1;min-width:0">
              <button type="button" class="ai-toggle" @click="showAiNotes = !showAiNotes">
                AI Extraction Notes ({{ detail.ai_notes.length }})
                <ChevronUp v-if="showAiNotes" :size="13" />
                <ChevronDown v-else :size="13" />
              </button>
              <div v-if="showAiNotes" class="ai-notes-list">
                <p v-for="note in detail.ai_notes" :key="note" class="ai-note">{{ note }}</p>
              </div>
            </div>
          </div>

          <!-- Arithmetic mismatch -->
          <div v-if="lineItemSumMismatch" class="notice notice-warn">
            <AlertTriangle :size="16" class="notice-icon" />
            <div class="notice-body">
              <strong>Arithmetic Discrepancy</strong>
              <p>Calculated sum of line items ({{ form.currency || '' }} {{ calculatedLineItemTotal }}) does not match the subtotal ({{ form.currency || '' }} {{ form.subtotal }}).</p>
            </div>
          </div>

          <!-- General error -->
          <div v-if="error" class="notice notice-error">
            <AlertTriangle :size="16" class="notice-icon" />
            <div class="notice-body">{{ error }}</div>
          </div>
        </div>

        <!-- â”€â”€ Duplicate conflict â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <div v-if="duplicateConflict" class="duplicate-card" role="alert">
          <div class="duplicate-card-header">
            <AlertTriangle :size="20" class="dup-icon" />
            <div>
              <h3 class="dup-title">This document may already exist</h3>
              <p class="dup-desc">DataBridge found a document with matching information. Review the existing record before importing another copy.</p>
            </div>
          </div>

          <div class="dup-meta-grid">
            <div class="dup-field">
              <span class="dup-label">Type</span>
              <span class="dup-value">{{ duplicateConflict.docType || (isReceipt ? 'Receipt' : 'Invoice') }}</span>
            </div>
            <div class="dup-field">
              <span class="dup-label">Doc Number</span>
              <span class="dup-value mono">{{ duplicateConflict.docNumber || 'â€”' }}</span>
            </div>
            <div class="dup-field">
              <span class="dup-label">Counterparty</span>
              <span class="dup-value">{{ duplicateConflict.counterparty || 'â€”' }}</span>
            </div>
            <div class="dup-field">
              <span class="dup-label">Date</span>
              <span class="dup-value">{{ duplicateConflict.date || 'â€”' }}</span>
            </div>
            <div class="dup-field">
              <span class="dup-label">Amount</span>
              <span class="dup-value">{{ duplicateConflict.currency || form.currency || '' }} {{ duplicateConflict.amount || 'â€”' }}</span>
            </div>
          </div>
          <p v-if="duplicateConflict.reason" class="dup-reason">{{ duplicateConflict.reason }}</p>

          <div class="dup-actions">
            <button v-if="duplicateConflict.recordId" type="button" class="btn btn-secondary" @click="viewExisting">
              <ExternalLink :size="13" /> View Existing
            </button>
            <button type="button" class="btn btn-warn" :disabled="saving" @click="acknowledgeImport">
              <Loader2 v-if="saving" :size="13" class="animate-spin" /> Import Anyway
            </button>
            <button type="button" class="btn btn-secondary" :disabled="saving" @click="cancelDuplicateWarning">Cancel</button>
          </div>
        </div>

        <!-- â”€â”€ Financial Direction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <section class="form-section">
          <div class="section-header">
            <div>
              <h3 class="section-title">Financial Direction</h3>
              <p class="section-sub">Specify the business accounting context for this {{ isReceipt ? 'receipt' : 'invoice' }}.</p>
            </div>
            <span class="badge" :class="`badge-${form.direction}`">{{ formatDirectionLabel(form.direction) }}</span>
          </div>

          <div v-if="isReceipt" class="direction-grid">
            <label class="dir-opt" :class="{ active: form.direction === 'unclassified' }">
              <input type="radio" v-model="form.direction" value="unclassified" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Unclassified</span>
                <span class="dir-opt-desc">Default context; direction not specified.</span>
              </div>
            </label>
            <label class="dir-opt" :class="{ active: form.direction === 'expense' }">
              <input type="radio" v-model="form.direction" value="expense" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Expense Receipt</span>
                <span class="dir-opt-desc">Business payment made. Does not automatically settle invoices.</span>
              </div>
            </label>
            <label class="dir-opt" :class="{ active: form.direction === 'income' }">
              <input type="radio" v-model="form.direction" value="income" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Income Receipt</span>
                <span class="dir-opt-desc">Customer payment received into business.</span>
              </div>
            </label>
          </div>

          <div v-else class="direction-grid">
            <label class="dir-opt" :class="{ active: form.direction === 'unclassified' }">
              <input type="radio" v-model="form.direction" value="unclassified" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Unclassified</span>
                <span class="dir-opt-desc">Default; sales or purchase not specified.</span>
              </div>
            </label>
            <label class="dir-opt" :class="{ active: form.direction === 'sales' }">
              <input type="radio" v-model="form.direction" value="sales" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Sales Invoice</span>
                <span class="dir-opt-desc">Billed to customer (Accounts Receivable).</span>
              </div>
            </label>
            <label class="dir-opt" :class="{ active: form.direction === 'purchase' }">
              <input type="radio" v-model="form.direction" value="purchase" />
              <div class="dir-opt-text">
                <span class="dir-opt-label">Purchase Invoice</span>
                <span class="dir-opt-desc">Billed by supplier (Accounts Payable).</span>
              </div>
            </label>
          </div>

          <p class="section-note">
            <Info :size="12" />
            <span v-if="isReceipt">Direction indicates business context. DataBridge does not assume invoices are settled without matching evidence.</span>
            <span v-else>Sales/purchase records billing obligations. Invoiced amounts are distinguished from cash movements.</span>
          </p>
        </section>

        <!-- â”€â”€ Receipt Fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <section v-if="isReceipt" class="form-section">
          <h3 class="section-title">Receipt Details</h3>
          <div class="fields-grid">
            <label class="field-group" :class="`conf-${confidence('merchant_name')}`">
              <span class="field-label">Merchant name <em :class="`pill-${confidence('merchant_name')}`">{{ confidence('merchant_name') }}</em></span>
              <input v-model="form.merchant_name" placeholder="e.g. Petronas Dagangan" />
              <small v-if="source('merchant_name')">{{ source('merchant_name') }}</small>
            </label>

            <label class="field-group" :class="`conf-${confidence('receipt_number')}`">
              <span class="field-label">Receipt / Txn # <em :class="`pill-${confidence('receipt_number')}`">{{ confidence('receipt_number') }}</em></span>
              <input v-model="form.receipt_number" placeholder="e.g. TXN-100234" />
              <small v-if="source('receipt_number')">{{ source('receipt_number') }}</small>
            </label>

            <label class="field-group" :class="`conf-${confidence('transaction_date')}`">
              <span class="field-label">Transaction date <em :class="`pill-${confidence('transaction_date')}`">{{ confidence('transaction_date') }}</em></span>
              <input v-model="form.transaction_date" type="date" />
            </label>

            <label class="field-group">
              <span class="field-label">Transaction time</span>
              <input v-model="form.transaction_time" placeholder="HH:MM" />
            </label>

            <label class="field-group" :class="`conf-${confidence('currency')}`">
              <span class="field-label">Currency <em :class="`pill-${confidence('currency')}`">{{ confidence('currency') }}</em></span>
              <input v-model="form.currency" placeholder="MYR, USD, SGD, EUR" />
            </label>

            <label class="field-group">
              <span class="field-label">Subtotal</span>
              <input v-model="form.subtotal" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label class="field-group">
              <span class="field-label">Tax amount (SST / GST)</span>
              <input v-model="form.tax_amount" type="number" step="0.01" placeholder="0.00" />
            </label>

            <label class="field-group" :class="`conf-${confidence('total_amount')}`">
              <span class="field-label">Total amount <em :class="`pill-${confidence('total_amount')}`">{{ confidence('total_amount') }}</em></span>
              <input v-model="form.total_amount" type="number" step="0.01" placeholder="0.00" />
            </label>
          </div>

          <!-- Extended metadata -->
          <button type="button" class="expand-btn" @click="showExtendedDetails = !showExtendedDetails">
            <ChevronUp v-if="showExtendedDetails" :size="14" />
            <ChevronDown v-else :size="14" />
            Additional Receipt Information (Address, Payment, Rounding)
          </button>

          <div v-if="showExtendedDetails" class="fields-grid extended-fields">
            <label class="field-group span-2">
              <span class="field-label">Store / Merchant Address</span>
              <input v-model="form.store_address" placeholder="Store address or branch location" />
            </label>
            <label class="field-group">
              <span class="field-label">Payment Method</span>
              <input v-model="form.payment_method" placeholder="Cash, Credit Card, etc." />
            </label>
            <label class="field-group">
              <span class="field-label">Cash Paid</span>
              <input v-model="form.cash_paid" type="number" step="0.01" placeholder="0.00" />
            </label>
            <label class="field-group">
              <span class="field-label">Change Amount</span>
              <input v-model="form.change_amount" type="number" step="0.01" placeholder="0.00" />
            </label>
            <label class="field-group">
              <span class="field-label">Rounding Adjustment</span>
              <input v-model="form.rounding_adjustment" type="number" step="0.01" placeholder="e.g. -0.02" />
            </label>
            <label class="field-group">
              <span class="field-label">Service Charge</span>
              <input v-model="form.service_charge" type="number" step="0.01" placeholder="0.00" />
            </label>
            <label class="field-group">
              <span class="field-label">Discount Amount</span>
              <input v-model="form.discount_amount" type="number" step="0.01" placeholder="0.00" />
            </label>
          </div>
        </section>

        <!-- â”€â”€ Invoice Fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <section v-else class="form-section">
          <h3 class="section-title">Invoice Details</h3>
          <div class="fields-grid">
            <label
              v-for="item in [
                ['company_name', 'Company name'],
                ['invoice_number', 'Invoice number'],
                ['invoice_date', 'Invoice date'],
                ['currency', 'Currency'],
                ['total_amount', 'Total amount'],
              ]"
              :key="item[0]"
              class="field-group"
              :class="`conf-${confidence(item[0])}`"
            >
              <span class="field-label">
                {{ item[1] }}
                <em :class="`pill-${confidence(item[0])}`">{{ confidence(item[0]) }}</em>
              </span>
              <input
                v-model="form[item[0] as 'company_name']"
                :type="item[0] === 'invoice_date' ? 'date' : item[0] === 'total_amount' ? 'number' : 'text'"
              />
              <small v-if="source(item[0])">{{ source(item[0]) }}</small>
            </label>
          </div>
        </section>

        <!-- â”€â”€ Line Items â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <section class="form-section">
          <div class="section-header">
            <div>
              <h3 class="section-title">Line Items</h3>
              <p v-if="form.line_items.length" class="section-sub">{{ form.line_items.length }} row{{ form.line_items.length !== 1 ? 's' : '' }} detected</p>
            </div>
            <span v-if="calculatedLineItemTotal" class="calc-sum">
              Î£ {{ form.currency || '' }} {{ calculatedLineItemTotal }}
            </span>
          </div>

          <p v-if="!form.line_items.length" class="empty-state">
            No itemized rows detected. Add line items manually or import the document header.
          </p>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Description</th>
                  <th class="col-narrow">Qty</th>
                  <th class="col-med">Unit Price</th>
                  <th class="col-narrow">Tax %</th>
                  <th class="col-med">Tax Amt</th>
                  <th class="col-med">Amount</th>
                  <th class="col-action"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(line, index) in form.line_items" :key="index">
                  <td><input v-model="line.description" placeholder="Item description" /></td>
                  <td><input v-model="line.quantity" type="number" step="any" placeholder="1" @input="calculateItemAmount(line)" /></td>
                  <td><input v-model="line.unit_price" type="number" step="0.01" placeholder="0.00" @input="calculateItemAmount(line)" /></td>
                  <td><input v-model="line.tax_rate" type="number" step="0.1" placeholder="%" /></td>
                  <td><input v-model="line.tax_amount" type="number" step="0.01" placeholder="0.00" /></td>
                  <td><input v-model="line.amount" type="number" step="0.01" placeholder="0.00" /></td>
                  <td>
                    <button class="del-btn" title="Remove" aria-label="Delete line item" @click="form.line_items.splice(index, 1)">
                      <Trash2 :size="13" />
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- â”€â”€ Action Bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ -->
        <div class="action-bar">
          <button class="btn btn-secondary" @click="addLine">
            <Plus :size="15" /> Add Line Item
          </button>
          <button class="btn btn-primary" :disabled="saving" @click="confirmImport">
            <Loader2 v-if="saving" class="animate-spin" :size="15" />
            <CheckCircle2 v-else :size="15" />
            Confirm & Import
          </button>
        </div>

      </div>
    </section>
  </main>
</template>

<style scoped>
/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   Zen Design â€” DocumentReviewView
   Clean, calm, well-spaced. Minimal chrome, focused content.
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */

.document-review {
  padding-block: 1.75rem 3rem;
}

/* â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.review-header {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.header-row-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.85rem;
}

.header-row-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.header-title {
  font-size: 1.45rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
  letter-spacing: -0.02em;
}

.header-filename {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  margin: 0;
}

.header-sub {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-shrink: 0;
}

.doc-type-group {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.control-label {
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.type-select {
  padding: 0.4rem 0.65rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
  cursor: pointer;
  transition: border-color 0.15s;
}
.type-select:focus { outline: 2px solid var(--accent-brand); outline-offset: 2px; }

.status-pill {
  padding: 0.35rem 0.8rem;
  border-radius: 999px;
  background: var(--status-warning-bg);
  color: var(--status-warning);
  border: 1px solid var(--status-warning-border);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: capitalize;
  white-space: nowrap;
  letter-spacing: 0.04em;
}

/* Back link */
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-muted);
  text-decoration: none;
  transition: color 0.15s;
}
.back-link:hover { color: var(--accent-brand); }

/* Queue nav */
.queue-nav {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  padding: 0.2rem 0.45rem;
}
.queue-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.18rem 0.45rem;
  border-radius: 999px;
  transition: background 0.12s, color 0.12s;
  font-family: inherit;
}
.queue-nav-btn:hover:not(:disabled) { background: rgba(255,255,255,0.07); color: var(--text-primary); }
.queue-nav-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.queue-nav-counter {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  padding-inline: 0.2rem;
}

/* â”€â”€ State cards (loading / error) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.state-card {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  padding: 1.5rem 1.75rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  font-size: 0.9rem;
  margin-top: 1rem;
}
.state-card.notice-error {
  color: var(--status-error);
  background: var(--status-error-bg);
  border-color: var(--status-error-border);
}

/* â”€â”€ Review split grid â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.review-grid {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(420px, 1.35fr);
  gap: 1.25rem;
  align-items: start;
}

/* â”€â”€ Pane base â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.pane {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.pane-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
}

.pane-title {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.01em;
}

.pane-sub {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0.2rem 0 0;
}

/* â”€â”€ Preview pane â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.pane-preview {
  position: sticky;
  top: 1.5rem;
}

.preview-viewport {
  background: var(--bg-subtle);
}
.preview-viewport iframe,
.preview-viewport img {
  width: 100%;
  height: 66vh;
  border: 0;
  object-fit: contain;
  display: block;
}

.preview-hint {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.65rem 1.25rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-subtle);
}
.preview-hint code {
  font-family: var(--font-mono);
  font-size: 0.72rem;
  background: var(--bg-subtle);
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  color: var(--text-secondary);
}

/* â”€â”€ Form pane â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.pane-form {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
}

.pane-form .pane-header {
  padding: 1rem 1.25rem 0.9rem;
}

.reprocess-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.mode-select {
  padding: 0.38rem 0.6rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: inherit;
}

/* â”€â”€ Engine badge â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.engine-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.25rem 0.6rem;
  border-radius: 999px;
  font-size: 0.74rem;
  font-weight: 600;
  white-space: nowrap;
}
.badge-ai   { background: rgba(147,51,234,0.1); color: #a855f7; border: 1px solid rgba(147,51,234,0.22); }
.badge-ocr  { background: rgba(59,130,246,0.1); color: #60a5fa; border: 1px solid rgba(59,130,246,0.22); }
.badge-native { background: rgba(16,185,129,0.1); color: #34d399; border: 1px solid rgba(16,185,129,0.22); }
.badge-mixed  { background: rgba(245,158,11,0.1); color: #fbbf24; border: 1px solid rgba(245,158,11,0.22); }
.badge-muted  { background: var(--bg-subtle); color: var(--text-secondary); border: 1px solid var(--border-subtle); }

/* â”€â”€ Notices stack â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.notices-stack {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-bottom: 1px solid var(--border-subtle);
}

.notice {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.85rem 1.25rem;
  font-size: 0.84rem;
  line-height: 1.45;
  border-top: 1px solid transparent;
}
.notice + .notice { border-top-color: rgba(255,255,255,0.04); }

.notice-icon {
  flex-shrink: 0;
  margin-top: 0.1rem;
}

.notice-body {
  min-width: 0;
  flex: 1;
}
.notice-body strong { display: block; margin-bottom: 0.2rem; font-size: 0.84rem; }
.notice-body p { margin: 0.15rem 0 0; color: inherit; opacity: 0.85; font-size: 0.82rem; }
.notice-body ul { margin: 0.35rem 0 0 1.1rem; padding: 0; }
.notice-body ul li { margin-bottom: 0.2rem; }

.notice-warn    { background: var(--status-warning-bg); color: var(--status-warning); }
.notice-error   { background: var(--status-error-bg);   color: var(--status-error); }
.notice-info    { background: var(--status-info-bg);    color: var(--status-info); }
.notice-success { background: rgba(16,185,129,0.08);    color: #34d399; }
.notice-ai      { background: rgba(147,51,234,0.06);    color: #c084fc; }

.v-detail {
  opacity: 0.7;
  font-size: 0.8em;
}

/* AI notes --*/
.ai-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: none;
  border: none;
  color: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  font-family: inherit;
}

.ai-notes-list {
  margin-top: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.ai-note {
  font-size: 0.79rem;
  margin: 0;
  padding-left: 0.6rem;
  border-left: 2px solid rgba(192,132,252,0.4);
  opacity: 0.9;
  line-height: 1.45;
}

/* â”€â”€ Duplicate conflict card â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.duplicate-card {
  margin: 0;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(245,158,11,0.06);
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}

.duplicate-card-header {
  display: flex;
  align-items: flex-start;
  gap: 0.7rem;
}
.dup-icon { color: #f59e0b; flex-shrink: 0; margin-top: 0.15rem; }
.dup-title {
  margin: 0 0 0.2rem;
  font-size: 0.9rem;
  font-weight: 700;
  color: #fbbf24;
}
.dup-desc { margin: 0; font-size: 0.8rem; color: var(--text-secondary); line-height: 1.4; }

.dup-meta-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
  padding: 0.75rem 1rem;
  background: rgba(0,0,0,0.18);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(245,158,11,0.15);
}
.dup-field { display: flex; flex-direction: column; gap: 0.1rem; }
.dup-label {
  font-size: 0.66rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  font-weight: 600;
}
.dup-value { font-size: 0.82rem; color: var(--text-primary); font-weight: 500; }
.dup-value.mono { font-family: var(--font-mono); }

.dup-reason {
  font-size: 0.79rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.45;
  border-top: 1px dashed rgba(245,158,11,0.2);
  padding-top: 0.65rem;
}

.dup-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.btn-warn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.45rem 0.9rem;
  border-radius: var(--radius-sm);
  background: #d97706;
  color: #fff;
  font-size: 0.82rem;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: background 0.15s;
  font-family: inherit;
}
.btn-warn:hover:not(:disabled) { background: #b45309; }
.btn-warn:disabled { opacity: 0.55; cursor: not-allowed; }

/* â”€â”€ Form sections â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.form-section {
  padding: 1.1rem 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
}
.form-section:last-of-type { border-bottom: none; }

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 0.9rem;
}

.section-title {
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
  letter-spacing: -0.01em;
}
.section-sub {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin: 0;
}
.section-note {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.74rem;
  color: var(--text-muted);
  margin: 0.75rem 0 0;
  line-height: 1.4;
}

/* â”€â”€ Direction cards â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.direction-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 0.6rem;
  margin-bottom: 0.25rem;
}

.dir-opt {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.7rem 0.85rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  background: var(--bg-subtle);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.dir-opt input[type="radio"] { margin-top: 0.15rem; accent-color: var(--accent-brand); flex-shrink: 0; }
.dir-opt:hover:not(.active) { border-color: var(--border-medium); background: var(--bg-elevated); }
.dir-opt.active {
  border-color: var(--accent-brand);
  background: var(--accent-brand-subtle);
}

.dir-opt-text { display: flex; flex-direction: column; gap: 0.1rem; }
.dir-opt-label { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); }
.dir-opt-desc  { font-size: 0.73rem; color: var(--text-muted); line-height: 1.35; }

/* â”€â”€ Direction / status badges â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  flex-shrink: 0;
}
.badge-sales, .badge-income    { background: rgba(16,185,129,0.12); color: #34d399; border: 1px solid rgba(16,185,129,0.25); }
.badge-purchase, .badge-expense { background: rgba(245,158,11,0.12); color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.badge-unclassified             { background: var(--bg-subtle); color: var(--text-muted); border: 1px solid var(--border-subtle); }

/* â”€â”€ Fields grid â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.fields-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.8rem;
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.field-group.span-2 { grid-column: 1 / -1; }

.field-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.77rem;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}

/* Confidence pills */
.pill-high, .pill-medium, .pill-low {
  font-style: normal;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  padding: 0.08rem 0.38rem;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.pill-high   { background: rgba(16,185,129,0.15); color: #34d399; }
.pill-medium { background: rgba(245,158,11,0.15); color: #fbbf24; }
.pill-low    { background: rgba(239,68,68,0.15);  color: #f87171; }

/* Field inputs */
.fields-grid input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.7rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-subtle);
  color: var(--text-primary);
  font-size: 0.85rem;
  font-family: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.fields-grid input:focus {
  outline: none;
  border-color: var(--accent-brand);
  box-shadow: 0 0 0 3px var(--accent-brand-subtle);
}

/* Confidence-based field tinting */
.conf-low .fields-grid input,
.field-group.conf-low > input {
  border-color: rgba(239,68,68,0.5);
  background: rgba(239,68,68,0.03);
}
.conf-medium .fields-grid input,
.field-group.conf-medium > input {
  border-color: rgba(245,158,11,0.45);
  background: rgba(245,158,11,0.03);
}

.fields-grid small,
.field-group small {
  font-size: 0.7rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
}

/* Expand button */
.expand-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: none;
  border: none;
  color: var(--accent-brand);
  font-size: 0.79rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.6rem 0;
  font-family: inherit;
  transition: opacity 0.15s;
}
.expand-btn:hover { opacity: 0.75; }

.extended-fields {
  padding: 0.75rem;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
  margin-top: 0.5rem;
}

/* â”€â”€ Line items table â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.empty-state {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin: 0;
  padding: 0.5rem 0;
}

.calc-sum {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--accent-brand);
  font-family: var(--font-mono);
  white-space: nowrap;
}

.table-wrap {
  overflow-x: auto;
  margin-top: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.82rem;
}

thead tr {
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

th {
  padding: 0.55rem 0.6rem;
  text-align: left;
  font-size: 0.71rem;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

td {
  padding: 0.3rem 0.4rem;
  border-top: 1px solid var(--border-subtle);
}
tbody tr:first-child td { border-top: none; }
tbody tr:hover { background: var(--bg-subtle); }

.col-narrow { width: 70px; }
.col-med    { width: 95px; }
.col-action { width: 36px; }

table input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.38rem 0.45rem;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--text-primary);
  font-size: 0.82rem;
  font-family: inherit;
  transition: border-color 0.12s, background 0.12s;
}
table input:focus {
  outline: none;
  border-color: var(--accent-brand);
  background: var(--bg-subtle);
}

.del-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.3rem;
  border-radius: 4px;
  transition: color 0.12s, background 0.12s;
  font-family: inherit;
}
.del-btn:hover { color: var(--status-error); background: var(--status-error-bg); }

/* â”€â”€ Action bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border-subtle);
  gap: 0.75rem;
  background: var(--bg-subtle);
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}

/* â”€â”€ Spin animation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
.animate-spin { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* â”€â”€ Responsive â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
@media (max-width: 920px) {
  .review-grid {
    grid-template-columns: 1fr;
  }
  .pane-preview {
    position: static;
  }
  .preview-viewport iframe,
  .preview-viewport img {
    height: 46vh;
  }
  .fields-grid {
    grid-template-columns: 1fr;
  }
  .direction-grid {
    grid-template-columns: 1fr;
  }
  .header-row-main {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
