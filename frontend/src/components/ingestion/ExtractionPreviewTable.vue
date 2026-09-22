<script setup lang="ts">
import { Code, FileSpreadsheet } from 'lucide-vue-next'
import StatusBadge from '@/components/common/StatusBadge.vue'
import type { ExtractedField } from '@/types/api'

defineProps<{
  fields: ExtractedField[]
  targetWorksheet: string
}>()

function formatRawValue(val: any): string {
  if (val === null || val === undefined) return '<Empty>'
  if (typeof val === 'object') return JSON.stringify(val)
  return String(val)
}

function formatNormalizedValue(val: any, field: ExtractedField): string {
  if (val === null || val === undefined) return '—'
  if (field.data_type === 'decimal' && typeof val === 'number') {
    return val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(val)
}
</script>

<template>
  <div class="glass-card preview-card">
    <div class="preview-header">
      <div>
        <h3 class="preview-title">Extracted Field Values & Cell Provenance</h3>
        <p class="preview-subtitle">
          Target worksheet: <span class="mono text-primary">{{ targetWorksheet }}</span>
        </p>
      </div>
      <span class="count-tag">{{ fields.length }} Fields Mapped</span>
    </div>

    <!-- Extraction Grid Table -->
    <div class="table-container">
      <table class="preview-table">
        <thead>
          <tr>
            <th>Field Name</th>
            <th>Cell Provenance</th>
            <th>Data Type</th>
            <th>Raw Excel Value</th>
            <th>Normalized Typed Value</th>
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
              <span class="field-label">{{ field.field_name }}</span>
              <span
                v-if="field.is_required"
                class="required-flag"
                title="Required Field"
              >
                Required
              </span>
              <span v-else class="optional-flag">Optional</span>
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
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
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
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
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
</style>
