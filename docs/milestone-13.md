# Milestone 13 — Batch Import and Interaction Feedback

## Batch domain model

`BatchImportSession` is an organization-scoped outer grouping for a user's multi-file upload. Each `BatchImportFile` points at a normal `SourceFile`; a successful file still creates its own existing `ImportBatch`, `InvoiceRecord`, and line items. This intentionally preserves single-file import semantics and makes every file atomic.

The default limit is 25 XLSX files per session (`MAX_BATCH_FILE_COUNT`), with the existing 10 MB per-file limit retained. Workbook planning is deliberately bounded: the initial synchronous API implementation analyzes one file at a time (therefore never exceeds the configurable `BATCH_ANALYSIS_CONCURRENCY` cap, default 4) and introduces no distributed worker.

## Processing and statuses

Each workbook is profiled, structurally detected, and passed to the existing deterministic template matcher. A high-confidence saved template is `READY`; smart mappings and unresolved layouts are `REVIEW`; unreadable workbooks are `FAILED`. `IMPORTING`, `IMPORTED`, `DUPLICATE`, and `SKIPPED` are user-facing lifecycle states. A mixed batch can contain invoice and dataset templates, and only ready files are confirmed by **Import Ready Files**.

Confirmation reuses the normal extractor, validator, duplicate checker, and persistence endpoint. Each confirmation has its own transaction: a failed file persists no partial record while other ready files remain imported. Existing soft-deleted import batches are excluded by the existing duplicate policy. A later file with the same canonical key is caught by that same workspace-scoped duplicate checker after the first succeeds.

## Needs Review workflow

`Needs Review` means the file was uploaded and extracted successfully, but validation produced non-fatal warnings and no invoice records have been persisted. The pending `BatchImportFile` is retained in the organization-scoped session, so it survives navigation and refresh. Import History lists these items separately from completed import batches. **Review** opens the existing extraction preview and warning list without uploading or selecting a template again; **Accept Warnings & Import** invokes the normal confirmation path with an internal acknowledgement. Confirmation reruns validation and duplicate checks, remains atomic, and changes only the accepted file to `IMPORTED`.

Import History also lists every session that still has pending files, rather than showing only warning files. A pending-session row provides its complete total and `Ready`, `Needs Review`, and `Imported` counts; **View Batch** resumes the persisted batch at `/history/batch/{sessionId}`. This keeps ready-but-unconfirmed files visible and does not fabricate `ImportBatch` records before confirmation.

Batch sessions and their child rows are tenant-scoped, and creation/completion produce `BATCH_UPLOAD_CREATED` and `BATCH_IMPORT_COMPLETED` audit events. Removing a pending item only marks it skipped in that session; it never deletes imported data. Failed/review items can be reanalyzed.

## Toasts

The app-wide `toast` service provides `success`, `info`, `warning`, and `error`. `ToastHost` is fixed bottom-right, stacks messages, auto-dismisses, allows keyboard-accessible manual dismissal, uses semantic tokens, and moves safely within the viewport on mobile. Toasts communicate asynchronous operation outcomes; field validation stays inline and dedicated import result panels remain intact.

## Limitations

M13 accepts XLSX only. It does not add JPG, PNG, PDF, OCR, handwritten-invoice processing, AI extraction, ZIP/folder/email ingestion, distributed background workers, or payment/subscription logic. Smart mappings remain review-first; only strong deterministic saved-template matches are eligible for direct batch import.
