"""
app/schemas/import_batch.py — Schemas for import confirmation and history endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ImportConfirmRequest(BaseModel):
    """
    Request payload to confirm and persist an imported batch.
    """

    file_id: int = Field(..., gt=0, description="ID of uploaded SourceFile")
    template_id: int = Field(..., gt=0, description="ID of Template configuration")
    acknowledge_warnings: bool = Field(
        False,
        description="Must be explicitly set to True if non-fatal warnings exist on the file.",
    )


class ValidationErrorRecordRead(BaseModel):
    id: int
    rule_id: str
    field_name: str | None = None
    severity: str
    message: str
    cell_ref: str | None = None
    worksheet: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceRecordRead(BaseModel):
    id: int
    batch_id: int
    company_name: str
    invoice_number: str
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    source_worksheet: str
    custom_fields: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceRecordUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    invoice_number: str | None = Field(None, min_length=1, max_length=100)
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = Field(None, max_length=10)

    model_config = ConfigDict(extra="forbid")


class ImportBatchListItem(BaseModel):
    id: int
    source_file_id: int
    original_filename: str
    template_id: int
    template_name: str
    status: str
    record_count: int
    warning_count: int
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportBatchDetailResponse(BaseModel):
    id: int
    source_file_id: int
    original_filename: str
    template_id: int
    template_name: str
    status: str
    record_count: int
    warning_count: int
    imported_at: datetime
    invoice_records: list[InvoiceRecordRead] = Field(default_factory=list)
    validation_issues: list[ValidationErrorRecordRead] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)
