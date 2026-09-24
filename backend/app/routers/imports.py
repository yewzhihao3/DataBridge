"""
app/routers/imports.py — Endpoints for extraction preview, confirmation, and import history.

──────────────────────────────────────────────────────────────────────────────
Features:
- POST /api/v1/imports/extract: in-memory preview with full provenance and validation.
- POST /api/v1/imports/confirm: transactional re-validation and database persistence.
- GET  /api/v1/imports: paginated list of historical import batches (excludes soft-deleted).
- GET  /api/v1/imports/{batch_id}: detailed view of an imported batch and records.
- DELETE /api/v1/imports/{batch_id}: soft-delete a batch (audit-safe).
- PATCH /api/v1/imports/{batch_id}/records/{record_id}: edit canonical fields on an invoice record.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.constants import CANONICAL_INVOICE_FIELDS
from app.database import get_db
from app.models.invoice import ImportBatch, InvoiceRecord, ValidationErrorRecord
from app.models.source_file import SourceFile
from app.models.template import Template
from app.schemas.extraction import (
    ExtractedFieldSchema,
    ExtractionErrorSchema,
    ExtractionPreviewResponse,
    ExtractionRequest,
    RowExtractionPreviewSchema,
    ValidationIssueSchema,
    ValidationReportSchema,
)
from app.schemas.import_batch import (
    ImportBatchDetailResponse,
    ImportBatchListItem,
    ImportConfirmRequest,
    InvoiceRecordRead,
    InvoiceRecordUpdate,
    ValidationErrorRecordRead,
)
from app.services.extractor import extract_from_file
from app.services.validator import ValidationConfig, validate_extraction
from app.services.workbook_inspector import (
    CorruptWorkbookError,
    FileSizeExceededError,
    InvalidFileFormatError,
)

router = APIRouter(prefix="/api/v1/imports", tags=["Imports"])


# ── Helper: Live Duplicate Checker ───────────────────────────────────────────


def _create_db_duplicate_checker(db: Session) -> Any:
    """
    Creates a read-only duplicate checker that queries existing InvoiceRecord entries.
    """
    def check_duplicate(company_name: str, invoice_number: str) -> bool:
        return (
            db.query(InvoiceRecord)
            .filter(
                InvoiceRecord.company_name == company_name,
                InvoiceRecord.invoice_number == invoice_number,
            )
            .first()
            is not None
        )

    return check_duplicate


def _json_serial(obj: Any) -> Any:
    """JSON serializer for Decimal, date, datetime objects."""
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


# ── Preview Endpoint ──────────────────────────────────────────────────────────


@router.post(
    "/extract",
    response_model=ExtractionPreviewResponse,
    summary="Extract and validate data from an uploaded file using a template",
)
def extract_preview(
    payload: ExtractionRequest,
    db: Session = Depends(get_db),
) -> ExtractionPreviewResponse:
    """
    Applies a template configuration against an uploaded Excel file, extracts cell data,
    and runs the business validation layer to return a complete in-memory preview report.
    """
    source_file = db.query(SourceFile).filter(SourceFile.id == payload.file_id).first()
    if not source_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source file with ID {payload.file_id} was not found.",
        )

    template = (
        db.query(Template)
        .options(joinedload(Template.field_mappings))
        .filter(Template.id == payload.template_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {payload.template_id} was not found.",
        )

    file_path = settings.upload_dir / source_file.stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file was not found on disk storage.",
        )

    try:
        extraction_result = extract_from_file(
            file_path=file_path,
            template=template,
            max_size_mb=settings.max_file_size_mb,
        )

        # Build target_field mapping so preview normalized_data keys match persistence
        preview_field_to_target: dict[str, str] = {
            m.field_name: m.target_field
            for m in template.field_mappings
            if m.target_field
        }
        validation_report = validate_extraction(
            extraction_result=extraction_result,
            config=ValidationConfig(),
            duplicate_checker=_create_db_duplicate_checker(db),
            field_to_target=preview_field_to_target if preview_field_to_target else None,
        )

        preview_records: list[RowExtractionPreviewSchema] = []
        if extraction_result.is_multi_record:
            row_results_by_num = {r.row_number: r for r in extraction_result.rows}
            for rr in validation_report.row_reports:
                row_res = row_results_by_num.get(rr.source_row_number)
                r_fields = row_res.fields if row_res else []
                r_errors = row_res.errors if row_res else []
                r_warnings = row_res.warnings if row_res else []
                r_has_errors = (not rr.is_valid) or (len(r_errors) > 0)

                preview_records.append(
                    RowExtractionPreviewSchema(
                        source_row_number=rr.source_row_number,
                        fields=[
                            ExtractedFieldSchema(
                                field_name=f.field_name,
                                mapping_type=f.mapping_type,
                                source_worksheet=f.source_worksheet,
                                source_cell_ref=f.source_cell_ref,
                                raw_value=f.raw_value,
                                data_type=f.data_type,
                                is_required=f.is_required,
                                is_empty_cell=f.is_empty_cell,
                                is_formula=f.is_formula,
                                formula_expression=f.formula_expression,
                                normalized_value=f.normalized_value,
                                status=f.status,
                                error_message=f.error_message,
                                warning_message=f.warning_message,
                            )
                            for f in r_fields
                        ],
                        has_errors=r_has_errors,
                        error_count=len(r_errors) + sum(1 for i in rr.issues if i.severity == "error"),
                        warning_count=len(r_warnings) + sum(1 for i in rr.issues if i.severity == "warning"),
                        errors=[
                            ExtractionErrorSchema(
                                field_name=e.field_name,
                                message=e.message,
                                worksheet=e.worksheet,
                                cell_ref=e.cell_ref,
                                error_type=e.error_type,
                            )
                            for e in r_errors
                        ],
                        warnings=r_warnings,
                        normalized_data=rr.normalized_data,
                    )
                )

        return ExtractionPreviewResponse(
            file_id=source_file.id,
            template_id=template.id,
            template_name=template.name,
            target_worksheet=extraction_result.target_worksheet,
            is_multi_record=extraction_result.is_multi_record,
            record_count=len(preview_records) if extraction_result.is_multi_record else 1,
            fields=[
                ExtractedFieldSchema(
                    field_name=f.field_name,
                    mapping_type=f.mapping_type,
                    source_worksheet=f.source_worksheet,
                    source_cell_ref=f.source_cell_ref,
                    raw_value=f.raw_value,
                    data_type=f.data_type,
                    is_required=f.is_required,
                    is_empty_cell=f.is_empty_cell,
                    is_formula=f.is_formula,
                    formula_expression=f.formula_expression,
                    normalized_value=f.normalized_value,
                    status=f.status,
                    error_message=f.error_message,
                    warning_message=f.warning_message,
                )
                for f in extraction_result.fields
            ] if not extraction_result.is_multi_record else [],
            records=preview_records,
            has_errors=extraction_result.has_errors or (not validation_report.is_valid_for_import),
            error_count=extraction_result.error_count + validation_report.error_count,
            warning_count=extraction_result.warning_count + validation_report.warning_count,
            errors=[
                ExtractionErrorSchema(
                    field_name=e.field_name,
                    message=e.message,
                    worksheet=e.worksheet,
                    cell_ref=e.cell_ref,
                    error_type=e.error_type,
                )
                for e in extraction_result.errors
            ],
            warnings=extraction_result.warnings,
            validation_report=ValidationReportSchema(
                is_valid_for_import=validation_report.is_valid_for_import,
                issues=[
                    ValidationIssueSchema(
                        rule_id=i.rule_id,
                        field_name=i.field_name,
                        severity=i.severity,
                        message=i.message,
                        cell_ref=i.cell_ref,
                        worksheet=i.worksheet,
                        actual_value=i.actual_value,
                    )
                    for i in validation_report.issues
                ],
                error_count=validation_report.error_count,
                warning_count=validation_report.warning_count,
                info_count=validation_report.info_count,
                normalized_data=validation_report.normalized_data,
            ),
        )

    except (InvalidFileFormatError, CorruptWorkbookError, FileSizeExceededError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extraction failed: {exc}",
        ) from exc


# ── Confirmation Endpoint (Transactional Persistence) ─────────────────────────


@router.post(
    "/confirm",
    response_model=ImportBatchDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm and persist an extraction into the database",
)
def confirm_import(
    payload: ImportConfirmRequest,
    db: Session = Depends(get_db),
) -> ImportBatchDetailResponse:
    """
    Re-extracts and validates the file, verifying data integrity before committing
    an ImportBatch and associated InvoiceRecord in an atomic database transaction.
    """
    source_file = db.query(SourceFile).filter(SourceFile.id == payload.file_id).first()
    if not source_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source file with ID {payload.file_id} was not found.",
        )

    template = (
        db.query(Template)
        .options(joinedload(Template.field_mappings))
        .filter(Template.id == payload.template_id)
        .first()
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template with ID {payload.template_id} was not found.",
        )

    file_path = settings.upload_dir / source_file.stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file was not found on disk storage.",
        )

    # 1. Perform atomic re-extraction
    try:
        extraction_result = extract_from_file(
            file_path=file_path,
            template=template,
            max_size_mb=settings.max_file_size_mb,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Re-extraction failed during confirmation: {exc}",
        ) from exc

    # 2. Run business validation, passing target_field mapping for correct key routing
    field_to_target: dict[str, str] = {
        m.field_name: m.target_field
        for m in template.field_mappings
        if m.target_field
    }
    validation_report = validate_extraction(
        extraction_result=extraction_result,
        config=ValidationConfig(),
        duplicate_checker=_create_db_duplicate_checker(db),
        field_to_target=field_to_target if field_to_target else None,
    )

    # 3. Validation rule checks: Hard block on errors
    if not validation_report.is_valid_for_import or extraction_result.has_errors:
        total_errors = extraction_result.error_count + validation_report.error_count
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot confirm import: extracted data failed validation with {total_errors} error(s). "
                "Please review the extraction preview and resolve all errors in the source file."
            ),
        )

    # 4. Warning policy check: require explicit acknowledgment
    if validation_report.warning_count > 0 and not payload.acknowledge_warnings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Import blocked: {validation_report.warning_count} warning(s) detected. "
                "Set 'acknowledge_warnings=true' in the request to confirm import with warnings."
            ),
        )

    # 5. Build and commit database transaction
    _norm_canonical_set = {
        str(c).strip().lower().replace(" ", "_").replace("-", "_")
        for c in CANONICAL_INVOICE_FIELDS
    } | {"company", "invoice_num", "date", "amount"}

    def _resolve_row_canonical(norm_data: dict[str, Any], primary: str, *aliases: str) -> Any:
        _norm_lookup = {
            str(_k).strip().lower().replace(" ", "_").replace("-", "_"): _v
            for _k, _v in norm_data.items()
        }
        for key in (primary, *aliases):
            if key in norm_data:
                return norm_data[key]
        for key in (primary, *aliases):
            if key in _norm_lookup:
                return _norm_lookup[key]
        return None

    if validation_report.is_multi_record:
        rec_count = len(validation_report.row_reports)
        batch = ImportBatch(
            source_file_id=source_file.id,
            template_id=template.id,
            status="imported",
            record_count=rec_count,
            warning_count=validation_report.warning_count,
        )

        rows_by_num = {r.row_number: r for r in extraction_result.rows}

        for rr in validation_report.row_reports:
            norm_data = rr.normalized_data
            comp_name = _resolve_row_canonical(norm_data, "company_name", "company") or "Unknown Company"
            inv_num = _resolve_row_canonical(norm_data, "invoice_number", "invoice_num") or "Unknown Invoice"
            inv_date = _resolve_row_canonical(norm_data, "invoice_date", "date")
            tot_amt = _resolve_row_canonical(norm_data, "total_amount", "amount")
            curr = _resolve_row_canonical(norm_data, "currency")

            custom_fields: dict[str, Any] = {}
            for key, val in norm_data.items():
                norm_k = str(key).strip().lower().replace(" ", "_").replace("-", "_")
                if key not in CANONICAL_INVOICE_FIELDS and norm_k not in _norm_canonical_set:
                    custom_fields[key] = val if not hasattr(val, "isoformat") else val.isoformat()

            row_res = rows_by_num.get(rr.source_row_number)
            raw_dict = {f.field_name: f.raw_value for f in row_res.fields} if row_res else {}
            raw_json = json.dumps(raw_dict, default=_json_serial)

            invoice_record = InvoiceRecord(
                company_name=str(comp_name),
                invoice_number=str(inv_num),
                invoice_date=inv_date,
                total_amount=tot_amt,
                currency=curr,
                source_worksheet=extraction_result.target_worksheet,
                source_row_number=rr.source_row_number,
                raw_data=raw_json,
                custom_fields=custom_fields if custom_fields else None,
            )
            batch.invoice_records.append(invoice_record)
    else:
        norm_data = validation_report.normalized_data
        comp_name = _resolve_row_canonical(norm_data, "company_name", "company") or "Unknown Company"
        inv_num = _resolve_row_canonical(norm_data, "invoice_number", "invoice_num") or "Unknown Invoice"
        inv_date = _resolve_row_canonical(norm_data, "invoice_date", "date")
        tot_amt = _resolve_row_canonical(norm_data, "total_amount", "amount")
        curr = _resolve_row_canonical(norm_data, "currency")

        custom_fields = {}
        for key, val in norm_data.items():
            norm_k = str(key).strip().lower().replace(" ", "_").replace("-", "_")
            if key not in CANONICAL_INVOICE_FIELDS and norm_k not in _norm_canonical_set:
                custom_fields[key] = val if not hasattr(val, "isoformat") else val.isoformat()

        raw_dict = {f.field_name: f.raw_value for f in extraction_result.fields}
        raw_json = json.dumps(raw_dict, default=_json_serial)

        batch = ImportBatch(
            source_file_id=source_file.id,
            template_id=template.id,
            status="imported",
            record_count=1,
            warning_count=validation_report.warning_count,
        )

        invoice_record = InvoiceRecord(
            company_name=str(comp_name),
            invoice_number=str(inv_num),
            invoice_date=inv_date,
            total_amount=tot_amt,
            currency=curr,
            source_worksheet=extraction_result.target_worksheet,
            source_row_number=None,
            raw_data=raw_json,
            custom_fields=custom_fields if custom_fields else None,
        )
        batch.invoice_records.append(invoice_record)

    # Persist historical warning diagnostics
    for issue in validation_report.issues:
        if issue.severity in {"warning", "info"}:
            batch.validation_issues.append(
                ValidationErrorRecord(
                    rule_id=issue.rule_id,
                    field_name=issue.field_name,
                    severity=issue.severity,
                    message=issue.message,
                    cell_ref=issue.cell_ref,
                    worksheet=issue.worksheet,
                )
            )

    try:
        db.add(batch)
        db.commit()
        db.refresh(batch)

        first_raw_dict = None
        if batch.invoice_records and batch.invoice_records[0].raw_data:
            try:
                first_raw_dict = json.loads(batch.invoice_records[0].raw_data)
            except Exception:
                first_raw_dict = None

        return ImportBatchDetailResponse(
            id=batch.id,
            source_file_id=source_file.id,
            original_filename=source_file.original_name,
            template_id=template.id,
            template_name=template.name,
            status=batch.status,
            record_count=batch.record_count,
            warning_count=batch.warning_count,
            imported_at=batch.imported_at,
            invoice_records=[
                InvoiceRecordRead.model_validate(rec) for rec in batch.invoice_records
            ],
            validation_issues=[
                ValidationErrorRecordRead.model_validate(iss)
                for iss in batch.validation_issues
            ],
            raw_data=first_raw_dict,
        )

    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to persist import batch: {exc}",
        ) from exc


# ── History Listing Endpoint ──────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[ImportBatchListItem],
    summary="List historical import batches",
)
def list_import_batches(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Limit of records returned"),
    db: Session = Depends(get_db),
) -> list[ImportBatchListItem]:
    """
    Retrieves a paginated list of historical import batches with summary metrics.
    """
    batches = (
        db.query(ImportBatch)
        .options(
            joinedload(ImportBatch.source_file),
            joinedload(ImportBatch.template),
        )
        .filter(ImportBatch.is_deleted == False)  # noqa: E712
        .order_by(ImportBatch.imported_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    results: list[ImportBatchListItem] = []
    for b in batches:
        results.append(
            ImportBatchListItem(
                id=b.id,
                source_file_id=b.source_file_id,
                original_filename=b.source_file.original_name if b.source_file else "Unknown",
                template_id=b.template_id,
                template_name=b.template.name if b.template else "Unknown",
                status=b.status,
                record_count=b.record_count,
                warning_count=b.warning_count,
                imported_at=b.imported_at,
            )
        )
    return results


# ── Batch Detail Endpoint ─────────────────────────────────────────────────────


@router.get(
    "/{batch_id}",
    response_model=ImportBatchDetailResponse,
    summary="Get details of an import batch by ID",
)
def get_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
) -> ImportBatchDetailResponse:
    """
    Retrieves complete details of an import batch, including associated invoice records
    and historical validation issues.
    """
    batch = (
        db.query(ImportBatch)
        .options(
            joinedload(ImportBatch.source_file),
            joinedload(ImportBatch.template),
            joinedload(ImportBatch.invoice_records),
            joinedload(ImportBatch.validation_issues),
        )
        .filter(ImportBatch.id == batch_id, ImportBatch.is_deleted == False)  # noqa: E712
        .first()
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import batch with ID {batch_id} was not found.",
        )

    # Parse raw_data from first invoice record if present
    raw_dict = None
    if batch.invoice_records and batch.invoice_records[0].raw_data:
        try:
            raw_dict = json.loads(batch.invoice_records[0].raw_data)
        except Exception:
            raw_dict = None

    return ImportBatchDetailResponse(
        id=batch.id,
        source_file_id=batch.source_file_id,
        original_filename=batch.source_file.original_name if batch.source_file else "Unknown",
        template_id=batch.template_id,
        template_name=batch.template.name if batch.template else "Unknown",
        status=batch.status,
        record_count=batch.record_count,
        warning_count=batch.warning_count,
        imported_at=batch.imported_at,
        invoice_records=[
            InvoiceRecordRead.model_validate(rec) for rec in batch.invoice_records
        ],
        validation_issues=[
            ValidationErrorRecordRead.model_validate(iss)
            for iss in batch.validation_issues
        ],
        raw_data=raw_dict,
    )


# ── Soft-Delete Endpoint ─────────────────────────────────────────────────────────────────────


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete an import batch (audit-safe)",
)
def soft_delete_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """
    Marks the specified import batch as deleted (is_deleted=True) without removing
    any data from the database. Soft-deleted batches are excluded from normal
    list and detail queries, preserving the audit trail.
    """
    batch = (
        db.query(ImportBatch)
        .filter(ImportBatch.id == batch_id, ImportBatch.is_deleted == False)  # noqa: E712
        .first()
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import batch with ID {batch_id} was not found or has already been deleted.",
        )
    batch.is_deleted = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Invoice Record Edit Endpoint ────────────────────────────────────────────────────────────────────


@router.patch(
    "/{batch_id}/records/{record_id}",
    response_model=InvoiceRecordRead,
    summary="Edit canonical fields on an invoice record",
)
def update_invoice_record(
    batch_id: int,
    record_id: int,
    payload: InvoiceRecordUpdate,
    db: Session = Depends(get_db),
) -> InvoiceRecordRead:
    """
    Updates one or more canonical fields on an existing invoice record.
    Custom fields are preserved unchanged. The parent batch must not be soft-deleted.
    Payload fields set to None are treated as "no change" (use explicit empty string for clearing text).
    """
    # Verify the batch exists and is not soft-deleted
    batch = (
        db.query(ImportBatch)
        .filter(ImportBatch.id == batch_id, ImportBatch.is_deleted == False)  # noqa: E712
        .first()
    )
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import batch with ID {batch_id} was not found or has been deleted.",
        )

    # Verify the record belongs to this batch
    record = (
        db.query(InvoiceRecord)
        .filter(InvoiceRecord.id == record_id, InvoiceRecord.batch_id == batch_id)
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice record with ID {record_id} was not found in batch {batch_id}.",
        )

    # Apply only the fields that were explicitly provided in the payload
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided to update.",
        )

    for field_name, value in update_data.items():
        setattr(record, field_name, value)

    try:
        db.commit()
        db.refresh(record)
        return InvoiceRecordRead.model_validate(record)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update invoice record: {exc}",
        ) from exc
