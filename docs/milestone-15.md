# Milestone 15 — AI-Powered Receipt Intelligence & Smart Ingestion Studio

## M15 — AI-Powered Receipt Intelligence (Implemented)

Integrates DeepSeek Vision alongside existing Tesseract OCR for receipt extraction.

### What was built

- **Vision provider** (`vision_provider.py`): DeepSeek Vision API client with base64 image encoding, timeout, rate-limit, and parse-error handling
- **AI receipt schemas** (`ai_receipt.py`): Structured `AIReceiptHeader`, `AIReceiptLineItem`, `AIReceiptExtraction` Pydantic models with validation
- **Receipt reconciliation** (`receipt_reconciliation.py`): Deterministic arithmetic validation of subtotal + tax = total, change, rounding
- **Three processing modes**: `auto` (Vision → OCR fallback), `vision_only`, `local_ocr`
- **PDF rasterisation**: scanned-PDF page detection via `pypdfium2`; rasterised to JPEG for Vision/OCR
- **Structured validation items**: `DocumentValidationItem` schema with `severity` (error/warning/info/success) and `category`
- **Receipt identifier sanitisation**: rejects masked PANs and table/tab numbers as receipt numbers

### Tests

352 backend tests passing at commit `3a013ad`.

---

## M15.6 — Unified Upload & Processing Queue (Implemented)

Replaces the two competing upload entry points (PDF/image button + batch XLSX button) with a single **Smart Ingestion Studio** workspace.

### Features

- **Universal drag-and-drop upload zone** accepting XLSX, PDF, JPG, and PNG in any combination
- **Multi-file selection** via browser picker and drag-and-drop; files can be added to an existing queue
- **Per-file queue row** showing: file name, format badge, suggested document type, file size, status, action links
- **File statuses**: Queued → Uploading → Processing → Needs Review → Imported / Failed
- **Bounded concurrency**: uploads are processed in parallel batches of 3 to avoid overwhelming the server
- **File validation**: type and size checked client-side; server errors shown per-file, not globally
- **Duplicate prevention**: files already in the queue are skipped with a warning
- **Queue summary counters**: total / uploading / needs review / imported / failed
- **Per-file routing**: XLSX files use the existing workbook flow; PDF/image files use the document ingestion API

### Architecture

The queue is in-memory (session-scoped). No new backend endpoints were introduced.
Each file delegates to the existing APIs:
- XLSX → `POST /api/v1/files/upload` then `POST /api/v1/batch-imports`
- PDF/image → `POST /api/v1/documents`

### Limitations

- Queue state is lost on page navigation or refresh (no durable background jobs)
- XLSX files with uncertain template matches go to Needs Review; the existing 4-step review flow handles them
- Mixed-format batch is a frontend orchestration only; no single backend endpoint processes mixed files together

---

## M15.7 — Smart Document Classification & Guided Import (Implemented)

Provides per-file document type suggestions as part of the queue.

### Features

- **Format detection**: determined from file extension/MIME type (XLSX, PDF, JPEG, PNG)
- **Suggested document type**: derived from backend `document_type` field after upload (invoice/receipt/unknown) or pre-classified as Spreadsheet for XLSX
- **Manual override**: compact type selector on each queue row; changing type triggers `POST /documents/{id}/parse`
- **No new paid AI calls**: classification uses existing deterministic extraction and AI Vision results already returned at upload time

### Routing per type

| File format | Suggested type | Review path |
|---|---|---|
| `.xlsx` | Spreadsheet | Existing workbook 4-step flow |
| `.pdf` / image | Invoice or Receipt | `DocumentReviewView` |
| `.pdf` / image (unresolved) | Unknown | `DocumentReviewView` with manual type selector |

---

## M15.8 — Receipt Review UX Refinement (Implemented)

Improves the `DocumentReviewView` without redesigning the split-pane layout.

### Changes

- **Severity-banded validation panel**: Error / Warning / Info / Success notices rendered from structured `validation_items`; legacy flat `warnings` list used as fallback for older documents
- **Collapsible AI Notes**: expandable section for `ai_notes` from DeepSeek provider; collapsed by default, shows note count
- **Receipt number optional**: confirmation no longer blocks on missing `receipt_number`; only `merchant_name` required
- **Confidence indicators**: Low-confidence fields have amber/red border; high-confidence fields appear normal
- **Line-item table**: existing horizontal scroll preserved; description inputs are full-width
- **Fallback notices**: AI Vision fallback and OCR error notices remain always-visible
- **Blocking errors never hidden**: Error-severity items render outside any collapsible

---

## M16 — Financial Document Classification & Reporting (Future)

> **Status: Research only — not implemented.**

### Open questions requiring research

- **Incoming vs outgoing invoices**: distinguishing supplier invoices (accounts payable) from customer invoices (accounts receivable)
- **Expense vs income receipts**: how to classify receipts by financial direction
- **History and Explorer impact**: where receipt and invoice records appear; filter/search implications
- **Dashboard and analytics impact**: how incoming/outgoing classification affects trend and summary charts
- **Data model changes**: whether new columns/tables are required or existing `custom_fields` JSON is sufficient
- **User workflow**: how users assign or correct document direction; whether it is manual, inferred, or rule-based

### Deferred until

M16 requires agreement on the accounting data model before implementation begins. No database migrations or API changes should be made speculatively.
