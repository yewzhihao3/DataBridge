# Milestone 14 — Document ingestion

DataBridge now accepts `.jpg`, `.jpeg`, `.png`, and `.pdf` in addition to the existing XLSX flow. Document uploads validate their extension, content signature, readability, size (images 10 MB, PDFs 20 MB), and PDFs are limited to 25 pages. Files remain private storage objects and every API read is tenant-scoped.

The pipeline is: source document → native PDF text extraction or OCR-provider abstraction → deterministic invoice parser → validation/review → existing `ImportBatch`, `InvoiceRecord`, and `InvoiceLineItem` persistence. PDF text is extracted first with `pypdf`; scanned PDFs and images route to the local Tesseract adapter when installed. The adapter is optional and returns a review-safe “OCR unavailable” result rather than claiming success. This keeps providers replaceable without coupling persistence to OCR.

Extraction caches bounded per-page text, field provenance, confidence (`high`, `medium`, `low`), warnings, and processing metadata in `document_extractions`. Raw OCR text is not put in audit events. Deterministic parsing recognizes common invoice labels, dates, currency marks, and totals. Confirming a document requires user-supplied company and invoice number; edits are the persisted values. Duplicate checks run before the existing canonical invoice records are created.

All document imports require review. This is especially important for handwriting, ambiguous dates or amounts, low-confidence fields, and incomplete OCR. Line-item extraction is deliberately conservative in this milestone; users can add or correct rows at confirmation. Reprocessing updates cached extraction only and never creates business records.

Endpoints are `POST /api/v1/documents`, `GET /api/v1/documents/{id}`, `GET /api/v1/documents/{id}/preview`, `POST /api/v1/documents/{id}/process`, and `POST /api/v1/documents/{id}/confirm`. Preview access uses the same authenticated organization scope as every source-file operation.

## Frontend workflow

Ingestion Studio offers **Choose PDF or image** alongside the unchanged XLSX workflow. A document upload opens the authenticated `/documents/:id/review` route, so it can be refreshed or bookmarked safely. The review page obtains the original through the authorized preview endpoint, renders images or the browser PDF viewer, and revokes its blob URL when closed. It displays editable canonical fields, source/provenance text, low/medium/high confidence, warnings, editable line items, reprocessing, and confirmation. Confirmation sends the edited values to the backend; it does not rerun OCR.

For image OCR in local development, install the native Tesseract executable and restart DataBridge. When it is unavailable, the review page exposes the backend's actionable manual-entry warning. Scanned PDFs similarly remain clearly marked as requiring OCR when no selectable PDF text is available. Manual QA: build/type-check passed; test text PDFs and local-Tesseract image files through Ingestion Studio after logging in.

Limitations: OCR accuracy depends on scan/photo quality; handwriting can be unreliable; no AI-assisted extraction is used; no perfect line-item detection or accounting certification is claimed. Human review remains mandatory for document imports.

## Receipt extension

OCR text is deterministically classified as `invoice`, `receipt`, or `unknown` using weighted business-document labels. Receipt parsing extracts merchant name, receipt number, transaction date and time, currency, subtotal, tax, total, and compact receipt line items. A bare `$` remains unassigned unless location or currency-code context resolves it. Users can switch between Invoice and Receipt in review; this reparses cached OCR text and does not rerun OCR.

Receipts persist in dedicated `receipt_records` and `receipt_line_items` tables linked to the existing tenant-scoped import batch. This preserves receipt semantics and keeps receipt totals out of invoice-only Explorer and Dashboard analytics. Import History identifies them through the `Document receipt` source template. Duplicate detection uses merchant, receipt number, and total within the active organization. A future unified Documents explorer can expose receipt browsing without silently mixing it into invoice analytics.
