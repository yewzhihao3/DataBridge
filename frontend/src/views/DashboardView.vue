<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertCircle, RefreshCw } from 'lucide-vue-next'
import InvoiceTrend from '@/components/dashboard/InvoiceTrend.vue'
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
    const result = await api.getDashboard({ currency: currency.value, date_from: dateFrom.value || undefined, date_to: dateTo.value || undefined, company: company.value || undefined })
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
  // The route watcher handles navigation; unchanged filters still support refresh.
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
const hasValue = computed(() => data.value?.invoice_value_over_time.some(p => p.invoice_value !== null) ?? false)
const activeCurrency = computed(() => data.value?.filters.currency ?? '')
const money = (value: string | null) => value === null ? 'No known value' : `${activeCurrency.value} ${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
</script>

<template>
  <div class="dashboard">
    <header class="page-heading">
      <div><h1>Dashboard</h1><p>Understand your standardized records.</p></div>
      <button class="quiet-button" :disabled="loading" @click="initialize"><RefreshCw :size="15" /> Refresh</button>
    </header>

    <form class="filters" @submit.prevent="applyFilters">
      <label>Currency<select v-model="currency" :disabled="!options" @change="applyFilters">
        <option v-for="code in options?.currencies ?? []" :key="code" :value="code">{{ code }}</option>
        <option v-if="options?.has_unspecified_currency || !options?.currencies.length || currency === ''" value="">Unspecified</option>
        <option v-if="currency && options && !options.currencies.includes(currency)" :value="currency">{{ currency }} (no active records)</option>
      </select></label>
      <label>Date From<input v-model="dateFrom" type="date" :aria-invalid="invalidRange" @change="applyFilters" /></label>
      <label>Date To<input v-model="dateTo" type="date" :aria-invalid="invalidRange" @change="applyFilters" /></label>
      <label class="company-filter">Company<input v-model="company" type="search" placeholder="Any company" list="dashboard-companies" @change="applyFilters" />
        <datalist id="dashboard-companies"><option v-for="name in options?.companies ?? []" :key="name" :value="name" /></datalist>
      </label>
      <button class="quiet-button reset" type="button" @click="reset">Reset Filters</button>
    </form>
    <p class="filter-note">All metrics use the selected currency and inclusive invoice dates. Company matches part of a name.</p>

    <div v-if="invalidRange" class="error" role="alert"><AlertCircle :size="18" /> Date From must be on or before Date To.</div>
    <div v-else-if="error" class="error" role="alert"><AlertCircle :size="18" /> {{ error }} <button class="quiet-button" @click="options ? load() : initialize()">Retry</button></div>
    <div v-else :aria-busy="loading">
      <p class="load-status" role="status">{{ loading ? 'Loading analytics…' : 'Based on active, persisted records' }}</p>
      <div v-if="!data" class="skeleton-grid" aria-hidden="true"><div v-for="n in 4" :key="n" class="skeleton" /></div>
      <div v-else :class="{ updating: loading }">
        <p v-if="!data.monetary_values_available" class="notice">Currency is unspecified. Counts are shown; monetary values are withheld because these records may use different currencies.</p>
        <div class="kpis">
          <section><h2>Invoices</h2><strong>{{ data.summary.invoice_count.toLocaleString() }}</strong><p>Matching active records</p></section>
          <section><h2>Invoice Value</h2><strong class="money">{{ money(data.summary.total_invoice_value) }}</strong><p>{{ data.summary.invoices_with_total }} of {{ data.summary.invoice_count }} invoices have totals</p></section>
          <section><h2>Average Invoice Value</h2><strong class="money">{{ money(data.summary.average_invoice_value) }}</strong><p>Based on {{ data.summary.invoices_with_total }} known totals</p></section>
          <section><h2>Line Items</h2><strong>{{ data.summary.line_item_count.toLocaleString() }}</strong><p>{{ data.summary.line_items_with_amount }} have amounts</p></section>
        </div>

        <p v-if="data.summary.invoice_count === 0" class="empty overall">No invoices match these filters. Import a workbook or adjust the filters.</p>
        <section class="trend-section section">
          <div class="section-heading"><h2>Invoice Value Over Time</h2><span>Monthly · {{ activeCurrency || 'Unspecified currency' }}</span></div>
          <InvoiceTrend v-if="hasValue && data.monetary_values_available" :periods="data.invoice_value_over_time" :currency="activeCurrency" />
          <p v-else class="empty">{{ !data.monetary_values_available ? 'Select a known currency to view invoice values.' : data.invoice_value_over_time.length === 0 ? 'No dated invoices in this range.' : 'No invoice value available for dated invoices.' }}</p>
          <p class="context">{{ data.summary.invoices_without_date }} invoices without dates are excluded from this chart. Months without records are omitted; missing totals are not zero.</p>
        </section>

        <div class="rankings">
          <section class="section"><div class="section-heading"><h2>Invoice Value by Company</h2><span>Top 10</span></div>
            <ol v-if="data.company_values.length" class="ranking-list">
              <li v-for="(entry, i) in data.company_values" :key="entry.company_name ?? i"><span class="rank">{{ i + 1 }}</span><div><span class="name">{{ entry.company_name || 'Company not specified' }}</span><small>{{ entry.invoice_count }} invoices · {{ entry.invoices_with_total }} with totals</small></div><strong>{{ money(entry.invoice_value) }}</strong></li>
            </ol><p v-else class="empty">No company invoice value available.</p>
          </section>
          <section class="section"><div class="section-heading"><h2>Top Line Items by Amount</h2><span>Top 10</span></div>
            <ol v-if="data.line_item_values.length" class="ranking-list">
              <li v-for="(entry, i) in data.line_item_values" :key="entry.description ?? i"><span class="rank">{{ i + 1 }}</span><div><span class="name">{{ entry.description || 'Description not specified' }}</span><small>{{ entry.line_item_count }} rows · {{ entry.line_items_with_amount }} with amounts</small></div><strong>{{ money(entry.amount) }}</strong></li>
            </ol><p v-else class="empty">No line-item amount data available.</p>
            <p class="context">Grouped by description with outer whitespace trimmed. Descriptions are not unique product identifiers.</p>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1440px; margin: 0 auto; padding: 2.5rem 2rem 4rem; color: var(--text-primary); }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 2rem; }
h1 { font-size: 1.8rem; letter-spacing: -.035em; margin: 0 0 .4rem; }
.page-heading p, .filter-note, .context, .load-status { color: var(--text-secondary); font-size: .82rem; }
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 1rem; }
label { display: flex; flex-direction: column; gap: .45rem; font-size: .75rem; color: var(--text-secondary); }
input, select { min-height: 40px; padding: .55rem .75rem; color: var(--text-primary); background: var(--bg-input); border: 1px solid var(--border-default); border-radius: 6px; color-scheme: dark; font: inherit; }
input:focus, select:focus, button:focus-visible { outline: 2px solid var(--accent-brand); outline-offset: 2px; }
.company-filter { flex: 1; min-width: 180px; max-width: 300px; }
.quiet-button { display: inline-flex; align-items: center; justify-content: center; gap: .5rem; min-height: 40px; border: 1px solid var(--border-default); border-radius: 6px; padding: .5rem .8rem; color: var(--text-secondary); background: transparent; cursor: pointer; font-size: .8rem; }
.quiet-button:hover { color: var(--text-primary); background: var(--bg-subtle); }
button:disabled { opacity: .5; cursor: default; }
.filter-note { margin: .8rem 0 1.5rem; }
.load-status { min-height: 1.3rem; margin-bottom: .7rem; font-size: .75rem; }
.kpis, .skeleton-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 1rem; margin-bottom: 2.5rem; }
.kpis section, .skeleton { border: 1px solid var(--border-subtle); border-radius: 8px; background: var(--bg-card); padding: 1.3rem; }
.kpis h2 { font-size: .8rem; color: var(--text-secondary); font-weight: 500; margin: 0 0 .85rem; }
.kpis strong { font-size: clamp(1.1rem,1.8vw,1.75rem); font-weight: 600; letter-spacing: -.025em; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.kpis p { font-size: .72rem; color: var(--text-muted); margin: .7rem 0 0; }
.section { min-width: 0; padding: 1.5rem 0; border-top: 1px solid var(--border-subtle); }
.section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: .8rem; margin-bottom: 1.4rem; }
.section-heading h2 { font-size: 1rem; font-weight: 600; }
.section-heading span { font-size: .72rem; color: var(--text-muted); white-space: nowrap; }
.rankings { display: grid; grid-template-columns: 1fr 1fr; gap: 2.5rem; }
.ranking-list { list-style: none; padding: 0; margin: 0; }
.ranking-list li { display: grid; grid-template-columns: 1.2rem minmax(0,1fr) auto; align-items: start; gap: .7rem; padding: 1rem 0; border-bottom: 1px solid var(--border-subtle); font-size: .82rem; }
.rank { color: var(--text-muted); font-size: .7rem; padding-top: .15rem; }
.name { overflow-wrap: anywhere; }
small { display: block; color: var(--text-muted); margin-top: .4rem; font-size: .7rem; }
.ranking-list strong { font-weight: 500; font-size: .8rem; font-variant-numeric: tabular-nums; }
.empty { padding: 2.5rem 1rem; text-align: center; color: var(--text-muted); font-size: .88rem; }
.overall { padding: 1rem; background: var(--bg-card); border-radius: 6px; }
.context { font-size: .72rem; line-height: 1.6; margin-top: 1rem; }
.notice { padding: 1rem; color: var(--text-secondary); background: var(--bg-subtle); border-radius: 6px; font-size: .82rem; margin-bottom: 1rem; }
.error { display: flex; align-items: center; flex-wrap: wrap; gap: .8rem; color: var(--status-error); background: var(--status-error-bg); padding: 1rem; border-radius: 6px; }
.skeleton { min-height: 125px; opacity: .6; }
.updating { opacity: .5; pointer-events: none; }
@media (max-width: 1000px) { .kpis,.skeleton-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } .rankings { grid-template-columns: 1fr; gap: 1rem; } }
@media (max-width: 560px) { .dashboard { padding: 1.5rem 1rem; } .filters > label { flex: 1 1 40%; min-width: 0; max-width: none; } input,select { width: 100%; min-width: 0; } .kpis { gap: .65rem; } .kpis section { padding: 1rem; } .ranking-list li { grid-template-columns: 1rem minmax(0,1fr); } .ranking-list strong { grid-column: 2; } .section-heading { flex-wrap: wrap; } }
</style>
