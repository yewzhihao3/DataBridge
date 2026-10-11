<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Info,
  Receipt,
  RefreshCw,
  ShieldCheck,
} from 'lucide-vue-next'
import DirectionTrendChart from '@/components/dashboard/DirectionTrendChart.vue'
import { api } from '@/services/api'
import type { AnalyticsFilterOptions, DashboardResponse } from '@/types/api'

const route = useRoute()
const router = useRouter()
const options = ref<AnalyticsFilterOptions | null>(null)
const data = ref<DashboardResponse | null>(null)
const currency = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const company = ref('')
const loading = ref(true)
const error = ref('')
const invalidRange = computed(() => Boolean(dateFrom.value && dateTo.value && dateFrom.value > dateTo.value))
let requestId = 0
let ready = false

function readQuery() {
  const text = (key: string) => typeof route.query[key] === 'string' ? String(route.query[key]) : ''
  currency.value = 'currency' in route.query ? text('currency').trim().toUpperCase() : options.value?.currencies[0] ?? ''
  dateFrom.value = text('date_from')
  dateTo.value = text('date_to')
  company.value = text('company')
}

async function load() {
  const id = ++requestId
  error.value = ''
  if (invalidRange.value) { loading.value = false; return }
  loading.value = true
  try {
    const result = await api.getDashboard({
      currency: currency.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
      company: company.value || undefined,
    })
    if (id === requestId) data.value = result
  } catch {
    if (id === requestId) error.value = 'Unable to load analytics.'
  } finally {
    if (id === requestId) loading.value = false
  }
}

async function applyFilters() {
  const query: Record<string, string> = { currency: currency.value }
  if (dateFrom.value) query.date_from = dateFrom.value
  if (dateTo.value) query.date_to = dateTo.value
  if (company.value) query.company = company.value
  if (router.resolve({ path: '/dashboard', query }).fullPath === route.fullPath) await load()
  else await router.replace({ path: '/dashboard', query })
}

async function initialize() {
  loading.value = true
  error.value = ''
  try {
    options.value = await api.getAnalyticsFilterOptions()
    readQuery()
    ready = true
    await applyFilters()
  } catch {
    loading.value = false
    error.value = 'Unable to load analytics.'
  }
}

function reset() {
  currency.value = options.value?.currencies[0] ?? ''
  dateFrom.value = ''
  dateTo.value = ''
  company.value = ''
  applyFilters()
}

watch(() => route.fullPath, () => { if (ready) { readQuery(); load() } })
onMounted(initialize)
onBeforeUnmount(() => { requestId++; ready = false })

const activeCurrency = computed(() => data.value?.filters.currency ?? '')

function formatDirectionKpi(options: {
  type: 'invoice' | 'receipt'
  value: string | null | undefined
  count: number
  withTotal: number
}): string {
  // 4. Currency not selected
  if (!data.value?.monetary_values_available || !activeCurrency.value) {
    return 'Select a currency to view totals'
  }

  // 3. No records exist in workspace
  if (options.type === 'receipt' && (data.value?.financial_summary?.total_workspace_receipts ?? 0) === 0) {
    return 'No receipts yet'
  }
  if (options.type === 'invoice' && (data.value?.financial_summary?.total_workspace_invoices ?? 0) === 0) {
    return 'No invoices yet'
  }

  // 1. No matching records for the current filter
  if (options.count === 0) {
    if (options.type === 'receipt') {
      return `No receipts in ${activeCurrency.value}`
    } else {
      return `No invoices in ${activeCurrency.value}`
    }
  }

  // 2. Matching records exist but missing monetary values
  if (options.value === null || options.value === undefined || options.withTotal === 0) {
    return 'Amount unavailable'
  }

  return `${activeCurrency.value} ${Number(options.value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function isKpiNonMonetary(options: {
  type: 'invoice' | 'receipt'
  value: string | null | undefined
  count: number
  withTotal: number
}): boolean {
  if (!data.value?.monetary_values_available || !activeCurrency.value) return true
  if (options.type === 'receipt' && (data.value?.financial_summary?.total_workspace_receipts ?? 0) === 0) return true
  if (options.type === 'invoice' && (data.value?.financial_summary?.total_workspace_invoices ?? 0) === 0) return true
  if (options.count === 0) return true
  if (options.value === null || options.value === undefined || options.withTotal === 0) return true
  return false
}

const money = (value: string | null | undefined) => {
  if (value === null || value === undefined) return '—'
  return `${activeCurrency.value} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const invoiceTrendPoints = computed(() => {
  return (data.value?.financial_invoice_trends ?? []).map(t => ({
    period: t.period,
    seriesA_count: t.sales_count,
    seriesA_value: t.sales_value,
    seriesB_count: t.purchase_count,
    seriesB_value: t.purchase_value,
    seriesC_count: t.unclassified_count,
    seriesC_value: t.unclassified_value,
    total_count: t.total_count,
  }))
})

const receiptTrendPoints = computed(() => {
  return (data.value?.financial_receipt_trends ?? []).map(t => ({
    period: t.period,
    seriesA_count: t.income_count,
    seriesA_value: t.income_value,
    seriesB_count: t.expense_count,
    seriesB_value: t.expense_value,
    seriesC_count: t.unclassified_count,
    seriesC_value: t.unclassified_value,
    total_count: t.total_count,
  }))
})

const unclassifiedInvoiceCount = computed(() => data.value?.financial_summary?.unclassified_invoice_count ?? 0)
const unclassifiedReceiptCount = computed(() => data.value?.financial_summary?.unclassified_receipt_count ?? 0)
const hasUnclassified = computed(() => unclassifiedInvoiceCount.value > 0 || unclassifiedReceiptCount.value > 0)
</script>

<template>
  <div class="dashboard">
    <!-- Header -->
    <header class="page-heading">
      <div>
        <div class="title-row">
          <h1>Financial Dashboard</h1>
          <span class="badge-zen">M16.4 Direction-Aware</span>
        </div>
        <p>Comprehensive directional analytics for invoices and receipts without cross-currency assumptions.</p>
      </div>
      <button class="quiet-button" :disabled="loading" @click="initialize">
        <RefreshCw :size="15" /> Refresh
      </button>
    </header>

    <!-- Filters -->
    <form class="filters" @submit.prevent="applyFilters">
      <label>
        Currency
        <select v-model="currency" :disabled="!options" @change="applyFilters">
          <option v-for="code in options?.currencies ?? []" :key="code" :value="code">{{ code }}</option>
          <option v-if="options?.has_unspecified_currency || !options?.currencies.length || currency === ''" value="">Unspecified</option>
          <option v-if="currency && options && !options.currencies.includes(currency)" :value="currency">{{ currency }} (no records)</option>
        </select>
      </label>
      <label>
        Date From
        <input v-model="dateFrom" type="date" :aria-invalid="invalidRange" @change="applyFilters" />
      </label>
      <label>
        Date To
        <input v-model="dateTo" type="date" :aria-invalid="invalidRange" @change="applyFilters" />
      </label>
      <label class="company-filter">
        Company / Merchant
        <input
          v-model="company"
          type="search"
          placeholder="Any company or merchant"
          list="dashboard-companies"
          @change="applyFilters"
        />
        <datalist id="dashboard-companies">
          <option v-for="name in options?.companies ?? []" :key="name" :value="name" />
        </datalist>
      </label>
      <button class="quiet-button reset" type="button" @click="reset">Reset Filters</button>
    </form>

    <p class="filter-note">
      All monetary metrics use the selected currency (no auto-conversion). Invoices are filtered by invoice date; receipts by transaction date.
    </p>

    <!-- Errors / Validation -->
    <div v-if="invalidRange" class="error-banner" role="alert">
      <AlertCircle :size="18" /> Date From must be on or before Date To.
    </div>
    <div v-else-if="error" class="error-banner" role="alert">
      <AlertCircle :size="18" /> {{ error }}
      <button class="quiet-button retry-btn" @click="options ? load() : initialize()">Retry</button>
    </div>

    <!-- Main Content -->
    <div v-else :aria-busy="loading">
      <p class="load-status" role="status">
        {{ loading ? 'Updating analytics…' : 'Based on active, verified financial records' }}
      </p>

      <div v-if="!data" class="skeleton-grid" aria-hidden="true">
        <div v-for="n in 4" :key="n" class="skeleton" />
      </div>

      <div v-else :class="{ updating: loading }">
        <!-- Notice for Unspecified Currency -->
        <div v-if="!data.monetary_values_available" class="notice-banner">
          <Info :size="18" />
          <div>
            <strong>Currency is unspecified.</strong> Document counts are displayed; monetary values are strictly withheld to protect against blending multiple currencies. Select a currency above to view monetary figures.
          </div>
        </div>

        <!-- Section A: Financial Overview (Direction-Aware KPI Cards) -->
        <section class="dashboard-block" aria-labelledby="heading-financial-overview">
          <div class="block-header">
            <div>
              <h2 id="heading-financial-overview">Financial Overview</h2>
              <p class="section-sub">Showing financial activity in {{ activeCurrency || 'unspecified currency' }}.</p>
            </div>
            <div class="integrity-chip" title="Direction classifications keep billing and receipts separated.">
              <ShieldCheck :size="14" /> Financial Integrity Guardrails Active
            </div>
          </div>

          <div class="kpi-grid">
            <!-- 1. Sales Invoiced -->
            <div class="kpi-card card-sales">
              <div class="kpi-top">
                <span class="kpi-title">Sales Invoiced</span>
                <span class="direction-tag tag-sales">Sales</span>
              </div>
              <strong
                class="money"
                :class="{ 'money-muted': isKpiNonMonetary({
                  type: 'invoice',
                  value: data.financial_summary?.sales_invoiced_value,
                  count: data.financial_summary?.sales_invoice_count ?? 0,
                  withTotal: data.financial_summary?.sales_invoices_with_total ?? 0,
                }) }"
              >
                {{ formatDirectionKpi({
                  type: 'invoice',
                  value: data.financial_summary?.sales_invoiced_value,
                  count: data.financial_summary?.sales_invoice_count ?? 0,
                  withTotal: data.financial_summary?.sales_invoices_with_total ?? 0,
                }) }}
              </strong>
              <div class="kpi-meta">
                <span>{{ data.financial_summary?.sales_invoices_with_total ?? 0 }} of {{ data.financial_summary?.sales_invoice_count ?? 0 }} sales invoices</span>
              </div>
              <p class="kpi-hint">Amount billed to customers</p>
            </div>

            <!-- 2. Purchases Invoiced -->
            <div class="kpi-card card-purchase">
              <div class="kpi-top">
                <span class="kpi-title">Purchases Invoiced</span>
                <span class="direction-tag tag-purchase">Purchase</span>
              </div>
              <strong
                class="money"
                :class="{ 'money-muted': isKpiNonMonetary({
                  type: 'invoice',
                  value: data.financial_summary?.purchases_invoiced_value,
                  count: data.financial_summary?.purchase_invoice_count ?? 0,
                  withTotal: data.financial_summary?.purchase_invoices_with_total ?? 0,
                }) }"
              >
                {{ formatDirectionKpi({
                  type: 'invoice',
                  value: data.financial_summary?.purchases_invoiced_value,
                  count: data.financial_summary?.purchase_invoice_count ?? 0,
                  withTotal: data.financial_summary?.purchase_invoices_with_total ?? 0,
                }) }}
              </strong>
              <div class="kpi-meta">
                <span>{{ data.financial_summary?.purchase_invoices_with_total ?? 0 }} of {{ data.financial_summary?.purchase_invoice_count ?? 0 }} purchase invoices</span>
              </div>
              <p class="kpi-hint">Amount billed by suppliers</p>
            </div>

            <!-- 3. Income Receipts -->
            <div class="kpi-card card-income">
              <div class="kpi-top">
                <span class="kpi-title">Income Receipts</span>
                <span class="direction-tag tag-income">Income</span>
              </div>
              <strong
                class="money"
                :class="{ 'money-muted': isKpiNonMonetary({
                  type: 'receipt',
                  value: data.financial_summary?.income_receipts_value,
                  count: data.financial_summary?.income_receipt_count ?? 0,
                  withTotal: data.financial_summary?.income_receipts_with_total ?? 0,
                }) }"
              >
                {{ formatDirectionKpi({
                  type: 'receipt',
                  value: data.financial_summary?.income_receipts_value,
                  count: data.financial_summary?.income_receipt_count ?? 0,
                  withTotal: data.financial_summary?.income_receipts_with_total ?? 0,
                }) }}
              </strong>
              <div class="kpi-meta">
                <span>{{ data.financial_summary?.income_receipts_with_total ?? 0 }} of {{ data.financial_summary?.income_receipt_count ?? 0 }} income receipts</span>
              </div>
              <p class="kpi-hint">Receipts classified as income</p>
            </div>

            <!-- 4. Expense Receipts -->
            <div class="kpi-card card-expense">
              <div class="kpi-top">
                <span class="kpi-title">Expense Receipts</span>
                <span class="direction-tag tag-expense">Expense</span>
              </div>
              <strong
                class="money"
                :class="{ 'money-muted': isKpiNonMonetary({
                  type: 'receipt',
                  value: data.financial_summary?.expense_receipts_value,
                  count: data.financial_summary?.expense_receipt_count ?? 0,
                  withTotal: data.financial_summary?.expense_receipts_with_total ?? 0,
                }) }"
              >
                {{ formatDirectionKpi({
                  type: 'receipt',
                  value: data.financial_summary?.expense_receipts_value,
                  count: data.financial_summary?.expense_receipt_count ?? 0,
                  withTotal: data.financial_summary?.expense_receipts_with_total ?? 0,
                }) }}
              </strong>
              <div class="kpi-meta">
                <span>{{ data.financial_summary?.expense_receipts_with_total ?? 0 }} of {{ data.financial_summary?.expense_receipt_count ?? 0 }} expense receipts</span>
              </div>
              <p class="kpi-hint">Receipts classified as expenses</p>
            </div>
          </div>
        </section>

        <!-- Section B: Unclassified Records Callout -->
        <section class="dashboard-block" aria-labelledby="heading-unclassified">
          <div v-if="hasUnclassified" class="unclassified-container">
            <div class="unclassified-header">
              <div class="unclassified-title-group">
                <AlertTriangle :size="18" class="warning-icon" />
                <h3 id="heading-unclassified">Unclassified Financial Records</h3>
              </div>
              <span class="unclassified-badge">
                {{ unclassifiedInvoiceCount + unclassifiedReceiptCount }} records require review
              </span>
            </div>
            <p class="unclassified-desc">
              These documents are currently unclassified and not assigned to sales, purchase, income, or expense. Review them in the Data Explorer to ensure complete financial visibility.
            </p>

            <div class="unclassified-cards">
              <!-- Invoices -->
              <div class="unclassified-card">
                <div>
                  <div class="doc-type-label"><FileText :size="14" /> Unclassified Invoices</div>
                  <strong>{{ unclassifiedInvoiceCount }} records</strong>
                  <span class="unclass-value">{{ money(data.financial_summary?.unclassified_invoice_value) }}</span>
                </div>
                <RouterLink
                  to="/explorer?type=invoices&direction=unclassified"
                  class="explorer-link"
                >
                  Review Invoices in Explorer <ArrowRight :size="14" />
                </RouterLink>
              </div>

              <!-- Receipts -->
              <div class="unclassified-card">
                <div>
                  <div class="doc-type-label"><Receipt :size="14" /> Unclassified Receipts</div>
                  <strong>{{ unclassifiedReceiptCount }} records</strong>
                  <span class="unclass-value">{{ money(data.financial_summary?.unclassified_receipts_value) }}</span>
                </div>
                <RouterLink
                  to="/explorer?type=receipts&direction=unclassified"
                  class="explorer-link"
                >
                  Review Receipts in Explorer <ArrowRight :size="14" />
                </RouterLink>
              </div>
            </div>
          </div>
          <div v-else class="classified-complete-bar">
            <CheckCircle2 :size="16" class="success-icon" />
            <span>All active documents in this workspace have an assigned financial direction.</span>
          </div>
        </section>

        <!-- Section C: Financial Activity Trends -->
        <section class="dashboard-block" aria-labelledby="heading-trends">
          <div class="block-header">
            <div>
              <h2 id="heading-trends">Financial Activity Trends</h2>
              <p class="section-sub">Monthly activity partitioned strictly by document direction.</p>
            </div>
          </div>

          <div class="trends-stack">
            <!-- Chart 1: Invoices (Sales vs Purchases) -->
            <div class="trend-card">
              <div class="trend-card-heading">
                <div>
                  <h3>Monthly Invoices: Sales vs Purchases</h3>
                  <p>Invoiced billing activity in {{ activeCurrency || 'unspecified currency' }} (undated invoices excluded)</p>
                </div>
                <span class="time-grain">Monthly · Invoices</span>
              </div>

              <DirectionTrendChart
                :periods="invoiceTrendPoints"
                :currency="activeCurrency"
                series-a-label="Sales Invoiced"
                series-a-color="#10b981"
                series-b-label="Purchases Invoiced"
                series-b-color="#f59e0b"
                series-c-label="Unclassified Invoices"
                series-c-color="#64748b"
                :empty-message="`No invoice activity in ${activeCurrency || 'selected currency'} for this period.`"
                :notice="`${data.summary.invoices_without_date} undated invoices are excluded from monthly charts.`"
              />
            </div>

            <!-- Chart 2: Receipts (Income vs Expense) -->
            <div class="trend-card">
              <div class="trend-card-heading">
                <div>
                  <h3>Monthly Receipts: Income vs Expense</h3>
                  <p>Documented receipt activity in {{ activeCurrency || 'unspecified currency' }} (undated receipts excluded)</p>
                </div>
                <span class="time-grain">Monthly · Receipts</span>
              </div>

              <DirectionTrendChart
                :periods="receiptTrendPoints"
                :currency="activeCurrency"
                series-a-label="Income Receipts"
                series-a-color="#0ea5e9"
                series-b-label="Expense Receipts"
                series-b-color="#f43f5e"
                series-c-label="Unclassified Receipts"
                series-c-color="#64748b"
                :empty-message="`No receipt activity in ${activeCurrency || 'selected currency'} for this period.`"
                :notice="`${data.financial_summary?.receipts_without_date ?? 0} undated receipts are excluded from monthly charts.`"
              />
            </div>
          </div>
        </section>

        <!-- Section D: Operational Insights & Document Volume -->
        <section class="dashboard-block" aria-labelledby="heading-operational">
          <div class="block-header">
            <div>
              <h2 id="heading-operational">Operational Volumes & Rankings</h2>
              <p class="section-sub">Core ingestion metrics, company distributions, and item volumes.</p>
            </div>
          </div>

          <!-- Secondary operational cards -->
          <div class="kpis-secondary">
            <div class="op-card">
              <h4>All Invoices</h4>
              <strong>{{ data.summary.invoice_count.toLocaleString() }}</strong>
              <p>{{ data.summary.invoices_with_total }} with total · {{ data.summary.invoices_without_date }} undated</p>
            </div>
            <div class="op-card">
              <h4>All Receipts</h4>
              <strong>{{ (data.financial_summary?.receipt_count ?? 0).toLocaleString() }}</strong>
              <p>{{ data.financial_summary?.receipts_with_total ?? 0 }} with total · {{ data.financial_summary?.receipts_without_date ?? 0 }} undated</p>
            </div>
            <div class="op-card">
              <h4>Extracted Line Items</h4>
              <strong>{{ data.summary.line_item_count.toLocaleString() }}</strong>
              <p>{{ data.summary.line_items_with_amount }} with explicit amounts</p>
            </div>
            <div class="op-card">
              <h4>Average Invoice Total</h4>
              <strong class="money">{{ money(data.summary.average_invoice_value) }}</strong>
              <p>Across all invoices with totals</p>
            </div>
          </div>

          <!-- Rankings -->
          <div class="rankings-grid">
            <!-- Company ranking -->
            <div class="ranking-panel">
              <div class="panel-head">
                <h4>Invoice Value by Company</h4>
                <span>Top 10</span>
              </div>
              <ol v-if="data.company_values.length" class="ranking-list">
                <li v-for="(entry, i) in data.company_values" :key="entry.company_name ?? i">
                  <span class="rank">{{ i + 1 }}</span>
                  <div class="rank-details">
                    <span class="name">{{ entry.company_name || 'Company not specified' }}</span>
                    <small>{{ entry.invoice_count }} invoices · {{ entry.invoices_with_total }} with totals</small>
                  </div>
                  <strong class="money">{{ money(entry.invoice_value) }}</strong>
                </li>
              </ol>
              <p v-else class="empty-panel">No company invoice value available in this currency.</p>
            </div>

            <!-- Line item ranking -->
            <div class="ranking-panel">
              <div class="panel-head">
                <h4>Top Line Items by Amount</h4>
                <span>Top 10</span>
              </div>
              <ol v-if="data.line_item_values.length" class="ranking-list">
                <li v-for="(entry, i) in data.line_item_values" :key="entry.description ?? i">
                  <span class="rank">{{ i + 1 }}</span>
                  <div class="rank-details">
                    <span class="name">{{ entry.description || 'Description not specified' }}</span>
                    <small>{{ entry.line_item_count }} rows · {{ entry.line_items_with_amount }} with amounts</small>
                  </div>
                  <strong class="money">{{ money(entry.amount) }}</strong>
                </li>
              </ol>
              <p v-else class="empty-panel">No line-item amount data available.</p>
            </div>
          </div>
        </section>

        <!-- Financial Integrity Statement Footer -->
        <footer class="integrity-footer">
          <ShieldCheck :size="16" />
          <p>
            <strong>Financial Integrity Guardrails:</strong> Sales and purchase invoices represent billing transactions and do not track payment settlement. Receipts represent recorded retail or counter documents and are not bank-reconciled statements. Multi-currency aggregation and combined net figures are strictly withheld.
          </p>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1440px;
  margin: 0 auto;
  padding: 2.5rem 2rem 5rem;
  color: var(--text-primary);
}

.page-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 2rem;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

h1 {
  font-size: 1.85rem;
  letter-spacing: -0.035em;
  margin: 0;
  font-weight: 700;
}

.badge-zen {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  font-size: 0.72rem;
  font-weight: 600;
  border-radius: 9999px;
  background: var(--bg-subtle);
  border: 1px solid var(--border-medium);
  color: var(--text-secondary);
}

.page-heading p {
  color: var(--text-secondary);
  font-size: 0.85rem;
  margin: 0.4rem 0 0;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 1rem;
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

input, select {
  min-height: 40px;
  padding: 0.55rem 0.75rem;
  color: var(--text-primary);
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: 6px;
  color-scheme: dark;
  font: inherit;
}

input:focus, select:focus, button:focus-visible {
  outline: 2px solid var(--accent-brand);
  outline-offset: 2px;
}

.company-filter {
  flex: 1;
  min-width: 180px;
  max-width: 320px;
}

.quiet-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-height: 40px;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  padding: 0.5rem 0.85rem;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 0.8rem;
  font-weight: 500;
  transition: all 0.15s ease;
}

.quiet-button:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}

.filter-note {
  margin: 0.8rem 0 1.5rem;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.load-status {
  min-height: 1.3rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  color: var(--status-error);
  background: var(--status-error-bg);
  padding: 1rem 1.25rem;
  border-radius: 6px;
  margin-bottom: 1.5rem;
  font-size: 0.85rem;
}

.notice-banner {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  padding: 1rem 1.25rem;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  font-size: 0.84rem;
  line-height: 1.5;
  margin-bottom: 2rem;
}

.notice-banner strong {
  color: var(--text-primary);
}

.dashboard-block {
  margin-bottom: 2.75rem;
}

.block-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.block-header h2 {
  font-size: 1.25rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  margin: 0;
}

.section-sub {
  color: var(--text-secondary);
  font-size: 0.8rem;
  margin: 0.25rem 0 0;
}

.integrity-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.35rem 0.7rem;
  border-radius: 9999px;
  border: 1px solid var(--border-subtle);
}

/* Section A: KPI Grid */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.kpi-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 1.35rem 1.25rem;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.kpi-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
}

.card-sales::before { background: #10b981; }
.card-purchase::before { background: #f59e0b; }
.card-income::before { background: #0ea5e9; }
.card-expense::before { background: #f43f5e; }

.kpi-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.85rem;
}

.kpi-title {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.direction-tag {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.15rem 0.5rem;
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.tag-sales { background: rgba(16, 185, 129, 0.12); color: #10b981; }
.tag-purchase { background: rgba(245, 158, 11, 0.12); color: #f59e0b; }
.tag-income { background: rgba(14, 165, 233, 0.12); color: #0ea5e9; }
.tag-expense { background: rgba(244, 63, 94, 0.12); color: #f43f5e; }

.kpi-card strong.money {
  font-size: clamp(1.2rem, 1.8vw, 1.7rem);
  font-weight: 700;
  letter-spacing: -0.025em;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  margin-bottom: 0.4rem;
}

.kpi-card strong.money.money-muted {
  font-size: clamp(0.95rem, 1.2vw, 1.15rem);
  font-weight: 500;
  color: var(--text-muted);
}

.kpi-meta {
  font-size: 0.74rem;
  color: var(--text-secondary);
}

.kpi-hint {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin: 0.6rem 0 0;
  padding-top: 0.5rem;
  border-top: 1px solid var(--border-subtle);
}

/* Section B: Unclassified Callout */
.unclassified-container {
  background: var(--bg-card);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 8px;
  padding: 1.5rem;
}

.unclassified-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.4rem;
}

.unclassified-title-group {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.warning-icon {
  color: #f59e0b;
}

.unclassified-header h3 {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
}

.unclassified-badge {
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.2rem 0.6rem;
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
  border-radius: 9999px;
}

.unclassified-desc {
  font-size: 0.8rem;
  color: var(--text-secondary);
  margin: 0 0 1.25rem;
  max-width: 800px;
}

.unclassified-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

.unclassified-card {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 1rem 1.25rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.doc-type-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.74rem;
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.unclassified-card strong {
  display: block;
  font-size: 1.15rem;
  font-weight: 600;
}

.unclass-value {
  font-size: 0.8rem;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.explorer-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--accent-brand);
  text-decoration: none;
  padding: 0.5rem 0.85rem;
  border-radius: 6px;
  background: rgba(14, 165, 233, 0.08);
  border: 1px solid rgba(14, 165, 233, 0.2);
  white-space: nowrap;
  transition: all 0.15s ease;
}

.explorer-link:hover {
  background: rgba(14, 165, 233, 0.18);
  border-color: var(--accent-brand);
}

.classified-complete-bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.85rem 1.25rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.success-icon {
  color: #10b981;
}

/* Section C: Trends Stack */
.trends-stack {
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}

.trend-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 1.5rem;
}

.trend-card-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1.25rem;
  flex-wrap: wrap;
}

.trend-card-heading h3 {
  font-size: 1.05rem;
  font-weight: 600;
  margin: 0;
}

.trend-card-heading p {
  font-size: 0.78rem;
  color: var(--text-secondary);
  margin: 0.25rem 0 0;
}

.time-grain {
  font-size: 0.72rem;
  color: var(--text-muted);
}

/* Section D: Operational & Rankings */
.kpis-secondary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.op-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 1rem 1.15rem;
}

.op-card h4 {
  font-size: 0.76rem;
  color: var(--text-secondary);
  font-weight: 500;
  margin: 0 0 0.5rem;
}

.op-card strong {
  font-size: 1.25rem;
  font-weight: 600;
  display: block;
  margin-bottom: 0.35rem;
  font-variant-numeric: tabular-nums;
}

.op-card p {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin: 0;
}

.rankings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2rem;
}

.ranking-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 1.5rem;
}

.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1.25rem;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 0.75rem;
}

.panel-head h4 {
  font-size: 0.95rem;
  font-weight: 600;
  margin: 0;
}

.panel-head span {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.ranking-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.ranking-list li {
  display: grid;
  grid-template-columns: 1.5rem minmax(0, 1fr) auto;
  align-items: start;
  gap: 0.75rem;
  padding: 0.85rem 0;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 0.82rem;
}

.rank {
  color: var(--text-muted);
  font-size: 0.74rem;
  font-weight: 600;
  padding-top: 0.1rem;
}

.rank-details .name {
  overflow-wrap: anywhere;
  font-weight: 500;
}

.rank-details small {
  display: block;
  color: var(--text-muted);
  font-size: 0.7rem;
  margin-top: 0.25rem;
}

.empty-panel {
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}

/* Footer statement */
.integrity-footer {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1.25rem 1.5rem;
  border-radius: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  font-size: 0.76rem;
  color: var(--text-muted);
  line-height: 1.6;
}

.integrity-footer strong {
  color: var(--text-secondary);
}

/* Skeletons */
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
  margin-bottom: 2.5rem;
}

.skeleton {
  min-height: 130px;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  opacity: 0.6;
}

.updating {
  opacity: 0.5;
  pointer-events: none;
}

/* Responsive */
@media (max-width: 1080px) {
  .kpi-grid,
  .kpis-secondary,
  .skeleton-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .rankings-grid {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }
}

@media (max-width: 720px) {
  .unclassified-cards {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 560px) {
  .dashboard {
    padding: 1.5rem 1rem 3rem;
  }
  .filters > label {
    flex: 1 1 100%;
    min-width: 0;
    max-width: none;
  }
  .company-filter {
    max-width: none;
  }
  .kpi-grid,
  .kpis-secondary,
  .skeleton-grid {
    grid-template-columns: 1fr;
  }
  .unclassified-card {
    flex-direction: column;
    align-items: flex-start;
  }
  .explorer-link {
    width: 100%;
    justify-content: center;
  }
}
</style>
