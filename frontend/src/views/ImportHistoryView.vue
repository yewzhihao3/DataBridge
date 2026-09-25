<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  Clock,
  Eye,
  FileSpreadsheet,
  History,
  Loader2,
  RefreshCw,
  Trash2,
  X,
  XCircle,
} from 'lucide-vue-next'

import ImportDetailsModal from '@/components/history/ImportDetailsModal.vue'
import { api } from '@/services/api'
import type {
  ApiError,
  ImportBatchDetail,
  ImportBatchListItem,
  InvoiceRecordUpdate,
} from '@/types/api'

const imports = ref<ImportBatchListItem[]>([])
const selectedImport = ref<ImportBatchDetail | null>(null)

const isLoading = ref(false)
const isLoadingDetails = ref(false)

const errorMessage = ref('')
const detailsError = ref('')

const searchQuery = ref('')
const statusFilter = ref('all')

const currentPage = ref(1)
const pageSize = 20

const hasNextPage = ref(false)

const filteredImports = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()

  return imports.value.filter((item) => {
    const matchesSearch =
      !query ||
      item.original_filename.toLowerCase().includes(query) ||
      item.template_name.toLowerCase().includes(query) ||
      String(item.id).includes(query)

    const matchesStatus =
      statusFilter.value === 'all' ||
      item.status.toLowerCase() === statusFilter.value.toLowerCase()

    return matchesSearch && matchesStatus
  })
})

const totalRecords = computed(() =>
  imports.value.reduce(
    (total, item) => total + item.record_count,
    0,
  ),
)

const totalWarnings = computed(() =>
  imports.value.reduce(
    (total, item) => total + item.warning_count,
    0,
  ),
)

const successfulImports = computed(() =>
  imports.value.filter((item) =>
    isSuccessfulStatus(item.status),
  ).length,
)

function isSuccessfulStatus(status: string): boolean {
  return [
    'success',
    'successful',
    'completed',
    'imported',
  ].includes(status.toLowerCase())
}

function getStatusClass(status: string): string {
  const normalizedStatus = status.toLowerCase()

  if (isSuccessfulStatus(normalizedStatus)) {
    return 'badge badge-success'
  }

  if (
    normalizedStatus.includes('fail') ||
    normalizedStatus.includes('error')
  ) {
    return 'badge badge-error'
  }

  if (
    normalizedStatus.includes('pending') ||
    normalizedStatus.includes('process')
  ) {
    return 'badge badge-warning'
  }

  return 'badge badge-neutral'
}

function getStatusIcon(status: string) {
  const normalizedStatus = status.toLowerCase()

  if (isSuccessfulStatus(normalizedStatus)) {
    return CheckCircle2
  }

  if (
    normalizedStatus.includes('fail') ||
    normalizedStatus.includes('error')
  ) {
    return XCircle
  }

  return Clock
}

function formatDate(dateString: string): string {
  if (!dateString) {
    return '—'
  }

  const date = new Date(dateString)

  if (Number.isNaN(date.getTime())) {
    return dateString
  }

  return new Intl.DateTimeFormat('en-MY', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function formatStatus(status: string): string {
  if (!status) {
    return 'Unknown'
  }

  return status
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (character) =>
      character.toUpperCase(),
    )
}



async function loadImports(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''

  try {
    const skip = (currentPage.value - 1) * pageSize

    const result = await api.listImportBatches(
      skip,
      pageSize + 1,
    )

    hasNextPage.value = result.length > pageSize

    imports.value = result.slice(0, pageSize)
  } catch (error: unknown) {
    const apiError = error as Partial<ApiError>

    errorMessage.value =
      apiError.message ||
      'Unable to load import history.'
  } finally {
    isLoading.value = false
  }
}

async function viewImportDetails(
  batchId: number,
): Promise<void> {
  selectedImport.value = null
  detailsError.value = ''
  isLoadingDetails.value = true

  try {
    selectedImport.value = await api.getImportBatch(batchId)
  } catch (error: unknown) {
    const apiError = error as Partial<ApiError>

    detailsError.value =
      apiError.message ||
      'Unable to load import details.'
  } finally {
    isLoadingDetails.value = false
  }
}

function closeDetails(): void {
  selectedImport.value = null
  detailsError.value = ''
}

async function refreshHistory(): Promise<void> {
  await loadImports()
}

async function goToPreviousPage(): Promise<void> {
  if (currentPage.value <= 1 || isLoading.value) return
  currentPage.value -= 1
  await loadImports()
}

async function goToNextPage(): Promise<void> {
  if (!hasNextPage.value || isLoading.value) return
  currentPage.value += 1
  await loadImports()
}

// ── Delete Batch State ─────────────────────────────────────────────────────
const batchToDelete = ref<ImportBatchListItem | null>(null)
const isDeleting = ref(false)
const deleteError = ref('')

function confirmDeleteBatch(item: ImportBatchListItem): void {
  batchToDelete.value = item
  deleteError.value = ''
}

function cancelDelete(): void {
  batchToDelete.value = null
  deleteError.value = ''
}

async function deleteBatch(): Promise<void> {
  if (!batchToDelete.value) return
  isDeleting.value = true
  deleteError.value = ''
  try {
    await api.deleteImportBatch(batchToDelete.value.id)
    // If the deleted batch was selected, close the detail panel
    if (selectedImport.value?.id === batchToDelete.value.id) {
      closeDetails()
    }
    batchToDelete.value = null
    await loadImports()
  } catch (error: unknown) {
    const apiError = error as Partial<ApiError>
    deleteError.value = apiError.message || 'Failed to delete import batch.'
  } finally {
    isDeleting.value = false
  }
}




async function handleSaveRecord(payload: { recordId: number; form: InvoiceRecordUpdate }): Promise<void> {
  if (!selectedImport.value) return
  try {
    const updated = await api.updateInvoiceRecord(
      selectedImport.value.id,
      payload.recordId,
      payload.form,
    )
    const idx = selectedImport.value.invoice_records.findIndex(
      (r) => r.id === updated.id,
    )
    if (idx !== -1) {
      selectedImport.value.invoice_records[idx] = updated
    }
  } catch (error: unknown) {
    const apiError = error as Partial<ApiError>
    throw new Error(apiError.message || 'Failed to save changes.')
  }
}

onMounted(() => {
  loadImports()
})
</script>

<template>
  <main class="history-page container">
    <!-- Page Header -->
    <section class="page-header">
      <div>
        <div class="eyebrow">
          <History :size="16" />
          DATA OPERATIONS
        </div>

        <h1>Import History</h1>

        <p class="page-description">
          Review previously imported files, processing results,
          and validation warnings.
        </p>
      </div>

      <button
        class="btn btn-secondary"
        type="button"
        :disabled="isLoading"
        @click="refreshHistory"
      >
        <RefreshCw
          :size="16"
          :class="{ 'animate-spin': isLoading }"
        />

        Refresh
      </button>
    </section>

    <!-- Summary Cards -->
    <section class="summary-grid">
      <div class="summary-card glass-card">
        <div class="summary-icon">
          <History :size="18" />
        </div>

        <div>
          <span class="summary-label">
            Imports Loaded
          </span>

          <strong>
            {{ imports.length }}
          </strong>
        </div>
      </div>

      <div class="summary-card glass-card">
        <div class="summary-icon success-icon">
          <CheckCircle2 :size="18" />
        </div>

        <div>
          <span class="summary-label">
            Successful
          </span>

          <strong class="success-text">
            {{ successfulImports }}
          </strong>
        </div>
      </div>

      <div class="summary-card glass-card">
        <div class="summary-icon">
          <FileSpreadsheet :size="18" />
        </div>

        <div>
          <span class="summary-label">
            Records Loaded
          </span>

          <strong>
            {{ totalRecords }}
          </strong>
        </div>
      </div>

      <div class="summary-card glass-card">
        <div class="summary-icon warning-icon">
          <AlertCircle :size="18" />
        </div>

        <div>
          <span class="summary-label">
            Warnings
          </span>

          <strong class="warning-text">
            {{ totalWarnings }}
          </strong>
        </div>
      </div>
    </section>

    <!-- Filters -->
    <section class="filters-card glass-card">
      <div class="filter-group">
        <label for="history-search">
          Search imports
        </label>

        <input
          id="history-search"
          v-model="searchQuery"
          class="filter-input"
          type="search"
          placeholder="Search filename, template, or batch ID..."
        />
      </div>

      <div class="filter-group status-filter">
        <label for="status-filter">
          Status
        </label>

        <select
          id="status-filter"
          v-model="statusFilter"
          class="filter-input"
        >
          <option value="all">
            All statuses
          </option>

          <option value="success">
            Success
          </option>

          <option value="completed">
            Completed
          </option>

          <option value="failed">
            Failed
          </option>

          <option value="pending">
            Pending
          </option>
        </select>
      </div>
    </section>

    <!-- Error State -->
    <div
      v-if="errorMessage"
      class="notice notice-error"
    >
      <AlertCircle :size="18" />

      <p>
        {{ errorMessage }}
      </p>

      <button
        class="btn btn-secondary btn-small"
        type="button"
        @click="loadImports"
      >
        Try Again
      </button>
    </div>

    <!-- Loading State -->
    <section
      v-if="isLoading"
      class="glass-card loading-card"
    >
      <Loader2
        :size="28"
        class="animate-spin"
      />

      <p>
        Loading import history...
      </p>
    </section>

    <!-- Empty State -->
    <section
      v-else-if="!errorMessage && filteredImports.length === 0"
      class="glass-card empty-card"
    >
      <History :size="42" />

      <h2>
        No imports found
      </h2>

      <p>
        No import records match your current filters.
      </p>
    </section>

    <!-- Import Table -->
    <section
      v-else-if="!isLoading"
      class="table-card glass-card"
    >
      <div class="table-header">
        <div>
          <h2>Recent Imports</h2>

          <p>
            Showing {{ filteredImports.length }} import records
          </p>
        </div>

        <span class="table-count">
          Page {{ currentPage }}
        </span>
      </div>

      <div class="table-wrapper">
        <table class="imports-table">
          <thead>
            <tr>
              <th>Batch</th>
              <th>Source File</th>
              <th>Template</th>
              <th>Status</th>
              <th>Records</th>
              <th>Warnings</th>
              <th>Imported At</th>
              <th class="actions-column">
                Action
              </th>
            </tr>
          </thead>

          <tbody>
            <tr
              v-for="item in filteredImports"
              :key="item.id"
            >
              <td>
                <span class="batch-id">
                  #{{ item.id }}
                </span>
              </td>

              <td>
                <div class="file-cell">
                  <FileSpreadsheet :size="17" />

                  <span
                    class="file-name"
                    :title="item.original_filename"
                  >
                    {{ item.original_filename }}
                  </span>
                </div>
              </td>

              <td>
                <span class="template-name">
                  {{ item.template_name }}
                </span>
              </td>

              <td>
                <span
                  :class="getStatusClass(item.status)"
                >
                  <component
                    :is="getStatusIcon(item.status)"
                    :size="13"
                  />

                  {{ formatStatus(item.status) }}
                </span>
              </td>

              <td>
                <span class="numeric-value">
                  {{ item.record_count }}
                </span>
              </td>

              <td>
                <span
                  :class="
                    item.warning_count > 0
                      ? 'warning-text'
                      : 'muted-value'
                  "
                >
                  {{ item.warning_count }}
                </span>
              </td>

              <td>
                <div class="date-cell">
                  <CalendarDays :size="14" />

                  {{ formatDate(item.imported_at) }}
                </div>
              </td>

              <td class="actions-column">
                <button
                  class="btn btn-secondary btn-small"
                  type="button"
                  :disabled="isLoadingDetails"
                  @click="viewImportDetails(item.id)"
                >
                  <Eye :size="14" />
                  View
                </button>

                <button
                  class="btn btn-danger btn-small"
                  type="button"
                  :disabled="isDeleting"
                  title="Delete Batch"
                  @click="confirmDeleteBatch(item)"
                >
                  <Trash2 :size="14" />
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination">
        <span class="pagination-info">
          Page {{ currentPage }}
        </span>

        <div class="pagination-actions">
          <button
            class="btn btn-secondary btn-small"
            type="button"
            :disabled="currentPage === 1 || isLoading"
            @click="goToPreviousPage"
          >
            Previous
          </button>

          <button
            class="btn btn-secondary btn-small"
            type="button"
            :disabled="!hasNextPage || isLoading"
            @click="goToNextPage"
          >
            Next
          </button>
        </div>
      </div>
    </section>

    <!-- Details Loading -->
    <div
      v-if="isLoadingDetails"
      class="details-overlay"
    >
      <div class="details-modal loading-modal">
        <Loader2
          :size="30"
          class="animate-spin"
        />

        <p>
          Loading import details...
        </p>
      </div>
    </div>

    <!-- Details Error -->
    <div
      v-if="detailsError"
      class="details-overlay"
      @click.self="closeDetails"
    >
      <div class="details-modal">
        <div class="modal-heading">
          <AlertCircle
            :size="22"
            class="error-text"
          />

          <h2>
            Unable to Load Details
          </h2>
        </div>

        <p class="modal-error">
          {{ detailsError }}
        </p>

        <button
          class="btn btn-secondary"
          type="button"
          @click="closeDetails"
        >
          Close
        </button>
      </div>
    </div>

    <!-- Import Details Modal -->
    <ImportDetailsModal
      v-if="selectedImport"
      :import-batch="selectedImport"
      :is-deleting="isDeleting"
      @close="closeDetails"
      @delete="confirmDeleteBatch"
      @save-record="handleSaveRecord"
    />

    <!-- Delete Confirmation Modal -->
    <div
      v-if="batchToDelete"
      class="details-overlay"
      @click.self="cancelDelete"
    >
      <div class="details-modal confirm-delete-modal">
        <div class="modal-heading">
          <div class="modal-title-with-icon">
            <AlertCircle :size="22" class="error-text" />
            <h2>Delete Import Batch</h2>
          </div>

          <button
            class="close-button"
            type="button"
            aria-label="Cancel deletion"
            @click="cancelDelete"
          >
            <X :size="20" />
          </button>
        </div>

        <p class="modal-description">
          Are you sure you want to delete batch <strong>#{{ batchToDelete.id }}</strong> (<em>{{ batchToDelete.original_filename }}</em>)?
        </p>

        <p class="modal-subtext">
          This soft-deletes the batch and excludes its {{ batchToDelete.record_count }} record(s) from history and reporting.
        </p>

        <div v-if="deleteError" class="modal-error">
          {{ deleteError }}
        </div>

        <div class="modal-actions">
          <button
            class="btn btn-secondary"
            type="button"
            :disabled="isDeleting"
            @click="cancelDelete"
          >
            Cancel
          </button>

          <button
            class="btn btn-danger"
            type="button"
            :disabled="isDeleting"
            @click="deleteBatch"
          >
            <Loader2 v-if="isDeleting" :size="15" class="animate-spin" />
            <Trash2 v-else :size="15" />
            {{ isDeleting ? 'Deleting...' : 'Delete Batch' }}
          </button>
        </div>
      </div>
    </div>
  </main>
</template>

<style scoped>
.history-page {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;

  padding-top: 2rem;
  padding-bottom: 2rem;
}

/* Page Header */

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.eyebrow {
  display: flex;
  align-items: center;
  gap: 0.4rem;

  margin-bottom: 0.5rem;

  color: var(--accent-brand);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.page-header h1 {
  margin: 0;

  color: var(--text-primary);
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -0.04em;
}

.page-description {
  max-width: 650px;
  margin-top: 0.5rem;

  color: var(--text-secondary);
  font-size: 0.95rem;
  line-height: 1.7;
}

/* Summary Cards */

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1rem;
}

.summary-card {
  display: flex;
  align-items: center;
  gap: 0.85rem;

  padding: 1.25rem;

  border: 1px solid var(--border-default);

  transition:
    border-color 0.2s ease,
    background 0.2s ease,
    transform 0.2s ease;
}

.summary-card:hover {
  border-color: var(--border-medium);
  background: var(--bg-card-hover);
  transform: translateY(-2px);
}

.summary-icon {
  display: flex;
  align-items: center;
  justify-content: center;

  width: 2.5rem;
  height: 2.5rem;

  border-radius: var(--radius-md);

  background: var(--bg-subtle);
  color: var(--accent-brand);
}

.success-icon {
  color: var(--status-success);
}

.warning-icon {
  color: var(--status-warning);
}

.summary-label {
  display: block;
  margin-bottom: 0.25rem;

  color: var(--text-muted);
  font-size: 0.78rem;
}

.summary-card strong {
  color: var(--text-primary);
  font-size: 1.35rem;
  font-weight: 800;
}

/* Filters */

.filters-card {
  display: flex;
  align-items: flex-end;
  gap: 1rem;

  padding: 1.25rem;
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  flex: 1;
}

.filter-group label {
  color: var(--text-secondary);
  font-size: 0.8rem;
  font-weight: 600;
}

.status-filter {
  max-width: 220px;
}

.filter-input {
  width: 100%;
  min-height: 2.6rem;

  padding: 0.65rem 0.8rem;

  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);

  background: var(--bg-input);
  color: var(--text-primary);

  font: inherit;
  font-size: 0.85rem;
}

.filter-input:focus {
  outline: none;
  border-color: var(--accent-brand);
}

/* Notices */

.notice {
  display: flex;
  align-items: center;
  gap: 0.75rem;

  padding: 1rem;

  border-radius: var(--radius-sm);

  font-size: 0.85rem;
}

.notice p {
  flex: 1;
  margin: 0;
}

.notice-error {
  border: 1px solid var(--status-error-border);
  background: var(--status-error-bg);
  color: var(--status-error);
}

.btn-small {
  min-height: 2rem;
  padding: 0.45rem 0.7rem;

  font-size: 0.75rem;
}

/* Loading and Empty States */

.loading-card,
.empty-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;

  gap: 0.75rem;

  min-height: 220px;
  padding: 2rem;

  text-align: center;
}

.loading-card {
  color: var(--accent-brand);
}

.empty-card {
  color: var(--text-muted);
}

.empty-card h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 1.2rem;
}

.empty-card p {
  margin: 0;
  font-size: 0.85rem;
}

/* Table */

.table-card {
  overflow: hidden;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;

  padding: 1.5rem;

  border-bottom: 1px solid var(--border-default);
}

.table-header h2 {
  margin: 0;

  color: var(--text-primary);
  font-size: 1.05rem;
}

.table-header p {
  margin-top: 0.3rem;

  color: var(--text-muted);
  font-size: 0.8rem;
}

.table-count {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.table-wrapper {
  overflow-x: auto;
}

.imports-table {
  width: 100%;
  min-width: 1050px;

  border-collapse: collapse;

  font-size: 0.82rem;
}

.imports-table th {
  padding: 0.9rem 1rem;

  background: var(--bg-subtle);

  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.imports-table td {
  padding: 1rem;

  border-top: 1px solid var(--border-subtle);

  color: var(--text-secondary);
  vertical-align: middle;
}

.imports-table tbody tr {
  transition: background 0.2s ease;
}

.imports-table tbody tr:hover {
  background: var(--bg-card-hover);
}

.actions-column {
  text-align: right !important;
}

td.actions-column {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.batch-id {
  color: var(--accent-brand);
  font-family: var(--font-mono);
  font-weight: 700;
}

.file-cell {
  display: flex;
  align-items: center;
  gap: 0.5rem;

  max-width: 230px;

  color: var(--text-secondary);
}

.file-name {
  overflow: hidden;

  color: var(--text-primary);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-name {
  color: var(--text-secondary);
}

.numeric-value {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.muted-value {
  color: var(--text-muted);
}

.date-cell {
  display: flex;
  align-items: center;
  gap: 0.4rem;

  min-width: 160px;

  color: var(--text-muted);
  font-size: 0.75rem;
}

/* Status Badge */

.badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;

  white-space: nowrap;
}

/* Pagination */

.pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;

  padding: 1rem 1.5rem;

  border-top: 1px solid var(--border-default);
}

.pagination-info {
  color: var(--text-muted);
  font-size: 0.8rem;
}

.pagination-actions {
  display: flex;
  gap: 0.5rem;
}

/* Details Modal */

.details-overlay {
  position: fixed;
  z-index: 100;

  inset: 0;

  display: flex;
  align-items: center;
  justify-content: center;

  padding: 1.5rem;

  background: rgba(3, 7, 18, 0.78);
  backdrop-filter: blur(5px);
}

.details-modal {
  width: 100%;
  max-width: 760px;
  max-height: 90vh;

  overflow-y: auto;

  padding: 1.5rem;

  border: 1px solid var(--border-medium);
  border-radius: var(--radius-lg);

  background: var(--bg-card);
  box-shadow: var(--shadow-lg);
}

.loading-modal {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;

  max-width: 320px;

  color: var(--accent-brand);
}

.loading-modal p {
  margin: 0;
  color: var(--text-secondary);
}

.modal-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;

  margin-bottom: 1.25rem;
}

.modal-heading h2 {
  margin: 0;

  color: var(--text-primary);
  font-size: 1.3rem;
}

.close-button {
  display: flex;
  align-items: center;
  justify-content: center;

  padding: 0.25rem;

  border: 0;
  background: transparent;

  color: var(--text-muted);
  cursor: pointer;
}

.close-button:hover {
  color: var(--text-primary);
}

.modal-error {
  margin-bottom: 1.25rem;
  color: var(--status-error);
  font-size: 0.85rem;
}

.detail-file {
  display: flex;
  align-items: center;
  gap: 0.75rem;

  padding: 1rem;

  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);

  background: var(--bg-subtle);
  color: var(--accent-brand);
}

.detail-file strong,
.detail-file span {
  display: block;
}

.detail-file strong {
  overflow: hidden;

  color: var(--text-primary);
  font-size: 0.9rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-file span {
  margin-top: 0.2rem;

  color: var(--text-muted);
  font-size: 0.78rem;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;

  margin-top: 1rem;
}

.detail-item {
  padding: 1rem;

  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);

  background: var(--bg-subtle);
}

.detail-item span,
.detail-item strong {
  display: block;
}

.detail-item span {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.detail-item strong {
  margin-top: 0.3rem;

  color: var(--text-primary);
  font-size: 0.85rem;
}

/* Detail Sections */

.detail-section {
  margin-top: 1.5rem;
}

.detail-section h3 {
  margin-bottom: 0.75rem;

  color: var(--text-primary);
  font-size: 0.95rem;
}

.record-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.record-item,
.validation-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;

  padding: 0.8rem;

  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);

  background: var(--bg-subtle);
}

.record-view-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 1rem;
}

.record-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.record-meta-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.record-amount {
  color: var(--text-primary);
  font-size: 0.9rem;
  font-weight: 700;
  font-family: var(--font-mono);
  white-space: nowrap;
}

/* Custom Field Chips */
.custom-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.35rem;
}

.custom-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.45rem;
  background: var(--bg-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  font-size: 0.72rem;
  color: var(--text-secondary);
}

.custom-chip strong {
  color: var(--accent-brand);
  font-weight: 600;
}

.custom-fields-box {
  padding: 0.5rem 0.75rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  margin: 0.35rem 0;
}

.custom-fields-title {
  display: block;
  margin-bottom: 0.25rem;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
}

/* In-line Record Edit Form */
.record-edit-form {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
  padding: 0.25rem 0;
}

.edit-form-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}

.edit-fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.6rem;
}

.edit-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.edit-field span {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 600;
}

.edit-field input {
  padding: 0.4rem 0.55rem;
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  font-size: 0.82rem;
}

.edit-field input:focus {
  outline: none;
  border-color: var(--accent-brand);
  box-shadow: 0 0 0 2px var(--accent-brand-subtle, rgba(99, 102, 241, 0.2));
}

.edit-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.25rem;
}

.detail-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.detail-section-header h3 {
  margin-bottom: 0;
}

.record-item strong,
.record-item span,
.validation-item strong,
.validation-item span {
  display: block;
}

.record-item strong,
.validation-item strong {
  color: var(--text-primary);
  font-size: 0.8rem;
}

.record-item span,
.validation-item span {
  margin-top: 0.2rem;

  color: var(--text-muted);
  font-size: 0.75rem;
}

.validation-item > span {
  margin-top: 0;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 0.75rem;

  margin-top: 1.5rem;
}

.modal-actions.space-between {
  justify-content: space-between;
}

.confirm-delete-modal {
  max-width: 480px;
}

.modal-title-with-icon {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.modal-title-with-icon h2 {
  margin: 0;
  font-size: 1.25rem;
}

.modal-description {
  margin-top: 1rem;
  color: var(--text-primary);
  font-size: 0.95rem;
  line-height: 1.5;
}

.modal-subtext {
  margin-top: 0.5rem;
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.5;
}

/* Animations */

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* Responsive */

@media (max-width: 1000px) {
  .summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .history-page {
    padding-top: 1rem;
    padding-bottom: 1rem;
  }

  .page-header {
    flex-direction: column;
  }

  .filters-card {
    flex-direction: column;
    align-items: stretch;
  }

  .status-filter {
    max-width: none;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }

  .details-overlay {
    padding: 0.75rem;
  }

  .details-modal {
    padding: 1rem;
  }
}

@media (max-width: 480px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }

  .summary-card {
    padding: 1rem;
  }

  .pagination {
    align-items: flex-start;
    flex-direction: column;
  }

  .pagination-actions {
    width: 100%;
  }

  .pagination-actions .btn {
    flex: 1;
  }
}
</style>