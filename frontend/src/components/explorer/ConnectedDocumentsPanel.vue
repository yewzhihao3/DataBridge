<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Eye,
  FileCheck,
  FileText,
  Layers,
  Link2,
  Link2Off,
  Loader2,
  Plus,
  Receipt,
  Sparkles,
  X,
} from 'lucide-vue-next'

import LinkDocumentModal from '@/components/explorer/LinkDocumentModal.vue'
import { api } from '@/services/api'
import type {
  EntityType,
  MatchCategory,
  RelationshipCreateRequest,
  RelationshipRead,
  SuggestionItem,
} from '@/types/api'

const props = defineProps<{
  entityType: EntityType
  entityId: number
  entityTitle?: string
}>()

const emit = defineEmits<{
  (e: 'view-related', payload: { type: EntityType; id: number }): void
  (e: 'count-changed', count: number): void
  (e: 'relationship-mutated', payload: { action: 'linked' | 'unlinked'; partnerType: EntityType; partnerId: number }): void
}>()

// ── Tab State ───────────────────────────────────────────────────────────────
const activeTab = ref<'confirmed' | 'suggestions'>('confirmed')

// ── Confirmed Relationships State ───────────────────────────────────────────
const relationships = ref<RelationshipRead[]>([])
const isLoadingRelationships = ref(false)
const relationshipsError = ref('')

// ── Suggestions State ───────────────────────────────────────────────────────
const suggestions = ref<SuggestionItem[]>([])
const isLoadingSuggestions = ref(false)
const suggestionsError = ref('')
const dismissedSuggestionKeys = ref<Set<string>>(new Set())

// ── Modals & Dialog State ───────────────────────────────────────────────────
const isLinkModalOpen = ref(false)
const unlinkTarget = ref<RelationshipRead | null>(null)
const isUnlinking = ref(false)
const unlinkError = ref('')

// Feedback toast / alert inside panel
const actionFeedback = ref<{ type: 'success' | 'error'; message: string } | null>(null)

// ── Computed Properties ─────────────────────────────────────────────────────
const activeSuggestions = computed(() => {
  return suggestions.value.filter((s) => {
    const key = `${s.candidate_type}_${s.candidate_id}`
    return !dismissedSuggestionKeys.value.has(key) && !s.is_already_linked
  })
})

const alreadyLinkedKeys = computed(() => {
  return relationships.value.map((r) => `${r.related_entity.entity_type}_${r.related_entity.entity_id}`)
})

// ── Fetch Functions ─────────────────────────────────────────────────────────
async function fetchRelationships() {
  if (!props.entityId) return
  isLoadingRelationships.value = true
  relationshipsError.value = ''
  try {
    const res = await api.getRelationships(props.entityType, props.entityId)
    relationships.value = res.items
    emit('count-changed', res.total)
  } catch (err: any) {
    relationshipsError.value = err.message || 'Failed to load connected documents.'
  } finally {
    isLoadingRelationships.value = false
  }
}

async function fetchSuggestions() {
  if (!props.entityId) return
  isLoadingSuggestions.value = true
  suggestionsError.value = ''
  try {
    const res = await api.getRelationshipSuggestions(props.entityType, props.entityId, 15)
    suggestions.value = res.suggestions
  } catch (err: any) {
    suggestionsError.value = err.message || 'Failed to load document suggestions.'
  } finally {
    isLoadingSuggestions.value = false
  }
}

async function refreshAll() {
  await Promise.all([fetchRelationships(), fetchSuggestions()])
}

watch(
  () => [props.entityType, props.entityId],
  () => {
    dismissedSuggestionKeys.value.clear()
    actionFeedback.value = null
    refreshAll()
  },
  { immediate: true },
)

// ── Unlink Actions ──────────────────────────────────────────────────────────
function promptUnlink(rel: RelationshipRead) {
  unlinkTarget.value = rel
  unlinkError.value = ''
}

function cancelUnlink() {
  unlinkTarget.value = null
  unlinkError.value = ''
}

async function confirmUnlink() {
  if (!unlinkTarget.value) return
  isUnlinking.value = true
  unlinkError.value = ''
  const partner = unlinkTarget.value.related_entity

  try {
    await api.deleteRelationship(unlinkTarget.value.id)
    showFeedback('success', 'Document relationship removed. Underlying records remain unchanged.')
    if (partner) {
      emit('relationship-mutated', {
        action: 'unlinked',
        partnerType: partner.entity_type,
        partnerId: partner.entity_id,
      })
    }
    unlinkTarget.value = null
    await refreshAll()
  } catch (err: any) {
    unlinkError.value = err.message || 'Failed to remove relationship.'
  } finally {
    isUnlinking.value = false
  }
}

// ── Suggestion Actions ──────────────────────────────────────────────────────
const linkingSuggestionKey = ref<string | null>(null)

async function linkSuggestion(item: SuggestionItem) {
  const key = `${item.candidate_type}_${item.candidate_id}`
  linkingSuggestionKey.value = key
  try {
    const payload: RelationshipCreateRequest = {
      source_type: props.entityType,
      source_id: props.entityId,
      target_type: item.candidate_type,
      target_id: item.candidate_id,
      relationship_type: 'related_to',
    }
    await api.createRelationship(payload)
    showFeedback('success', `Linked ${formatType(item.candidate_type)} #${item.candidate_id} as related document.`)
    emit('relationship-mutated', {
      action: 'linked',
      partnerType: item.candidate_type,
      partnerId: item.candidate_id,
    })
    await refreshAll()
  } catch (err: any) {
    showFeedback('error', err.message || 'Could not link suggested document.')
  } finally {
    linkingSuggestionKey.value = null
  }
}

function dismissSuggestion(item: SuggestionItem) {
  const key = `${item.candidate_type}_${item.candidate_id}`
  dismissedSuggestionKeys.value.add(key)
  showFeedback('success', 'Suggestion dismissed for this session.')
}

// ── Manual Link Handled ─────────────────────────────────────────────────────
function handleLinkCreated(created: RelationshipRead) {
  showFeedback('success', 'Document linked successfully.')
  if (created?.related_entity) {
    emit('relationship-mutated', {
      action: 'linked',
      partnerType: created.related_entity.entity_type,
      partnerId: created.related_entity.entity_id,
    })
  }
  refreshAll()
}

function showFeedback(type: 'success' | 'error', message: string) {
  actionFeedback.value = { type, message }
  setTimeout(() => {
    if (actionFeedback.value?.message === message) {
      actionFeedback.value = null
    }
  }, 4500)
}

// ── Formatting Helpers ──────────────────────────────────────────────────────
function formatType(type: EntityType): string {
  if (type === 'invoice') return 'Invoice'
  if (type === 'receipt') return 'Receipt'
  if (type === 'source_file') return 'Source File'
  return type
}

function formatMatchCategory(category: MatchCategory): string {
  switch (category) {
    case 'exact_file_duplicate':
      return 'Identical Source File'
    case 'possible_duplicate':
      return 'Possible Duplicate'
    case 'possible_related':
      return 'Possibly Related'
    default:
      return category
  }
}

function formatRelLabel(rel: RelationshipRead): string {
  if (rel.relationship_type === 'related_to') {
    return 'Related document'
  }
  if (rel.direction_semantic === 'supports') {
    return 'Supports'
  }
  if (rel.direction_semantic === 'supported_by') {
    return 'Supported by'
  }
  return 'Supporting document'
}

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
  <div class="connected-panel-root">
    <!-- Feedback Banner -->
    <div
      v-if="actionFeedback"
      class="panel-feedback-banner"
      :class="actionFeedback.type"
      role="status"
    >
      <CheckCircle2 v-if="actionFeedback.type === 'success'" :size="15" />
      <AlertCircle v-else :size="15" />
      <span>{{ actionFeedback.message }}</span>
      <button
        type="button"
        class="btn-close-feedback"
        @click="actionFeedback = null"
      >
        <X :size="13" />
      </button>
    </div>

    <!-- Panel Header: Tabs & Action Button -->
    <div class="panel-header-row">
      <div class="tabs-segmented" role="tablist">
        <button
          type="button"
          role="tab"
          class="tab-btn"
          :class="{ active: activeTab === 'confirmed' }"
          :aria-selected="activeTab === 'confirmed'"
          @click="activeTab = 'confirmed'"
        >
          <Link2 :size="14" />
          <span>Connected Documents</span>
          <span class="count-chip">{{ relationships.length }}</span>
        </button>

        <button
          type="button"
          role="tab"
          class="tab-btn"
          :class="{ active: activeTab === 'suggestions' }"
          :aria-selected="activeTab === 'suggestions'"
          @click="activeTab = 'suggestions'"
        >
          <Sparkles :size="14" />
          <span>Suggested Matches</span>
          <span v-if="activeSuggestions.length > 0" class="count-chip highlight">
            {{ activeSuggestions.length }}
          </span>
          <span v-else class="count-chip">0</span>
        </button>
      </div>

      <button
        type="button"
        class="btn-link-action"
        @click="isLinkModalOpen = true"
      >
        <Plus :size="13" />
        <span>Link Document</span>
      </button>
    </div>

    <!-- ── TAB 1: CONFIRMED RELATIONSHIPS ─────────────────────────────────── -->
    <div v-if="activeTab === 'confirmed'" class="tab-content">
      <div v-if="isLoadingRelationships" class="loading-state">
        <Loader2 :size="18" class="spinner" />
        <span>Loading connected documents...</span>
      </div>

      <div v-else-if="relationshipsError" class="alert-box error">
        <AlertCircle :size="15" />
        <span>{{ relationshipsError }}</span>
      </div>

      <!-- Empty State -->
      <div v-else-if="relationships.length === 0" class="empty-connected-box">
        <div class="empty-icon-circle">
          <Link2 :size="24" />
        </div>
        <h4 class="empty-title">No connected documents yet</h4>
        <p class="empty-sub">
          Link related invoices, receipts, or supporting files to keep business records connected.
        </p>
        <button
          type="button"
          class="btn-empty-cta"
          @click="isLinkModalOpen = true"
        >
          <Plus :size="14" />
          <span>Link First Document</span>
        </button>
      </div>

      <!-- Confirmed Relationships List -->
      <div v-else class="relationships-grid">
        <div
          v-for="rel in relationships"
          :key="rel.id"
          class="relationship-card"
        >
          <div class="card-main">
            <div class="card-type-row">
              <span class="doc-type-badge" :class="rel.related_entity.entity_type">
                <FileText v-if="rel.related_entity.entity_type === 'invoice'" :size="12" />
                <Receipt v-else-if="rel.related_entity.entity_type === 'receipt'" :size="12" />
                <Layers v-else :size="12" />
                <span>{{ formatType(rel.related_entity.entity_type) }}</span>
              </span>

              <span class="rel-semantic-badge" :class="rel.relationship_type">
                {{ formatRelLabel(rel) }}
              </span>
            </div>

            <div class="card-identity-row">
              <span class="doc-identifier">
                {{ rel.related_entity.document_number || rel.related_entity.filename || `Record #${rel.related_entity.entity_id}` }}
              </span>
              <span v-if="rel.related_entity.counterparty" class="doc-counterparty">
                {{ rel.related_entity.counterparty }}
              </span>
            </div>

            <div class="card-metadata-row">
              <span class="meta-item">
                Date: <strong>{{ formatDate(rel.related_entity.document_date) }}</strong>
              </span>
              <span v-if="rel.related_entity.total_amount" class="meta-item amount">
                {{ formatAmount(rel.related_entity.total_amount, rel.related_entity.currency) }}
              </span>
              <span v-if="rel.related_entity.direction" class="direction-badge" :class="rel.related_entity.direction">
                {{ rel.related_entity.direction }}
              </span>
            </div>
          </div>

          <!-- Card Actions -->
          <div class="card-actions">
            <button
              type="button"
              class="btn-card-action view"
              title="View document details"
              @click="emit('view-related', { type: rel.related_entity.entity_type, id: rel.related_entity.entity_id })"
            >
              <Eye :size="14" />
              <span>View</span>
            </button>

            <button
              type="button"
              class="btn-card-action unlink"
              title="Unlink document"
              @click="promptUnlink(rel)"
            >
              <Link2Off :size="14" />
              <span>Unlink</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── TAB 2: SUGGESTED MATCHES ───────────────────────────────────────── -->
    <div v-else class="tab-content">
      <div v-if="isLoadingSuggestions" class="loading-state">
        <Loader2 :size="18" class="spinner" />
        <span>Evaluating intelligent matching suggestions...</span>
      </div>

      <div v-else-if="suggestionsError" class="alert-box error">
        <AlertCircle :size="15" />
        <span>{{ suggestionsError }}</span>
      </div>

      <!-- Empty State -->
      <div v-else-if="activeSuggestions.length === 0" class="empty-connected-box">
        <div class="empty-icon-circle green">
          <FileCheck :size="24" />
        </div>
        <h4 class="empty-title">No matching document suggestions</h4>
        <p class="empty-sub">
          DataBridge did not detect duplicate files or matching counterparties and amounts for this document.
        </p>
      </div>

      <!-- Suggestions List -->
      <div v-else class="suggestions-list">
        <div
          v-for="sug in activeSuggestions"
          :key="`${sug.candidate_type}_${sug.candidate_id}`"
          class="suggestion-card"
        >
          <div class="sug-header">
            <div class="sug-meta-left">
              <span class="category-badge" :class="sug.match_category">
                <Sparkles :size="11" />
                <span>{{ formatMatchCategory(sug.match_category) }}</span>
              </span>

              <span class="doc-type-badge" :class="sug.candidate_type">
                <FileText v-if="sug.candidate_type === 'invoice'" :size="12" />
                <Receipt v-else-if="sug.candidate_type === 'receipt'" :size="12" />
                <span>{{ formatType(sug.candidate_type) }}</span>
              </span>

              <span class="candidate-num">
                {{ sug.candidate_summary.document_number || `Record #${sug.candidate_id}` }}
              </span>
            </div>

            <div class="sug-meta-right">
              <span v-if="sug.candidate_summary.total_amount" class="sug-amount">
                {{ formatAmount(sug.candidate_summary.total_amount, sug.candidate_summary.currency) }}
              </span>
              <span class="sug-date">
                {{ formatDate(sug.candidate_summary.document_date) }}
              </span>
            </div>
          </div>

          <div v-if="sug.candidate_summary.counterparty" class="sug-counterparty-row">
            <span class="label">Counterparty:</span>
            <span class="val">{{ sug.candidate_summary.counterparty }}</span>
          </div>

          <!-- Evidence List -->
          <div class="evidence-box">
            <span class="evidence-title">Matching Evidence:</span>
            <ul class="evidence-list">
              <li v-for="(ev, idx) in sug.evidence" :key="idx" class="evidence-item">
                <Check :size="12" class="ev-check" />
                <span>{{ ev }}</span>
              </li>
            </ul>
          </div>

          <!-- Suggestion Actions -->
          <div class="sug-footer-actions">
            <div class="footer-left">
              <button
                type="button"
                class="btn-text-action"
                @click="emit('view-related', { type: sug.candidate_type, id: sug.candidate_id })"
              >
                <Eye :size="13" />
                <span>Inspect Candidate</span>
              </button>
              <button
                type="button"
                class="btn-text-action dismiss"
                title="Dismiss suggestion for this session"
                @click="dismissSuggestion(sug)"
              >
                <X :size="13" />
                <span>Dismiss</span>
              </button>
            </div>

            <button
              type="button"
              class="btn-confirm-link"
              :disabled="linkingSuggestionKey === `${sug.candidate_type}_${sug.candidate_id}`"
              @click="linkSuggestion(sug)"
            >
              <Loader2
                v-if="linkingSuggestionKey === `${sug.candidate_type}_${sug.candidate_id}`"
                :size="13"
                class="spinner"
              />
              <Link2 v-else :size="13" />
              <span>Link as Related</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── MANUAL LINK MODAL ──────────────────────────────────────────────── -->
    <LinkDocumentModal
      :is-open="isLinkModalOpen"
      :focal-entity-type="props.entityType"
      :focal-entity-id="props.entityId"
      :focal-title="props.entityTitle"
      :already-linked-keys="alreadyLinkedKeys"
      @close="isLinkModalOpen = false"
      @linked="handleLinkCreated"
    />

    <!-- ── UNLINK CONFIRMATION DIALOG (teleported to body to avoid modal stacking) -->
    <Teleport to="body">
      <div v-if="unlinkTarget" class="zen-dialog-backdrop" @click.self="cancelUnlink">
        <div class="zen-confirm-card" role="alertdialog">
          <div class="confirm-icon-wrap">
            <Link2Off :size="20" />
          </div>
          <h3 class="confirm-title">Remove Document Relationship?</h3>
          <p class="confirm-body">
            Are you sure you want to unlink
            <strong>
              {{ unlinkTarget.related_entity.document_number || unlinkTarget.related_entity.filename || `${unlinkTarget.related_entity.entity_type} #${unlinkTarget.related_entity.entity_id}` }}
            </strong>?
          </p>
          <p class="confirm-note">
            Only the relationship link will be removed. Both underlying business documents and source files remain completely safe and untouched.
          </p>

          <div v-if="unlinkError" class="alert-box error mt-2">
            <AlertCircle :size="14" />
            <span>{{ unlinkError }}</span>
          </div>

          <div class="confirm-actions">
            <button
              type="button"
              class="btn-dialog-secondary"
              :disabled="isUnlinking"
              @click="cancelUnlink"
            >
              Cancel
            </button>
            <button
              type="button"
              class="btn-dialog-danger"
              :disabled="isUnlinking"
              @click="confirmUnlink"
            >
              <Loader2 v-if="isUnlinking" :size="13" class="spinner" />
              <span>{{ isUnlinking ? 'Unlinking...' : 'Confirm Unlink' }}</span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.connected-panel-root {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.panel-feedback-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.875rem;
  border-radius: var(--radius-xs, 6px);
  font-size: 0.8125rem;
  animation: fadeIn 0.15s ease;
}

.panel-feedback-banner.success {
  background: var(--status-success-bg, rgba(16, 185, 129, 0.12));
  border: 1px solid var(--status-success-border, rgba(16, 185, 129, 0.25));
  color: var(--status-success, #34d399);
}

.panel-feedback-banner.error {
  background: var(--status-error-bg, rgba(239, 68, 68, 0.12));
  border: 1px solid var(--status-error-border, rgba(239, 68, 68, 0.25));
  color: var(--status-error, #fb7185);
}

.btn-close-feedback {
  margin-left: auto;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  opacity: 0.7;
}

.btn-close-feedback:hover {
  opacity: 1;
}

.panel-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border-subtle);
  padding-bottom: 0.75rem;
}

.tabs-segmented {
  display: inline-flex;
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 2px;
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 0.4rem 0.85rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.count-chip {
  background: var(--bg-elevated);
  padding: 0.1rem 0.4rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}

.count-chip.highlight {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent-border);
}

.btn-link-action {
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
  color: var(--accent);
  padding: 0.4rem 0.85rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-link-action:hover {
  background: var(--accent);
  color: var(--on-accent);
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.loading-state {
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.8125rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.empty-connected-box {
  padding: 3rem 1.5rem;
  text-align: center;
  background: var(--bg-subtle);
  border: 1px dashed var(--border-default);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
}

.empty-icon-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 0.25rem;
}

.empty-icon-circle.green {
  background: var(--status-success-bg, rgba(16, 185, 129, 0.12));
  color: var(--status-success, #34d399);
}

.empty-title {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-sub {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  max-width: 420px;
  line-height: 1.4;
}

.btn-empty-cta {
  margin-top: 0.5rem;
  background: var(--accent);
  border: 1px solid var(--accent);
  color: var(--on-accent);
  padding: 0.45rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.15s ease;
}

.btn-empty-cta:hover {
  background: var(--accent-hover);
}

.relationships-grid {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.relationship-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s ease;
}

.relationship-card:hover {
  border-color: var(--border-medium);
}

.card-main {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  overflow: hidden;
}

.card-type-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.doc-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.doc-type-badge.invoice {
  background: var(--status-info-bg, rgba(56, 189, 248, 0.15));
  color: var(--status-info, #38bdf8);
  border: 1px solid var(--status-info-border, rgba(56, 189, 248, 0.3));
}

.doc-type-badge.receipt {
  background: var(--status-success-bg, rgba(52, 211, 153, 0.15));
  color: var(--status-success, #34d399);
  border: 1px solid var(--status-success-border, rgba(52, 211, 153, 0.3));
}

.doc-type-badge.source_file {
  background: color-mix(in srgb, #a855f7 15%, transparent);
  color: #c084fc;
  border: 1px solid color-mix(in srgb, #a855f7 30%, transparent);
}

.rel-semantic-badge {
  font-size: 0.6875rem;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  background: var(--bg-subtle);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  font-weight: 500;
}

.rel-semantic-badge.supports {
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.card-identity-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.doc-identifier {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.875rem;
}

.doc-counterparty {
  color: var(--text-secondary);
  font-size: 0.8125rem;
}

.card-metadata-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.meta-item strong {
  color: var(--text-secondary);
}

.meta-item.amount {
  font-family: monospace;
  color: var(--text-primary);
  font-weight: 600;
}

.direction-badge {
  text-transform: capitalize;
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 500;
}

.direction-badge.sales {
  background: var(--status-info-bg, rgba(56, 189, 248, 0.15));
  color: var(--status-info, #38bdf8);
}

.direction-badge.purchase,
.direction-badge.expense {
  background: var(--status-error-bg, rgba(251, 113, 133, 0.15));
  color: var(--status-error, #fb7185);
}

.direction-badge.income {
  background: var(--status-success-bg, rgba(52, 211, 153, 0.15));
  color: var(--status-success, #34d399);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-card-action {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  padding: 0.35rem 0.65rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  transition: all 0.15s ease;
}

.btn-card-action:hover {
  background: var(--bg-elevated);
  border-color: var(--border-medium);
  color: var(--text-primary);
}

.btn-card-action.unlink:hover {
  background: var(--status-error-bg, rgba(239, 68, 68, 0.15));
  border-color: var(--status-error-border, rgba(239, 68, 68, 0.3));
  color: var(--status-error, #fb7185);
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.suggestion-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 10px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s ease;
}

.suggestion-card:hover {
  border-color: var(--accent-border);
}

.sug-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.sug-meta-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.category-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.15rem 0.5rem;
  border-radius: 9999px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.category-badge.exact_file_duplicate {
  background: var(--status-warning-bg, rgba(251, 191, 36, 0.15));
  color: var(--status-warning, #fbbf24);
  border: 1px solid var(--status-warning-border, rgba(251, 191, 36, 0.3));
}

.category-badge.possible_duplicate {
  background: var(--status-error-bg, rgba(251, 113, 133, 0.15));
  color: var(--status-error, #fb7185);
  border: 1px solid var(--status-error-border, rgba(251, 113, 133, 0.3));
}

.category-badge.possible_related {
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.candidate-num {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
  font-size: 0.8125rem;
}

.sug-meta-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.75rem;
}

.sug-amount {
  font-family: monospace;
  font-weight: 600;
  color: var(--text-primary);
}

.sug-date {
  color: var(--text-muted);
}

.sug-counterparty-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.8125rem;
}

.sug-counterparty-row .label {
  color: var(--text-muted);
}

.sug-counterparty-row .val {
  color: var(--text-secondary);
  font-weight: 500;
}

.evidence-box {
  background: var(--bg-subtle);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.evidence-title {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-weight: 600;
  color: var(--text-muted);
}

.evidence-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.evidence-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.ev-check {
  color: var(--status-success, #34d399);
  flex-shrink: 0;
}

.sug-footer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 0.4rem;
  border-top: 1px solid var(--border-subtle);
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.btn-text-action {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.4rem;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.btn-text-action:hover {
  color: var(--text-primary);
  background: var(--bg-subtle);
}

.btn-text-action.dismiss:hover {
  color: var(--status-error, #fb7185);
  background: var(--status-error-bg, rgba(239, 68, 68, 0.1));
}

.btn-confirm-link {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: var(--on-accent);
  padding: 0.35rem 0.85rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  transition: all 0.15s ease;
}

.btn-confirm-link:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-confirm-link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── Confirmation Dialog ─────────────────────────────────────────────────── */
.zen-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10000;
  background: var(--overlay);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}

.zen-confirm-card {
  width: 100%;
  max-width: 440px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: 12px;
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  box-shadow: var(--shadow-lg);
  color: var(--text-primary);
}

.confirm-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--status-error-bg, rgba(239, 68, 68, 0.15));
  color: var(--status-error, #fb7185);
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--status-error-border, rgba(239, 68, 68, 0.25));
}

.confirm-title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--text-primary);
}

.confirm-body {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--text-secondary);
  line-height: 1.45;
}

.confirm-note {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-subtle);
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  border-left: 2px solid var(--border-medium);
  line-height: 1.4;
}

.confirm-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.65rem;
  margin-top: 0.5rem;
}

.btn-dialog-secondary {
  background: var(--bg-subtle);
  border: 1px solid var(--border-default);
  color: var(--text-secondary);
  padding: 0.45rem 0.85rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
}

.btn-dialog-secondary:hover:not(:disabled) {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.btn-dialog-danger {
  background: var(--danger, #dc2626);
  border: 1px solid var(--danger, #ef4444);
  color: #ffffff;
  padding: 0.45rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.btn-dialog-danger:hover:not(:disabled) {
  opacity: 0.9;
}

.alert-box {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.85rem;
  border-radius: 6px;
  font-size: 0.8125rem;
}

.alert-box.error {
  background: var(--status-error-bg, rgba(239, 68, 68, 0.12));
  border: 1px solid var(--status-error-border, rgba(239, 68, 68, 0.25));
  color: var(--status-error, #fb7185);
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

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
