<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  AlertCircle,
  ArrowUpDown,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Download,
  FileSpreadsheet,
  FileText,
  Layers,
  RefreshCw,
  Search,
  X,
} from 'lucide-vue-next'

import InvoiceDetailModal from '@/components/explorer/InvoiceDetailModal.vue'
import { api } from '@/services/api'
import type {
  DataExplorerFilterOptions,
  InvoiceDetailResponse,
  InvoiceListItem,
  InvoiceRecordUpdate,
  LineItemListItem,
} from '@/types/api'

const router = useRouter()

// ── Active Tab ──────────────────────────────────────────────────────────────
const activeTab = ref<'invoices' | 'line-items'>('invoices')

// ── Shared Filter Options ───────────────────────────────────────────────────
const filterOptions = ref<DataExplorerFilterOptions>({
  companies: [],
  currencies: [],
})

// ── Invoices State ──────────────────────────────────────────────────────────
const invoices = ref<InvoiceListItem[]>([])
const invoicesTotal = ref(0)
const invoicesTotalPages = ref(0)
const invoicesPage = ref(1)
const invoicesPageSize = ref(25)
const invoicesSortBy = ref<string>('invoice_date')
const invoicesSortOrder = ref<'asc' | 'desc'>('desc')

const invoiceSearch = ref('')
const invoiceCompanyFilter = ref('')
const invoiceCurrencyFilter = ref('')
const invoiceDateFrom = ref('')
const invoiceDateTo = ref('')
const invoiceHasLineItems = ref<string>('all')

const isLoadingInvoices = ref(false)
const invoicesError = ref('')

// ── Line Items State ────────────────────────────────────────────────────────
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

// ── Detail Modal State ──────────────────────────────────────────────────────
const selectedInvoice = ref<InvoiceDetailResponse | null>(null)
const isModalOpen = ref(false)
const isLoadingDetail = ref(false)

// ── Debounce Timer ──────────────────────────────────────────────────────────
let searchDebounceTimer: any = null

// ── Computed Filters Active ─────────────────────────────────────────────────
const hasInvoiceFiltersApplied = computed(() => {
  return (
    invoiceSearch.value.trim() !== '' ||
    invoiceCompanyFilter.value !== '' ||
    invoiceCurrencyFilter.value !== '' ||
    invoiceDateFrom.value !== '' ||
    invoiceDateTo.value !== '' ||
    invoiceHasLineItems.value !== 'all'
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

function friendlyLabel(key: string): string {
  const map: Record<string, string> = {
    due_date: 'Due Date',
    sub_total: 'Subtotal',
    sku_code: 'SKU',
  }
  return map[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
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

function onInvoiceSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    invoicesPage.value = 1
    fetchInvoices()
  }, 300)
}

function onLineItemSearchInput() {
  clearTimeout(searchDebounceTimer)
  searchDebounceTimer = setTimeout(() => {
    lineItemsPage.value = 1
    fetchLineItems()
  }, 300)
}

function onInvoiceFilterChange() {
  invoicesPage.value = 1
  fetchInvoices()
}

function onLineItemFilterChange() {
  lineItemsPage.value = 1
  fetchLineItems()
}

function clearInvoiceFilters() {
  invoiceSearch.value = ''
  invoiceCompanyFilter.value = ''
  invoiceCurrencyFilter.value = ''
  invoiceDateFrom.value = ''
  invoiceDateTo.value = ''
  invoiceHasLineItems.value = 'all'
  invoicesPage.value = 1
  fetchInvoices()
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

function setInvoicePage(page: number) {
  if (page >= 1 && page <= invoicesTotalPages.value) {
    invoicesPage.value = page
    fetchInvoices()
  }
}

function setLineItemPage(page: number) {
  if (page >= 1 && page <= lineItemsTotalPages.value) {
    lineItemsPage.value = page
    fetchLineItems()
  }
}

function onInvoicePageSizeChange() {
  invoicesPage.value = 1
  fetchInvoices()
}

function onLineItemPageSizeChange() {
  lineItemsPage.value = 1
  fetchLineItems()
}

// ── Detail Modal Handlers ───────────────────────────────────────────────────

async function openInvoiceDetail(invoiceId: number) {
  isLoadingDetail.value = true
  try {
    const detail = await api.getDataExplorerInvoice(invoiceId)
    selectedInvoice.value = detail
    isModalOpen.value = true
  } catch (err: any) {
    alert(err.message || 'Failed to load invoice details.')
  } finally {
    isLoadingDetail.value = false
  }
}

function closeDetailModal() {
  isModalOpen.value = false
  selectedInvoice.value = null
}

async function handleSaveInvoiceEdit(payload: {
  invoiceId: number
  form: InvoiceRecordUpdate
}) {
  try {
    const updated = await api.updateDataExplorerInvoice(payload.invoiceId, payload.form)
    selectedInvoice.value = updated
    // Refresh table row data
    fetchInvoices()
    if (activeTab.value === 'line-items') {
      fetchLineItems()
    }
  } catch (err: any) {
    throw err
  }
}

function navigateToIngestion() {
  router.push('/')
}

function navigateToExport(dataset: 'invoices' | 'line-items') {
  const qp: Record<string, string> = { dataset }
  if (dataset === 'invoices') {
    if (invoiceSearch.value.trim()) qp.search = invoiceSearch.value.trim()
    if (invoiceCompanyFilter.value) qp.company = invoiceCompanyFilter.value
    if (invoiceCurrencyFilter.value) qp.currency = invoiceCurrencyFilter.value
    if (invoiceDateFrom.value) qp.date_from = invoiceDateFrom.value
    if (invoiceDateTo.value) qp.date_to = invoiceDateTo.value
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
  fetchInvoices()
})

watch(activeTab, (tab) => {
  if (tab === 'line-items' && lineItems.value.length === 0) {
    fetchLineItems()
  }
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
            Browse, search, and inspect standardized business records in DataBridge.
          </p>
        </div>

        <!-- Tab Controls -->
        <div class="zen-tabs" role="tablist" aria-label="Data Explorer Views">
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
      <!-- TAB 1: INVOICES VIEW                                          -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'invoices'"
        class="zen-tab-content"
        aria-label="Invoices View"
      >
        <!-- Filter & Search Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="invoiceSearch"
              type="text"
              class="search-input"
              placeholder="Search by company or invoice number..."
              aria-label="Search invoices by company or invoice number"
              @input="onInvoiceSearchInput"
            />
            <button
              v-if="invoiceSearch"
              type="button"
              class="clear-search-btn"
              @click="invoiceSearch = ''; onInvoiceSearchInput()"
              aria-label="Clear search"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <!-- Company Filter -->
            <div class="filter-item">
              <label for="inv-company-filter" class="filter-label">Company</label>
              <select
                id="inv-company-filter"
                v-model="invoiceCompanyFilter"
                class="filter-select"
                @change="onInvoiceFilterChange"
              >
                <option value="">All Companies</option>
                <option
                  v-for="c in filterOptions.companies"
                  :key="c"
                  :value="c"
                >
                  {{ c }}
                </option>
              </select>
            </div>

            <!-- Currency Filter -->
            <div class="filter-item">
              <label for="inv-currency-filter" class="filter-label">Currency</label>
              <select
                id="inv-currency-filter"
                v-model="invoiceCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="onInvoiceFilterChange"
              >
                <option value="">All</option>
                <option
                  v-for="curr in filterOptions.currencies"
                  :key="curr"
                  :value="curr"
                >
                  {{ curr }}
                </option>
              </select>
            </div>

            <!-- Date Range From -->
            <div class="filter-item">
              <label for="inv-date-from" class="filter-label">From</label>
              <input
                id="inv-date-from"
                v-model="invoiceDateFrom"
                type="date"
                class="filter-input-date"
                @change="onInvoiceFilterChange"
              />
            </div>

            <!-- Date Range To -->
            <div class="filter-item">
              <label for="inv-date-to" class="filter-label">To</label>
              <input
                id="inv-date-to"
                v-model="invoiceDateTo"
                type="date"
                class="filter-input-date"
                @change="onInvoiceFilterChange"
              />
            </div>

            <!-- Line Items Selector -->
            <div class="filter-item">
              <label for="inv-has-items" class="filter-label">Items</label>
              <select
                id="inv-has-items"
                v-model="invoiceHasLineItems"
                class="filter-select filter-select-sm"
                @change="onInvoiceFilterChange"
              >
                <option value="all">All</option>
                <option value="yes">Has Items</option>
                <option value="no">No Items</option>
              </select>
            </div>

            <!-- Clear Filters Button -->
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

            <!-- Refresh Button -->
            <button
              type="button"
              class="btn-refresh"
              @click="fetchInvoices"
              title="Refresh invoice data"
              :disabled="isLoadingInvoices"
              aria-label="Refresh invoices"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingInvoices }" />
            </button>

            <!-- Export Shortcut Button -->
            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('invoices')"
              title="Export filtered invoices"
              aria-label="Export filtered invoices"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Error State -->
        <div v-if="invoicesError" class="zen-alert zen-alert-error" role="alert">
          <AlertCircle :size="18" />
          <div class="alert-content">
            <span class="alert-title">Unable to load invoice data.</span>
            <span class="alert-msg">{{ invoicesError }}</span>
          </div>
          <button type="button" class="btn-zen-secondary btn-sm" @click="fetchInvoices">
            Retry
          </button>
        </div>

        <!-- Loading State Skeleton -->
        <div v-else-if="isLoadingInvoices" class="zen-table-card">
          <div class="skeleton-table">
            <div class="skeleton-header"></div>
            <div v-for="i in 8" :key="i" class="skeleton-row"></div>
          </div>
        </div>

        <!-- Empty State (No Data in System) -->
        <div
          v-else-if="invoicesTotal === 0 && !hasInvoiceFiltersApplied"
          class="zen-empty-state"
        >
          <div class="empty-icon-wrap">
            <FileSpreadsheet :size="32" class="text-accent" />
          </div>
          <h3 class="empty-title">No invoice data yet.</h3>
          <p class="empty-desc">
            Import and confirm a file in Ingestion Studio to start building your Data Explorer.
          </p>
          <button
            type="button"
            class="btn-zen-primary"
            @click="navigateToIngestion"
          >
            Go to Ingestion Studio
          </button>
        </div>

        <!-- Empty State (No Search Results) -->
        <div
          v-else-if="invoicesTotal === 0 && hasInvoiceFiltersApplied"
          class="zen-empty-state"
        >
          <div class="empty-icon-wrap">
            <Search :size="32" class="text-muted" />
          </div>
          <h3 class="empty-title">No invoices match your current search and filters.</h3>
          <p class="empty-desc">
            Try adjusting your query, clearing the company or date filters.
          </p>
          <button
            type="button"
            class="btn-zen-secondary"
            @click="clearInvoiceFilters"
          >
            Clear filters
          </button>
        </div>

        <!-- Main Invoices Table -->
        <div v-else class="zen-table-card">
          <div class="zen-table-responsive">
            <table class="zen-table">
              <thead>
                <tr>
                  <th
                    scope="col"
                    class="th-sortable th-company"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'company_name' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('company_name')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('company_name')"
                  >
                    <div class="th-content">
                      <span>Company</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'company_name' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'company_name' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-inv-num"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'invoice_number' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('invoice_number')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('invoice_number')"
                  >
                    <div class="th-content">
                      <span>Invoice</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'invoice_number' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'invoice_number' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-date"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'invoice_date' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('invoice_date')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('invoice_date')"
                  >
                    <div class="th-content">
                      <span>Date</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'invoice_date' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'invoice_date' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th scope="col" class="th-curr">Currency</th>

                  <th
                    scope="col"
                    class="th-sortable th-amount"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'total_amount' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('total_amount')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('total_amount')"
                  >
                    <div class="th-content justify-end">
                      <span>Total</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'total_amount' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'total_amount' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-items"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'line_item_count' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('line_item_count')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('line_item_count')"
                  >
                    <div class="th-content justify-center">
                      <span>Items</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'line_item_count' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'line_item_count' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-imported"
                    tabindex="0"
                    :aria-sort="invoicesSortBy === 'created_at' ? (invoicesSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleInvoiceSort('created_at')"
                    @keydown.enter.space.prevent="toggleInvoiceSort('created_at')"
                  >
                    <div class="th-content">
                      <span>Imported</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="invoicesSortBy === 'created_at' && invoicesSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="invoicesSortBy === 'created_at' && invoicesSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="inv in invoices"
                  :key="inv.id"
                  class="zen-row"
                  tabindex="0"
                  role="button"
                  :aria-label="`View details for invoice ${inv.invoice_number} from ${inv.company_name}`"
                  @click="openInvoiceDetail(inv.id)"
                  @keydown.enter.space.prevent="openInvoiceDetail(inv.id)"
                >
                  <td class="td-company">
                    <span class="cell-main-text font-medium">{{ inv.company_name }}</span>
                  </td>
                  <td class="td-inv-num">
                    <span class="cell-sub-text font-mono font-medium">{{ inv.invoice_number }}</span>
                  </td>
                  <td class="td-date">
                    <span class="cell-sub-text">{{ formatDate(inv.invoice_date) }}</span>
                  </td>
                  <td class="td-curr">
                    <span v-if="inv.currency" class="currency-tag">{{ inv.currency }}</span>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="td-amount font-mono">
                    <span class="cell-amount-text font-medium">
                      {{ formatNumber(parseNumeric(inv.total_amount) ?? 0) }}
                    </span>
                  </td>
                  <td class="td-items">
                    <span
                      class="items-count-badge"
                      :class="{ 'has-items': inv.line_item_count > 0 }"
                    >
                      {{ inv.line_item_count }}
                    </span>
                  </td>
                  <td class="td-imported">
                    <span class="cell-sub-text text-muted">{{ formatDate(inv.created_at) }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination Bar -->
          <div class="zen-pagination-bar">
            <div class="pagination-info">
              Showing
              <span class="font-medium">
                {{ (invoicesPage - 1) * invoicesPageSize + 1 }}–{{ Math.min(invoicesPage * invoicesPageSize, invoicesTotal) }}
              </span>
              of
              <span class="font-medium">{{ invoicesTotal }}</span>
              records
            </div>

            <div class="pagination-controls">
              <!-- Page Size Select -->
              <div class="page-size-wrap">
                <label for="inv-page-size" class="page-size-label">Rows per page:</label>
                <select
                  id="inv-page-size"
                  v-model="invoicesPageSize"
                  class="page-size-select"
                  @change="onInvoicePageSizeChange"
                >
                  <option :value="25">25</option>
                  <option :value="50">50</option>
                  <option :value="100">100</option>
                </select>
              </div>

              <!-- Nav Buttons -->
              <div class="page-nav-btns">
                <button
                  type="button"
                  class="btn-page"
                  :disabled="invoicesPage <= 1"
                  @click="setInvoicePage(invoicesPage - 1)"
                  aria-label="Previous page"
                >
                  <ChevronLeft :size="16" />
                </button>

                <span class="page-indicator">
                  Page {{ invoicesPage }} of {{ invoicesTotalPages || 1 }}
                </span>

                <button
                  type="button"
                  class="btn-page"
                  :disabled="invoicesPage >= invoicesTotalPages"
                  @click="setInvoicePage(invoicesPage + 1)"
                  aria-label="Next page"
                >
                  <ChevronRight :size="16" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ═════════════════════════════════════════════════════════════ -->
      <!-- TAB 2: LINE ITEMS VIEW                                        -->
      <!-- ═════════════════════════════════════════════════════════════ -->
      <section
        v-if="activeTab === 'line-items'"
        class="zen-tab-content"
        aria-label="Line Items View"
      >
        <!-- Filter & Search Toolbar -->
        <div class="zen-toolbar">
          <div class="search-box">
            <Search :size="16" class="search-icon" />
            <input
              v-model="lineItemSearch"
              type="text"
              class="search-input"
              placeholder="Search descriptions, company, or invoice..."
              aria-label="Search line items"
              @input="onLineItemSearchInput"
            />
            <button
              v-if="lineItemSearch"
              type="button"
              class="clear-search-btn"
              @click="lineItemSearch = ''; onLineItemSearchInput()"
              aria-label="Clear search"
            >
              <X :size="14" />
            </button>
          </div>

          <div class="filter-group">
            <!-- Company Filter -->
            <div class="filter-item">
              <label for="li-company-filter" class="filter-label">Company</label>
              <select
                id="li-company-filter"
                v-model="lineItemCompanyFilter"
                class="filter-select"
                @change="onLineItemFilterChange"
              >
                <option value="">All Companies</option>
                <option
                  v-for="c in filterOptions.companies"
                  :key="c"
                  :value="c"
                >
                  {{ c }}
                </option>
              </select>
            </div>

            <!-- Currency Filter -->
            <div class="filter-item">
              <label for="li-currency-filter" class="filter-label">Currency</label>
              <select
                id="li-currency-filter"
                v-model="lineItemCurrencyFilter"
                class="filter-select filter-select-sm"
                @change="onLineItemFilterChange"
              >
                <option value="">All</option>
                <option
                  v-for="curr in filterOptions.currencies"
                  :key="curr"
                  :value="curr"
                >
                  {{ curr }}
                </option>
              </select>
            </div>

            <!-- Date Range From -->
            <div class="filter-item">
              <label for="li-date-from" class="filter-label">From</label>
              <input
                id="li-date-from"
                v-model="lineItemDateFrom"
                type="date"
                class="filter-input-date"
                @change="onLineItemFilterChange"
              />
            </div>

            <!-- Date Range To -->
            <div class="filter-item">
              <label for="li-date-to" class="filter-label">To</label>
              <input
                id="li-date-to"
                v-model="lineItemDateTo"
                type="date"
                class="filter-input-date"
                @change="onLineItemFilterChange"
              />
            </div>

            <!-- Clear Filters Button -->
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

            <!-- Refresh Button -->
            <button
              type="button"
              class="btn-refresh"
              @click="fetchLineItems"
              title="Refresh line item data"
              :disabled="isLoadingLineItems"
              aria-label="Refresh line items"
            >
              <RefreshCw :size="15" :class="{ spin: isLoadingLineItems }" />
            </button>

            <!-- Export Shortcut Button -->
            <button
              type="button"
              class="btn-export-shortcut"
              @click="navigateToExport('line-items')"
              title="Export filtered line items"
              aria-label="Export filtered line items"
            >
              <Download :size="14" />
              <span>Export</span>
            </button>
          </div>
        </div>

        <!-- Error State -->
        <div v-if="lineItemsError" class="zen-alert zen-alert-error" role="alert">
          <AlertCircle :size="18" />
          <div class="alert-content">
            <span class="alert-title">Unable to load line items.</span>
            <span class="alert-msg">{{ lineItemsError }}</span>
          </div>
          <button type="button" class="btn-zen-secondary btn-sm" @click="fetchLineItems">
            Retry
          </button>
        </div>

        <!-- Loading State Skeleton -->
        <div v-else-if="isLoadingLineItems" class="zen-table-card">
          <div class="skeleton-table">
            <div class="skeleton-header"></div>
            <div v-for="i in 8" :key="i" class="skeleton-row"></div>
          </div>
        </div>

        <!-- Empty State (No Line Items in System) -->
        <div
          v-else-if="lineItemsTotal === 0 && !hasLineItemFiltersApplied"
          class="zen-empty-state"
        >
          <div class="empty-icon-wrap">
            <Layers :size="32" class="text-muted" />
          </div>
          <h3 class="empty-title">No line items found.</h3>
          <p class="empty-desc">
            Invoices imported using templates without line-item mappings may not contain line items.
          </p>
        </div>

        <!-- Empty State (No Search Results) -->
        <div
          v-else-if="lineItemsTotal === 0 && hasLineItemFiltersApplied"
          class="zen-empty-state"
        >
          <div class="empty-icon-wrap">
            <Search :size="32" class="text-muted" />
          </div>
          <h3 class="empty-title">No line items match your current search and filters.</h3>
          <p class="empty-desc">
            Try adjusting your search query or clearing the filters.
          </p>
          <button
            type="button"
            class="btn-zen-secondary"
            @click="clearLineItemFilters"
          >
            Clear filters
          </button>
        </div>

        <!-- Main Line Items Table -->
        <div v-else class="zen-table-card">
          <div class="zen-table-responsive">
            <table class="zen-table">
              <thead>
                <tr>
                  <th
                    scope="col"
                    class="th-sortable th-desc"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'description' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('description')"
                    @keydown.enter.space.prevent="toggleLineItemSort('description')"
                  >
                    <div class="th-content">
                      <span>Description</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'description' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'description' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-company"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'company_name' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('company_name')"
                    @keydown.enter.space.prevent="toggleLineItemSort('company_name')"
                  >
                    <div class="th-content">
                      <span>Company</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'company_name' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'company_name' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-inv-num"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'invoice_number' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('invoice_number')"
                    @keydown.enter.space.prevent="toggleLineItemSort('invoice_number')"
                  >
                    <div class="th-content">
                      <span>Invoice</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'invoice_number' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'invoice_number' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-date"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'invoice_date' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('invoice_date')"
                    @keydown.enter.space.prevent="toggleLineItemSort('invoice_date')"
                  >
                    <div class="th-content">
                      <span>Date</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'invoice_date' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'invoice_date' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-qty"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'quantity' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('quantity')"
                    @keydown.enter.space.prevent="toggleLineItemSort('quantity')"
                  >
                    <div class="th-content justify-end">
                      <span>Qty</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'quantity' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'quantity' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-unit-price"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'unit_price' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('unit_price')"
                    @keydown.enter.space.prevent="toggleLineItemSort('unit_price')"
                  >
                    <div class="th-content justify-end">
                      <span>Price</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'unit_price' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'unit_price' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-tax"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'tax_rate' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('tax_rate')"
                    @keydown.enter.space.prevent="toggleLineItemSort('tax_rate')"
                  >
                    <div class="th-content justify-end">
                      <span>Tax</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'tax_rate' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'tax_rate' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th
                    scope="col"
                    class="th-sortable th-amount"
                    tabindex="0"
                    :aria-sort="lineItemsSortBy === 'amount' ? (lineItemsSortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                    @click="toggleLineItemSort('amount')"
                    @keydown.enter.space.prevent="toggleLineItemSort('amount')"
                  >
                    <div class="th-content justify-end">
                      <span>Amount</span>
                      <span class="sort-icon">
                        <ChevronUp v-if="lineItemsSortBy === 'amount' && lineItemsSortOrder === 'asc'" :size="14" />
                        <ChevronDown v-else-if="lineItemsSortBy === 'amount' && lineItemsSortOrder === 'desc'" :size="14" />
                        <ArrowUpDown v-else :size="12" class="sort-inactive" />
                      </span>
                    </div>
                  </th>

                  <th scope="col" class="th-custom">Details</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="li in lineItems"
                  :key="li.id"
                  class="zen-row"
                  tabindex="0"
                  role="button"
                  :aria-label="`View parent invoice for ${li.description}`"
                  @click="openInvoiceDetail(li.invoice_id)"
                  @keydown.enter.space.prevent="openInvoiceDetail(li.invoice_id)"
                >
                  <td class="td-desc">
                    <span class="cell-main-text font-medium">{{ li.description || '—' }}</span>
                  </td>
                  <td class="td-company">
                    <span class="cell-sub-text">{{ li.company_name }}</span>
                  </td>
                  <td class="td-inv-num">
                    <span class="cell-sub-text font-mono">{{ li.invoice_number }}</span>
                  </td>
                  <td class="td-date">
                    <span class="cell-sub-text">{{ formatDate(li.invoice_date) }}</span>
                  </td>
                  <td class="td-qty font-mono">
                    <span class="cell-sub-text">{{ formatQuantity(li.quantity) }}</span>
                  </td>
                  <td class="td-unit-price font-mono">
                    <span class="cell-sub-text">{{ formatNumber(parseNumeric(li.unit_price) ?? 0) }}</span>
                  </td>
                  <td class="td-tax font-mono">
                    <span class="cell-sub-text">{{ formatTax(li.tax_rate, li.tax_amount, li.currency) }}</span>
                  </td>
                  <td class="td-amount font-mono">
                    <span class="cell-amount-text font-medium">
                      {{ formatNumber(parseNumeric(li.amount) ?? 0) }}
                    </span>
                  </td>
                  <td class="td-custom">
                    <div v-if="li.custom_fields && Object.keys(li.custom_fields).length > 0" class="line-custom-tags">
                      <span
                        v-for="(val, k) in li.custom_fields"
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

          <!-- Pagination Bar -->
          <div class="zen-pagination-bar">
            <div class="pagination-info">
              Showing
              <span class="font-medium">
                {{ (lineItemsPage - 1) * lineItemsPageSize + 1 }}–{{ Math.min(lineItemsPage * lineItemsPageSize, lineItemsTotal) }}
              </span>
              of
              <span class="font-medium">{{ lineItemsTotal }}</span>
              items
            </div>

            <div class="pagination-controls">
              <!-- Page Size Select -->
              <div class="page-size-wrap">
                <label for="li-page-size" class="page-size-label">Items per page:</label>
                <select
                  id="li-page-size"
                  v-model="lineItemsPageSize"
                  class="page-size-select"
                  @change="onLineItemPageSizeChange"
                >
                  <option :value="25">25</option>
                  <option :value="50">50</option>
                  <option :value="100">100</option>
                </select>
              </div>

              <!-- Nav Buttons -->
              <div class="page-nav-btns">
                <button
                  type="button"
                  class="btn-page"
                  :disabled="lineItemsPage <= 1"
                  @click="setLineItemPage(lineItemsPage - 1)"
                  aria-label="Previous page"
                >
                  <ChevronLeft :size="16" />
                </button>

                <span class="page-indicator">
                  Page {{ lineItemsPage }} of {{ lineItemsTotalPages || 1 }}
                </span>

                <button
                  type="button"
                  class="btn-page"
                  :disabled="lineItemsPage >= lineItemsTotalPages"
                  @click="setLineItemPage(lineItemsPage + 1)"
                  aria-label="Next page"
                >
                  <ChevronRight :size="16" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Detail Modal ─────────────────────────────────────────── -->
      <InvoiceDetailModal
        v-if="selectedInvoice"
        :invoice="selectedInvoice"
        :is-open="isModalOpen"
        @close="closeDetailModal"
        @save="handleSaveInvoiceEdit"
      />
    </div>
  </div>
</template>

<style scoped>
.zen-explorer-page {
  min-height: calc(100vh - 4.25rem);
  background: var(--bg-app);
  color: var(--text-primary);
  padding: 2rem 0;
}

.zen-container {
  max-width: 1360px;
  margin: 0 auto;
  padding: 0 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* Page Header */
.zen-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 1.25rem;
}

.page-title {
  margin: 0 0 0.35rem;
  font-size: 1.65rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.page-subtitle {
  margin: 0;
  font-size: 0.88rem;
  color: var(--text-secondary);
}

/* Tab Bar */
.zen-tabs {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--bg-card);
  padding: 0.3rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
}

.zen-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.85rem;
  font-weight: 600;
  padding: 0.45rem 1rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.zen-tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.zen-tab-btn.active {
  color: var(--text-primary);
  background: var(--bg-subtle);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-medium);
}

.tab-count-pill {
  font-size: 0.72rem;
  background: var(--bg-app);
  padding: 0.1rem 0.45rem;
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font-weight: 600;
}

/* Toolbar */
.zen-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 0.85rem 1.15rem;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 260px;
  max-width: 400px;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  color: var(--text-muted);
  pointer-events: none;
}

.search-input {
  width: 100%;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0.45rem 2rem 0.45rem 2.2rem;
  font-size: 0.85rem;
  color: var(--text-primary);
  transition: all var(--transition-fast);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent-brand);
  background: var(--bg-card);
}

.clear-search-btn {
  position: absolute;
  right: 0.5rem;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.2rem;
  display: flex;
  align-items: center;
}

.clear-search-btn:hover {
  color: var(--text-primary);
}

.filter-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.filter-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.filter-select, .filter-input-date {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0.4rem 0.65rem;
  font-size: 0.82rem;
  color: var(--text-primary);
  outline: none;
}

.filter-select:focus, .filter-input-date:focus {
  border-color: var(--accent-brand);
}

.filter-select-sm {
  max-width: 90px;
}

.btn-clear-filters {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.4rem 0.65rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.btn-clear-filters:hover {
  color: var(--status-error);
  border-color: var(--status-error);
}

.btn-refresh {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  padding: 0.4rem;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  cursor: pointer;
}

.btn-refresh:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-medium);
}

.btn-export-shortcut {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-size: 0.78rem;
  font-weight: 600;
  padding: 0.4rem 0.75rem;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-export-shortcut:hover {
  border-color: var(--accent-brand);
  color: var(--accent-brand);
  background: var(--accent-brand-subtle);
}


/* Table Card */
.zen-table-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}

.zen-table-responsive {
  overflow-x: auto;
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
  user-select: none;
}

.th-sortable {
  cursor: pointer;
  transition: color var(--transition-fast);
}

.th-sortable:hover {
  color: var(--text-primary);
}

.th-content {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
}

.justify-end {
  justify-content: flex-end;
}

.justify-center {
  justify-content: center;
}

.sort-icon {
  display: inline-flex;
  align-items: center;
  color: var(--accent-brand);
}

.sort-inactive {
  color: var(--text-muted);
  opacity: 0.4;
}

.th-sortable:hover .sort-inactive {
  opacity: 0.8;
}

.zen-table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
}

.zen-row {
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.zen-row:hover {
  background-color: var(--bg-subtle);
}

.zen-row:focus-visible {
  outline: 2px solid var(--accent-brand);
  outline-offset: -2px;
}

/* Column Specific Styles */
.th-company, .td-company {
  min-width: 220px;
}

.th-inv-num, .td-inv-num {
  min-width: 140px;
}

.th-date, .td-date {
  min-width: 110px;
  white-space: nowrap;
}

.th-curr, .td-curr {
  width: 80px;
}

.th-amount, .td-amount {
  min-width: 120px;
  text-align: right;
  white-space: nowrap;
}

.th-items, .td-items {
  width: 80px;
  text-align: center;
}

.th-imported, .td-imported {
  min-width: 110px;
  white-space: nowrap;
}

.th-desc, .td-desc {
  min-width: 260px;
}

.th-qty, .td-qty, .th-unit-price, .td-unit-price, .th-tax, .td-tax {
  min-width: 90px;
  text-align: right;
  white-space: nowrap;
}

.th-custom, .td-custom {
  min-width: 140px;
}

.cell-main-text {
  color: var(--text-primary);
}

.cell-sub-text {
  color: var(--text-secondary);
}

.cell-amount-text {
  color: var(--text-primary);
  font-size: 0.9rem;
}

.currency-tag {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 600;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  padding: 0.15rem 0.4rem;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
}

.items-count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.5rem;
  height: 1.35rem;
  padding: 0 0.35rem;
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 600;
  background: var(--bg-subtle);
  color: var(--text-muted);
}

.items-count-badge.has-items {
  background: var(--accent-brand-subtle);
  color: var(--accent-brand);
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

/* Pagination */
.zen-pagination-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.85rem 1.25rem;
  background: var(--bg-subtle);
  border-top: 1px solid var(--border-subtle);
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.page-size-wrap {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.page-size-select {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xs);
  padding: 0.2rem 0.45rem;
  font-size: 0.8rem;
  color: var(--text-primary);
}

.page-nav-btns {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-page {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  padding: 0.3rem 0.5rem;
  border-radius: var(--radius-xs);
  display: flex;
  align-items: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-page:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-medium);
}

.btn-page:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-indicator {
  font-weight: 500;
  color: var(--text-primary);
}

/* Empty & Error States */
.zen-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 4rem 2rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  gap: 0.75rem;
}

.empty-icon-wrap {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: var(--radius-full);
  background: var(--bg-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.5rem;
}

.empty-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-desc {
  margin: 0;
  font-size: 0.88rem;
  color: var(--text-secondary);
  max-width: 440px;
}

.zen-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-radius: var(--radius-md);
  margin-bottom: 1rem;
}

.zen-alert-error {
  background: var(--status-error-bg);
  border: 1px solid var(--status-error-border);
  color: var(--status-error);
}

.alert-content {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  flex: 1;
  margin: 0 1rem;
}

.alert-title {
  font-weight: 600;
  font-size: 0.88rem;
}

.alert-msg {
  font-size: 0.8rem;
  opacity: 0.9;
}

/* Skeleton Loading */
.skeleton-table {
  padding: 1rem;
}

.skeleton-header {
  height: 36px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  margin-bottom: 0.75rem;
  animation: pulse 1.5s infinite;
}

.skeleton-row {
  height: 44px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  margin-bottom: 0.5rem;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
}

/* Buttons */
.btn-zen-primary {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  background: var(--accent-brand);
  color: var(--on-accent);
  border: none;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
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
  padding: 0.5rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-zen-secondary:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.btn-sm {
  padding: 0.35rem 0.75rem;
  font-size: 0.78rem;
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

.text-accent {
  color: var(--accent-brand);
}

.text-muted {
  color: var(--text-muted);
}
</style>
