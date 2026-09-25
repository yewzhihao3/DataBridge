<script setup lang="ts">
import { ref, computed } from 'vue'
import {
  ChevronDown,
  ChevronRight,
  Info,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  FileSpreadsheet,
  Code,
} from 'lucide-vue-next'
import type { ExtractedField, RowExtractionPreview } from '@/types/api'

const props = withDefaults(
  defineProps<{
    fields?: ExtractedField[]
    targetWorksheet: string
    isMultiRecord?: boolean
    records?: RowExtractionPreview[]
    hasLineItems?: boolean
    lineItems?: RowExtractionPreview[]
  }>(),
  {
    fields: () => [],
    isMultiRecord: false,
    records: () => [],
    hasLineItems: false,
    lineItems: () => [],
  },
)

// ── Progressive disclosure state ─────────────────────────────────

const showHeaderDetails = ref(false)
const expandedLineItemRow = ref<number | null>(null)
const expandedRecordRow = ref<number | null>(null)

function toggleLineItemRow(rowNum: number) {
  expandedLineItemRow.value = expandedLineItemRow.value === rowNum ? null : rowNum
}

function toggleRecordRow(rowNum: number) {
  expandedRecordRow.value = expandedRecordRow.value === rowNum ? null : rowNum
}

// ── Derived data ─────────────────────────────────────────────────

/** Extract known header fields into a clean key→value summary */
const invoiceSummary = computed(() => {
  const result: Record<string, { display: string; field: ExtractedField }> = {}
  for (const f of props.fields) {
    result[f.field_name] = {
      display: formatBusinessValue(f.normalized_value, f),
      field: f,
    }
  }
  return result
})

/** Detect currency from header fields */
const detectedCurrency = computed(() => {
  const currField = props.fields.find(
    (f) => f.field_name === 'currency',
  )
  if (currField?.normalized_value) return String(currField.normalized_value)
  return null
})

/** Currency symbol for display */
const currencyPrefix = computed(() => {
  const c = detectedCurrency.value
  if (!c) return ''
  if (c === 'MYR') return 'RM '
  if (c === 'USD') return 'US$ '
  if (c === 'EUR') return '€'
  if (c === 'GBP') return '£'
  if (c === 'SGD') return 'S$ '
  return c + ' '
})

/** Fields that have problems */
const fieldErrors = computed(() =>
  props.fields.filter((f) => f.status === 'error'),
)
const fieldWarnings = computed(() =>
  props.fields.filter((f) => f.status === 'warning'),
)

/** Line items with problems */
const lineItemErrors = computed(() =>
  props.lineItems.filter((li) => li.has_errors),
)
const lineItemWarnings = computed(() =>
  props.lineItems.filter((li) => li.warning_count > 0 && !li.has_errors),
)

/** Overall header validation status */
const headerStatus = computed(() => {
  if (fieldErrors.value.length > 0) return 'error'
  if (fieldWarnings.value.length > 0) return 'warning'
  return 'success'
})

/** Overall line items validation status */
const lineItemsStatus = computed(() => {
  if (lineItemErrors.value.length > 0) return 'error'
  if (lineItemWarnings.value.length > 0) return 'warning'
  return 'success'
})

/** Identify the "key" fields to show prominently in the business table */
const lineItemColumns = computed(() => {
  if (props.lineItems.length === 0) return []
  const firstItem = props.lineItems[0]
  if (!firstItem.normalized_data) return []
  return Object.keys(firstItem.normalized_data)
})

/** Friendly column header name */
function friendlyColumnName(key: string): string {
  const map: Record<string, string> = {
    description: 'Description',
    quantity: 'Qty',
    unit_price: 'Unit Price',
    tax_rate: 'Tax',
    tax_amount: 'Tax Amt',
    amount: 'Amount',
    item_code: 'Code',
    discount: 'Discount',
  }
  return map[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Identify monetary columns for right-alignment */
function isNumericColumn(key: string): boolean {
  return ['quantity', 'unit_price', 'tax_rate', 'tax_amount', 'amount', 'discount', 'subtotal', 'total'].includes(key)
}

/** Is this a description-like column (wide) */
function isDescriptionColumn(key: string): boolean {
  return ['description', 'item_description', 'product_name', 'name'].includes(key)
}

// ── Money fields that should have currency prefix ────────────────

const moneyFields = new Set([
  'subtotal', 'sub_total', 'tax', 'tax_amount', 'total', 'total_amount',
  'amount', 'unit_price', 'discount', 'grand_total',
])

const moneyColumnFields = new Set([
  'unit_price', 'tax_amount', 'amount', 'discount',
])

// ── Known field display order for the invoice summary ────────────

const invoiceInfoFields = [
  'company_name', 'invoice_number', 'invoice_date', 'due_date', 'currency',
]
const invoiceMoneyFields = [
  'subtotal', 'sub_total', 'tax', 'tax_amount', 'total', 'total_amount', 'grand_total',
]

/** Fields in the "info" section */
const infoFieldEntries = computed(() => {
  const entries: Array<{ key: string; label: string; display: string; field: ExtractedField }> = []
  for (const key of invoiceInfoFields) {
    if (invoiceSummary.value[key]) {
      entries.push({
        key,
        label: friendlyFieldName(key),
        display: invoiceSummary.value[key].display,
        field: invoiceSummary.value[key].field,
      })
    }
  }
  return entries
})

/** Fields in the "money" section */
const moneyFieldEntries = computed(() => {
  const entries: Array<{ key: string; label: string; display: string; field: ExtractedField }> = []
  for (const key of invoiceMoneyFields) {
    if (invoiceSummary.value[key]) {
      entries.push({
        key,
        label: friendlyFieldName(key),
        display: invoiceSummary.value[key].display,
        field: invoiceSummary.value[key].field,
      })
    }
  }
  return entries
})

/** Any fields that don't fit the known buckets */
const otherFieldEntries = computed(() => {
  const known = new Set([...invoiceInfoFields, ...invoiceMoneyFields])
  const entries: Array<{ key: string; label: string; display: string; field: ExtractedField }> = []
  for (const [key, val] of Object.entries(invoiceSummary.value)) {
    if (!known.has(key)) {
      entries.push({
        key,
        label: friendlyFieldName(key),
        display: val.display,
        field: val.field,
      })
    }
  }
  return entries
})

// ── Format helpers (PRESENTATION ONLY) ───────────────────────────

function formatBusinessValue(val: any, field: ExtractedField): string {
  if (val === null || val === undefined) return '—'

  // Date formatting
  if (field.data_type === 'date') {
    return formatDate(val)
  }

  // Decimal formatting with money prefix
  if (field.data_type === 'decimal' && typeof val === 'number') {
    if (moneyFields.has(field.field_name)) {
      return currencyPrefix.value + formatNumber(val)
    }
    // Tax rate → percentage
    if (field.field_name === 'tax_rate') {
      return formatPercent(val)
    }
    return formatNumber(val)
  }

  if (field.data_type === 'integer' && typeof val === 'number') {
    return val.toLocaleString()
  }

  return String(val)
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

function formatPercent(val: any): string {
  const num = parseNumeric(val)
  if (num === null) return String(val)
  // If value is between 0 and 1, treat as decimal percentage
  const pct = num <= 1 && num > 0 ? num * 100 : num
  return pct.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }) + '%'
}

function formatDate(val: any): string {
  if (!val) return '—'
  const str = String(val)
  try {
    const d = new Date(str)
    if (isNaN(d.getTime())) return str
    return d.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return str
  }
}

function friendlyFieldName(key: string): string {
  const map: Record<string, string> = {
    company_name: 'Company',
    invoice_number: 'Invoice Number',
    invoice_date: 'Invoice Date',
    due_date: 'Due Date',
    currency: 'Currency',
    subtotal: 'Subtotal',
    sub_total: 'Subtotal',
    tax: 'Tax',
    tax_amount: 'Tax',
    total: 'Total',
    total_amount: 'Total',
    grand_total: 'Grand Total',
    tax_rate: 'Tax Rate',
  }
  return map[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Format a line-item cell value for the business table */
function formatCellValue(key: string, val: any): string {
  if (val === null || val === undefined || val === '') return '—'
  const num = parseNumeric(val)

  if (key === 'tax_rate') return formatPercent(val)

  if (num !== null) {
    if (key === 'quantity') {
      return num.toLocaleString()
    }
    if (moneyColumnFields.has(key) || isNumericColumn(key) || moneyFields.has(key)) {
      return formatNumber(num)
    }
    if (!Number.isInteger(num)) {
      return formatNumber(num)
    }
    return num.toLocaleString()
  }

  return String(val)
}

/** Format raw value for the details panel */
function formatRawValue(val: any): string {
  if (val === null || val === undefined) return '<Empty>'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatNormalizedValue(val: any, field?: ExtractedField): string {
  if (val === null || val === undefined || val === '') return '—'
  const num = parseNumeric(val)
  if (num !== null && (field?.data_type === 'decimal' || !Number.isInteger(num))) {
    return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  if (num !== null && Number.isInteger(num)) {
    return num.toLocaleString()
  }
  return String(val)
}

/** Check if a money field is the "total" — give it visual emphasis */
function isTotalField(key: string): boolean {
  return ['total', 'total_amount', 'grand_total'].includes(key)
}
</script>

<template>
  <div class="zen-preview">
    <!-- ═══════════════════════════════════════════════════════════════
         SINGLE INVOICE PREVIEW
         ═══════════════════════════════════════════════════════════ -->
    <template v-if="!isMultiRecord">

      <!-- ── Invoice Details Section ──────────────────────────────── -->
      <section class="zen-section" aria-label="Invoice details">
        <div class="section-header">
          <h3 class="section-title">Invoice Details</h3>
          <div
            v-if="headerStatus === 'success'"
            class="zen-status zen-status--success"
          >
            <CheckCircle2 :size="14" />
            <span>All fields valid</span>
          </div>
          <div
            v-else-if="headerStatus === 'warning'"
            class="zen-status zen-status--warning"
          >
            <AlertTriangle :size="14" />
            <span>{{ fieldWarnings.length }} warning{{ fieldWarnings.length > 1 ? 's' : '' }}</span>
          </div>
          <div
            v-else
            class="zen-status zen-status--error"
          >
            <AlertCircle :size="14" />
            <span>{{ fieldErrors.length }} error{{ fieldErrors.length > 1 ? 's' : '' }}</span>
          </div>
        </div>

        <div class="zen-separator"></div>

        <!-- Info fields grid -->
        <div class="summary-layout">
          <div class="summary-info-grid" v-if="infoFieldEntries.length > 0">
            <div
              v-for="entry in infoFieldEntries"
              :key="entry.key"
              class="summary-field"
              :class="{ 'field-has-issue': entry.field.status === 'error' || entry.field.status === 'warning' }"
            >
              <span class="summary-label">{{ entry.label }}</span>
              <span class="summary-value">
                {{ entry.display }}
                <span
                  v-if="entry.field.is_formula"
                  class="formula-indicator"
                  :title="`Formula: ${entry.field.formula_expression || 'cached'}`"
                >
                  <Info :size="12" />
                </span>
              </span>
              <span v-if="entry.field.error_message" class="field-issue field-issue--error">
                <AlertCircle :size="12" />
                {{ entry.field.error_message }}
              </span>
              <span v-else-if="entry.field.warning_message" class="field-issue field-issue--warning">
                <AlertTriangle :size="12" />
                {{ entry.field.warning_message }}
              </span>
            </div>
          </div>

          <!-- Other fields -->
          <div class="summary-info-grid" v-if="otherFieldEntries.length > 0">
            <div
              v-for="entry in otherFieldEntries"
              :key="entry.key"
              class="summary-field"
              :class="{ 'field-has-issue': entry.field.status === 'error' || entry.field.status === 'warning' }"
            >
              <span class="summary-label">{{ entry.label }}</span>
              <span class="summary-value">
                {{ entry.display }}
                <span
                  v-if="entry.field.is_formula"
                  class="formula-indicator"
                  :title="`Formula: ${entry.field.formula_expression || 'cached'}`"
                >
                  <Info :size="12" />
                </span>
              </span>
              <span v-if="entry.field.error_message" class="field-issue field-issue--error">
                <AlertCircle :size="12" />
                {{ entry.field.error_message }}
              </span>
              <span v-else-if="entry.field.warning_message" class="field-issue field-issue--warning">
                <AlertTriangle :size="12" />
                {{ entry.field.warning_message }}
              </span>
            </div>
          </div>

          <!-- Money summary -->
          <div v-if="moneyFieldEntries.length > 0" class="money-summary">
            <div class="zen-separator"></div>
            <div
              v-for="entry in moneyFieldEntries"
              :key="entry.key"
              class="money-row"
              :class="{
                'money-row--total': isTotalField(entry.key),
                'field-has-issue': entry.field.status === 'error' || entry.field.status === 'warning',
              }"
            >
              <span class="money-label">{{ entry.label }}</span>
              <span class="money-value">
                {{ entry.display }}
                <span
                  v-if="entry.field.is_formula"
                  class="formula-indicator"
                  :title="`Formula: ${entry.field.formula_expression || 'cached'}`"
                >
                  <Info :size="12" />
                </span>
              </span>
              <span v-if="entry.field.error_message" class="field-issue field-issue--error">
                <AlertCircle :size="12" />
                {{ entry.field.error_message }}
              </span>
              <span v-else-if="entry.field.warning_message" class="field-issue field-issue--warning">
                <AlertTriangle :size="12" />
                {{ entry.field.warning_message }}
              </span>
            </div>
          </div>
        </div>

        <!-- Progressive disclosure: extraction details -->
        <button
          class="disclosure-toggle"
          type="button"
          :aria-expanded="showHeaderDetails"
          @click="showHeaderDetails = !showHeaderDetails"
        >
          <component :is="showHeaderDetails ? ChevronDown : ChevronRight" :size="16" />
          <span>{{ showHeaderDetails ? 'Hide' : 'Show' }} extraction details</span>
        </button>

        <transition name="slide">
          <div v-if="showHeaderDetails" class="details-panel">
            <table class="details-table" aria-label="Header field extraction details">
              <thead>
                <tr>
                  <th>Field</th>
                  <th>Source Cell</th>
                  <th>Data Type</th>
                  <th>Raw Value</th>
                  <th>Normalized</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="field in fields"
                  :key="field.field_name"
                  :class="{
                    'detail-row--error': field.status === 'error',
                    'detail-row--warning': field.status === 'warning',
                  }"
                >
                  <td class="detail-field-name">
                    <span>{{ field.field_name }}</span>
                    <span v-if="field.is_required" class="required-tag">Required</span>
                    <span v-else class="optional-tag">Optional</span>
                  </td>
                  <td class="detail-cell-ref mono">
                    <FileSpreadsheet :size="12" class="text-accent" />
                    {{ field.source_worksheet }}!{{ field.source_cell_ref }}
                    <div v-if="field.is_formula" class="detail-formula mono">
                      <Code :size="11" />
                      <span>{{ field.formula_expression || 'Formula' }}</span>
                    </div>
                  </td>
                  <td><span class="type-pill mono">{{ field.data_type }}</span></td>
                  <td class="mono detail-raw">{{ formatRawValue(field.raw_value) }}</td>
                  <td class="detail-normalized">
                    <span :class="{ 'text-muted': field.normalized_value === null }">
                      {{ formatNormalizedValue(field.normalized_value, field) }}
                    </span>
                  </td>
                  <td>
                    <span class="detail-status" :class="`detail-status--${field.status}`">
                      <CheckCircle2 v-if="field.status === 'success'" :size="12" />
                      <AlertTriangle v-else-if="field.status === 'warning'" :size="12" />
                      <AlertCircle v-else-if="field.status === 'error'" :size="12" />
                      {{ field.status }}
                    </span>
                    <div v-if="field.error_message" class="detail-message detail-message--error">
                      {{ field.error_message }}
                    </div>
                    <div v-if="field.warning_message" class="detail-message detail-message--warning">
                      {{ field.warning_message }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </transition>
      </section>

      <!-- ── Line Items Section ───────────────────────────────────── -->
      <section v-if="hasLineItems" class="zen-section" aria-label="Line items">
        <div class="section-header">
          <h3 class="section-title">Line Items</h3>
          <span class="item-count">{{ lineItems.length }} item{{ lineItems.length !== 1 ? 's' : '' }}</span>
          <div
            v-if="lineItemsStatus === 'success' && lineItems.length > 0"
            class="zen-status zen-status--success"
          >
            <CheckCircle2 :size="14" />
            <span>All valid</span>
          </div>
          <div
            v-else-if="lineItemsStatus === 'warning'"
            class="zen-status zen-status--warning"
          >
            <AlertTriangle :size="14" />
            <span>{{ lineItemWarnings.length }} warning{{ lineItemWarnings.length > 1 ? 's' : '' }}</span>
          </div>
          <div
            v-else-if="lineItemsStatus === 'error'"
            class="zen-status zen-status--error"
          >
            <AlertCircle :size="14" />
            <span>{{ lineItemErrors.length }} error{{ lineItemErrors.length > 1 ? 's' : '' }}</span>
          </div>
        </div>

        <div class="zen-separator"></div>

        <!-- Business table -->
        <div class="line-items-container">
          <table class="business-table" aria-label="Invoice line items">
            <thead>
              <tr>
                <th
                  v-for="col in lineItemColumns"
                  :key="col"
                  :class="{
                    'col-numeric': isNumericColumn(col),
                    'col-description': isDescriptionColumn(col),
                  }"
                >
                  {{ friendlyColumnName(col) }}
                </th>
                <th class="col-expand" aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="li in lineItems" :key="li.source_row_number">
                <!-- Main business row -->
                <tr
                  class="business-row"
                  :class="{
                    'business-row--error': li.has_errors,
                    'business-row--warning': li.warning_count > 0 && !li.has_errors,
                    'business-row--expanded': expandedLineItemRow === li.source_row_number,
                  }"
                  tabindex="0"
                  role="button"
                  :aria-expanded="expandedLineItemRow === li.source_row_number"
                  @click="toggleLineItemRow(li.source_row_number)"
                  @keydown.enter="toggleLineItemRow(li.source_row_number)"
                  @keydown.space.prevent="toggleLineItemRow(li.source_row_number)"
                >
                  <td
                    v-for="col in lineItemColumns"
                    :key="col"
                    :class="{
                      'col-numeric': isNumericColumn(col),
                      'col-description': isDescriptionColumn(col),
                    }"
                  >
                    {{ formatCellValue(col, li.normalized_data?.[col]) }}
                  </td>
                  <td class="col-expand">
                    <span class="row-status-hint">
                      <AlertCircle v-if="li.has_errors" :size="14" class="status-icon--error" />
                      <AlertTriangle v-else-if="li.warning_count > 0" :size="14" class="status-icon--warning" />
                    </span>
                    <component
                      :is="expandedLineItemRow === li.source_row_number ? ChevronDown : ChevronRight"
                      :size="14"
                      class="expand-chevron"
                    />
                  </td>
                </tr>

                <!-- Expanded detail row -->
                <tr
                  v-if="expandedLineItemRow === li.source_row_number"
                  class="detail-expansion-row"
                >
                  <td :colspan="lineItemColumns.length + 1">
                    <div class="line-item-details">
                      <div class="detail-section-label">Source Details</div>
                      <div class="detail-grid">
                        <div class="detail-item">
                          <span class="detail-item-label">Source Row</span>
                          <span class="detail-item-value mono">{{ li.source_row_number }}</span>
                        </div>
                        <div
                          v-for="f in li.fields"
                          :key="f.field_name"
                          class="detail-item"
                        >
                          <span class="detail-item-label">{{ friendlyColumnName(f.field_name) }}</span>
                          <span class="detail-item-value mono">
                            <FileSpreadsheet :size="11" class="text-accent" />
                            {{ f.source_cell_ref }}
                          </span>
                          <span v-if="f.is_formula" class="detail-formula-tag mono">
                            <Code :size="10" />
                            {{ f.formula_expression || 'Formula' }}
                          </span>
                        </div>
                      </div>

                      <!-- Raw vs Normalized values -->
                      <div class="detail-section-label" style="margin-top: 1rem;">Raw &amp; Normalized Values</div>
                      <div class="detail-grid">
                        <div
                          v-for="f in li.fields"
                          :key="`raw-${f.field_name}`"
                          class="detail-item"
                        >
                          <span class="detail-item-label">{{ friendlyColumnName(f.field_name) }}</span>
                          <span class="detail-item-value">
                            <span class="detail-raw-label">Raw:</span>
                            <span class="mono">{{ formatRawValue(f.raw_value) }}</span>
                          </span>
                          <span class="detail-item-value">
                            <span class="detail-raw-label">Normalized:</span>
                            <span class="mono">{{ formatNormalizedValue(f.normalized_value, f) }}</span>
                          </span>
                        </div>
                      </div>

                      <!-- Errors/Warnings -->
                      <div v-if="li.errors.length > 0" class="detail-errors">
                        <div
                          v-for="err in li.errors"
                          :key="err.message"
                          class="detail-error-item"
                        >
                          <AlertCircle :size="13" />
                          {{ err.message }}
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <p v-if="lineItems.length > 0" class="zen-hint">
          Click a row to inspect source details
        </p>
      </section>
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         MULTI-RECORD / DATASET PREVIEW
         ═══════════════════════════════════════════════════════════ -->
    <template v-else>
      <section class="zen-section" aria-label="Dataset records">
        <div class="section-header">
          <h3 class="section-title">Extracted Records</h3>
          <span class="item-count">{{ records.length }} record{{ records.length !== 1 ? 's' : '' }}</span>
        </div>

        <div class="zen-separator"></div>

        <div class="line-items-container">
          <table class="business-table" aria-label="Dataset records">
            <thead>
              <tr>
                <th class="col-row-num">Row</th>
                <th
                  v-for="col in (records.length > 0 ? Object.keys(records[0].normalized_data || {}) : [])"
                  :key="col"
                  :class="{
                    'col-numeric': isNumericColumn(col),
                    'col-description': isDescriptionColumn(col),
                  }"
                >
                  {{ friendlyColumnName(col) }}
                </th>
                <th class="col-expand" aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="rec in records" :key="rec.source_row_number">
                <tr
                  class="business-row"
                  :class="{
                    'business-row--error': rec.has_errors,
                    'business-row--warning': rec.warning_count > 0 && !rec.has_errors,
                    'business-row--expanded': expandedRecordRow === rec.source_row_number,
                  }"
                  tabindex="0"
                  role="button"
                  :aria-expanded="expandedRecordRow === rec.source_row_number"
                  @click="toggleRecordRow(rec.source_row_number)"
                  @keydown.enter="toggleRecordRow(rec.source_row_number)"
                  @keydown.space.prevent="toggleRecordRow(rec.source_row_number)"
                >
                  <td class="col-row-num mono">{{ rec.source_row_number }}</td>
                  <td
                    v-for="col in Object.keys(rec.normalized_data || {})"
                    :key="col"
                    :class="{
                      'col-numeric': isNumericColumn(col),
                      'col-description': isDescriptionColumn(col),
                    }"
                  >
                    {{ formatCellValue(col, rec.normalized_data?.[col]) }}
                  </td>
                  <td class="col-expand">
                    <span class="row-status-hint">
                      <AlertCircle v-if="rec.has_errors" :size="14" class="status-icon--error" />
                      <AlertTriangle v-else-if="rec.warning_count > 0" :size="14" class="status-icon--warning" />
                    </span>
                    <component
                      :is="expandedRecordRow === rec.source_row_number ? ChevronDown : ChevronRight"
                      :size="14"
                      class="expand-chevron"
                    />
                  </td>
                </tr>

                <!-- Expanded details for dataset record -->
                <tr
                  v-if="expandedRecordRow === rec.source_row_number"
                  class="detail-expansion-row"
                >
                  <td :colspan="Object.keys(rec.normalized_data || {}).length + 2">
                    <div class="line-item-details">
                      <div class="detail-section-label">Source Details</div>
                      <div class="detail-grid">
                        <div class="detail-item">
                          <span class="detail-item-label">Source Row</span>
                          <span class="detail-item-value mono">{{ rec.source_row_number }}</span>
                        </div>
                        <div
                          v-for="f in rec.fields"
                          :key="f.field_name"
                          class="detail-item"
                        >
                          <span class="detail-item-label">{{ friendlyColumnName(f.field_name) }}</span>
                          <span class="detail-item-value mono">
                            <FileSpreadsheet :size="11" class="text-accent" />
                            {{ f.source_cell_ref }}
                          </span>
                        </div>
                      </div>

                      <div v-if="rec.errors.length > 0" class="detail-errors">
                        <div
                          v-for="err in rec.errors"
                          :key="err.message"
                          class="detail-error-item"
                        >
                          <AlertCircle :size="13" />
                          {{ err.message }}
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <p v-if="records.length > 0" class="zen-hint">
          Click a row to inspect source details
        </p>
      </section>
    </template>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════
   ZEN DATA — Extraction Preview Styles
   ═══════════════════════════════════════════════════════════════ */

.zen-preview {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

/* ── Section ──────────────────────────────────────────────────── */

.zen-section {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 2rem;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.section-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.item-count {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.15rem 0.6rem;
  border-radius: var(--radius-full);
}

.zen-separator {
  height: 1px;
  background: var(--border-subtle);
  margin: 1rem 0;
}

/* ── Validation Status Badges ─────────────────────────────────── */

.zen-status {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  font-weight: 600;
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-full);
  margin-left: auto;
}

.zen-status--success {
  color: var(--status-success);
  background: var(--status-success-bg);
}

.zen-status--warning {
  color: var(--status-warning);
  background: var(--status-warning-bg);
}

.zen-status--error {
  color: var(--status-error);
  background: var(--status-error-bg);
}

/* ── Invoice Summary Layout ───────────────────────────────────── */

.summary-layout {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1.25rem 2rem;
  padding: 0.5rem 0;
}

.summary-field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.summary-label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.summary-value {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.formula-indicator {
  color: var(--accent-cyan);
  cursor: help;
  display: inline-flex;
  opacity: 0.7;
  transition: opacity var(--transition-fast);
}

.formula-indicator:hover {
  opacity: 1;
}

.field-has-issue .summary-value {
  position: relative;
}

.field-issue {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.73rem;
  font-weight: 500;
  margin-top: 0.15rem;
}

.field-issue--error {
  color: var(--status-error);
}

.field-issue--warning {
  color: var(--status-warning);
}

/* ── Money Summary ────────────────────────────────────────────── */

.money-summary {
  max-width: 360px;
  margin-left: auto;
  margin-top: 0.5rem;
}

.money-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  padding: 0.45rem 0;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.money-row--total {
  padding-top: 0.65rem;
  margin-top: 0.25rem;
  border-top: 1px solid var(--border-default);
}

.money-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text-secondary);
}

.money-value {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
  font-variant-numeric: tabular-nums;
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.money-row--total .money-label {
  font-weight: 700;
  color: var(--text-primary);
  font-size: 0.9rem;
}

.money-row--total .money-value {
  font-size: 1.1rem;
  font-weight: 800;
  color: var(--text-primary);
}

/* ── Progressive Disclosure Toggle ────────────────────────────── */

.disclosure-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 1.25rem;
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.disclosure-toggle:hover {
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-color: var(--border-subtle);
}

.disclosure-toggle:focus-visible {
  outline: 2px solid var(--accent-brand);
  outline-offset: 2px;
}

/* ── Details Panel (Header Field Technical Table) ─────────────── */

.details-panel {
  margin-top: 0.75rem;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-surface);
}

.details-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

.details-table th {
  background: var(--bg-subtle);
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.6rem 0.85rem;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  white-space: nowrap;
}

.details-table td {
  padding: 0.65rem 0.85rem;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
  color: var(--text-secondary);
}

.details-table tr:last-child td {
  border-bottom: none;
}

.detail-row--error {
  background: rgba(239, 68, 68, 0.04);
}

.detail-row--warning {
  background: rgba(245, 158, 11, 0.04);
}

.detail-field-name {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
}

.required-tag {
  font-size: 0.62rem;
  font-weight: 600;
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
}

.optional-tag {
  font-size: 0.62rem;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
}

.detail-cell-ref {
  font-size: 0.76rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-wrap: wrap;
}

.detail-formula {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  font-size: 0.68rem;
  color: var(--accent-cyan);
  background: var(--accent-cyan-subtle);
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-pill {
  font-size: 0.7rem;
  background: var(--bg-subtle);
  padding: 0.15rem 0.4rem;
  border-radius: var(--radius-sm);
  color: var(--text-muted);
}

.detail-raw {
  max-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.76rem;
}

.detail-normalized {
  font-weight: 600;
  color: var(--text-primary);
}

.detail-status {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: capitalize;
}

.detail-status--success { color: var(--status-success); }
.detail-status--warning { color: var(--status-warning); }
.detail-status--error { color: var(--status-error); }
.detail-status--empty_optional { color: var(--text-muted); }

.detail-message {
  font-size: 0.72rem;
  margin-top: 0.2rem;
}

.detail-message--error { color: var(--status-error); }
.detail-message--warning { color: var(--status-warning); }

/* ── Line Items Business Table ────────────────────────────────── */

.line-items-container {
  overflow-x: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.business-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.business-table thead th {
  background: var(--bg-subtle);
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.7rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
  white-space: nowrap;
}

.business-table thead th.col-numeric {
  text-align: right;
}

.business-table thead th.col-description {
  min-width: 200px;
}

.business-table thead th.col-expand {
  width: 50px;
  text-align: center;
}

.business-table thead th.col-row-num {
  width: 60px;
}

/* ── Business Row ─────────────────────────────────────────────── */

.business-row {
  cursor: pointer;
  transition: background var(--transition-fast);
}

.business-row td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.business-row:last-child td,
.business-row + .detail-expansion-row:last-child td {
  border-bottom: none;
}

.business-row:hover {
  background: rgba(255, 255, 255, 0.02);
}

.business-row--expanded {
  background: rgba(99, 102, 241, 0.04);
}

.business-row--error {
  background: rgba(239, 68, 68, 0.04);
}

.business-row--error:hover {
  background: rgba(239, 68, 68, 0.07);
}

.business-row--warning {
  background: rgba(245, 158, 11, 0.03);
}

.business-row--warning:hover {
  background: rgba(245, 158, 11, 0.06);
}

.business-row td.col-numeric {
  text-align: right;
  font-weight: 500;
}

.business-row td.col-description {
  font-weight: 500;
}

.business-row td.col-expand {
  text-align: center;
}

.business-row td.col-row-num {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.business-row:focus-visible {
  outline: 2px solid var(--accent-brand);
  outline-offset: -2px;
}

/* ── Expand Chevron & Status Hints ────────────────────────────── */

.col-expand {
  text-align: center;
  white-space: nowrap;
}

.expand-chevron {
  color: var(--text-muted);
  transition: color var(--transition-fast);
}

.business-row:hover .expand-chevron {
  color: var(--text-secondary);
}

.row-status-hint {
  display: inline-flex;
}

.status-icon--error { color: var(--status-error); }
.status-icon--warning { color: var(--status-warning); }

/* ── Detail Expansion Row ─────────────────────────────────────── */

.detail-expansion-row td {
  padding: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}

.line-item-details {
  padding: 1.25rem 1.5rem;
}

.detail-section-label {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 0.65rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 0.85rem 1.5rem;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.detail-item-label {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.detail-item-value {
  font-size: 0.8rem;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}

.detail-raw-label {
  font-size: 0.68rem;
  color: var(--text-muted);
  font-weight: 500;
  min-width: 4rem;
}

.detail-formula-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  font-size: 0.68rem;
  color: var(--accent-cyan);
  background: var(--accent-cyan-subtle);
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-errors {
  margin-top: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.detail-error-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: var(--status-error);
  font-weight: 500;
}

/* ── Hint Text ────────────────────────────────────────────────── */

.zen-hint {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-align: center;
  margin-top: 0.75rem;
  font-style: italic;
}

/* ── Slide Transition ─────────────────────────────────────────── */

.slide-enter-active,
.slide-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 2000px;
}

/* ── Utility ──────────────────────────────────────────────────── */

.text-accent {
  color: var(--accent-brand);
}

.text-muted {
  color: var(--text-muted);
}

/* ── Responsive ───────────────────────────────────────────────── */

@media (max-width: 768px) {
  .zen-section {
    padding: 1.25rem;
  }

  .summary-info-grid {
    grid-template-columns: 1fr 1fr;
  }

  .money-summary {
    max-width: 100%;
  }

  .detail-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 520px) {
  .summary-info-grid {
    grid-template-columns: 1fr;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
