<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  ArrowUpDown,
  Building2,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  FileText,
  Layers,
  Receipt,
  RefreshCw,
  Search,
  X,
} from 'lucide-vue-next'

import InvoiceDetailModal from '@/components/explorer/InvoiceDetailModal.vue'
import ReceiptDetailModal from '@/components/explorer/ReceiptDetailModal.vue'
import SourcePreviewModal from '@/components/explorer/SourcePreviewModal.vue'
import { api } from '@/services/api'
import type {
  DataExplorerFilterOptions,
  InvoiceDetailResponse,
  InvoiceListItem,
  InvoiceRecordUpdate,
  LineItemListItem,
  ReceiptDetailResponse,
  ReceiptListItem,
  UnifiedDocumentListItem,
} from '@/types/api'

const router = useRouter()

// ── Active Tab ──────────────────────────────────────────────────────────────
const activeTab = ref<'documents' | 'invoices' | 'receipts' | 'line-items'>('documents')

// ── Shared Filter Options ───────────────────────────────────────────────────
const filterOptions = ref<DataExplorerFilterOptions>({
  companies: [],
  currencies: [],
  merchants: [],
  payment_methods: [],
  directions: [],
})

// ── 1. Unified Documents State ──────────────────────────────────────────────
const documents = ref<UnifiedDocumentListItem[]>([])
const documentsTotal = ref(0)
const documentsTotalPages = ref(0)
const documentsPage = ref(1)
const documentsPageSize = ref(25)
const documentsSortBy = ref<string>('document_date')
const documentsSortOrder = ref<'asc' | 'desc'>('desc')

const documentSearch = ref('')
const documentTypeFilter = ref<string>('all')
const documentDirectionFilter = ref<string>('all')
const documentCurrencyFilter = ref('')
const documentDateFrom = ref('')
const documentDateTo = ref('')

const isLoadingDocuments = ref(false)
const documentsError = ref('')

// ── 2. Invoices State ───────────────────────────────────────────────────────
const invoices = ref<InvoiceListItem[]>([])
const invoicesTotal = ref(0)
const invoicesTotalPages = ref(0)
const invoicesPage = ref(1)
const invoicesPageSize = ref(25)
const invoicesSortBy = ref<string>('invoice_date')
const invoicesSortOrder = ref<'asc' | 'desc'>('desc')

const invoiceSearch = ref('')
const invoiceCompanyFilter = ref('')
const invoiceDirectionFilter = ref<string>('all')
const invoiceCurrencyFilter = ref('')
const invoiceDateFrom = ref('')
const invoiceDateTo = ref('')
const invoiceHasLineItems = ref<string>('all')

const isLoadingInvoices = ref(false)
const invoicesError = ref('')

// ── 3. Receipts State ───────────────────────────────────────────────────────
const receipts = ref<ReceiptListItem[]>([])
const receiptsTotal = ref(0)
const receiptsTotalPages = ref(0)
const receiptsPage = ref(1)
const receiptsPageSize = ref(25)
const receiptsSortBy = ref<string>('transaction_date')
const receiptsSortOrder = ref<'asc' | 'desc'>('desc')

const receiptSearch = ref('')
const receiptMerchantFilter = ref('')
const receiptDirectionFilter = ref<string>('all')
const receiptPaymentMethodFilter = ref('')
const receiptCurrencyFilter = ref('')
const receiptDateFrom = ref('')
const receiptDateTo = ref('')

const isLoadingReceipts = ref(false)
const receiptsError = ref('')

// ── 4. Line Items State ─────────────────────────────────────────────────────
const lineItems = ref<LineItemListItem[]>([])
const lineItemsTotal = ref(0)
const lineItemsTotalPages = ref(0)
const lineItemsPage = ref(1)
const lineItemsPageSize = ref(25)
const lineItemsSortBy = ref<string>('id')
const lineItemsSortOrder = ref<'asc' | 'desc'>('asc')

const lineItemSearch = ref('')
const lineItemCompanyFilter = ref('')
const lineItemCurrencyFilter = ref('')
const lineItemDateFrom = ref('')
const lineItemDateTo = ref('')

const isLoadingLineItems = ref(false)
const lineItemsError = ref('')

// ── Detail Modals State ─────────────────────────────────────────────────────
const selectedInvoice = ref<InvoiceDetailResponse | null>(null)
const isInvoiceModalOpen = ref(false)
const isLoadingInvoiceDetail = ref(false)

const selectedReceipt = ref<ReceiptDetailResponse | null>(null)
const isReceiptModalOpen = ref(false)
const isLoadingReceiptDetail = ref(false)

// ── Debounce Timer ──────────────────────────────────────────────────────────
let searchDebounceTimer: any = null

// ── Computed Filter Status ──────────────────────────────────────────────────
const hasDocumentFiltersApplied = computed(() => {
  return (
    documentSearch.value.trim() !== '' ||
    documentTypeFilter.value !== 'all' ||
    documentDirectionFilter.value !== 'all' ||
    documentCurrencyFilter.value !== '' ||
    documentDateFrom.value !== '' ||
    documentDateTo.value !== ''
  )
})

const hasInvoiceFiltersApplied = computed(() => {
  return (
    invoiceSearch.value.trim() !== '' ||
    invoiceCompanyFilter.value !== '' ||
    invoiceDirectionFilter.value !== 'all' ||
    invoiceCurrencyFilter.value !== '' ||
    invoiceDateFrom.value !== '' ||
    invoiceDateTo.value !== '' ||
    invoiceHasLineItems.value !== 'all'
  )
})

const hasReceiptFiltersApplied = computed(() => {
  return (
    receiptSearch.value.trim() !== '' ||
    receiptMerchantFilter.value !== '' ||
    receiptDirectionFilter.value !== 'all' ||
    receiptPaymentMethodFilter.value !== '' ||
    receiptCurrencyFilter.value !== '' ||
    receiptDateFrom.value !== '' ||
    receiptDateTo.value !== ''
  )
})

const hasLineItemFiltersApplied = computed(() => {
  return (
    lineItemSearch.value.trim() !== '' ||
    lineItemCompanyFilter.value !== '' ||
    lineItemCurrencyFilter.value !== '' ||
    lineItemDateFrom.value !== '' ||
    lineItemDateTo.value !== ''
  )
})

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

function formatNumber(val: number): string {
  return val.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
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

function formatDirection(dir?: string | null): string {
  if (!dir) return 'Unclassified'
  const map: Record<string, string> = {
    sales: 'Sales',
    purchase: 'Purchase',
    expense: 'Expense',
    income: 'Income',
    unclassified: 'Unclassified',
  }
  return map[dir.toLowerCase()] || dir
}

function getDirectionBadgeClass(dir?: string | null): string {
  if (!dir) return 'badge-neutral'
  const norm = dir.toLowerCase()
  if (norm === 'sales' || norm === 'income') return 'badge-success'
  if (norm === 'purchase' || norm === 'expense') return 'badge-warning'
  return 'badge-neutral'
}

function isDocumentSource(item: {
  source_media_type?: string | null
  source_filename?: string | null
  source_worksheet?: string | null
}): boolean {
  if (item.source_media_type) {
    return item.source_media_type.startsWith('image/') || item.source_media_type === 'application/pdf'
  }
  if (item.source_filename) {
    const ext = item.source_filename.toLowerCase().split('.').pop()
    if (ext && ['pdf', 'jpg', 'jpeg', 'png', 'webp'].includes(ext)) return true
    if (ext === 'xlsx') return false
  }
  if (item.source_worksheet === 'Document') return true
  return false
}

function getSourcePreviewUrl(
  sourceFileId?: number | null,
  isDocument = false,
  worksheetName?: string | null,
): string | undefined {
  if (!sourceFileId) return undefined
  if (isDocument) {
    return `/api/v1/documents/${sourceFileId}/preview`
  }
  const sheetParam = worksheetName && worksheetName.trim() ? `?sheet_name=${encodeURIComponent(worksheetName.trim())}` : ''
  return `/api/v1/files/${sourceFileId}/preview${sheetParam}`
}

const isSourcePreviewOpen = ref(false)
const previewSourceFileId = ref<number | null>(null)
const previewFilename = ref<string | null>(null)
const previewMediaType = ref<string | null>(null)
const previewWorksheet = ref<string | null>(null)
const previewBatchId = ref<number | null>(null)

function openSourcePreviewModal(item: {
  source_file_id?: number | null
  source_filename?: string | null
  source_media_type?: string | null
  source_worksheet?: string | null
  batch_id?: number | null
}) {
  if (!item.source_file_id) return
  previewSourceFileId.value = item.source_file_id
  previewFilename.value = item.source_filename || null
  previewMediaType.value = item.source_media_type || null
  previewWorksheet.value = item.source_worksheet || null
  previewBatchId.value = item.batch_id || null
  isSourcePreviewOpen.value = true
}

function closeSourcePreviewModal() {
  isSourcePreviewOpen.value = false
  previewSourceFileId.value = null
  previewFilename.value = null
  previewMediaType.value = null
  previewWorksheet.value = null
  previewBatchId.value = null
}

function handleSourceClick(
  _event: MouseEvent,
  item: {
    source_file_id?: number | null
    source_filename?: string | null
    source_media_type?: string | null
    source_worksheet?: string | null
    batch_id?: number | null
  },
) {
  if (!item.source_file_id) return
  const isDoc = isDocumentSource(item)
  if (isDoc) {
    window.open(`/api/v1/documents/${item.source_file_id}/preview`, '_blank', 'noopener,noreferrer')
  } else {
    openSourcePreviewModal(item)
  }
}

// ── Data Fetching ───────────────────────────────────────────────────────────

async function fetchFilterOptions() {
  try {
    const opts = await api.getDataExplorerFilterOptions()
    filterOptions.value = opts
  } catch (err) {
    console.error('Failed to load filter options', err)
  }
}

async function fetchDocuments() {
  isLoadingDocuments.value = true
  documentsError.value = ''
  try {
    const res = await api.listDataExplorerDocuments({
      search: documentSearch.value.trim() || undefined,
      document_type: documentTypeFilter.value !== 'all' ? documentTypeFilter.value : undefined,
      direction: documentDirectionFilter.value !== 'all' ? documentDirectionFilter.value : undefined,
      currency: documentCurrencyFilter.value || undefined,
      date_from: documentDateFrom.value || undefined,
      date_to: documentDateTo.value || undefined,
      sort_by: documentsSortBy.value,
      sort_order: documentsSortOrder.value,
      page: documentsPage.value,
      page_size: documentsPageSize.value,
    })
    documents.value = res.items
    documentsTotal.value = res.total
    documentsTotalPages.value = res.total_pages
  } catch (err: any) {
    documentsError.value = err.message || 'Unable to load documents register.'
  } finally {
    isLoadingDocuments.value = false
  }
}

async function fetchInvoices() {
  isLoadingInvoices.value = true
  invoicesError.value = ''
  try {
    let hasLineItemsParam: boolean | undefined = undefined
    if (invoiceHasLineItems.value === 'yes') hasLineItemsParam = true
    if (invoiceHasLineItems.value === 'no') hasLineItemsParam = false

    const res = await api.listDataExplorerInvoices({
      search: invoiceSearch.value.trim() || undefined,
      company: invoiceCompanyFilter.value || undefined,
      currency: invoiceCurrencyFilter.value || undefined,
      direction: invoiceDirectionFilter.value !== 'all' ? invoiceDirectionFilter.value : undefined,
      date_from: invoiceDateFrom.value || undefined,
      date_to: invoiceDateTo.value || undefined,
      has_line_items: hasLineItemsParam,
      sort_by: invoicesSortBy.value,
      sort_order: invoicesSortOrder.value,
      page: invoicesPage.value,
      page_size: invoicesPageSize.value,
    })

    invoices.value = res.items
    invoicesTotal.value = res.total
    invoicesTotalPages.value = res.total_pages
  } catch (err: any) {
    invoicesError.value = err.message || 'Unable to load invoice data.'
  } finally {
    isLoadingInvoices.value = false
  }
}

async function fetchReceipts() {
  isLoadingReceipts.value = true
  receiptsError.value = ''
  try {
    const res = await api.listDataExplorerReceipts({
      search: receiptSearch.value.trim() || undefined,
      merchant: receiptMerchantFilter.value || undefined,
      direction: receiptDirectionFilter.value !== 'all' ? receiptDirectionFilter.value : undefined,
      payment_method: receiptPaymentMethodFilter.value || undefined,
      currency: receiptCurrencyFilter.value || undefined,
      date_from: receiptDateFrom.value || undefined,
      date_to: receiptDateTo.value || undefined,
      sort_by: receiptsSortBy.value,
      sort_order: receiptsSortOrder.value,
      page: receiptsPage.value,
      page_size: receiptsPageSize.value,
    })

    receipts.value = res.items
    receiptsTotal.value = res.total
    receiptsTotalPages.value = res.total_pages
  } catch (err: any) {
    receiptsError.value = err.message || 'Unable to load receipt data.'
  } finally {
    isLoadingReceipts.value = false
  }
}

async function fetchLineItems() {
  isLoadingLineItems.value = true
  lineItemsError.value = ''
  try {
    const res = await api.listDataExplorerLineItems({
      search: lineItemSearch.value.trim() || undefined,
      company: lineItemCompanyFilter.value || undefined,
      currency: lineItemCurrencyFilter.value || undefined,
      date_from: lineItemDateFrom.value || undefined,
      date_to: lineItemDateTo.value || undefined,
      sort_by: lineItemsSortBy.value,
      sort_order: lineItemsSortOrder.value,
      page: lineItemsPage.value,
      page_size: lineItemsPageSize.value,
    })

    lineItems.value = res.items
    lineItemsTotal.value = res.total
    lineItemsTotalPages.value = res.total_pages
  } catch (err: any) {
    lineItemsError.value = err.message || 'Unable to load line items.'
  } finally {
    isLoadingLineItems.value = false
  }
}

// ── Search & Filter Handlers ────────────────────────────────────────────────

function onDocumentSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    documentsPage.value = 1
    fetchDocuments()
  }, 300)
}

function onInvoiceSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    invoicesPage.value = 1
    fetchInvoices()
  }, 300)
}

function onReceiptSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    receiptsPage.value = 1
    fetchReceipts()
  }, 300)
}

function onLineItemSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    lineItemsPage.value = 1
    fetchLineItems()
  }, 300)
}

function clearDocumentFilters() {
  documentSearch.value = ''
  documentTypeFilter.value = 'all'
  documentDirectionFilter.value = 'all'
  documentCurrencyFilter.value = ''
  documentDateFrom.value = ''
  documentDateTo.value = ''
  documentsPage.value = 1
  fetchDocuments()
}

function clearInvoiceFilters() {
  invoiceSearch.value = ''
  invoiceCompanyFilter.value = ''
  invoiceDirectionFilter.value = 'all'
  invoiceCurrencyFilter.value = ''
  invoiceDateFrom.value = ''
  invoiceDateTo.value = ''
  invoiceHasLineItems.value = 'all'
  invoicesPage.value = 1
  fetchInvoices()
}

function clearReceiptFilters() {
  receiptSearch.value = ''
  receiptMerchantFilter.value = ''
  receiptDirectionFilter.value = 'all'
  receiptPaymentMethodFilter.value = ''
  receiptCurrencyFilter.value = ''
  receiptDateFrom.value = ''
  receiptDateTo.value = ''
  receiptsPage.value = 1
  fetchReceipts()
}

function clearLineItemFilters() {
  lineItemSearch.value = ''
  lineItemCompanyFilter.value = ''
  lineItemCurrencyFilter.value = ''
  lineItemDateFrom.value = ''
  lineItemDateTo.value = ''
  lineItemsPage.value = 1
  fetchLineItems()
}

// ── Sorting Handlers ────────────────────────────────────────────────────────

function toggleDocumentSort(column: string) {
  if (documentsSortBy.value === column) {
    documentsSortOrder.value = documentsSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    documentsSortBy.value = column
    documentsSortOrder.value = column.includes('date') || column === 'total_amount' ? 'desc' : 'asc'
  }
  documentsPage.value = 1
  fetchDocuments()
}

function toggleInvoiceSort(column: string) {
  if (invoicesSortBy.value === column) {
    invoicesSortOrder.value = invoicesSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    invoicesSortBy.value = column
    invoicesSortOrder.value = column.includes('date') || column === 'created_at' || column === 'total_amount' ? 'desc' : 'asc'
  }
  invoicesPage.value = 1
  fetchInvoices()
}

function toggleReceiptSort(column: string) {
  if (receiptsSortBy.value === column) {
    receiptsSortOrder.value = receiptsSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    receiptsSortBy.value = column
    receiptsSortOrder.value = column.includes('date') || column === 'total_amount' ? 'desc' : 'asc'
  }
  receiptsPage.value = 1
  fetchReceipts()
}

function toggleLineItemSort(column: string) {
  if (lineItemsSortBy.value === column) {
    lineItemsSortOrder.value = lineItemsSortOrder.value === 'asc' ? 'desc' : 'asc'
  } else {
    lineItemsSortBy.value = column
    lineItemsSortOrder.value = 'asc'
  }
  lineItemsPage.value = 1
  fetchLineItems()
}

// ── Pagination Handlers ─────────────────────────────────────────────────────

function setDocumentPage(page: number) {
  if (page >= 1 && page <= documentsTotalPages.value) {
    documentsPage.value = page
    fetchDocuments()
  }
}

function setInvoicePage(page: number) {
  if (page >= 1 && page <= invoicesTotalPages.value) {
    invoicesPage.value = page
    fetchInvoices()
  }
}

function setReceiptPage(page: number) {
  if (page >= 1 && page <= receiptsTotalPages.value) {
    receiptsPage.value = page
    fetchReceipts()
  }
}

function setLineItemPage(page: number) {
  if (page >= 1 && page <= lineItemsTotalPages.value) {
    lineItemsPage.value = page
    fetchLineItems()
  }
}

// ── Detail Modal Handlers ───────────────────────────────────────────────────

async function openInvoiceDetail(invoiceId: number) {
  isLoadingInvoiceDetail.value = true
  try {
    const detail = await api.getDataExplorerInvoice(invoiceId)
    selectedInvoice.value = detail
    isInvoiceModalOpen.value = true
  } catch (err: any) {
    alert(err.message || 'Failed to load invoice details.')
  } finally {
    isLoadingInvoiceDetail.value = false
  }
}

async function openReceiptDetail(receiptId: number) {
  isLoadingReceiptDetail.value = true
  try {
    const detail = await api.getDataExplorerReceipt(receiptId)
    selectedReceipt.value = detail
    isReceiptModalOpen.value = true
  } catch (err: any) {
    alert(err.message || 'Failed to load receipt details.')
  } finally {
    isLoadingReceiptDetail.value = false
  }
}

function inspectDocumentRow(doc: UnifiedDocumentListItem) {
  if (doc.document_type === 'receipt') {
    openReceiptDetail(doc.record_id)
  } else {
    openInvoiceDetail(doc.record_id)
  }
}

async function handleSaveInvoiceEdit(payload: {
  invoiceId: number
  form: InvoiceRecordUpdate
}) {
  try {
    const updated = await api.updateDataExplorerInvoice(payload.invoiceId, payload.form)
    selectedInvoice.value = updated
    fetchInvoices()
    if (activeTab.value === 'documents') fetchDocuments()
    if (activeTab.value === 'line-items') fetchLineItems()
  } catch (err: any) {
    throw err
  }
}

// ── Export Routing ──────────────────────────────────────────────────────────

function navigateToExport(dataset: 'documents' | 'invoices' | 'receipts' | 'line-items') {
  const qp: Record<string, string> = { dataset }
  if (dataset === 'documents') {
    if (documentSearch.value.trim()) qp.search = documentSearch.value.trim()
    if (documentTypeFilter.value !== 'all') qp.document_type = documentTypeFilter.value
    if (documentDirectionFilter.value !== 'all') qp.direction = documentDirectionFilter.value
    if (documentCurrencyFilter.value) qp.currency = documentCurrencyFilter.value
    if (documentDateFrom.value) qp.date_from = documentDateFrom.value
    if (documentDateTo.value) qp.date_to = documentDateTo.value
  } else if (dataset === 'invoices') {
    if (invoiceSearch.value.trim()) qp.search = invoiceSearch.value.trim()
    if (invoiceCompanyFilter.value) qp.company = invoiceCompanyFilter.value
    if (invoiceDirectionFilter.value !== 'all') qp.direction = invoiceDirectionFilter.value
    if (invoiceCurrencyFilter.value) qp.currency = invoiceCurrencyFilter.value
    if (invoiceDateFrom.value) qp.date_from = invoiceDateFrom.value
    if (invoiceDateTo.value) qp.date_to = invoiceDateTo.value
  } else if (dataset === 'receipts') {
    if (receiptSearch.value.trim()) qp.search = receiptSearch.value.trim()
    if (receiptMerchantFilter.value) qp.company = receiptMerchantFilter.value
    if (receiptDirectionFilter.value !== 'all') qp.direction = receiptDirectionFilter.value
    if (receiptPaymentMethodFilter.value) qp.payment_method = receiptPaymentMethodFilter.value
    if (receiptCurrencyFilter.value) qp.currency = receiptCurrencyFilter.value
    if (receiptDateFrom.value) qp.date_from = receiptDateFrom.value
    if (receiptDateTo.value) qp.date_to = receiptDateTo.value
  } else {
    if (lineItemSearch.value.trim()) qp.search = lineItemSearch.value.trim()
    if (lineItemCompanyFilter.value) qp.company = lineItemCompanyFilter.value
    if (lineItemCurrencyFilter.value) qp.currency = lineItemCurrencyFilter.value
    if (lineItemDateFrom.value) qp.date_from = lineItemDateFrom.value
    if (lineItemDateTo.value) qp.date_to = lineItemDateTo.value
  }
  router.push({ path: '/exports', query: qp })
}

// ── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  fetchFilterOptions()
  fetchDocuments()
})

watch(activeTab, (tab) => {
  if (tab === 'documents' && documents.value.length === 0) fetchDocuments()
  if (tab === 'invoices' && invoices.value.length === 0) fetchInvoices()
  if (tab === 'receipts' && receipts.value.length === 0) fetchReceipts()
  if (tab === 'line-items' && lineItems.value.length === 0) fetchLineItems()
})
</script>

<template>
  <div class="zen-explorer-page">
    <div class="zen-container">
      <!-- ── Page Header ───────────────────────────────────────────── -->
      <header class="zen-page-header">
        <div class="header-left">
          <h1 class="page-title">Data Explorer</h1>
          <p class="page-subtitle">
            Browse, search, and inspect standardized invoices, receipts, and line items.
          </p>
        </div>

        <!-- Primary Navigation Tabs -->
        <div class="zen-tabs" role="tablist" aria-label="Data Explorer Views">
          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'documents'"
            class="zen-tab-btn"
            :class="{ active: activeTab === 'documents' }"
            @click="activeTab = 'documents'"
          >
            <Building2 :size="16" />
            <span>All Documents</span>
            <span v-if="documentsTotal > 0" class="tab-count-pill">{{ documentsTotal }}</span>
          </button>

          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'invoices'"
            class="zen-tab-btn"
            :class="{ active: activeTab === 'invoices' }"
            @click="activeTab = 'invoices'"
          >
            <FileText :size="16" />
            <span>Invoices</span>
            <span v-if="invoicesTotal > 0" class="tab-count-pill">{{ invoicesTotal }}</span>
          </button>

          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'receipts'"
            class="zen-tab-btn"
            :class="{ active: activeTab === 'receipts' }"
            @click="activeTab = 'receipts'"
          >
            <Receipt :size="16" />
            <span>Receipts</span>
            <span v-if="receiptsTotal > 0" class="tab-count-pill">{{ receiptsTotal }}</span>
          </button>

          <button
            type="button"
            role="tab"
            :aria-selected="activeTab === 'line-items'"
            class="zen-tab-btn"
            :class="{ active: activeTab === 'line-items' }"
            @click="activeTab = 'line-items'"
          >
            <Layers :size="16" />
            <span>Line Items</span>
            <span v-if="lineItemsTotal > 0" class="tab-count-pill">{{ lineItemsTotal }}</span>
          </button>
        </div>
      </header>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- TAB 1: ALL DOCUMENTS VIEW                                     -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'documents'"
        class="zen-tab-content"
        aria-label="Unified Financial Documents View"
      >
        <!-- Filter Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="documentSearch"
              type="text"
              class="search-input"
              placeholder="Search by counterparty or document number..."
              aria-label="Search documents"
              @input="onDocumentSearchInput"
            />
            <button
              v-if="documentSearch"
              type="button"
              class="clear-search-btn"
              @click="documentSearch = ''; onDocumentSearchInput()"
              aria-label="Clear search"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <!-- Document Type -->
            <div class="filter-item">
              <label for="doc-type-filter" class="filter-label">Type</label>
              <select
                id="doc-type-filter"
                v-model="documentTypeFilter"
                class="filter-select filter-select-sm"
                @change="documentsPage = 1; fetchDocuments()"
              >
                <option value="all">All Types</option>
                <option value="invoice">Invoices</option>
                <option value="receipt">Receipts</option>
              </select>
            </div>

            <!-- Direction -->
            <div class="filter-item">
              <label for="doc-dir-filter" class="filter-label">Direction</label>
              <select
                id="doc-dir-filter"
                v-model="documentDirectionFilter"
                class="filter-select filter-select-sm"
                @change="documentsPage = 1; fetchDocuments()"
              >
                <option value="all">All Directions</option>
                <option value="sales">Sales</option>
                <option value="purchase">Purchase</option>
                <option value="expense">Expense</option>
                <option value="income">Income</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </div>

            <!-- Currency -->
            <div class="filter-item">
              <label for="doc-curr-filter" class="filter-label">Currency</label>
              <select
                id="doc-curr-filter"
                v-model="documentCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="documentsPage = 1; fetchDocuments()"
              >
                <option value="">All</option>
                <option v-for="curr in filterOptions.currencies" :key="curr" :value="curr">
                  {{ curr }}
                </option>
              </select>
            </div>

            <!-- Date From -->
            <div class="filter-item">
              <label for="doc-date-from" class="filter-label">From</label>
              <input
                id="doc-date-from"
                v-model="documentDateFrom"
                type="date"
                class="filter-input-date"
                @change="documentsPage = 1; fetchDocuments()"
              />
            </div>

            <!-- Date To -->
            <div class="filter-item">
              <label for="doc-date-to" class="filter-label">To</label>
              <input
                id="doc-date-to"
                v-model="documentDateTo"
                type="date"
                class="filter-input-date"
                @change="documentsPage = 1; fetchDocuments()"
              />
            </div>

            <!-- Clear -->
            <button
              v-if="hasDocumentFiltersApplied"
              type="button"
              class="btn-clear-filters"
              @click="clearDocumentFilters"
              title="Reset all filters"
            >
              <X :size="14" />
              <span>Clear</span>
            </button>

            <!-- Refresh -->
            <button
              type="button"
              class="btn-refresh"
              @click="fetchDocuments"
              title="Refresh document register"
              :disabled="isLoadingDocuments"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingDocuments }" />
            </button>

            <!-- Export -->
            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('documents')"
              title="Export unified documents"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Error State -->
        <div v-if="documentsError" class="zen-alert zen-alert-error" role="alert">
          <AlertCircle :size="18" />
          <span>{{ documentsError }}</span>
          <button type="button" class="btn-retry" @click="fetchDocuments">Retry</button>
        </div>

        <!-- Table View -->
        <div class="zen-table-card">
          <div class="zen-table-scroll">
            <table class="zen-data-table">
              <thead>
                <tr>
                  <th class="col-sortable" @click="toggleDocumentSort('document_date')">
                    <div class="th-wrap">
                      <span>Date</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleDocumentSort('document_number')">
                    <div class="th-wrap">
                      <span>Document #</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Type</th>
                  <th class="col-sortable" @click="toggleDocumentSort('counterparty')">
                    <div class="th-wrap">
                      <span>Counterparty</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleDocumentSort('direction')">
                    <div class="th-wrap">
                      <span>Direction</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right col-sortable" @click="toggleDocumentSort('total_amount')">
                    <div class="th-wrap justify-end">
                      <span>Amount</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Status</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="isLoadingDocuments && documents.length === 0">
                  <td colspan="8" class="empty-state">
                    <div class="loading-wrap">
                      <RefreshCw :size="20" class="spin" />
                      <span>Loading documents register...</span>
                    </div>
                  </td>
                </tr>

                <tr v-else-if="documents.length === 0">
                  <td colspan="8" class="empty-state">
                    <span>No financial documents found matching your filter criteria.</span>
                  </td>
                </tr>

                <tr
                  v-for="doc in documents"
                  :key="doc.id"
                  class="cursor-pointer hover:bg-slate-50/80 transition-colors"
                  @click="inspectDocumentRow(doc)"
                >
                  <td class="font-mono text-xs text-slate-600">
                    {{ formatDate(doc.document_date) }}
                  </td>
                  <td class="font-mono text-xs font-medium text-slate-800">
                    {{ doc.document_number || 'Not provided' }}
                  </td>
                  <td>
                    <span
                      class="doc-type-tag"
                      :class="doc.document_type === 'invoice' ? 'type-invoice' : 'type-receipt'"
                    >
                      {{ doc.document_type === 'invoice' ? 'Invoice' : 'Receipt' }}
                    </span>
                  </td>
                  <td class="font-medium text-slate-900 max-w-xs truncate">
                    {{ doc.counterparty }}
                  </td>
                  <td>
                    <span :class="['zen-badge', getDirectionBadgeClass(doc.direction)]">
                      {{ formatDirection(doc.direction) }}
                    </span>
                  </td>
                  <td class="text-right font-mono font-medium text-slate-900">
                    {{ formatCurrency(doc.total_amount, doc.currency) }}
                  </td>
                  <td>
                    <span class="status-pill status-imported">{{ doc.status || 'imported' }}</span>
                  </td>
                  <td class="text-right" @click.stop>
                    <div class="action-buttons justify-end">
                      <button
                        type="button"
                        class="btn-row-action"
                        title="Inspect Document Details"
                        @click="inspectDocumentRow(doc)"
                      >
                        <Eye :size="14" />
                        <span>Inspect</span>
                      </button>
                      <a
                        v-if="doc.source_file_id"
                        :href="getSourcePreviewUrl(doc.source_file_id, isDocumentSource(doc), doc.source_worksheet)"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn-row-action btn-source"
                        :title="isDocumentSource(doc) ? 'View Source Document' : 'View Source Workbook'"
                        @click.prevent="handleSourceClick($event, doc)"
                      >
                        <ExternalLink :size="13" />
                        <span>Source</span>
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="documentsTotal > 0" class="zen-pagination-bar">
            <span class="page-meta">
              Showing {{ (documentsPage - 1) * documentsPageSize + 1 }}–{{ Math.min(documentsPage * documentsPageSize, documentsTotal) }} of {{ documentsTotal }}
            </span>
            <div class="pagination-controls">
              <button
                type="button"
                class="btn-page-nav"
                :disabled="documentsPage <= 1"
                @click="setDocumentPage(documentsPage - 1)"
              >
                <ChevronLeft :size="16" />
              </button>
              <span class="page-current">Page {{ documentsPage }} of {{ documentsTotalPages }}</span>
              <button
                type="button"
                class="btn-page-nav"
                :disabled="documentsPage >= documentsTotalPages"
                @click="setDocumentPage(documentsPage + 1)"
              >
                <ChevronRight :size="16" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- TAB 2: INVOICES VIEW                                          -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'invoices'"
        class="zen-tab-content"
        aria-label="Invoices View"
      >
        <!-- Filter Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="invoiceSearch"
              type="text"
              class="search-input"
              placeholder="Search by company or invoice number..."
              aria-label="Search invoices"
              @input="onInvoiceSearchInput"
            />
            <button
              v-if="invoiceSearch"
              type="button"
              class="clear-search-btn"
              @click="invoiceSearch = ''; onInvoiceSearchInput()"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <!-- Company -->
            <div class="filter-item">
              <label for="inv-company-filter" class="filter-label">Company</label>
              <select
                id="inv-company-filter"
                v-model="invoiceCompanyFilter"
                class="filter-select"
                @change="invoicesPage = 1; fetchInvoices()"
              >
                <option value="">All Companies</option>
                <option v-for="c in filterOptions.companies" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>

            <!-- Direction -->
            <div class="filter-item">
              <label for="inv-dir-filter" class="filter-label">Direction</label>
              <select
                id="inv-dir-filter"
                v-model="invoiceDirectionFilter"
                class="filter-select filter-select-sm"
                @change="invoicesPage = 1; fetchInvoices()"
              >
                <option value="all">All</option>
                <option value="sales">Sales</option>
                <option value="purchase">Purchase</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </div>

            <!-- Currency -->
            <div class="filter-item">
              <label for="inv-currency-filter" class="filter-label">Currency</label>
              <select
                id="inv-currency-filter"
                v-model="invoiceCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="invoicesPage = 1; fetchInvoices()"
              >
                <option value="">All</option>
                <option v-for="curr in filterOptions.currencies" :key="curr" :value="curr">{{ curr }}</option>
              </select>
            </div>

            <!-- Date From -->
            <div class="filter-item">
              <label for="inv-date-from" class="filter-label">From</label>
              <input
                id="inv-date-from"
                v-model="invoiceDateFrom"
                type="date"
                class="filter-input-date"
                @change="invoicesPage = 1; fetchInvoices()"
              />
            </div>

            <!-- Date To -->
            <div class="filter-item">
              <label for="inv-date-to" class="filter-label">To</label>
              <input
                id="inv-date-to"
                v-model="invoiceDateTo"
                type="date"
                class="filter-input-date"
                @change="invoicesPage = 1; fetchInvoices()"
              />
            </div>

            <!-- Line Items -->
            <div class="filter-item">
              <label for="inv-has-items" class="filter-label">Items</label>
              <select
                id="inv-has-items"
                v-model="invoiceHasLineItems"
                class="filter-select filter-select-sm"
                @change="invoicesPage = 1; fetchInvoices()"
              >
                <option value="all">All</option>
                <option value="yes">Has Items</option>
                <option value="no">No Items</option>
              </select>
            </div>

            <!-- Clear -->
            <button
              v-if="hasInvoiceFiltersApplied"
              type="button"
              class="btn-clear-filters"
              @click="clearInvoiceFilters"
              title="Reset all filters"
            >
              <X :size="14" />
              <span>Clear</span>
            </button>

            <!-- Refresh -->
            <button
              type="button"
              class="btn-refresh"
              @click="fetchInvoices"
              title="Refresh invoices"
              :disabled="isLoadingInvoices"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingInvoices }" />
            </button>

            <!-- Export -->
            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('invoices')"
              title="Export filtered invoices"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Table View -->
        <div class="zen-table-card">
          <div class="zen-table-scroll">
            <table class="zen-data-table">
              <thead>
                <tr>
                  <th class="col-sortable" @click="toggleInvoiceSort('company_name')">
                    <div class="th-wrap">
                      <span>Company Name</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleInvoiceSort('invoice_number')">
                    <div class="th-wrap">
                      <span>Invoice Number</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleInvoiceSort('invoice_date')">
                    <div class="th-wrap">
                      <span>Invoice Date</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Currency</th>
                  <th class="text-right col-sortable" @click="toggleInvoiceSort('total_amount')">
                    <div class="th-wrap justify-end">
                      <span>Total Amount</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleInvoiceSort('direction')">
                    <div class="th-wrap">
                      <span>Direction</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-center col-sortable" @click="toggleInvoiceSort('line_item_count')">
                    <div class="th-wrap justify-center">
                      <span>Lines</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Source File</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="isLoadingInvoices && invoices.length === 0">
                  <td colspan="9" class="empty-state">
                    <div class="loading-wrap">
                      <RefreshCw :size="20" class="spin" />
                      <span>Loading invoices...</span>
                    </div>
                  </td>
                </tr>

                <tr v-else-if="invoices.length === 0">
                  <td colspan="9" class="empty-state">
                    <span>No invoices found matching your criteria.</span>
                  </td>
                </tr>

                <tr
                  v-for="inv in invoices"
                  :key="inv.id"
                  class="cursor-pointer hover:bg-slate-50/80 transition-colors"
                  @click="openInvoiceDetail(inv.id)"
                >
                  <td class="font-medium text-slate-900 max-w-xs truncate">{{ inv.company_name }}</td>
                  <td class="font-mono text-xs text-slate-800">{{ inv.invoice_number }}</td>
                  <td class="font-mono text-xs text-slate-600">{{ formatDate(inv.invoice_date) }}</td>
                  <td class="font-mono text-xs text-slate-600">{{ inv.currency || '—' }}</td>
                  <td class="text-right font-mono font-medium text-slate-900">
                    {{ formatCurrency(inv.total_amount, inv.currency) }}
                  </td>
                  <td>
                    <span :class="['zen-badge', getDirectionBadgeClass(inv.direction)]">
                      {{ formatDirection(inv.direction) }}
                    </span>
                  </td>
                  <td class="text-center font-mono text-xs">
                    <span v-if="inv.line_item_count > 0" class="items-count-badge">
                      {{ inv.line_item_count }}
                    </span>
                    <span v-else class="text-slate-300">—</span>
                  </td>
                  <td class="text-xs text-slate-500 truncate max-w-xs">{{ inv.source_filename || '—' }}</td>
                  <td class="text-right" @click.stop>
                    <div class="action-buttons justify-end">
                      <button
                        type="button"
                        class="btn-row-action"
                        title="Inspect invoice details"
                        @click="openInvoiceDetail(inv.id)"
                      >
                        <Eye :size="14" />
                        <span>Inspect</span>
                      </button>
                      <a
                        v-if="inv.source_file_id"
                        :href="getSourcePreviewUrl(inv.source_file_id, isDocumentSource(inv), inv.source_worksheet)"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn-row-action btn-source"
                        :title="isDocumentSource(inv) ? 'View Source Document' : 'View Source Workbook'"
                        @click.prevent="handleSourceClick($event, inv)"
                      >
                        <ExternalLink :size="13" />
                        <span>Source</span>
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="invoicesTotal > 0" class="zen-pagination-bar">
            <span class="page-meta">
              Showing {{ (invoicesPage - 1) * invoicesPageSize + 1 }}–{{ Math.min(invoicesPage * invoicesPageSize, invoicesTotal) }} of {{ invoicesTotal }}
            </span>
            <div class="pagination-controls">
              <button
                type="button"
                class="btn-page-nav"
                :disabled="invoicesPage <= 1"
                @click="setInvoicePage(invoicesPage - 1)"
              >
                <ChevronLeft :size="16" />
              </button>
              <span class="page-current">Page {{ invoicesPage }} of {{ invoicesTotalPages }}</span>
              <button
                type="button"
                class="btn-page-nav"
                :disabled="invoicesPage >= invoicesTotalPages"
                @click="setInvoicePage(invoicesPage + 1)"
              >
                <ChevronRight :size="16" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- TAB 3: RECEIPTS VIEW                                          -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'receipts'"
        class="zen-tab-content"
        aria-label="Receipts View"
      >
        <!-- Filter Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="receiptSearch"
              type="text"
              class="search-input"
              placeholder="Search by merchant or receipt number..."
              aria-label="Search receipts"
              @input="onReceiptSearchInput"
            />
            <button
              v-if="receiptSearch"
              type="button"
              class="clear-search-btn"
              @click="receiptSearch = ''; onReceiptSearchInput()"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <!-- Merchant -->
            <div class="filter-item">
              <label for="rec-merchant-filter" class="filter-label">Merchant</label>
              <select
                id="rec-merchant-filter"
                v-model="receiptMerchantFilter"
                class="filter-select"
                @change="receiptsPage = 1; fetchReceipts()"
              >
                <option value="">All Merchants</option>
                <option v-for="m in filterOptions.merchants" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>

            <!-- Direction -->
            <div class="filter-item">
              <label for="rec-dir-filter" class="filter-label">Direction</label>
              <select
                id="rec-dir-filter"
                v-model="receiptDirectionFilter"
                class="filter-select filter-select-sm"
                @change="receiptsPage = 1; fetchReceipts()"
              >
                <option value="all">All</option>
                <option value="expense">Expense</option>
                <option value="income">Income</option>
                <option value="unclassified">Unclassified</option>
              </select>
            </div>

            <!-- Payment Method -->
            <div class="filter-item">
              <label for="rec-pay-filter" class="filter-label">Payment</label>
              <select
                id="rec-pay-filter"
                v-model="receiptPaymentMethodFilter"
                class="filter-select filter-select-sm"
                @change="receiptsPage = 1; fetchReceipts()"
              >
                <option value="">All</option>
                <option v-for="p in filterOptions.payment_methods" :key="p" :value="p">{{ p }}</option>
              </select>
            </div>

            <!-- Currency -->
            <div class="filter-item">
              <label for="rec-currency-filter" class="filter-label">Currency</label>
              <select
                id="rec-currency-filter"
                v-model="receiptCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="receiptsPage = 1; fetchReceipts()"
              >
                <option value="">All</option>
                <option v-for="curr in filterOptions.currencies" :key="curr" :value="curr">{{ curr }}</option>
              </select>
            </div>

            <!-- Date From -->
            <div class="filter-item">
              <label for="rec-date-from" class="filter-label">From</label>
              <input
                id="rec-date-from"
                v-model="receiptDateFrom"
                type="date"
                class="filter-input-date"
                @change="receiptsPage = 1; fetchReceipts()"
              />
            </div>

            <!-- Date To -->
            <div class="filter-item">
              <label for="rec-date-to" class="filter-label">To</label>
              <input
                id="rec-date-to"
                v-model="receiptDateTo"
                type="date"
                class="filter-input-date"
                @change="receiptsPage = 1; fetchReceipts()"
              />
            </div>

            <!-- Clear -->
            <button
              v-if="hasReceiptFiltersApplied"
              type="button"
              class="btn-clear-filters"
              @click="clearReceiptFilters"
              title="Reset all filters"
            >
              <X :size="14" />
              <span>Clear</span>
            </button>

            <!-- Refresh -->
            <button
              type="button"
              class="btn-refresh"
              @click="fetchReceipts"
              title="Refresh receipts"
              :disabled="isLoadingReceipts"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingReceipts }" />
            </button>

            <!-- Export -->
            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('receipts')"
              title="Export filtered receipts"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Table View -->
        <div class="zen-table-card">
          <div class="zen-table-scroll">
            <table class="zen-data-table">
              <thead>
                <tr>
                  <th class="col-sortable" @click="toggleReceiptSort('merchant_name')">
                    <div class="th-wrap">
                      <span>Merchant</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleReceiptSort('receipt_number')">
                    <div class="th-wrap">
                      <span>Receipt #</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleReceiptSort('transaction_date')">
                    <div class="th-wrap">
                      <span>Date / Time</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Currency</th>
                  <th class="text-right col-sortable" @click="toggleReceiptSort('total_amount')">
                    <div class="th-wrap justify-end">
                      <span>Total Amount</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleReceiptSort('direction')">
                    <div class="th-wrap">
                      <span>Direction</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th>Payment Method</th>
                  <th class="text-center col-sortable" @click="toggleReceiptSort('line_item_count')">
                    <div class="th-wrap justify-center">
                      <span>Lines</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="isLoadingReceipts && receipts.length === 0">
                  <td colspan="9" class="empty-state">
                    <div class="loading-wrap">
                      <RefreshCw :size="20" class="spin" />
                      <span>Loading receipts...</span>
                    </div>
                  </td>
                </tr>

                <tr v-else-if="receipts.length === 0">
                  <td colspan="9" class="empty-state">
                    <span>No receipts found matching your criteria.</span>
                  </td>
                </tr>

                <tr
                  v-for="rec in receipts"
                  :key="rec.id"
                  class="cursor-pointer hover:bg-slate-50/80 transition-colors"
                  @click="openReceiptDetail(rec.id)"
                >
                  <td class="font-medium text-slate-900 max-w-xs truncate">{{ rec.merchant_name }}</td>
                  <td class="font-mono text-xs text-slate-800">
                    {{ rec.receipt_number || 'Not provided' }}
                  </td>
                  <td class="font-mono text-xs text-slate-600">
                    {{ formatDate(rec.transaction_date) }}
                    <span v-if="rec.transaction_time" class="text-slate-400 ml-1">{{ rec.transaction_time }}</span>
                  </td>
                  <td class="font-mono text-xs text-slate-600">{{ rec.currency || '—' }}</td>
                  <td class="text-right font-mono font-medium text-slate-900">
                    {{ formatCurrency(rec.total_amount, rec.currency) }}
                  </td>
                  <td>
                    <span :class="['zen-badge', getDirectionBadgeClass(rec.direction)]">
                      {{ formatDirection(rec.direction) }}
                    </span>
                  </td>
                  <td class="text-xs text-slate-700">{{ rec.payment_method || '—' }}</td>
                  <td class="text-center font-mono text-xs">
                    <span v-if="rec.line_item_count > 0" class="items-count-badge">
                      {{ rec.line_item_count }}
                    </span>
                    <span v-else class="text-slate-300">—</span>
                  </td>
                  <td class="text-right" @click.stop>
                    <div class="action-buttons justify-end">
                      <button
                        type="button"
                        class="btn-row-action"
                        title="Inspect receipt details"
                        @click="openReceiptDetail(rec.id)"
                      >
                        <Eye :size="14" />
                        <span>Inspect</span>
                      </button>
                      <a
                        v-if="rec.source_file_id"
                        :href="getSourcePreviewUrl(rec.source_file_id, true)"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="btn-row-action btn-source"
                        title="View source receipt document"
                        @click.prevent="handleSourceClick($event, rec)"
                      >
                        <ExternalLink :size="13" />
                        <span>Source</span>
                      </a>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="receiptsTotal > 0" class="zen-pagination-bar">
            <span class="page-meta">
              Showing {{ (receiptsPage - 1) * receiptsPageSize + 1 }}–{{ Math.min(receiptsPage * receiptsPageSize, receiptsTotal) }} of {{ receiptsTotal }}
            </span>
            <div class="pagination-controls">
              <button
                type="button"
                class="btn-page-nav"
                :disabled="receiptsPage <= 1"
                @click="setReceiptPage(receiptsPage - 1)"
              >
                <ChevronLeft :size="16" />
              </button>
              <span class="page-current">Page {{ receiptsPage }} of {{ receiptsTotalPages }}</span>
              <button
                type="button"
                class="btn-page-nav"
                :disabled="receiptsPage >= receiptsTotalPages"
                @click="setReceiptPage(receiptsPage + 1)"
              >
                <ChevronRight :size="16" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- TAB 4: LINE ITEMS VIEW                                        -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'line-items'"
        class="zen-tab-content"
        aria-label="Line Items View"
      >
        <!-- Filter Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="lineItemSearch"
              type="text"
              class="search-input"
              placeholder="Search description, company, or invoice..."
              aria-label="Search line items"
              @input="onLineItemSearchInput"
            />
            <button
              v-if="lineItemSearch"
              type="button"
              class="clear-search-btn"
              @click="lineItemSearch = ''; onLineItemSearchInput()"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <div class="filter-item">
              <label for="li-company-filter" class="filter-label">Company</label>
              <select
                id="li-company-filter"
                v-model="lineItemCompanyFilter"
                class="filter-select"
                @change="lineItemsPage = 1; fetchLineItems()"
              >
                <option value="">All Companies</option>
                <option v-for="c in filterOptions.companies" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>

            <div class="filter-item">
              <label for="li-currency-filter" class="filter-label">Currency</label>
              <select
                id="li-currency-filter"
                v-model="lineItemCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="lineItemsPage = 1; fetchLineItems()"
              >
                <option value="">All</option>
                <option v-for="curr in filterOptions.currencies" :key="curr" :value="curr">{{ curr }}</option>
              </select>
            </div>

            <div class="filter-item">
              <label for="li-date-from" class="filter-label">From</label>
              <input
                id="li-date-from"
                v-model="lineItemDateFrom"
                type="date"
                class="filter-input-date"
                @change="lineItemsPage = 1; fetchLineItems()"
              />
            </div>

            <div class="filter-item">
              <label for="li-date-to" class="filter-label">To</label>
              <input
                id="li-date-to"
                v-model="lineItemDateTo"
                type="date"
                class="filter-input-date"
                @change="lineItemsPage = 1; fetchLineItems()"
              />
            </div>

            <button
              v-if="hasLineItemFiltersApplied"
              type="button"
              class="btn-clear-filters"
              @click="clearLineItemFilters"
              title="Reset all filters"
            >
              <X :size="14" />
              <span>Clear</span>
            </button>

            <button
              type="button"
              class="btn-refresh"
              @click="fetchLineItems"
              title="Refresh line items"
              :disabled="isLoadingLineItems"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingLineItems }" />
            </button>

            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('line-items')"
              title="Export line items"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Table View -->
        <div class="zen-table-card">
          <div class="zen-table-scroll">
            <table class="zen-data-table">
              <thead>
                <tr>
                  <th class="col-sortable" @click="toggleLineItemSort('company_name')">
                    <div class="th-wrap">
                      <span>Company</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleLineItemSort('invoice_number')">
                    <div class="th-wrap">
                      <span>Invoice #</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="col-sortable" @click="toggleLineItemSort('description')">
                    <div class="th-wrap">
                      <span>Description</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right col-sortable" @click="toggleLineItemSort('quantity')">
                    <div class="th-wrap justify-end">
                      <span>Qty</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right col-sortable" @click="toggleLineItemSort('unit_price')">
                    <div class="th-wrap justify-end">
                      <span>Unit Price</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right">Tax</th>
                  <th class="text-right col-sortable" @click="toggleLineItemSort('amount')">
                    <div class="th-wrap justify-end">
                      <span>Amount</span>
                      <ArrowUpDown :size="13" class="sort-icon" />
                    </div>
                  </th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="isLoadingLineItems && lineItems.length === 0">
                  <td colspan="8" class="empty-state">
                    <div class="loading-wrap">
                      <RefreshCw :size="20" class="spin" />
                      <span>Loading line items...</span>
                    </div>
                  </td>
                </tr>

                <tr v-else-if="lineItems.length === 0">
                  <td colspan="8" class="empty-state">
                    <span>No line items found matching your criteria.</span>
                  </td>
                </tr>

                <tr
                  v-for="li in lineItems"
                  :key="li.id"
                  class="cursor-pointer hover:bg-slate-50/80 transition-colors"
                  @click="openInvoiceDetail(li.invoice_id)"
                >
                  <td class="font-medium text-slate-800 max-w-xs truncate">{{ li.company_name }}</td>
                  <td class="font-mono text-xs text-slate-600">{{ li.invoice_number }}</td>
                  <td class="text-slate-900 font-medium max-w-sm truncate">{{ li.description || '—' }}</td>
                  <td class="text-right font-mono text-slate-600">{{ formatQuantity(li.quantity) }}</td>
                  <td class="text-right font-mono text-slate-600">{{ formatCurrency(li.unit_price, li.currency) }}</td>
                  <td class="text-right font-mono text-slate-600">{{ formatTax(li.tax_rate, li.tax_amount, li.currency) }}</td>
                  <td class="text-right font-mono font-medium text-slate-900">{{ formatCurrency(li.amount, li.currency) }}</td>
                  <td class="text-right" @click.stop>
                    <button
                      type="button"
                      class="btn-row-action"
                      title="Inspect parent invoice"
                      @click="openInvoiceDetail(li.invoice_id)"
                    >
                      <Eye :size="14" />
                      <span>Invoice</span>
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination -->
          <div v-if="lineItemsTotal > 0" class="zen-pagination-bar">
            <span class="page-meta">
              Showing {{ (lineItemsPage - 1) * lineItemsPageSize + 1 }}–{{ Math.min(lineItemsPage * lineItemsPageSize, lineItemsTotal) }} of {{ lineItemsTotal }}
            </span>
            <div class="pagination-controls">
              <button
                type="button"
                class="btn-page-nav"
                :disabled="lineItemsPage <= 1"
                @click="setLineItemPage(lineItemsPage - 1)"
              >
                <ChevronLeft :size="16" />
              </button>
              <span class="page-current">Page {{ lineItemsPage }} of {{ lineItemsTotalPages }}</span>
              <button
                type="button"
                class="btn-page-nav"
                :disabled="lineItemsPage >= lineItemsTotalPages"
                @click="setLineItemPage(lineItemsPage + 1)"
              >
                <ChevronRight :size="16" />
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- ── Modals ────────────────────────────────────────────────── -->
    <InvoiceDetailModal
      v-if="selectedInvoice"
      :invoice="selectedInvoice"
      :is-open="isInvoiceModalOpen"
      @close="isInvoiceModalOpen = false; selectedInvoice = null"
      @save="handleSaveInvoiceEdit"
    />

    <ReceiptDetailModal
      v-if="selectedReceipt"
      :receipt="selectedReceipt"
      :is-open="isReceiptModalOpen"
      @close="isReceiptModalOpen = false; selectedReceipt = null"
    />

    <SourcePreviewModal
      :is-open="isSourcePreviewOpen"
      :source-file-id="previewSourceFileId"
      :filename="previewFilename"
      :media-type="previewMediaType"
      :initial-worksheet="previewWorksheet"
      :batch-id="previewBatchId"
      @close="closeSourcePreviewModal"
    />
  </div>
</template>

<style scoped>
/* ── Page Layout ────────────────────────────────────────────── */
.zen-explorer-page {
  min-height: 100vh;
  background: var(--bg-app);
  padding: 2rem 1.5rem;
}

.zen-container {
  max-width: 80rem;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* ── Page Header ────────────────────────────────────────────── */
.zen-page-header {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  justify-content: space-between;
}

@media (min-width: 768px) {
  .zen-page-header {
    flex-direction: row;
    align-items: flex-end;
  }
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.page-title {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.page-subtitle {
  font-size: 0.875rem;
  color: var(--text-muted);
}

/* ── Tabs ────────────────────────────────────────────────────── */
.zen-tabs {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  background: var(--border-default);
  padding: 0.25rem;
  border-radius: 0.5rem;
  width: fit-content;
}

.zen-tab-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.875rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-muted);
  transition: all 0.15s;
  background: transparent;
  border: none;
  cursor: pointer;
}

.zen-tab-btn:hover { color: var(--text-primary); }

.zen-tab-btn.active {
  background: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.15), 0 1px 2px -1px rgba(0, 0, 0, 0.1);
}

.tab-count-pill {
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  background: var(--bg-elevated);
  color: var(--text-muted);
}

.zen-tab-btn.active .tab-count-pill {
  background: var(--border-default);
  color: var(--text-secondary);
}

/* ── Tab Content ─────────────────────────────────────────────── */
.zen-tab-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

/* ── Toolbar — single scrollable row ─────────────────────────── */
.zen-toolbar {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.625rem;
  background: var(--bg-surface);
  padding: 0.5rem 0.875rem;
  border-radius: 0.5rem;
  border: 1px solid var(--border-default);
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

/* Search Box — fixed width, never grows */
.search-box {
  position: relative;
  flex: 0 0 auto;
  width: 13rem;
}

@media (min-width: 1280px) {
  .search-box { width: 16rem; }
}

.search-icon {
  position: absolute;
  left: 0.625rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 0.375rem 1.75rem 0.375rem 2rem;
  font-size: 0.8125rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-elevated);
  color: var(--text-primary);
  box-sizing: border-box;
}

.search-input::placeholder { color: var(--text-muted); }

.search-input:focus {
  outline: none;
  border-color: var(--accent-brand);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.clear-search-btn {
  position: absolute;
  right: 0.5rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  cursor: pointer;
  background: transparent;
  border: none;
  display: flex;
  align-items: center;
}

.clear-search-btn:hover { color: var(--text-secondary); }

/* Filter group — nowrap horizontal scroll, hides scrollbar */
.filter-group {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.filter-group::-webkit-scrollbar { display: none; }

.filter-item {
  display: flex;
  align-items: center;
  gap: 0.3125rem;
  flex-shrink: 0;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  white-space: nowrap;
}

.filter-select,
.filter-input-date {
  font-size: 0.8125rem;
  padding: 0.3125rem 0.5rem;
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  background: var(--bg-elevated);
  color: var(--text-primary);
  flex-shrink: 0;
}

.filter-select-sm { max-width: 7.5rem; }

.filter-select:focus,
.filter-input-date:focus {
  outline: none;
  border-color: var(--accent-brand);
}

/* Toolbar action buttons — always shrink to icon if needed */
.btn-clear-filters {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: var(--status-error);
  padding: 0.3125rem 0.5625rem;
  background: var(--status-error-bg);
  border: 1px solid var(--status-error-border);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
  flex-shrink: 0;
}

.btn-clear-filters:hover { filter: brightness(0.94); }

.btn-refresh {
  flex-shrink: 0;
  padding: 0.375rem;
  color: var(--text-muted);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-refresh:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-elevated);
}

.btn-export-shortcut {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--on-accent);
  background: var(--accent-brand);
  border: 1px solid transparent;
  border-radius: 0.375rem;
  cursor: pointer;
  transition: background-color 0.15s;
  white-space: nowrap;
}

.btn-export-shortcut:hover { background: var(--accent-brand-hover); }

/* ── Alert ───────────────────────────────────────────────────── */
.zen-alert {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.8125rem;
}

.zen-alert-error {
  background: var(--status-error-bg);
  border: 1px solid var(--status-error-border);
  color: var(--status-error);
}

.btn-retry {
  margin-left: auto;
  padding: 0.25rem 0.625rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--status-error);
  background: transparent;
  border: 1px solid var(--status-error-border);
  border-radius: 0.25rem;
  cursor: pointer;
}

/* ── Data Table Card ─────────────────────────────────────────── */
.zen-table-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 0.5rem;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

.zen-table-scroll { overflow-x: auto; }

.zen-data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
  text-align: left;
}

.zen-data-table th {
  background: var(--bg-elevated);
  padding: 0.75rem 1rem;
  font-weight: 600;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-default);
  white-space: nowrap;
}

.zen-data-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-default);
  color: var(--text-secondary);
  vertical-align: middle;
}

.zen-data-table tr:last-child td { border-bottom: none; }
.zen-data-table tbody tr:hover td { background: var(--bg-elevated); }

.col-sortable { cursor: pointer; user-select: none; }
.col-sortable:hover { background: var(--bg-elevated) !important; }

.th-wrap { display: flex; align-items: center; gap: 0.375rem; }
.sort-icon { color: var(--text-muted); }

.empty-state {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-muted);
  font-size: 0.875rem;
}

.loading-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: var(--text-muted);
}

/* ── Document type tags ──────────────────────────────────────── */
.doc-type-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.type-invoice {
  background: var(--status-info-bg);
  color: var(--status-info);
}

.type-receipt {
  background: var(--status-warning-bg);
  color: var(--status-warning);
}

/* ── Direction badges ────────────────────────────────────────── */
.zen-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 500;
  border: 1px solid transparent;
}

.badge-success {
  background: var(--status-success-bg);
  color: var(--status-success);
  border-color: var(--status-success-border);
}

.badge-warning {
  background: var(--status-warning-bg);
  color: var(--status-warning);
  border-color: var(--status-warning-border);
}

.badge-neutral {
  background: var(--bg-elevated);
  color: var(--text-muted);
  border-color: var(--border-default);
}

/* ── Status pill ─────────────────────────────────────────────── */
.status-pill {
  display: inline-flex;
  align-items: center;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: capitalize;
}

.status-imported {
  background: var(--status-success-bg);
  color: var(--status-success);
}

/* ── Line item count pill ────────────────────────────────────── */
.items-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.25rem;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-weight: 600;
  border: 1px solid var(--border-default);
}

/* ── Row action buttons ──────────────────────────────────────── */
.action-buttons {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.btn-row-action {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.75rem;
  font-weight: 500;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border: 1px solid var(--border-default);
  transition: all 0.15s;
  cursor: pointer;
  text-decoration: none;
}

.btn-row-action:hover {
  background: var(--border-default);
  color: var(--text-primary);
}

.btn-source {
  color: var(--accent-brand);
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.btn-source:hover {
  filter: brightness(1.1);
}

/* ── Pagination bar ──────────────────────────────────────────── */
.zen-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border-default);
}

.page-meta { font-size: 0.75rem; color: var(--text-muted); }

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-page-nav {
  padding: 0.25rem;
  border-radius: 0.25rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-page-nav:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-page-nav:not(:disabled):hover { background: var(--bg-elevated); }

.page-current { font-size: 0.75rem; color: var(--text-muted); }

/* ── Spin ────────────────────────────────────────────────────── */
.spin { animation: spin 1s linear infinite; }

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* ── Text helpers reused in table cells ─────────────────────── */
.text-right { text-align: right; }

/* Ensure font/color helpers on td */
.zen-data-table td.font-medium { font-weight: 500; }
.zen-data-table td.font-mono   { font-family: var(--font-mono, ui-monospace, monospace); }
.zen-data-table td.text-slate-900,
.zen-data-table td.font-medium { color: var(--text-primary); }
.zen-data-table td.text-slate-600 { color: var(--text-muted); }
.zen-data-table td.text-slate-500 { color: var(--text-muted); }
</style>