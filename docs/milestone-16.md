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
| M16.5 | Advanced Financial Analytics & Export Reconciliations | Planned |

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

## M16.5 Roadmap
- Payment settlement tagging (paid / unpaid / partial).
- Invoice-to-receipt matching and reconciliation suggestions.
- Direction-aware CSV and Excel bulk financial summary exports from Dashboard.
- Advanced variance analytics between invoiced purchases and counter receipts.
