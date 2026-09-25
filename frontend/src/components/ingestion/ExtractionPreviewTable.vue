<script setup lang="ts">
import { Code, FileSpreadsheet, Layers } from 'lucide-vue-next'
import StatusBadge from '@/components/common/StatusBadge.vue'
import type { ExtractedField, RowExtractionPreview } from '@/types/api'

withDefaults(
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

function formatRawValue(val: any): string {
  if (val === null || val === undefined) return '<Empty>'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatNormalizedValue(val: any, field?: ExtractedField): string {
  if (val === null || val === undefined) return '—'
  if (field && field.data_type === 'decimal' && typeof val === 'number') {
    return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(val)
}
</script>

<template>
  <div class="glass-card preview-card">
    <!-- Multi-Record Header -->
    <div v-if="isMultiRecord" class="preview-header">
      <div>
        <h3 class="preview-title">Multi-Record Data Rows & Cell Provenance</h3>
        <p class="preview-subtitle">
          Target worksheet: <span class="mono text-primary">{{ targetWorksheet }}</span>
        </p>
      </div>
      <span class="count-tag">{{ records.length }} Invoice Record(s) Extracted</span>
    </div>

    <!-- Single Invoice Header -->
    <div v-else class="preview-header">
      <div>
        <h3 class="preview-title">Extracted Invoice Header Fields</h3>
        <p class="preview-subtitle">
          Target worksheet: <span class="mono text-primary">{{ targetWorksheet }}</span>
        </p>
      </div>
      <span class="count-tag">{{ fields.length }} Header Fields Mapped</span>
    </div>

    <!-- Multi-Record Row Grid Table -->
    <div v-if="isMultiRecord" class="table-container">
      <table class="preview-table">
        <thead>
          <tr>
            <th>Row #</th>
            <th>Row Provenance</th>
            <th>Extracted Row Record</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="rec in records"
            :key="rec.source_row_number"
            :class="{
              'row-error': rec.has_errors,
              'row-warning': rec.warning_count > 0 && !rec.has_errors,
            }"
          >
            <!-- Row Number -->
            <td class="field-name-cell">
              <span class="coord-badge mono">
                <Layers :size="13" class="text-accent" />
                <span>Row {{ rec.source_row_number }}</span>
              </span>
            </td>

            <!-- Cell Provenance List -->
            <td class="provenance-cell">
              <div v-for="f in rec.fields" :key="f.field_name" class="coord-badge mono" style="font-size: 0.73rem;">
                <FileSpreadsheet :size="11" class="text-accent" />
                <span>{{ f.field_name }}: {{ f.source_cell_ref }}</span>
              </div>
            </td>

            <!-- Extracted Record Fields -->
            <td class="norm-val-cell">
              <div class="record-data-grid">
                <div v-for="(val, k) in rec.normalized_data" :key="k" class="data-chip">
                  <span class="data-key">{{ k }}:</span>
                  <span class="data-val">{{ formatNormalizedValue(val) }}</span>
                </div>
              </div>
              <div v-for="err in rec.errors" :key="err.message" class="field-error-text">
                {{ err.message }}
              </div>
            </td>

            <!-- Status Badge -->
            <td>
              <StatusBadge :status="rec.has_errors ? 'error' : (rec.warning_count > 0 ? 'warning' : 'success')" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Single-Invoice Header Grid Table -->
    <div v-else class="table-container">
      <table class="preview-table">
        <thead>
          <tr>
            <th>Field Name</th>
            <th>Cell Provenance</th>
            <th>Data Type</th>
            <th>Raw Excel Value</th>
            <th>Normalized Value</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="field in fields"
            :key="field.field_name"
            :class="{
              'row-error': field.status === 'error',
              'row-warning': field.status === 'warning',
            }"
          >
            <!-- Field Name & Required Flag -->
            <td class="field-name-cell">
              <div class="field-name-inner">
                <span class="field-label">{{ field.field_name }}</span>
                <span
                  v-if="field.is_required"
                  class="required-flag"
                  title="Required Field"
                >
                  Required
                </span>
                <span v-else class="optional-flag">Optional</span>
              </div>
            </td>

            <!-- Cell Provenance Coordinate -->
            <td class="provenance-cell">
              <div class="coord-badge mono">
                <FileSpreadsheet :size="13" class="text-accent" />
                <span>{{ field.source_worksheet }}!{{ field.source_cell_ref }}</span>
              </div>
              <div v-if="field.is_formula" class="formula-box mono" :title="`Formula: ${field.formula_expression || 'cached'}`">
                <Code :size="11" />
                <span>{{ field.formula_expression || 'Formula' }}</span>
              </div>
            </td>

            <!-- Target Data Type -->
            <td>
              <span class="type-pill mono">{{ field.data_type }}</span>
            </td>

            <!-- Raw Value -->
            <td class="raw-val-cell">
              <span
                class="mono text-truncate"
                :class="{ 'text-muted': field.raw_value === null }"
                :title="String(field.raw_value)"
              >
                {{ formatRawValue(field.raw_value) }}
              </span>
            </td>

            <!-- Normalized Value -->
            <td class="norm-val-cell">
              <span
                class="norm-value"
                :class="{ 'norm-null': field.normalized_value === null }"
              >
                {{ formatNormalizedValue(field.normalized_value, field) }}
              </span>
              <span v-if="field.error_message" class="field-error-text">
                {{ field.error_message }}
              </span>
              <span v-else-if="field.warning_message" class="field-warning-text">
                {{ field.warning_message }}
              </span>
            </td>

            <!-- Status Badge -->
            <td>
              <StatusBadge :status="field.status" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Line Items Table (When Invoice Template has Line Items) -->
    <div v-if="!isMultiRecord && hasLineItems" class="line-items-section" style="margin-top: 2rem;">
      <div class="preview-header">
        <div>
          <h3 class="preview-title">Extracted Invoice Line Items</h3>
          <p class="preview-subtitle">
            Repeating table breakdown (<span class="mono text-primary">{{ lineItems.length }} Line Item(s)</span> extracted)
          </p>
        </div>
        <span class="count-tag">{{ lineItems.length }} Line Items</span>
      </div>

      <div class="table-container">
        <table class="preview-table line-items-table">
          <colgroup>
            <col style="width: 100px;" />
            <col style="width: 200px;" />
            <col />
            <col style="width: 100px;" />
          </colgroup>
          <thead>
            <tr>
              <th>Row #</th>
              <th>Cell Coordinates</th>
              <th>Extracted Line Item Values</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="li in lineItems"
              :key="li.source_row_number"
              :class="{
                'row-error': li.has_errors,
                'row-warning': li.warning_count > 0 && !li.has_errors,
              }"
            >
              <td>
                <div class="li-row-label">
                  <Layers :size="13" class="text-accent" />
                  <span class="mono">Row {{ li.source_row_number }}</span>
                </div>
              </td>

              <td>
                <div class="li-coords-list">
                  <div v-for="f in li.fields" :key="f.field_name" class="coord-badge mono" style="font-size: 0.73rem;">
                    <FileSpreadsheet :size="11" class="text-accent" />
                    <span>{{ f.field_name }}: {{ f.source_cell_ref }}</span>
                  </div>
                </div>
              </td>

              <td>
                <div class="record-data-grid">
                  <div v-for="(val, k) in li.normalized_data" :key="k" class="data-chip">
                    <span class="data-key">{{ k }}:</span>
                    <span class="data-val">{{ formatNormalizedValue(val) }}</span>
                  </div>
                </div>
                <div v-for="err in li.errors" :key="err.message" class="field-error-text" style="margin-top: 0.35rem;">
                  {{ err.message }}
                </div>
              </td>

              <td style="text-align: center;">
                <StatusBadge :status="li.has_errors ? 'error' : (li.warning_count > 0 ? 'warning' : 'success')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.preview-card {
  padding: 1.5rem;
}

.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.25rem;
}

.preview-title {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-primary);
}

.preview-subtitle {
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.count-tag {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.25rem 0.65rem;
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

.table-container {
  overflow-x: auto;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--bg-card);
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.85rem;
}

.preview-table th {
  background: var(--bg-subtle);
  color: var(--text-secondary);
  font-weight: 600;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  white-space: nowrap;
}

.preview-table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: middle;
}

.preview-table tr:last-child td {
  border-bottom: none;
}

.preview-table tr:hover {
  background: rgba(255, 255, 255, 0.02);
}

.row-error {
  background: rgba(239, 68, 68, 0.04);
}

.row-warning {
  background: rgba(245, 158, 11, 0.04);
}

.field-name-cell {
  white-space: nowrap;
}

.field-name-inner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.field-label {
  font-weight: 600;
  color: var(--text-primary);
}

.required-flag {
  font-size: 0.68rem;
  font-weight: 600;
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}

.optional-flag {
  font-size: 0.68rem;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
}

.provenance-cell {
  vertical-align: top;
}

.coord-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.78rem;
  color: var(--text-primary);
}

.formula-box {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.7rem;
  color: var(--accent-cyan);
  background: var(--accent-cyan-subtle);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  max-width: 14rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.type-pill {
  font-size: 0.75rem;
  background: var(--bg-subtle);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
}

.raw-val-cell {
  max-width: 12rem;
}

.text-truncate {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.norm-val-cell {
  vertical-align: top;
}

.norm-value {
  font-weight: 600;
  color: var(--text-primary);
}

.norm-null {
  color: var(--text-muted);
  font-weight: 400;
}

.field-error-text {
  font-size: 0.75rem;
  color: var(--status-error);
}

.field-warning-text {
  font-size: 0.75rem;
  color: var(--status-warning);
}

.record-data-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

/* ── Line Items Table ──────────────────────────────────────────── */

.line-items-table {
  table-layout: fixed;
}

.li-row-label {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
}

.li-coords-list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.data-chip {
  display: inline-flex;
  gap: 0.25rem;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  padding: 0.2rem 0.5rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
}

.data-key {
  color: var(--text-muted);
  font-weight: 500;
}

.data-val {
  color: var(--text-primary);
  font-weight: 600;
}
</style>
