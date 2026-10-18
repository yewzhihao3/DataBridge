<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  AlertCircle,
  Check,
  FileText,
  Link as LinkIcon,
  Loader2,
  Receipt,
  Search,
  X,
} from 'lucide-vue-next'

import { api } from '@/services/api'
import type {
  EntityType,
  RelationshipCreateRequest,
  RelationshipRead,
  RelationshipType,
  UnifiedDocumentListItem,
} from '@/types/api'

const props = defineProps<{
  isOpen: boolean
  focalEntityType: EntityType
  focalEntityId: number
  focalTitle?: string
  alreadyLinkedKeys?: string[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'linked', relationship: RelationshipRead): void
}>()

// ── Search & Filter State ───────────────────────────────────────────────────
const searchQuery = ref('')
const docTypeFilter = ref<'all' | 'invoice' | 'receipt'>('all')
const searchResults = ref<UnifiedDocumentListItem[]>([])
const isLoading = ref(false)
const searchError = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// ── Selection & Form State ──────────────────────────────────────────────────
const selectedCandidate = ref<UnifiedDocumentListItem | null>(null)
const selectedRelType = ref<RelationshipType>('related_to')
const supportDirection = ref<'candidate_supports_focal' | 'focal_supports_candidate'>('candidate_supports_focal')
const isSubmitting = ref(false)
const submitError = ref('')

// ── Debounced Search ────────────────────────────────────────────────────────
async function executeSearch() {
  if (!props.isOpen) return
  isLoading.value = true
  searchError.value = ''
  try {
    const res = await api.listDataExplorerDocuments({
      search: searchQuery.value.trim() || undefined,
      document_type: docTypeFilter.value !== 'all' ? docTypeFilter.value : undefined,
      page: 1,
      page_size: 15,
      sort_by: 'document_date',
      sort_order: 'desc',
    })
    searchResults.value = res.items
  } catch (err: any) {
    searchError.value = err.message || 'Failed to search documents.'
  } finally {
    isLoading.value = false
  }
}

function handleSearchInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    executeSearch()
  }, 250)
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      searchQuery.value = ''
      docTypeFilter.value = 'all'
      selectedCandidate.value = null
      selectedRelType.value = 'related_to'
      supportDirection.value = 'candidate_supports_focal'
      submitError.value = ''
      searchError.value = ''
      executeSearch()
    }
  },
  { immediate: true },
)

watch(docTypeFilter, () => {
  executeSearch()
})

// ── Validation Helpers ──────────────────────────────────────────────────────
function isSelf(item: UnifiedDocumentListItem): boolean {
  return item.document_type === props.focalEntityType && item.record_id === props.focalEntityId
}

function isAlreadyLinked(item: UnifiedDocumentListItem): boolean {
  const key = `${item.document_type}_${item.record_id}`
  return !!props.alreadyLinkedKeys?.includes(key)
}

function isSelectable(item: UnifiedDocumentListItem): boolean {
  return !isSelf(item) && !isAlreadyLinked(item)
}

function selectCandidate(item: UnifiedDocumentListItem) {
  if (!isSelectable(item)) return
  selectedCandidate.value = item
  submitError.value = ''
}

// ── Submit Link Creation ────────────────────────────────────────────────────
async function handleSubmit() {
  if (!selectedCandidate.value || !isSelectable(selectedCandidate.value)) return
  isSubmitting.value = true
  submitError.value = ''

  try {
    let payload: RelationshipCreateRequest

    if (selectedRelType.value === 'related_to') {
      payload = {
        source_type: props.focalEntityType,
        source_id: props.focalEntityId,
        target_type: selectedCandidate.value.document_type as EntityType,
        target_id: selectedCandidate.value.record_id,
        relationship_type: 'related_to',
      }
    } else {
      // supports (directional)
      if (supportDirection.value === 'candidate_supports_focal') {
        payload = {
          source_type: selectedCandidate.value.document_type as EntityType,
          source_id: selectedCandidate.value.record_id,
          target_type: props.focalEntityType,
          target_id: props.focalEntityId,
          relationship_type: 'supports',
        }
      } else {
        payload = {
          source_type: props.focalEntityType,
          source_id: props.focalEntityId,
          target_type: selectedCandidate.value.document_type as EntityType,
          target_id: selectedCandidate.value.record_id,
          relationship_type: 'supports',
        }
      }
    }

    const created = await api.createRelationship(payload)
    emit('linked', created)
    emit('close')
  } catch (err: any) {
    if (err.status === 409) {
      submitError.value = 'These two documents are already linked.'
    } else if (err.status === 422) {
      submitError.value = err.message || 'Cannot link a document to itself or invalid entity.'
    } else if (err.status === 404) {
      submitError.value = 'Candidate document was not found or is outside your workspace.'
    } else {
      submitError.value = err.message || 'Failed to establish relationship.'
    }
  } finally {
    isSubmitting.value = false
  }
}

// ── Formatting Helpers ──────────────────────────────────────────────────────
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

function formatAmount(amt?: number | string | null, cur?: string | null): string {
  if (amt === null || amt === undefined || amt === '') return ''
  const num = Number(amt)
  if (isNaN(num)) return String(amt)
  const val = num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return cur ? `${cur} ${val}` : val
}
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="zen-modal-overlay" @click.self="emit('close')">
      <div class="zen-modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-link-title">
      <!-- Header -->
      <header class="zen-modal-header">
        <div class="header-content">
          <div class="header-icon-wrap">
            <LinkIcon :size="18" />
          </div>
          <div>
            <h2 id="modal-link-title" class="zen-modal-title">Link Document</h2>
            <p class="zen-modal-sub">
              Connect to: <span class="text-accent">{{ focalTitle || `${focalEntityType} #${focalEntityId}` }}</span>
            </p>
          </div>
        </div>
        <button
          type="button"
          class="btn-close-zen"
          @click="emit('close')"
          aria-label="Close modal"
        >
          <X :size="18" />
        </button>
      </header>

      <!-- Body -->
      <div class="zen-modal-body">
        <!-- Search & Filter Controls -->
        <div class="search-filter-row">
          <div class="search-input-wrap">
            <Search :size="15" class="search-icon" />
            <input
              v-model="searchQuery"
              type="text"
              class="zen-search-input"
              placeholder="Search by number, counterparty, amount..."
              @input="handleSearchInput"
            />
          </div>

          <div class="type-filter-group" role="radiogroup" aria-label="Filter by type">
            <button
              type="button"
              class="btn-type-filter"
              :class="{ active: docTypeFilter === 'all' }"
              @click="docTypeFilter = 'all'"
            >
              All
            </button>
            <button
              type="button"
              class="btn-type-filter"
              :class="{ active: docTypeFilter === 'invoice' }"
              @click="docTypeFilter = 'invoice'"
            >
              Invoices
            </button>
            <button
              type="button"
              class="btn-type-filter"
              :class="{ active: docTypeFilter === 'receipt' }"
              @click="docTypeFilter = 'receipt'"
            >
              Receipts
            </button>
          </div>
        </div>

        <!-- Search Results List -->
        <div class="candidates-container">
          <div v-if="isLoading" class="zen-loading-box">
            <Loader2 :size="20" class="spinner" />
            <span>Searching workspace documents...</span>
          </div>

          <div v-else-if="searchError" class="zen-alert zen-alert-error">
            <AlertCircle :size="15" />
            <span>{{ searchError }}</span>
          </div>

          <div v-else-if="searchResults.length === 0" class="zen-empty-box">
            <span>No documents match your query.</span>
          </div>

          <div v-else class="candidates-list">
            <div
              v-for="item in searchResults"
              :key="`${item.document_type}_${item.record_id}`"
              class="candidate-row"
              :class="{
                selected: selectedCandidate?.document_type === item.document_type && selectedCandidate?.record_id === item.record_id,
                disabled: !isSelectable(item),
              }"
              @click="selectCandidate(item)"
            >
              <div class="row-left">
                <span class="type-badge" :class="item.document_type">
                  <FileText v-if="item.document_type === 'invoice'" :size="12" />
                  <Receipt v-else :size="12" />
                  <span>{{ item.document_type === 'invoice' ? 'Invoice' : 'Receipt' }}</span>
                </span>
                <span class="doc-num">{{ item.document_number || `ID #${item.record_id}` }}</span>
                <span class="counterparty">{{ item.counterparty }}</span>
              </div>

              <div class="row-right">
                <span v-if="isSelf(item)" class="status-pill self">Current</span>
                <span v-else-if="isAlreadyLinked(item)" class="status-pill linked">Linked</span>
                <template v-else>
                  <span class="doc-date">{{ formatDate(item.document_date) }}</span>
                  <span v-if="item.total_amount" class="doc-amount">
                    {{ formatAmount(item.total_amount, item.currency) }}
                  </span>
                  <div class="radio-indicator">
                    <Check
                      v-if="selectedCandidate?.document_type === item.document_type && selectedCandidate?.record_id === item.record_id"
                      :size="12"
                    />
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Relationship Configuration (when candidate selected) -->
        <div v-if="selectedCandidate" class="relationship-config-box">
          <h3 class="config-heading">Select Relationship Type</h3>

          <div class="rel-type-options">
            <label
              class="rel-type-card"
              :class="{ active: selectedRelType === 'related_to' }"
            >
              <input
                v-model="selectedRelType"
                type="radio"
                value="related_to"
                class="sr-only"
              />
              <div class="card-radio">
                <div class="radio-dot" />
              </div>
              <div class="card-info">
                <span class="card-title">Related Document</span>
                <span class="card-desc">
                  These documents are associated with the same business activity (symmetric).
                </span>
              </div>
            </label>

            <label
              class="rel-type-card"
              :class="{ active: selectedRelType === 'supports' }"
            >
              <input
                v-model="selectedRelType"
                type="radio"
                value="supports"
                class="sr-only"
              />
              <div class="card-radio">
                <div class="radio-dot" />
              </div>
              <div class="card-info">
                <span class="card-title">Supporting Document</span>
                <span class="card-desc">
                  One document provides supporting evidence for another (directional).
                </span>
              </div>
            </label>
          </div>

          <!-- Direction options for supports -->
          <div v-if="selectedRelType === 'supports'" class="supports-direction-selector">
            <span class="dir-title">Direction of Support:</span>
            <div class="dir-options">
              <label class="dir-option">
                <input
                  v-model="supportDirection"
                  type="radio"
                  value="candidate_supports_focal"
                />
                <span>
                  <strong>{{ selectedCandidate.document_number || `${selectedCandidate.document_type} #${selectedCandidate.record_id}` }}</strong>
                  supports
                  <strong>{{ focalTitle || `${focalEntityType} #${focalEntityId}` }}</strong>
                </span>
              </label>

              <label class="dir-option">
                <input
                  v-model="supportDirection"
                  type="radio"
                  value="focal_supports_candidate"
                />
                <span>
                  <strong>{{ focalTitle || `${focalEntityType} #${focalEntityId}` }}</strong>
                  supports
                  <strong>{{ selectedCandidate.document_number || `${selectedCandidate.document_type} #${selectedCandidate.record_id}` }}</strong>
                </span>
              </label>
            </div>
          </div>

          <div v-if="submitError" class="zen-alert zen-alert-error" role="alert">
            <AlertCircle :size="15" />
            <span>{{ submitError }}</span>
          </div>
        </div>
      </div>

      <!-- Footer Actions -->
      <footer class="zen-modal-footer">
        <button
          type="button"
          class="btn-zen-secondary"
          :disabled="isSubmitting"
          @click="emit('close')"
        >
          Cancel
        </button>

        <button
          type="button"
          class="btn-zen-primary"
          :disabled="!selectedCandidate || isSubmitting"
          @click="handleSubmit"
        >
          <Loader2 v-if="isSubmitting" :size="14" class="spinner" />
          <LinkIcon v-else :size="14" />
          <span>{{ isSubmitting ? 'Linking...' : 'Establish Link' }}</span>
        </button>
      </footer>
    </div>
  </div>
  </Teleport>
</template>

<style scoped>
.zen-modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background-color: var(--overlay);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.zen-modal-card {
  width: 100%;
  max-width: 680px;
  max-height: 90vh;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  color: var(--text-primary);
}

.zen-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--border-subtle);
}

.header-content {
  display: flex;
  align-items: center;
  gap: 0.875rem;
}

.header-icon-wrap {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--accent-border);
}

.zen-modal-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
}

.zen-modal-sub {
  margin: 0.2rem 0 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
}

.text-accent {
  color: var(--accent);
  font-weight: 500;
}

.btn-close-zen {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0.5rem;
  border-radius: 8px;
  transition: all 0.15s ease;
}

.btn-close-zen:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.zen-modal-body {
  padding: 1.25rem 1.5rem;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.search-filter-row {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.search-input-wrap {
  position: relative;
  flex: 1;
  min-width: 220px;
}

.search-icon {
  position: absolute;
  left: 0.75rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
}

.zen-search-input {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 0.5rem 0.75rem 0.5rem 2.25rem;
  font-size: 0.8125rem;
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s ease;
}

.zen-search-input:focus {
  border-color: var(--accent);
}

.type-filter-group {
  display: inline-flex;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 2px;
}

.btn-type-filter {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.35rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-type-filter.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.candidates-container {
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  background: var(--bg-subtle);
}

.zen-loading-box,
.zen-empty-box {
  padding: 2rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.candidates-list {
  display: flex;
  flex-direction: column;
}

.candidate-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 0.875rem;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background-color 0.15s ease;
  font-size: 0.8125rem;
  color: var(--text-primary);
}

.candidate-row:last-child {
  border-bottom: none;
}

.candidate-row:hover:not(.disabled) {
  background: var(--bg-card-hover);
}

.candidate-row.selected {
  background: var(--accent-soft);
  border-color: var(--accent-border);
}

.candidate-row.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.row-left {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  overflow: hidden;
}

.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.type-badge.invoice {
  background: var(--status-info-bg, rgba(56, 189, 248, 0.15));
  color: var(--status-info, #38bdf8);
  border: 1px solid var(--status-info-border, rgba(56, 189, 248, 0.3));
}

.type-badge.receipt {
  background: var(--status-success-bg, rgba(52, 211, 153, 0.15));
  color: var(--status-success, #34d399);
  border: 1px solid var(--status-success-border, rgba(52, 211, 153, 0.3));
}

.doc-num {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.counterparty {
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.row-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
}

.doc-date {
  color: var(--text-muted);
}

.doc-amount {
  font-family: monospace;
  font-weight: 500;
  color: var(--text-primary);
}

.status-pill {
  font-size: 0.6875rem;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  font-weight: 500;
}

.status-pill.self {
  background: var(--bg-elevated);
  color: var(--text-muted);
  border: 1px solid var(--border-subtle);
}

.status-pill.linked {
  background: var(--status-warning-bg, rgba(251, 191, 36, 0.12));
  color: var(--status-warning, #fbbf24);
  border: 1px solid var(--status-warning-border, rgba(251, 191, 36, 0.3));
}

.radio-indicator {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid var(--border-medium);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
}

.candidate-row.selected .radio-indicator {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.relationship-config-box {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.config-heading {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.rel-type-options {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.rel-type-card {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  padding: 0.75rem;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.rel-type-card:hover {
  border-color: var(--border-strong);
}

.rel-type-card.active {
  background: var(--accent-soft);
  border-color: var(--accent);
}

.card-radio {
  margin-top: 0.15rem;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--border-medium);
  display: flex;
  align-items: center;
  justify-content: center;
}

.rel-type-card.active .card-radio {
  border-color: var(--accent);
}

.radio-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0;
}

.rel-type-card.active .radio-dot {
  opacity: 1;
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.card-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--text-primary);
}

.card-desc {
  font-size: 0.75rem;
  color: var(--text-secondary);
  line-height: 1.35;
}

.supports-direction-selector {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.dir-title {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
}

.dir-options {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.dir-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.zen-alert {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.875rem;
  border-radius: 6px;
  font-size: 0.8125rem;
}

.zen-alert-error {
  background: var(--status-error-bg, rgba(239, 68, 68, 0.12));
  border: 1px solid var(--status-error-border, rgba(239, 68, 68, 0.3));
  color: var(--status-error, #fb7185);
}

.zen-modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-surface);
}

.btn-zen-secondary {
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-zen-secondary:hover:not(:disabled) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-zen-primary {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: var(--on-accent);
  padding: 0.5rem 1.125rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.15s ease;
}

.btn-zen-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-zen-primary:disabled,
.btn-zen-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinner {
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
