# Milestone 16 - Financial Document Classification & Unified Business Intelligence

## Status Overview

| Sub-milestone | Name | Status |
|---|---|---|
| M16.1 | Repository Inspection & Architecture Audit | Complete |
| M16.2 | Financial Direction Classification & Receipt History Visibility | Complete |
| M16.3 | Unified Financial Data Explorer | Complete |
| M16.3.1 | Source Preview Reliability Hotfix | Complete |
| M16.4 | Direction-Aware Financial Dashboard | Complete |
| M16.4.1 | Financial Direction Editing & Workbook Classification | Complete |
| M16.4.2 | Queue Lifecycle Cleanup, Receipt Direction Editing & Dashboard UX Polish | Complete |
| M16.5A | Business Document Intelligence & Relationship Architecture Audit | Complete |
| M16.5B | Document Relationship Foundation | Complete |
| M16.5C | Intelligent Duplicate Detection & Related Document Suggestions | Complete |
| M16.5D | Frontend Connected Documents Workspace & Relationship Management | Planned |

---

## M16.2 - Financial Direction Classification

### Data Model

- `InvoiceRecord.direction`: `sales` / `purchase` / `unclassified` (default). CHECK constraint.
- `ReceiptRecord.direction`: `expense` / `income` / `unclassified` (default). CHECK constraint.
- Alembic migration: `0007_financial_direction`

### Changes
- `ReceiptRecord` to `ImportBatch` ORM relationship
- Receipt visibility in Import History
- Direction selection during document confirmation
- 367 backend tests passed at completion

---

## M16.3 - Unified Financial Data Explorer

### New Backend Endpoints

- `GET /api/v1/data/receipts` - Paginated receipt list with filters
- `GET /api/v1/data/receipts/{receipt_id}` - Full receipt detail
- `GET /api/v1/data/documents` - Unified invoice+receipt register (UNION ALL)

Filter options endpoint extended: merchants, payment_methods, directions.

### Receipt Filters
`search`, `merchant`, `receipt_number`, `currency`, `direction` (expense/income/unclassified),
`payment_method`, `date_from`, `date_to`, `amount_min`, `amount_max`,
`sort_by` (transaction_date/merchant_name/total_amount/id/created_at/direction/receipt_number),
`sort_order`, `page`, `page_size`

### Document Filters
`search`, `document_type` (invoice/receipt/all), `direction`, `currency`, `date_from`, `date_to`,
`sort_by` (document_date/counterparty/total_amount/created_at/document_number/line_item_count/direction/record_id)

### Frontend - DataExplorerView.vue (four tabs)
- All Documents: Unified register with type/direction/currency/date filters
- Invoices: Direction badge + filter; existing edit preserved
- Receipts: Merchant, payment method, direction, source traceability
- Line Items: Existing, unchanged

### ReceiptDetailModal.vue (new component)
- Merchant, receipt number, transaction date/time, total amount
- Subtotal, tax, cash paid, change, store address, branch, cashier (conditional)
- Line items table
- Source file link and batch provenance

### Export Support
Invoices: CSV+XLSX with Direction column
Line Items: CSV+XLSX
Receipts: CSV+XLSX with Direction column
Unified Documents: CSV+XLSX with Document Type + Direction columns
Formula injection protection applied to all text cells.

---

## M16.3.1 - Source Preview Reliability Hotfix

- Harmonized `SourcePreviewModal.vue` payload to safely detect `worksheet` / `sheet_name` across Excel workbooks and OCR/vision documents.
- Fixed API validation error `sheet_name: Field required` on Excel file source previews.
- Verified test suite: 388/388 backend tests passing.

---

## M16.4 - Direction-Aware Financial Dashboard

### Primary Objective
Upgrade the business dashboard to accurately reflect financial activity by direction classification:
- **Invoices**: Sales, Purchases, Unclassified
- **Receipts**: Income, Expenses, Unclassified

Preserve operational statistics while enforcing strict financial guardrails (no combining sales and purchases into net profit, no labeling invoices as cash received/paid, and zero cross-currency blending).

### Financial Metric Definitions

#### 1. Invoice Activity
- **Sales Invoiced**:
  - `SUM(InvoiceRecord.total_amount) WHERE direction = 'sales'`
  - Document count & count with total.
  - Represents amounts billed to customers (strictly not labeled as cash received).
- **Purchases Invoiced**:
  - `SUM(InvoiceRecord.total_amount) WHERE direction = 'purchase'`
  - Document count & count with total.
  - Represents amounts billed by suppliers (strictly not labeled as cash paid).
- **Unclassified Invoices**:
  - `SUM(InvoiceRecord.total_amount) WHERE direction = 'unclassified'`
  - Kept visible to avoid hiding untriaged financial documents.

#### 2. Receipt Activity
- **Income Receipts**:
  - `SUM(ReceiptRecord.total_amount) WHERE direction = 'income'`
  - Document count & count with total.
  - Represents counter/point-of-sale income documents (not bank-settled cash receipts).
- **Expense Receipts**:
  - `SUM(ReceiptRecord.total_amount) WHERE direction = 'expense'`
  - Document count & count with total.
  - Represents retail/vendor expense slips.
- **Unclassified Receipts**:
  - `SUM(ReceiptRecord.total_amount) WHERE direction = 'unclassified'`
  - Kept visible with count and value.

### Aggregation & Query Architecture
- **Single-Pass SQL Aggregation**:
  - Evaluated in SQL using integer minor units (`BigInteger` cents via `func.sum(cast(func.round(total_amount * 100, 0), BigInteger))`) with SQL `case` expressions per direction.
  - Rounding artifacts and SQLite/PostgreSQL floating inaccuracies are eliminated.
  - Converted to canonical `Decimal("0.01")` in Python.
- **Zero Fan-Out**:
  - Header queries (`InvoiceRecord`, `ReceiptRecord`) and line-item queries (`InvoiceLineItem`, `ReceiptLineItem`) are queried independently, preventing Cartesian multiplication of monetary totals.
- **Tenant & Soft-Delete Isolation**:
  - Every query joins `ImportBatch` and applies `active_record_scope()` (`ImportBatch.is_deleted.is_(False)`).
  - Multi-tenant query isolation is enforced through SQLAlchemy session `with_loader_criteria` on `organization_id`.

### Filtering Rules
- **Explicit Currency Filter**:
  - If a currency is selected (e.g., `MYR`), only records exactly matching that currency are included.
  - If unspecified (`None`), monetary figures are withheld (`monetary_values_available = False`), while record counts are displayed.
  - Currencies from both active invoices and receipts are aggregated in `filter-options`.
- **Date Filter**:
  - Invoices use `InvoiceRecord.invoice_date`.
  - Receipts use `ReceiptRecord.transaction_date`.
  - Undated records are counted and included in overall totals when no date filter is active, but safely omitted from monthly time-series groupings.
- **Company / Merchant Search**:
  - Filters `InvoiceRecord.company_name` and `ReceiptRecord.merchant_name`.

### Dashboard UI Redesign (`DashboardView.vue` & `DirectionTrendChart.vue`)
- **Section A — Financial Overview**:
  - 4 prominent KPI cards: *Sales Invoiced*, *Purchases Invoiced*, *Income Receipts*, *Expense Receipts*.
  - Direction badges, monetary sums in the selected currency, and record counts with totals.
  - Explicit micro-copy explaining that invoices represent billing activity and receipts represent document slips.
- **Section B — Unclassified Financial Records**:
  - Dedicated callout highlighting unclassified invoices and unclassified receipts.
  - Direct deep-links to `/explorer?type=invoices&direction=unclassified` and `/explorer?type=receipts&direction=unclassified`.
- **Section C — Financial Activity Trends**:
  - Reusable `DirectionTrendChart.vue` component.
  - Side-by-side monthly comparison of **Sales Invoiced vs Purchases Invoiced** with unclassified series.
  - Side-by-side monthly comparison of **Income Receipts vs Expense Receipts** with unclassified series.
  - Interactive hover zones, tooltips, and accessible `<details>` data tables.
- **Section D — Operational Volume & Insights**:
  - Preserved operational statistics: Total Invoices, Total Receipts, Line Items, Average Invoice Total.
  - Top 10 Companies by Invoice Value and Top 10 Line Items by Amount.
- **Financial Integrity Statement**:
  - Persistent footer clarifying accounting guardrails and absence of payment settlement inference.

### Files Modified & Created
- `backend/app/schemas/analytics.py` (Extended with `FinancialSummary`, `FinancialInvoiceTrend`, `FinancialReceiptTrend`)
- `backend/app/services/analytics_service.py` (Unified invoice & receipt direction-aware aggregation)
- `backend/tests/integration/test_m16_4_financial_dashboard.py` (12 comprehensive integration tests)
- `frontend/src/types/api.ts` (TypeScript interfaces for M16.4 schemas)
- `frontend/src/components/dashboard/DirectionTrendChart.vue` (New multi-series accessible trend chart)
- `frontend/src/views/DashboardView.vue` (Upgraded direction-aware dashboard)
- `docs/milestone-16.md` (Updated milestone documentation)

### Verification Results
- **New M16.4 Tests**: 12/12 passed
- **Full Backend Pytest Suite**: 400/400 passed (54.72s)
- **Frontend TypeScript Check (`vue-tsc --noEmit`)**: 0 errors
- **Frontend Production Build (`vite build`)**: Clean (3.01s)
- **`git diff --check`**: Clean (0 whitespace/formatting errors)

### Outstanding Limitations
1. No payment tracking (sales and purchase invoices cannot be confirmed as settled/paid).
2. No invoice-receipt linking (receipts may represent purchases already invoiced).
3. No cross-currency FX conversion (all sums are isolated to a single selected currency).
4. No net profit or cash flow derivation (withheld due to incomplete document settlement data).

---

## M16.4.1 - Financial Direction Editing & Workbook Classification

### Objectives & Capabilities
1. **Workbook Classification**:
   - Enables users to specify direction (`sales`, `purchase`, `unclassified`) during workbook review before final ingestion.
   - Bulk classification selector with individual override support across parsed invoice sheets.
2. **Post-Import Invoice Direction Editing**:
   - Dedicated `InvoiceDetailModal.vue` direction selector allowing real-time edits to previously imported invoices.
   - Backend audit logging and persistence across Data Explorer queries.

---

## M16.4.2 - Queue Lifecycle Cleanup, Receipt Direction Editing & Dashboard UX Polish

### Objectives & Capabilities
1. **Safe Queue Lifecycle Management (`useIngestionQueue.ts` & `IngestionStudioView.vue`)**:
   - Non-destructive **Dismiss Completed**: Cleans up already imported files (`status === 'imported'`) from the local queue while preserving in-progress or queued uploads.
   - Confirmed **Discard Unfinished**: Requires explicit user confirmation to cancel and clear queued/review items. Never deletes backend batches or imported documents.
   - Authoritative Batch-Queue Synchronization: Resolves the "Imported vs Ready" ambiguity by synchronizing upload queue items with backend batch file session states.
   - Streamlined Batch Review UI: Replaced redundant table in `BatchImportReview.vue` with a clean summary card and expandable "View File Details" toggle.
   - "You're all caught up" Zen empty state when queue and batch are clear.

2. **Receipt Financial Direction Editing (`ReceiptDetailModal.vue` & `data_explorer.py`)**:
   - Interactive segmented direction control (`Expense`, `Income`, `Unclassified`) added to `ReceiptDetailModal.vue`.
   - Backend endpoint: `PATCH /api/v1/data/receipts/{receipt_id}`.
   - Strict validation via `ReceiptRecordUpdate` schema (`extra="forbid"`, valid directions only).
   - Multi-tenant boundary checks and soft-deletion protection.
   - Audit event logged: `RECEIPT_DIRECTION_UPDATED` with previous and new direction in metadata.
   - Immediate reactive cache/list refresh across Data Explorer and Dashboard.

3. **Dashboard Empty-State & Filter Clarity (`DashboardView.vue` & `analytics_service.py`)**:
   - Distinguishes 4 distinct states for business users:
     1. **Workspace has zero receipts**: Displays *"No receipts yet in workspace"*.
     2. **Receipts exist in workspace, but none match selected currency**: Displays *"No receipts in {CURRENCY} — receipts exist in other currencies"*.
     3. **Receipts match currency, but total amount is missing**: Displays *"Amount unavailable — 1 receipt has no total"*.
     4. **No currency selected**: Displays *"Select a currency to view totals — 5 receipts recorded"*.
   - Added `total_workspace_invoices` and `total_workspace_receipts` to `FinancialSummary` backend schema to compute these states authoritatively.
   - Updated metric subtitles and trend chart empty messages to remove ambiguity.

### Verification Results
- **M16.4.2 Test Suite (`test_m16_4_2_queue_and_receipt_direction.py`)**: 12/12 passed
- **Full Backend Pytest Suite**: 412/412 passed (99.33s)
- **Frontend TypeScript Check (`vue-tsc --noEmit`)**: 0 errors
- **Frontend Production Build (`vite build`)**: Clean (2.99s)
- **`git diff --check`**: Clean (0 whitespace/formatting warnings)

---

## M16.5A — Business Document Intelligence & Relationship Architecture Audit
- Positioned DataBridge officially as a **Business Document Intelligence Platform**, not an accounting ERP.
- Comprehensive audit of `SourceFile`, `DocumentExtraction`, `ImportBatch`, `InvoiceRecord`, and `ReceiptRecord`.
- Evaluated duplicate detection across uploads, spreadsheet imports, and document confirmation.
- Compared 3 relationship options (Source-to-Source, Record-to-Record, and Unified Relationship Graph).
- Established 3-tier matching strategy (Deterministic, Heuristic, AI-Assisted).
- Designed non-breaking, tenant-scoped relationship architecture with explainable signals.

---

## M16.5B — Document Relationship Foundation

### 1. Architecture Choice & Trade-offs
- **Chosen Design:** Unified Relationship Graph (`document_relationships` table with polymorphic references: `source_type`, `source_id`, `target_type`, `target_id`).
- **Why Selected:**
  1. **Multi-Record XLSX Support:** Directly links individual invoices within a multi-row spreadsheet batch (which cannot be achieved by linking source files).
  2. **Supporting Attachments:** Allows physical files (`source_file`) to support business records (`invoice`, `receipt`) without schema changes.
  3. **Zero ERP Overhead:** Avoids rigid double-entry accounts or ledger coupling.
  4. **Referential Integrity Strategy:** While polymorphic keys lack cross-table SQL foreign keys, integrity is enforced via check constraints (`ck_document_relationships_type`, `ck_document_relationships_source_type`, `ck_document_relationships_target_type`, `ck_document_relationships_no_self_link`), unique constraints (`uq_document_relationships_edge`), and centralized service-layer verification in `RelationshipService` (`validate_and_resolve_entity`).

### 2. Supported Relationship Types & Semantics
- **`related_to` (Symmetric):** Mutual relationship between two business documents (e.g. Invoice ↔ Receipt, Invoice ↔ Invoice). Canonically normalized lexicographically (`source <= target`) so $A \rightarrow B$ and $B \rightarrow A$ map to the exact same edge, preventing duplicate inverse links.
- **`supports` (Directional):** One entity serves as supporting evidence for another (e.g. Delivery Order SourceFile supports InvoiceRecord). Perspective-aware queries return `direction_semantic: "supports"` (from source perspective) or `"supported_by"` (from target perspective).
- **Deferred Types:** `duplicate_of`, `possible_duplicate_of`, and `replaces` are deferred to M16.5C and M17.

### 3. Database Schema & Migration
- **Migration:** `0008_document_relationships.py` (revises `0007_financial_direction`).
- **Table:** `document_relationships`
  - `id`: Integer Primary Key
  - `organization_id`: Integer ForeignKey(`organizations.id`, `ondelete="CASCADE"`)
  - `source_type`: String(30), check constraint in `('invoice', 'receipt', 'source_file')`
  - `source_id`: Integer
  - `target_type`: String(30), check constraint in `('invoice', 'receipt', 'source_file')`
  - `target_id`: Integer
  - `relationship_type`: String(30), check constraint in `('related_to', 'supports')`
  - `created_by_user_id`: Integer ForeignKey(`users.id`, `ondelete="SET NULL"`), nullable
  - `created_at`: DateTime, server default `func.now()`
- **Indexes:** `ix_doc_rel_org_source`, `ix_doc_rel_org_target`, `ix_doc_rel_org_type`.

### 4. API Endpoints
- `POST /api/v1/relationships`: Creates an explicit relationship. Resolves tenant ownership from authenticated session, rejects cross-tenant references with 404, prevents self-links (422) and duplicates (409).
- `GET /api/v1/relationships/{entity_type}/{entity_id}`: Lists active relationships for an entity with rich display summaries. Excludes soft-deleted partner records.
- `DELETE /api/v1/relationships/{relationship_id}`: Removes the relationship record. Underlying financial records and source files remain completely untouched.

### 5. Multi-Tenant Safety & Soft Deletion
- Registered in `backend/app/tenancy.py`:
  - Query loader criteria: `(DocumentRelationship, DocumentRelationship.organization_id == org)`
  - Write scoping: Enforces `obj.organization_id = org` and blocks cross-tenant writes.
- Soft-deletion: Querying relationships filters out any edge whose related document belongs to an `ImportBatch` with `is_deleted = True`.

### 6. Verification Results
- **Unit Tests (`test_relationship_service.py`)**: 11/11 passed
- **Integration Tests (`test_api_relationships.py`)**: 10/10 passed
- **Migration Tests (`test_migrations.py`)**: 3/3 passed (including PostgreSQL schema compilation)
- **Full Pytest Suite**: 433/433 passed (100% pass rate, 0 regressions)

---

## M16.5C — Intelligent Duplicate Detection & Related Document Suggestions

### 1. Primary Objectives & Design Philosophy
- Position DataBridge as a **Business Document Intelligence Platform**, not an accounting ERP.
- Deliver non-destructive duplicate detection and intelligent, explainable related-document suggestions.
- **Zero Financial Mutation**: Suggestions and relationships never modify invoice/receipt totals, dates, directions, or tax amounts.
- **Zero Paid AI / Vector Dependencies**: 100% deterministic and heuristic rule engine running in-process via fast string comparison and database queries.
- **Explainability First**: Every suggestion returns an array of human-readable evidence strings detailing *why* the candidate was surfaced.

### 2. Disambiguated Duplicate Detection on Confirmation
- **Prior Problem**: When `receipt_number` was empty or `None`, duplicate checks matched on `merchant_name + total_amount`. This falsely rejected legitimate repeat purchases (e.g. coffee daily for 12.00 MYR).
- **Corrected Rule**:
  1. **Printed Receipt Number Present**: Rejects with HTTP 409 if `merchant_name` and `receipt_number` match an existing active receipt in the tenant workspace.
  2. **Receipt Number Missing/Empty**: Only flags a duplicate if `merchant_name`, `total_amount`, AND `transaction_date` all match. Different dates (or missing vs present date) are recognized as distinct repeat transactions and allowed.
  3. **Explicit Override**: `DocumentConfirmRequest` supports `acknowledge_duplicate: bool = False` (and legacy alias `acknowledge_warnings: bool = False`). When `True`, the confirmation bypasses the 409 block and annotates `raw_data` with:
     ```json
     {
       "duplicate_acknowledged": true,
       "duplicate_warning_reason": "...",
       "conflicting_record_id": 123
     }
     ```

### 3. Explainable Matching Engine (`matching_service.py`)
- Evaluates candidate documents using a multi-factor scoring pipeline:
  - **Counterparty Normalization**: Strips corporate/legal suffixes (`sdn bhd`, `berhad`, `bhd`, `pte ltd`, `pte`, `pty ltd`, `pty`, `llc`, `inc`, `corp`, `ltd`, `limited`, `co`, `company`, `holdings`, `enterprises`), punctuation, and extra whitespace.
  - **Fuzzy Counterparty Similarity**: Combined character and token-sorted `difflib.SequenceMatcher` (weights: max of token-order and character similarity). High similarity ($\ge 0.85$) adds $+0.35$ with evidence.
  - **Document Identifier Matching**: Identifiers with length $\ge 3$ not in generic blocklist (`N/A`, `NULL`, `INV`, etc.) generate strong evidence. Exact identifier match awards $+0.60$ or cross-references via raw metadata award $+0.50$.
  - **Amount & Currency Matching**: Exact total match with identical currency awards $+0.30$. Currency mismatch prevents amount matching.
  - **Date Proximity**: Dates within 0 days award $+0.20$; within 3 days $+0.15$; within 7 days $+0.10$; within 14 days $+0.05$. Missing dates are handled gracefully without penalties.
  - **Exact File Checksum**: When `SourceFile.checksum` matches between candidate and focal document, instantly emits `exact_file_duplicate` with heuristic score $1.0$.
- **Categorization Rules**:
  - `exact_file_duplicate`: Identical source file SHA-256 hash across batches.
  - `possible_duplicate`: Same document type (e.g. invoice-to-invoice or receipt-to-receipt) with identical/near-identical counterparty and same identifier or matching amount+date.
  - `possible_related`: Cross-type documents (e.g. invoice-to-receipt payment proof) or same-type documents sharing counterparty, cross-referenced identifiers, or proximate transactions.

### 4. Suggestions API Endpoint
- **Route**: `GET /api/v1/relationships/suggestions/{entity_type}/{entity_id}`
- **Query Parameter**: `limit: int = Query(10, ge=1, le=50)`
- **Response**: `SuggestionListResponse`
  ```json
  {
    "focal_entity": { "type": "invoice", "id": 1, "summary": "INV-2026-001 | Acme Supplies | 500.00 MYR" },
    "suggestions": [
      {
        "candidate_type": "receipt",
        "candidate_id": 4,
        "match_category": "possible_related",
        "heuristic_score": 0.85,
        "evidence": [
          "Focal invoice number 'INV-2026-001' is referenced in candidate metadata",
          "Exact amount match (500.00 MYR)",
          "Transaction date within 2 days of invoice date"
        ],
        "candidate_summary": "RCP-889 | Acme Supplies | 500.00 MYR",
        "is_already_linked": false
      }
    ],
    "total_found": 1
  }
  ```
- **Integrity & Filtering**:
  - Excludes self (same entity type and ID).
  - Excludes soft-deleted records (`ImportBatch.is_deleted == True`).
  - Flags already-linked entities (`is_already_linked: bool`).
  - Strict multi-tenant isolation: Only candidates sharing the authenticated user's `organization_id` are examined.
  - Deterministic sort order: Category priority (`exact_file_duplicate` $\rightarrow$ `possible_duplicate` $\rightarrow$ `possible_related`), then score descending, then candidate ID descending.

### 5. Verification Results
- **Matching Service Unit Tests (`test_matching_service.py`)**: 43/43 passed
- **Duplicate Detection & Suggestions Integration Tests (`test_api_duplicate_and_suggestions.py`)**: 16/16 passed
- **Full Backend Pytest Suite**: 492/492 passed (100% pass rate, 0 regressions)
- **Frontend Production Build (`vite build`)**: Clean (0 errors, 2.77s)
- **Code Hygiene (`git diff --check`)**: Clean (0 whitespace errors)


---

## M16.5E — Document Intelligence UX & Matching Quality Hotfix

### 1. Root Cause Matrix

| Reported Problem | Severity | Root Cause | Fix Applied | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Inspect Candidate / Source Preview Blocked** (`ERR_BLOCKED_BY_RESPONSE`, `localhost refused to connect`) | **P0** | `SourcePreviewModal.vue` embedded `/api/v1/documents/{id}/preview` directly inside an `<iframe>`. The backend `SecurityMiddleware` enforces `X-Frame-Options: DENY`, blocking the browser from framing API endpoints directly. | Replaced direct URL iframe embedding with authenticated `api.getDocumentPreview()` fetching binary blob. Images render via native `<img>` elements; PDFs render via managed `blob:` object URLs. Added explicit `URL.revokeObjectURL()` cleanup in `onBeforeUnmount` and modal reset. | **RESOLVED** |
| **B01 Tax Invoice Misclassified as Receipt** | **P0** | In `document_processing.py`, vision processing for image/scanned PDF files hardcoded `"document_type": "receipt"` and lacked `"tax invoice"` heuristics in `detect_document_type()`. Symmetrical fields (`merchant_name` vs `company_name`) were also wiped out when changing document types. | 1. Added `"tax invoice"` and `"tax inv"` signals in document type detection. 2. Dynamically inferred document type from vision payload/numbers in `process_document()`. 3. Added symmetrical alias population in `map_ai_extraction_to_review_state()` and field/line preservation in `parse_as()`. | **RESOLVED** |
| **Date-Only Matching Suggestions Noise** (e.g. ABC Office Supplies matched with cafes and furniture stores) | **P1** | `matching_service.py` accumulated date proximity score (up to 0.25) without requiring a core anchor. Any entity with a close transaction date could pass the 0.35 candidate threshold. | Enforced a strict core evidence gate: candidates must have an identifier match, high counterparty similarity (≥ 0.60), or moderate similarity (≥ 0.40) combined with exact amount match. Date proximity now only corroborates valid anchors; date-alone or amount-alone never qualifies. | **RESOLVED** |
| **Stale Relationship Counts on Partner Document** | **P1** | Linking or unlinking Invoice A and Receipt B only updated the focal entity's local state. The partner entity's `connected_count` in the explorer list remained stale until manual browser refresh. | Added `relationship-mutated` event pipeline from `ConnectedDocumentsPanel` -> detail modals (`InvoiceDetailModal`, `ReceiptDetailModal`) -> `DataExplorerView`. Mutates both entities' in-memory badge counts immediately without extra N+1 queries. | **RESOLVED** |
| **Duplicate Warning UX Exposes Developer Text** (`Set acknowledge_duplicate=true to confirm.`) | **P1** | 409 duplicate responses were rendered as raw developer-facing error text rather than business-friendly decision prompts. | Implemented user-friendly duplicate card: **"This document may already exist"** with structured metadata (existing type, number, counterparty, date, amount, reason) and 3 explicit actions: **View Existing**, **Import Anyway** (deliberate user acknowledgement), and **Cancel** (preserves form edits). | **RESOLVED** |
| **Duplicate Edit Receipt Action in Modal** | **P2** | `ReceiptDetailModal.vue` displayed "Edit Receipt" in both the header bar and the footer. | Removed header button, standardizing on a single primary action in the footer alongside Close. | **RESOLVED** |
| **Browser Console Error** (`startTime` undefined) | **P2** | Uncaught TypeError reading `'startTime'` in error-reporting stack. | Comprehensive audit confirmed zero instances of `startTime` exist in DataBridge codebase. The error originates from browser performance monitoring / APM extensions inspecting undefined timing metrics. Documented external origin. | **INVESTIGATED** |

---

### 2. Source Preview Security & Architecture
- **Preserved Security Posture**: `X-Frame-Options: DENY` and `Content-Security-Policy` headers remain globally active on all backend endpoints; security headers were not disabled or weakened.
- **Client-Side Blob Architecture**:
  - `SourcePreviewModal.vue` calls authenticated `api.getDocumentPreview(sourceFileId)`.
  - For image media types (`image/jpeg`, `image/png`, `image/webp`), renders safely in a dedicated container via `<img :src="objectUrl" />` (completely avoiding iframes).
  - For PDF media types (`application/pdf`), renders via `<iframe :src="objectUrl" />` using safe in-memory blob URLs that do not violate origin framing policies.
  - XLSX preview continues utilizing the structured table worksheet preview interface.
  - Memory leak protection: Every created `blob:` URL is explicitly tracked and revoked upon modal close, file switch, and component unmount via `URL.revokeObjectURL()`.

---

### 3. Document Classification & Type Correction (B01 Findings)
- **Root Cause**: DeepSeek Vision pipeline defaulted document types to `"receipt"`, while `detect_document_type` only matched `"invoice"`. Malaysian and Singaporean tax invoices frequently use the heading `"TAX INVOICE"` or abbreviation `"TAX INV"`.
- **Classification Enhancements**:
  - Enhanced keyword matching in `detect_document_type()` to capture `tax invoice`, `tax inv`, and `cukai inv`.
  - In `process_document()`, if vision output indicates `"invoice"` or document numbers start with `INV-`, the initial suggested type is set to `invoice`.
  - In `map_ai_extraction_to_review_state()`, populated bidirectional aliases:
    - `merchant_name` $\leftrightarrow$ `company_name`
    - `receipt_number` $\leftrightarrow$ `invoice_number`
    - `transaction_date` $\leftrightarrow$ `invoice_date`
  - In `POST /api/v1/documents/{id}/parse`, existing user edits and line items are preserved across document type switches, eliminating loss of extraction state.
  - Safe reimport / correction: Confirmed documents in the database are never auto-mutated. Users can toggle and correct document type prior to confirmation, persisting cleanly into either `InvoiceRecord` or `ReceiptRecord`.

---

### 4. Matching Quality & Evidence Gate Improvements
- **Strict Evidence Gate**: Date proximity score is strictly conditional upon `has_core_anchor`:
  $$	ext{has\_core\_anchor} = 	ext{ident\_matched} \lor 	ext{name\_sim} \ge 0.60 \lor (	ext{amount\_matched} \land 	ext{name\_sim} \ge 0.40)$$
- **Noise Rejection**:
  - Date proximity alone yields a total score of 0.0, rejecting unrelated businesses with close dates (e.g., ABC Office Supplies vs. cafes/furnishings).
  - Currency mismatches (e.g., USD 100 vs. MYR 100) are explicitly disqualified from amount matching.
  - Same currency alone provides zero score points.
  - Identical amounts without counterparty or reference correlation cannot qualify as related documents.
- **Negative Test Coverage**:
  - Added unit tests in `test_matching_service.py`:
    - `test_unrelated_merchants_with_nearby_dates_produce_no_suggestion`
    - `test_same_amount_unrelated_merchant_different_dates_produces_no_suggestion`
    - `test_currency_mismatch_prevents_amount_match`
    - `test_exact_identifier_cross_reference_anchors_match`

---

### 5. Reactive Both-End Relationship Synchronization
- **Event Flow**:
  1. `ConnectedDocumentsPanel.vue` emits `relationship-mutated` with `{ action: 'linked' | 'unlinked', partnerType, partnerId }` upon successful backend mutation.
  2. Forwarded through `InvoiceDetailModal.vue` and `ReceiptDetailModal.vue`.
  3. `DataExplorerView.vue` captures the mutation and updates in-memory arrays for both `documents`, `invoices`, and `receipts`:
     - Focal document `connected_count` updated via `count-changed`.
     - Partner document `connected_count` updated via `relationship-mutated`.
  4. Both table row badges immediately reflect the new connection state without manual page refresh.
  5. Navigating to the linked partner via `handleViewRelated` or "View Existing" opens with up-to-date counts.

---

### 6. Duplicate Warning & Review UX Polish
- **Business-Friendly Duplicate Dialog**:
  - Heading: **"This document may already exist"**
  - Subtitle: *"DataBridge found a document with matching information. Review the existing record before importing another copy."*
  - Structured metadata card displays: Existing Type, Document Number, Merchant/Company, Date, Amount/Currency, and Match Reason.
  - Developer text (such as `Set acknowledge_duplicate=true to confirm.`) is stripped and sanitized.
- **Three Clear Actions**:
  - **View Existing**: Deep-links to `/explorer?tab={type}&recordId={id}&docType={type}` in a new tab, auto-activating the tab and opening the detail modal.
  - **Import Anyway**: Prompts intentional user confirmation and re-sends payload with `acknowledge_duplicate: true`. Retains blocking validation checks so missing required fields cannot be bypassed.
  - **Cancel**: Dismisses the warning banner while preserving all entered form fields and line items.
- **Header & Note Polish**:
  - Removed uppercase technical eyebrow `DOCUMENT INGESTION & AUDIT`.
  - Subtitle displays the original filename with icon.
  - Compact collapsible AI extraction notes prevent clutter.
  - Desktop retains side-by-side preview/form grid; mobile cleanly stacks at $\le 850	ext{px}$.
  - Removed duplicate "Edit Receipt" button in `ReceiptDetailModal.vue` header.

---

### 7. Dataset B Acceptance Scenarios

| Scenario | Input | Expected Outcome | Verification Status |
| :--- | :--- | :--- | :--- |
| **B01 + B02** | B01 (Tax Invoice INV-1001, MYR 250) + B02 (Receipt RCP-1001, MYR 250) | B01 classified as Invoice; B02 as Receipt. Suggestion engine finds related document via merchant/reference/amount. Linking updates badges on both records. Candidate preview renders original source without `ERR_BLOCKED_BY_RESPONSE`. | **PASSED** |
| **B03** | Exact file duplicate upload | Recognized via SHA-256 checksum match as `exact_file_duplicate`. Duplicate warning offers View Existing, Import Anyway, and Cancel. | **PASSED** |
| **B04** | Modified image bytes, identical business transaction | Recognized as `possible_duplicate` via business metadata (merchant + receipt_number). Distinct from checksum duplicate. | **PASSED** |
| **B05 + B06** | Same merchant & amount, different transaction dates | Legitimate repeat purchase allowed. No hard 409 duplicate rejection solely from merchant + amount. | **PASSED** |
| **B07** | Unrelated merchants with close transaction dates | Disqualified by core evidence gate. No noisy suggestions surfaced. | **PASSED** |
| **B08** | Currency mismatch (e.g. USD vs MYR with same numeric amount) | Disqualified from monetary match. No suggestion created without corroborating anchor. | **PASSED** |

---

### 8. Verification Results
- **Matching Service Unit Tests (`test_matching_service.py`)**: 47/47 passed (100% pass rate)
- **Relationship Service Unit Tests (`test_relationship_service.py`)**: 14/14 passed
- **Full Backend Unit Test Suite (`tests/unit`)**: 268/268 passed (7.61s)
- **Duplicate & Suggestion Integration Tests (`test_api_duplicate_and_suggestions.py`)**: 16/16 passed
- **Relationship Integration Tests (`test_api_relationships.py`)**: 10/10 passed
- **Source Preview & Data Explorer Integration Tests (`test_m16_3_1_source_preview_hotfix.py`, `test_m16_3_data_explorer.py`, `test_api_documents_ai.py`)**: 26/26 passed
- **Frontend TypeScript Validation (`vue-tsc --noEmit`)**: 0 errors
- **Frontend Production Build (`vite build`)**: Clean build in 2.92s
- **Code Hygiene (`git diff --check`)**: Clean (0 whitespace errors)
- **Alembic Migration State**: Clean at `0008_document_relationships (head)`. No unnecessary migrations added.

---

### 9. Remaining Limitations & M17 Readiness
- **Current Scope**: Relationships remain user-confirmed and non-destructive. No automated financial reconciliation or payment settlement is performed, adhering strictly to the Business Document Intelligence platform charter.
- **M17 Readiness**: All P0/P1 defects identified in Dataset B browser testing have been fixed, tested, and verified. The codebase is clean, robust, and fully prepared for Milestone 17.
