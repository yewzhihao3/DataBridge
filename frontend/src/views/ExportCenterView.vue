<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileSpreadsheet,
  FileText,
  Layers,
  Loader2,
  RefreshCw,
  Search,
  Table,
  X,
} from 'lucide-vue-next'

import { api } from '@/services/api'
import type {
  DataExplorerFilterOptions,
  ExportSummaryResponse,
} from '@/types/api'

const route = useRoute()

// ── Step 1: Dataset ─────────────────────────────────────────────────────────
const selectedDataset = ref<'invoices' | 'line-items'>('invoices')

// ── Step 2: Filters ─────────────────────────────────────────────────────────
const searchQuery = ref('')
const companyFilter = ref('')
const currencyFilter = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const hasLineItemsFilter = ref<string>('all')

const filterOptions = ref<DataExplorerFilterOptions>({
  companies: [],
  currencies: [],
})

// ── Step 3: Format ──────────────────────────────────────────────────────────
const selectedFormat = ref<'csv' | 'xlsx'>('xlsx')

// ── Step 4: Summary & Export State ──────────────────────────────────────────
const summary = ref<ExportSummaryResponse>({
  dataset: 'invoices',
  total_records: 0,
  column_count: 0,
  columns: [],
})

const isLoadingSummary = ref(false)
const summaryError = ref('')
const isExporting = ref(false)
const exportError = ref('')
const exportSuccessMessage = ref('')
const showColumnsList = ref(false)

let debounceTimer: any = null

// ── Computed Filter State ───────────────────────────────────────────────────
const hasFiltersApplied = computed(() => {
  return (
    searchQuery.value.trim() !== '' ||
    companyFilter.value !== '' ||
    currencyFilter.value !== '' ||
    dateFrom.value !== '' ||
    dateTo.value !== '' ||
    hasLineItemsFilter.value !== 'all'
  )
})

// ── Fetch Filter Options & Live Summary ──────────────────────────────────────

async function loadFilterOptions() {
  try {
    const opts = await api.getDataExplorerFilterOptions()
    filterOptions.value = opts
  } catch (err) {
    console.error('Failed to load filter options', err)
  }
}

async function updateSummary() {
  isLoadingSummary.value = true
  summaryError.value = ''
  exportSuccessMessage.value = ''

  try {
    let hasLineItemsParam: boolean | undefined = undefined
    if (selectedDataset.value === 'invoices') {
      if (hasLineItemsFilter.value === 'yes') hasLineItemsParam = true
      if (hasLineItemsFilter.value === 'no') hasLineItemsParam = false
    }

    const res = await api.getExportSummary(selectedDataset.value, {
      search: searchQuery.value.trim() || undefined,
      company: companyFilter.value || undefined,
      currency: currencyFilter.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      has_line_items: hasLineItemsParam,
    })

    summary.value = res
  } catch (err: any) {
    summaryError.value = err.message || 'Unable to calculate export summary.'
  } finally {
    isLoadingSummary.value = false
  }
}

function onFilterInputDebounced() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    updateSummary()
  }, 300)
}

function onFilterChangeImmediate() {
  updateSummary()
}

function clearFilters() {
  searchQuery.value = ''
  companyFilter.value = ''
  currencyFilter.value = ''
  dateFrom.value = ''
  dateTo.value = ''
  hasLineItemsFilter.value = 'all'
  updateSummary()
}

// ── Export Trigger ──────────────────────────────────────────────────────────

async function triggerExport() {
  if (summary.value.total_records === 0 || isExporting.value) return

  isExporting.value = true
  exportError.value = ''
  exportSuccessMessage.value = ''

  try {
    let hasLineItemsParam: boolean | undefined = undefined
    if (selectedDataset.value === 'invoices') {
      if (hasLineItemsFilter.value === 'yes') hasLineItemsParam = true
      if (hasLineItemsFilter.value === 'no') hasLineItemsParam = false
    }

    const downloadedFile = await api.downloadExport(
      selectedDataset.value,
      selectedFormat.value,
      {
        search: searchQuery.value.trim() || undefined,
        company: companyFilter.value || undefined,
        currency: currencyFilter.value || undefined,
        date_from: dateFrom.value || undefined,
        date_to: dateTo.value || undefined,
        has_line_items: hasLineItemsParam,
      },
    )

    exportSuccessMessage.value = `Successfully exported ${downloadedFile}`
  } catch (err: any) {
    exportError.value = err.message || 'Export failed. Please try again.'
  } finally {
    isExporting.value = false
  }
}

// ── Lifecycle & Route Query Pre-population ──────────────────────────────────

onMounted(() => {
  loadFilterOptions()

  // Prepopulate from route query if passed from Data Explorer shortcut
  if (route.query.dataset === 'line-items' || route.query.dataset === 'invoices') {
    selectedDataset.value = route.query.dataset
  }
  if (typeof route.query.search === 'string') {
    searchQuery.value = route.query.search
  }
  if (typeof route.query.company === 'string') {
    companyFilter.value = route.query.company
  }
  if (typeof route.query.currency === 'string') {
    currencyFilter.value = route.query.currency
  }
  if (typeof route.query.date_from === 'string') {
    dateFrom.value = route.query.date_from
  }
  if (typeof route.query.date_to === 'string') {
    dateTo.value = route.query.date_to
  }

  updateSummary()
})

watch(selectedDataset, () => {
  updateSummary()
})
</script>

<template>
  <div class="zen-export-page">
    <div class="zen-container">
      <!-- ── Page Header ───────────────────────────────────────────── -->
      <header class="zen-page-header">
        <div class="header-left">
          <h1 class="page-title">Export Center</h1>
          <p class="page-subtitle">
            Export clean, standardized business records from DataBridge into portable CSV or Excel spreadsheets.
          </p>
        </div>
      </header>

      <!-- ── Main Workspace Grid ────────────────────────────────────── -->
      <div class="zen-export-grid">
        <!-- LEFT COLUMN: Workflow Options -->
        <div class="zen-config-column">
          <!-- Step 1: Choose Dataset -->
          <section class="zen-section-card" aria-labelledby="step-dataset-title">
            <div class="zen-step-indicator">
              <span class="step-num">1</span>
              <h2 id="step-dataset-title" class="section-title">Choose Dataset</h2>
            </div>

            <div class="dataset-selector-grid">
              <label
                class="dataset-card"
                :class="{ active: selectedDataset === 'invoices' }"
              >
                <input
                  v-model="selectedDataset"
                  type="radio"
                  value="invoices"
                  name="dataset"
                  class="sr-only"
                />
                <div class="dataset-card-header">
                  <FileText :size="20" class="card-icon" />
                  <span class="card-title">Invoices</span>
                </div>
                <p class="card-desc">
                  One row per invoice record with canonical headers, flattened custom fields, and provenance.
                </p>
              </label>

              <label
                class="dataset-card"
                :class="{ active: selectedDataset === 'line-items' }"
              >
                <input
                  v-model="selectedDataset"
                  type="radio"
                  value="line-items"
                  name="dataset"
                  class="sr-only"
                />
                <div class="dataset-card-header">
                  <Layers :size="20" class="card-icon" />
                  <span class="card-title">Line Items</span>
                </div>
                <p class="card-desc">
                  One row per product or service line item, flattened with parent invoice company and date.
                </p>
              </label>
            </div>
          </section>

          <!-- Step 2: Filter Records -->
          <section class="zen-section-card" aria-labelledby="step-filters-title">
            <div class="zen-step-indicator">
              <span class="step-num">2</span>
              <div class="step-title-wrap">
                <h2 id="step-filters-title" class="section-title">Filter Records</h2>
                <span class="step-subtitle">Optional filters to scope down your exported data.</span>
              </div>
            </div>

            <div class="filters-form-grid">
              <!-- Search Query -->
              <div class="form-group full-width">
                <label for="exp-search" class="form-label">Search Query</label>
                <div class="search-input-wrap">
                  <Search :size="16" class="input-icon" />
                  <input
                    id="exp-search"
                    v-model="searchQuery"
                    type="text"
                    class="form-input with-icon"
                    :placeholder="selectedDataset === 'invoices' ? 'Search company or invoice number...' : 'Search description, company, or invoice...'"
                    @input="onFilterInputDebounced"
                  />
                  <button
                    v-if="searchQuery"
                    type="button"
                    class="clear-input-btn"
                    @click="searchQuery = ''; onFilterInputDebounced()"
                    aria-label="Clear search"
                  >
                    <X :size="14" />
                  </button>
                </div>
              </div>

              <!-- Company Filter -->
              <div class="form-group">
                <label for="exp-company" class="form-label">Company</label>
                <select
                  id="exp-company"
                  v-model="companyFilter"
                  class="form-select"
                  @change="onFilterChangeImmediate"
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
              <div class="form-group">
                <label for="exp-currency" class="form-label">Currency</label>
                <select
                  id="exp-currency"
                  v-model="currencyFilter"
                  class="form-select"
                  @change="onFilterChangeImmediate"
                >
                  <option value="">All Currencies</option>
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
              <div class="form-group">
                <label for="exp-date-from" class="form-label">Invoice Date From</label>
                <input
                  id="exp-date-from"
                  v-model="dateFrom"
                  type="date"
                  class="form-input"
                  @change="onFilterChangeImmediate"
                />
              </div>

              <!-- Date Range To -->
              <div class="form-group">
                <label for="exp-date-to" class="form-label">Invoice Date To</label>
                <input
                  id="exp-date-to"
                  v-model="dateTo"
                  type="date"
                  class="form-input"
                  @change="onFilterChangeImmediate"
                />
              </div>

              <!-- Has Line Items (Invoices dataset only) -->
              <div v-if="selectedDataset === 'invoices'" class="form-group">
                <label for="exp-has-items" class="form-label">Line Items</label>
                <select
                  id="exp-has-items"
                  v-model="hasLineItemsFilter"
                  class="form-select"
                  @change="onFilterChangeImmediate"
                >
                  <option value="all">All Invoices</option>
                  <option value="yes">Invoices With Line Items</option>
                  <option value="no">Invoices Without Line Items</option>
                </select>
              </div>
            </div>

            <div v-if="hasFiltersApplied" class="filters-footer">
              <button
                type="button"
                class="btn-reset-filters"
                @click="clearFilters"
              >
                <X :size="14" />
                <span>Reset all filters</span>
              </button>
            </div>
          </section>

          <!-- Step 3: Choose Format -->
          <section class="zen-section-card" aria-labelledby="step-format-title">
            <div class="zen-step-indicator">
              <span class="step-num">3</span>
              <h2 id="step-format-title" class="section-title">Choose Format</h2>
            </div>

            <div class="format-selector-grid">
              <label
                class="format-card"
                :class="{ active: selectedFormat === 'xlsx' }"
              >
                <input
                  v-model="selectedFormat"
                  type="radio"
                  value="xlsx"
                  name="format"
                  class="sr-only"
                />
                <div class="format-header">
                  <FileSpreadsheet :size="22" class="format-icon text-excel" />
                  <div class="format-info">
                    <span class="format-title">Excel Spreadsheet (.xlsx)</span>
                    <span class="format-tag">Recommended</span>
                  </div>
                </div>
                <p class="format-desc">
                  Formatted spreadsheet with frozen header row, autofilter, and typed numeric/date cells for Excel and Google Sheets.
                </p>
              </label>

              <label
                class="format-card"
                :class="{ active: selectedFormat === 'csv' }"
              >
                <input
                  v-model="selectedFormat"
                  type="radio"
                  value="csv"
                  name="format"
                  class="sr-only"
                />
                <div class="format-header">
                  <Table :size="22" class="format-icon text-csv" />
                  <div class="format-info">
                    <span class="format-title">Comma-Separated Values (.csv)</span>
                  </div>
                </div>
                <p class="format-desc">
                  Universal UTF-8 encoded text format with formula injection protection, compatible with databases and analytical scripts.
                </p>
              </label>
            </div>
          </section>
        </div>

        <!-- RIGHT COLUMN: Export Summary & Download -->
        <div class="zen-summary-column">
          <div class="sticky-summary-wrap">
            <section class="zen-summary-card" aria-labelledby="summary-title">
              <div class="summary-header">
                <h2 id="summary-title" class="summary-title">Export Summary</h2>
                <button
                  type="button"
                  class="btn-refresh-summary"
                  @click="updateSummary"
                  title="Refresh record count"
                  :disabled="isLoadingSummary"
                  aria-label="Refresh count"
                >
                  <RefreshCw :size="14" :class="{ spin: isLoadingSummary }" />
                </button>
              </div>

              <!-- Loading State -->
              <div v-if="isLoadingSummary" class="summary-skeleton">
                <div class="skeleton-stat"></div>
                <div class="skeleton-stat"></div>
              </div>

              <!-- Error State -->
              <div v-else-if="summaryError" class="zen-alert zen-alert-error" role="alert">
                <AlertCircle :size="16" />
                <span class="alert-msg">{{ summaryError }}</span>
              </div>

              <!-- Metrics -->
              <div v-else class="summary-metrics">
                <div class="summary-stat-box">
                  <span class="stat-label">Matching Records</span>
                  <span class="stat-value font-mono">
                    {{ summary.total_records.toLocaleString() }}
                  </span>
                </div>

                <div class="summary-stat-box">
                  <span class="stat-label">Total Columns</span>
                  <span class="stat-value font-mono">
                    {{ summary.column_count }}
                  </span>
                </div>
              </div>

              <!-- Details breakdown -->
              <div class="summary-breakdown">
                <div class="breakdown-row">
                  <span class="row-label">Dataset:</span>
                  <span class="row-val font-medium text-capitalize">
                    {{ selectedDataset === 'invoices' ? 'Invoices' : 'Line Items' }}
                  </span>
                </div>

                <div class="breakdown-row">
                  <span class="row-label">Output Format:</span>
                  <span class="row-val font-mono">
                    {{ selectedFormat === 'xlsx' ? 'Excel (.xlsx)' : 'CSV (.csv)' }}
                  </span>
                </div>

                <div class="breakdown-row">
                  <span class="row-label">Active Filters:</span>
                  <span v-if="hasFiltersApplied" class="row-val text-accent">Active</span>
                  <span v-else class="row-val text-muted">All active records</span>
                </div>
              </div>

              <!-- Columns Disclosure -->
              <div v-if="summary.columns.length > 0" class="columns-disclosure">
                <button
                  type="button"
                  class="btn-toggle-columns"
                  @click="showColumnsList = !showColumnsList"
                  :aria-expanded="showColumnsList"
                >
                  <span>Included Columns ({{ summary.columns.length }})</span>
                  <ChevronUp v-if="showColumnsList" :size="15" />
                  <ChevronDown v-else :size="15" />
                </button>

                <div v-if="showColumnsList" class="columns-tags-wrap">
                  <span
                    v-for="col in summary.columns"
                    :key="col"
                    class="column-tag"
                  >
                    {{ col }}
                  </span>
                </div>
              </div>

              <!-- Error Alert -->
              <div v-if="exportError" class="zen-alert zen-alert-error" role="alert">
                <AlertCircle :size="16" />
                <div class="alert-content">
                  <span class="alert-msg">{{ exportError }}</span>
                </div>
              </div>

              <!-- Success Alert -->
              <div v-if="exportSuccessMessage" class="zen-alert zen-alert-success" role="status">
                <CheckCircle2 :size="16" />
                <span class="alert-msg">{{ exportSuccessMessage }}</span>
              </div>

              <!-- Main Action Button -->
              <button
                type="button"
                class="btn-export-primary"
                :disabled="summary.total_records === 0 || isExporting || isLoadingSummary"
                @click="triggerExport"
              >
                <Loader2 v-if="isExporting" :size="18" class="spin" />
                <Download v-else :size="18" />
                <span v-if="isExporting">Preparing export...</span>
                <span v-else-if="summary.total_records === 0">No records to export</span>
                <span v-else>
                  Export {{ summary.total_records.toLocaleString() }} {{ selectedDataset === 'invoices' ? 'invoices' : 'items' }} (.{{ selectedFormat }})
                </span>
              </button>

              <p class="export-hint">
                Exports reflect standardized database records excluding soft-deleted imports.
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.zen-export-page {
  min-height: calc(100vh - 4.25rem);
  background: var(--bg-app);
  color: var(--text-primary);
  padding: 2.25rem 0 3.5rem;
}

.zen-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.zen-page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
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
  max-width: 600px;
}

/* Main Grid Layout */
.zen-export-grid {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 1.75rem;
  align-items: start;
}

@media (max-width: 960px) {
  .zen-export-grid {
    grid-template-columns: 1fr;
  }
}

.zen-config-column {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.zen-section-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.zen-step-indicator {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.step-num {
  width: 1.65rem;
  height: 1.65rem;
  border-radius: var(--radius-full);
  background: var(--accent-brand-subtle);
  color: var(--accent-brand);
  font-weight: 700;
  font-size: 0.82rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.section-title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
  color: var(--text-primary);
}

.step-subtitle {
  font-size: 0.78rem;
  color: var(--text-muted);
}

/* Dataset Selector */
.dataset-selector-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .dataset-selector-grid {
    grid-template-columns: 1fr;
  }
}

.dataset-card {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1.15rem;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.dataset-card:hover {
  border-color: var(--border-medium);
  background: var(--bg-card-hover);
}

.dataset-card.active {
  border-color: var(--accent-brand);
  background: rgba(99, 102, 241, 0.08);
  box-shadow: 0 0 12px rgba(99, 102, 241, 0.15);
}

.dataset-card-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.card-icon {
  color: var(--accent-brand);
}

.card-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-desc {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.45;
}

/* Filters Form */
.filters-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .filters-form-grid {
    grid-template-columns: 1fr;
  }
}

.full-width {
  grid-column: 1 / -1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.form-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.form-input, .form-select {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0.5rem 0.75rem;
  font-size: 0.85rem;
  color: var(--text-primary);
  outline: none;
  transition: all var(--transition-fast);
}

.form-input:focus, .form-select:focus {
  border-color: var(--accent-brand);
  background: var(--bg-card);
}

.search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 0.75rem;
  color: var(--text-muted);
  pointer-events: none;
}

.form-input.with-icon {
  padding-left: 2.25rem;
  width: 100%;
}

.clear-input-btn {
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

.clear-input-btn:hover {
  color: var(--text-primary);
}

.filters-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-subtle);
}

.btn-reset-filters {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
}

.btn-reset-filters:hover {
  color: var(--status-error);
}

/* Format Selector */
.format-selector-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 640px) {
  .format-selector-grid {
    grid-template-columns: 1fr;
  }
}

.format-card {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1.15rem;
  cursor: pointer;
  transition: all var(--transition-fast);
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.format-card:hover {
  border-color: var(--border-medium);
}

.format-card.active {
  border-color: var(--accent-brand);
  background: rgba(99, 102, 241, 0.08);
}

.format-header {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.format-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.format-title {
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-primary);
}

.format-tag {
  font-size: 0.68rem;
  font-weight: 600;
  background: var(--accent-brand-subtle);
  color: var(--accent-brand);
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-full);
}

.format-desc {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.text-excel {
  color: #10b981;
}

.text-csv {
  color: #38bdf8;
}

/* Sticky Summary Card */
.sticky-summary-wrap {
  position: sticky;
  top: 5.5rem;
}

.zen-summary-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  box-shadow: var(--shadow-sm);
}

.summary-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.summary-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text-primary);
}

.btn-refresh-summary {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  padding: 0.35rem;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  cursor: pointer;
}

.btn-refresh-summary:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-medium);
}

.summary-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.summary-stat-box {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  padding: 0.85rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.stat-label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--text-muted);
}

.stat-value {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--accent-brand);
}

.summary-breakdown {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.85rem 0;
  border-top: 1px solid var(--border-subtle);
  border-bottom: 1px solid var(--border-subtle);
}

.breakdown-row {
  display: flex;
  justify-content: space-between;
  font-size: 0.82rem;
}

.row-label {
  color: var(--text-muted);
}

.row-val {
  color: var(--text-primary);
}

/* Columns List */
.columns-disclosure {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.btn-toggle-columns {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.78rem;
  font-weight: 600;
  padding: 0;
  cursor: pointer;
}

.btn-toggle-columns:hover {
  color: var(--text-primary);
}

.columns-tags-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  max-height: 140px;
  overflow-y: auto;
  padding: 0.5rem;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}

.column-tag {
  font-size: 0.72rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  padding: 0.15rem 0.45rem;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
}

/* Export Button */
.btn-export-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: var(--accent-brand);
  color: #ffffff;
  border: none;
  padding: 0.75rem 1.25rem;
  border-radius: var(--radius-sm);
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.btn-export-primary:hover:not(:disabled) {
  opacity: 0.92;
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.35);
}

.btn-export-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

.export-hint {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.4;
}

/* Alerts */
.zen-alert {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
}

.zen-alert-error {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--status-error);
}

.zen-alert-success {
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: var(--status-success);
}

.alert-msg {
  word-break: break-word;
}

/* Skeleton Loading */
.summary-skeleton {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.skeleton-stat {
  height: 60px;
  background: var(--bg-subtle);
  border-radius: var(--radius-sm);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 0.8; }
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

.text-capitalize {
  text-transform: capitalize;
}

.text-accent {
  color: var(--accent-brand);
}

.text-muted {
  color: var(--text-muted);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  border: 0;
}
</style>
