# Milestone 16 - Financial Document Classification & Unified Business Intelligence

## Status Overview

| Sub-milestone | Name | Status |
|---|---|---|
| M16.1 | Repository Inspection & Architecture Audit | Complete |
| M16.2 | Financial Direction Classification & Receipt History Visibility | Complete |
| M16.3 | Unified Financial Data Explorer | Complete |
| M16.4 | Direction-Aware Dashboard Analytics | Next |

---

## M16.2 - Financial Direction Classification

### Data Model

InvoiceRecord.direction: sales / purchase / unclassified (default). CHECK constraint.
ReceiptRecord.direction: expense / income / unclassified (default). CHECK constraint.
Alembic migration: 0007_financial_direction

### Changes
- ReceiptRecord to ImportBatch ORM relationship
- Receipt visibility in Import History
- Direction selection during document confirmation
- 367 backend tests passed at completion

---

## M16.3 - Unified Financial Data Explorer

### New Backend Endpoints

GET /api/v1/data/receipts - Paginated receipt list with filters
GET /api/v1/data/receipts/{receipt_id} - Full receipt detail
GET /api/v1/data/documents - Unified invoice+receipt register (UNION ALL)

Filter options endpoint extended: merchants, payment_methods, directions.

### Receipt Filters
search, merchant, receipt_number, currency, direction (expense/income/unclassified),
payment_method, date_from, date_to, amount_min, amount_max,
sort_by (transaction_date/merchant_name/total_amount/id/created_at/direction/receipt_number),
sort_order, page, page_size

### Document Filters
search, document_type (invoice/receipt/all), direction, currency, date_from, date_to,
sort_by (document_date/counterparty/total_amount/created_at/document_number/line_item_count/direction/record_id)

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

### Security
- get_tenant_db injects organization_id into each SQLAlchemy session
- active_record_scope() excludes is_deleted=True batches
- Receipt detail returns 404 for cross-tenant IDs
- UNION ALL queries apply active_record_scope() per arm

### Files Changed
Backend: data_explorer.py, schemas/data_explorer.py, business_query.py,
         export_builder.py, routers/exports.py, schemas/export.py
Frontend: types/api.ts, services/api.ts, DataExplorerView.vue,
          components/explorer/ReceiptDetailModal.vue (new)
Tests: tests/integration/test_m16_3_data_explorer.py (new, 7 tests)

### Test and Build Results
M16.3 integration tests: 7/7 passed
Full backend pytest suite: 374/374 passed
Frontend TypeScript (tsc --noEmit): 0 errors
Frontend Vite production build: Clean
git diff --check: No whitespace errors

### Known Limitations
1. Receipt line items not in bulk exports (detail modal only)
2. No custom_fields on ReceiptRecord - no dynamic columns in receipt export
3. No invoice-receipt linking
4. No currency conversion - original currency preserved
5. Store address, branch, cashier not in receipt CSV/XLSX rows

### M16.4 Readiness
InvoiceRecord.direction and ReceiptRecord.direction fully queryable with tenant isolation.
Suggested M16.4: revenue vs expense summary by direction, month-over-month breakdown,
unclassified document count indicator. Currency grouping required before summing.

---
Document last updated: M16.3 completion.
