# Milestone 16.5D — Connected Documents Workspace & Duplicate Review UX

**Status:** ✅ Complete  
**Build:** ✓ 1827 modules, zero TypeScript errors  
**Depends on:** M16.5B (DocumentRelationship backend), M16.5C (Intelligent duplicate detection)

---

## Overview

M16.5D surfaces the backend document-relationship and intelligent matching features from M16.5B–C into a complete, user-facing experience across the DataBridge frontend.

---

## Deliverables

### 1. `LinkDocumentModal.vue` — Manual Document Linking

**Path:** `frontend/src/components/explorer/LinkDocumentModal.vue`

A focused modal for creating explicit relationships between documents:

- **Debounced search** against `GET /api/v1/data/documents` (unified register) with document type filter.
- **Candidate inspection** — expands to show counterparty, date, amount, direction, and source provenance.
- **Relationship type picker** — `related_to` (symmetric) or `supports`/`supported_by` (directional).
- **Duplicate prevention** — filters out already-linked document keys.
- **API integration** — `POST /api/v1/relationships` with full tenant scoping.

---

### 2. `ConnectedDocumentsPanel.vue` — Connected Documents & Suggestions Panel

**Path:** `frontend/src/components/explorer/ConnectedDocumentsPanel.vue`

An embedded tabbed panel used inside both `InvoiceDetailModal` and `ReceiptDetailModal`:

| Tab | Content |
|-----|---------|
| **Confirmed Links** | All explicit `DocumentRelationship` records; shows type, counterparty, date, and amount. Unlink via confirmation dialog. |
| **Suggestions** | AI/heuristic candidates from `GET /api/v1/relationships/suggestions`. One-click accept (creates relationship) or dismiss (session-only, no DB write). |

**Events emitted:**
- `view-related` — navigates the parent to open the related document's detail modal.
- `count-changed` — keeps the parent's connected count badge in sync after link/unlink.

---

### 3. `InvoiceDetailModal.vue` — Panel Integration

**Path:** `frontend/src/components/explorer/InvoiceDetailModal.vue`

- `ConnectedDocumentsPanel` mounted below the provenance footer.
- **Linked count badge** in the header meta bar (`N linked`) when `connected_count > 0`.
- Modal widened to `max-width: 1080px` to accommodate the panel.
- New emit: `view-related` propagated to `DataExplorerView`.

---

### 4. `ReceiptDetailModal.vue` — Panel Integration

**Path:** `frontend/src/components/explorer/ReceiptDetailModal.vue`

- `ConnectedDocumentsPanel` mounted below the provenance section.
- **Linked count badge** in the header direction group.
- Modal widened to `max-width: 64rem`.
- New emit: `view-related`.

---

### 5. `DataExplorerView.vue` — Connected Count Badges

**Path:** `frontend/src/views/DataExplorerView.vue`

All three document tables now display a subtle `link2 N` pill in the Actions column when `connected_count > 0`:

- **All Documents** tab — `doc.connected_count`
- **Invoices** tab — `inv.connected_count`
- **Receipts** tab — `rec.connected_count`

The badge uses the brand-accent color palette and is non-interactive — clicking the row opens the detail modal where relationships are managed.

---

### 6. `DocumentReviewView.vue` — 409 Duplicate Conflict UX

**Path:** `frontend/src/views/DocumentReviewView.vue`

Replaces the silent toast-only duplicate warning with a structured inline conflict banner.

#### Conflict Detection
`confirmImport()` catches `ApiError.isDuplicateConflict === true` (set by the api client when HTTP 409 is received with headers `X-Duplicate-Record-Id` / `X-Duplicate-Document-Type`).

#### Conflict Banner
Shows the backend message, existing record reference (`RECEIPT #42`), a guidance note, and two actions:

- **Import Anyway** — calls `acknowledgeImport()`, retries `POST /confirm` with `acknowledge_duplicate: true`.
- **Cancel** — clears the banner so the user can edit fields before retrying.

---

## API Surface Used

| Method | Endpoint | Component |
|--------|----------|-----------|
| `GET` | `/api/v1/data/documents` | `LinkDocumentModal` (search) |
| `GET` | `/api/v1/relationships` | `ConnectedDocumentsPanel` |
| `GET` | `/api/v1/relationships/suggestions` | `ConnectedDocumentsPanel` |
| `POST` | `/api/v1/relationships` | `LinkDocumentModal`, `ConnectedDocumentsPanel` |
| `DELETE` | `/api/v1/relationships/{id}` | `ConnectedDocumentsPanel` |
| `POST` | `/api/v1/documents/{id}/confirm` | `DocumentReviewView` (+ `acknowledge_duplicate`) |

---

## Type Changes (`frontend/src/types/api.ts`)

```typescript
type EntityType = 'invoice' | 'receipt'
type RelationshipType = 'related_to' | 'supports' | 'supported_by'
type MatchCategory = 'exact_duplicate' | 'likely_duplicate' | 'related'

interface RelationshipRead { id, source_type, source_id, target_type, target_id, relationship_type, created_at }
interface RelationshipCreateRequest { source_type, source_id, target_type, target_id, relationship_type }
interface SuggestionItem { id, entity_type, entity_id, candidate_type, candidate_id, score, reason, category }

// ApiError extended with:
isDuplicateConflict?: boolean
duplicateRecordId?: number | null
duplicateDocumentType?: string | null

// List items extended with:
connected_count?: number   // UnifiedDocumentListItem, InvoiceListItem, ReceiptListItem
                           // InvoiceDetailResponse, ReceiptDetailResponse
```

---

## Architecture Notes

- **No AI/vector dependencies** — suggestions use the deterministic M16.5C heuristic engine.
- **Tenant isolation** — all relationship queries are scoped by `organization_id` server-side; frontend passes no org param.
- **Session-only dismissal** — dismissed suggestion keys live in a `Set<string>` ref; reset on page reload. No DB write.
- **N+1 prevention** — `connected_count` populated via `get_connected_counts_batch` (2 queries per page) in `data_explorer.py`.

---

## Build Verification

```
✓ vue-tsc --noEmit     exit code 0
✓ vite build           1827 modules, 9.22s, exit code 0
```
