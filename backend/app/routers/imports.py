"""
app/routers/imports.py — Endpoints for data extraction and validation previews.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.source_file import SourceFile
from app.models.template import Template
from app.schemas.extraction import (
    ExtractedFieldSchema,
    ExtractionErrorSchema,
    ExtractionPreviewResponse,
    ExtractionRequest,
    ValidationIssueSchema,
    ValidationReportSchema,
)
from app.services.extractor import extract_from_file
from app.services.validator import ValidationConfig, validate_extraction
from app.services.workbook_inspector import (
    CorruptWorkbookError,
    FileSizeExceededError,
    InvalidFileFormatError,
)

router = APIRouter(prefix="/api/v1/imports", tags=["Imports"])


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
    and runs the business validation layer to return a complete preview with diagnostic report.
    """
    # 1. Fetch source file record
    source_file = db.query(SourceFile).filter(SourceFile.id == payload.file_id).first()
    if not source_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source file with ID {payload.file_id} was not found.",
        )

    # 2. Fetch template record with field mappings
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

    # 3. Verify physical file on disk
    file_path = settings.upload_dir / source_file.stored_filename
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source file was not found on disk storage.",
        )

    # 4. Perform extraction
    try:
        extraction_result = extract_from_file(
            file_path=file_path,
            template=template,
            max_size_mb=settings.max_file_size_mb,
        )

        # 5. Run Business Validation (In-memory, read-only)
        def duplicate_checker(company_name: str, invoice_number: str) -> bool:
            # Future milestone: query imported invoice records
            return False

        validation_report = validate_extraction(
            extraction_result=extraction_result,
            config=ValidationConfig(),
            duplicate_checker=duplicate_checker,
        )

        return ExtractionPreviewResponse(
            file_id=source_file.id,
            template_id=template.id,
            template_name=template.name,
            target_worksheet=extraction_result.target_worksheet,
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
            ],
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
