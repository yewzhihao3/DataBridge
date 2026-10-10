<script setup lang="ts">
import { computed } from 'vue'
import {
  CreditCard,
  ExternalLink,
  FileText,
  Receipt,
  Tag,
  X,
} from 'lucide-vue-next'

import type { ReceiptDetailResponse } from '@/types/api'

const props = defineProps<{
  receipt: ReceiptDetailResponse | null
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

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

function formatDirection(dir?: string | null): string {
  if (!dir) return 'Unclassified'
  const map: Record<string, string> = {
    expense: 'Expense',
    income: 'Income',
    unclassified: 'Unclassified',
  }
  return map[dir.toLowerCase()] || dir
}

function getDirectionBadgeClass(dir?: string | null): string {
  if (!dir) return 'badge-neutral'
  const norm = dir.toLowerCase()
  if (norm === 'income') return 'badge-success'
  if (norm === 'expense') return 'badge-warning'
  return 'badge-neutral'
}

const sourcePreviewUrl = computed(() => {
  if (props.receipt?.batch?.source_file_id) {
    return `/api/v1/documents/${props.receipt.batch.source_file_id}/preview`
  }
  return null
})

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) {
    emit('close')
  }
}
</script>

<template>
  <div
    v-if="isOpen && receipt"
    class="zen-modal-overlay"
    tabindex="-1"
    role="dialog"
    aria-modal="true"
    aria-labelledby="receipt-detail-modal-title"
    @click="onBackdropClick"
    @keydown.esc="emit('close')"
  >
    <div class="zen-modal-container">
      <!-- Modal Header -->
      <div class="zen-modal-header">
        <div class="header-titles">
          <div class="flex items-center gap-2">
            <Receipt :size="20" class="text-slate-600" />
            <h2 id="receipt-detail-modal-title" class="text-lg font-semibold text-slate-900">
              Receipt Details
            </h2>
            <span :class="['zen-badge', getDirectionBadgeClass(receipt.direction)]">
              {{ formatDirection(receipt.direction) }}
            </span>
          </div>
          <span class="text-xs text-slate-500 font-mono mt-0.5">
            {{ receipt.receipt_number || 'Receipt number: Not provided' }}
          </span>
        </div>
        <button
          type="button"
          class="btn-close"
          aria-label="Close receipt details modal"
          @click="emit('close')"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- Modal Body -->
      <div class="zen-modal-body">
        <!-- Overview Cards -->
        <div class="zen-summary-cards">
          <div class="zen-card">
            <span class="zen-card-label">Merchant</span>
            <span class="zen-card-value font-medium">{{ receipt.merchant_name }}</span>
          </div>
          <div class="zen-card">
            <span class="zen-card-label">Receipt Number</span>
            <span class="zen-card-value font-mono">
              {{ receipt.receipt_number ? receipt.receipt_number : 'Not provided' }}
            </span>
          </div>
          <div class="zen-card">
            <span class="zen-card-label">Transaction Date</span>
            <span class="zen-card-value">
              {{ formatDate(receipt.transaction_date) }}
              <span v-if="receipt.transaction_time" class="text-xs text-slate-400 ml-1">
                {{ receipt.transaction_time }}
              </span>
            </span>
          </div>
          <div class="zen-card highlight-card">
            <span class="zen-card-label">Total Amount</span>
            <span class="zen-card-value font-mono total-value">
              {{ formatCurrency(receipt.total_amount, receipt.currency) }}
            </span>
          </div>
        </div>

        <!-- Payment & Location Breakdown -->
        <div class="zen-custom-fields-section">
          <h3 class="zen-section-heading">
            <CreditCard :size="15" />
            <span>Financial & Payment Breakdown</span>
          </h3>
          <div class="zen-custom-fields-grid">
            <div class="custom-field-item">
              <span class="field-label">Payment Method</span>
              <span class="field-value">{{ receipt.payment_method || '—' }}</span>
            </div>
            <div class="custom-field-item">
              <span class="field-label">Subtotal</span>
              <span class="field-value font-mono">
                {{ formatCurrency(receipt.subtotal, receipt.currency) }}
              </span>
            </div>
            <div class="custom-field-item">
              <span class="field-label">Tax Amount</span>
              <span class="field-value font-mono">
                {{ formatCurrency(receipt.tax_amount, receipt.currency) }}
              </span>
            </div>
            <div v-if="receipt.cash_paid" class="custom-field-item">
              <span class="field-label">Cash Paid</span>
              <span class="field-value font-mono">
                {{ formatCurrency(receipt.cash_paid, receipt.currency) }}
              </span>
            </div>
            <div v-if="receipt.change_amount" class="custom-field-item">
              <span class="field-label">Change Amount</span>
              <span class="field-value font-mono">
                {{ formatCurrency(receipt.change_amount, receipt.currency) }}
              </span>
            </div>
            <div v-if="receipt.store_address" class="custom-field-item col-span-2">
              <span class="field-label">Store Address</span>
              <span class="field-value">{{ receipt.store_address }}</span>
            </div>
            <div v-if="receipt.branch" class="custom-field-item">
              <span class="field-label">Branch</span>
              <span class="field-value">{{ receipt.branch }}</span>
            </div>
            <div v-if="receipt.cashier" class="custom-field-item">
              <span class="field-label">Cashier</span>
              <span class="field-value">{{ receipt.cashier }}</span>
            </div>
          </div>
        </div>

        <!-- Line Items Section -->
        <div class="zen-line-items-section">
          <div class="section-header-row">
            <h3 class="zen-section-heading">
              <Tag :size="15" />
              <span>Extracted Line Items ({{ receipt.line_items.length }})</span>
            </h3>
          </div>

          <div v-if="receipt.line_items.length === 0" class="empty-line-items">
            <span>No itemized breakdown extracted for this receipt.</span>
          </div>

          <div v-else class="zen-table-wrapper">
            <table class="zen-table">
              <thead>
                <tr>
                  <th class="w-12 text-center">#</th>
                  <th>Description</th>
                  <th class="text-right">Qty</th>
                  <th class="text-right">Unit Price</th>
                  <th class="text-right">Tax</th>
                  <th class="text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, idx) in receipt.line_items" :key="item.id || idx">
                  <td class="text-center font-mono text-xs text-slate-400">
                    {{ item.source_row_number || idx + 1 }}
                  </td>
                  <td class="font-medium text-slate-800">
                    {{ item.description || '—' }}
                  </td>
                  <td class="text-right font-mono text-slate-600">
                    {{ formatQuantity(item.quantity) }}
                  </td>
                  <td class="text-right font-mono text-slate-600">
                    {{ formatCurrency(item.unit_price, receipt.currency) }}
                  </td>
                  <td class="text-right font-mono text-slate-600">
                    {{ formatCurrency(item.tax_amount, receipt.currency) }}
                  </td>
                  <td class="text-right font-mono font-medium text-slate-900">
                    {{ formatCurrency(item.amount, receipt.currency) }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Provenance & Source File Traceability -->
        <div class="zen-provenance-section">
          <div class="provenance-grid">
            <div class="provenance-item">
              <span class="provenance-label">Source File</span>
              <div class="flex items-center gap-2 mt-0.5">
                <FileText :size="14" class="text-slate-400" />
                <span class="font-medium text-slate-800 text-xs">
                  {{ receipt.batch?.source_filename || 'Unknown' }}
                </span>
                <a
                  v-if="sourcePreviewUrl"
                  :href="sourcePreviewUrl"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="btn-source-link"
                  title="Open source receipt document in new tab"
                >
                  <ExternalLink :size="12" />
                  <span>View Source</span>
                </a>
              </div>
            </div>

            <div class="provenance-item">
              <span class="provenance-label">Import Batch</span>
              <span class="font-mono text-xs text-slate-700 mt-0.5">
                Batch #{{ receipt.batch_id }} ({{ receipt.batch?.status || 'imported' }})
              </span>
            </div>

            <div class="provenance-item">
              <span class="provenance-label">Imported At</span>
              <span class="text-xs text-slate-700 mt-0.5">
                {{ formatDateTime(receipt.batch?.imported_at || receipt.created_at) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="zen-modal-footer">
        <button type="button" class="btn-zen-secondary" @click="emit('close')">
          Close
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.zen-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  padding: 1rem;
}

.zen-modal-container {
  background: var(--bg-surface);
  border-radius: 0.5rem;
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 52rem;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-default);
}

.zen-modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-default);
  background: var(--bg-elevated);
}

.header-titles {
  display: flex;
  flex-direction: column;
}

.btn-close {
  color: var(--text-muted);
  padding: 0.25rem;
  border-radius: 0.25rem;
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
}

.btn-close:hover {
  color: var(--text-primary);
  background: var(--border-default);
}

.zen-modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.zen-summary-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr));
  gap: 0.75rem;
}

.zen-card {
  padding: 0.875rem 1rem;
  border-radius: 0.375rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.zen-card.highlight-card {
  background: var(--status-success-bg);
  border-color: var(--status-success-border);
}

.zen-card-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.zen-card-value {
  font-size: 0.9375rem;
  color: var(--text-primary);
}

.total-value {
  color: var(--status-success);
  font-weight: 600;
  font-size: 1.0625rem;
}

/* Direction badges */
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

/* Sections */
.zen-custom-fields-section,
.zen-line-items-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.zen-section-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.zen-custom-fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
}

.custom-field-item {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.field-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.field-value {
  font-size: 0.8125rem;
  color: var(--text-primary);
}

/* Table */
.zen-table-wrapper {
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  overflow-x: auto;
}

.zen-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.zen-table th {
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-weight: 600;
  text-align: left;
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid var(--border-default);
}

.zen-table td {
  padding: 0.625rem 0.75rem;
  border-bottom: 1px solid var(--border-default);
  color: var(--text-secondary);
}

.zen-table tr:last-child td { border-bottom: none; }
.zen-table tbody tr:hover td { background: var(--bg-elevated); }

.empty-line-items {
  padding: 1.5rem;
  text-align: center;
  background: var(--bg-elevated);
  border: 1px dashed var(--border-default);
  border-radius: 0.375rem;
  font-size: 0.8125rem;
  color: var(--text-muted);
}

/* Provenance */
.zen-provenance-section {
  padding: 0.875rem 1rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
}

.provenance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
  gap: 1rem;
}

.provenance-item {
  display: flex;
  flex-direction: column;
}

.provenance-label {
  font-size: 0.6875rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.btn-source-link {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: var(--accent-brand);
  font-weight: 500;
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  background: var(--accent-soft);
  transition: background-color 0.15s;
  text-decoration: none;
  border: 1px solid var(--accent-border);
}

.btn-source-link:hover { filter: brightness(1.1); }

/* Footer */
.zen-modal-footer {
  padding: 0.875rem 1.5rem;
  border-top: 1px solid var(--border-default);
  background: var(--bg-elevated);
  display: flex;
  justify-content: flex-end;
}

.btn-zen-secondary {
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 0.375rem;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-zen-secondary:hover {
  background: var(--bg-elevated);
  border-color: var(--border-strong);
}
</style>