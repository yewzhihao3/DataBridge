"""
app/schemas/import_batch.py — Schemas for import confirmation and history endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from pydantic import model_validator, BaseModel, ConfigDict, Field


class RowDirectionOverride(BaseModel):
    source_row_number: int | None = None
    invoice_number: str | None = None
    direction: str

    @model_validator(mode="after")
    def validate_direction(self):
        norm = self.direction.strip().lower()
        if norm not in {"sales", "purchase", "unclassified"}:
            raise ValueError("direction must be 'sales', 'purchase', or 'unclassified'")
        self.direction = norm
        return self


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
    direction: str = Field(
        "unclassified",
        description="Bulk default financial direction ('sales', 'purchase', or 'unclassified')",
    )
    row_directions: list[RowDirectionOverride] | None = Field(
        default=None,
        description="Optional per-row or per-invoice financial direction overrides",
    )

    @model_validator(mode="after")
    def validate_default_direction(self):
        norm = self.direction.strip().lower()
        if norm not in {"sales", "purchase", "unclassified"}:
            raise ValueError("direction must be 'sales', 'purchase', or 'unclassified'")
        self.direction = norm
        return self



class ValidationErrorRecordRead(BaseModel):
    id: int
    rule_id: str
    field_name: str | None = None
    severity: str
    message: str
    cell_ref: str | None = None
    worksheet: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceLineItemRead(BaseModel):
    id: int
    invoice_id: int
    source_row_number: int
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    amount: Decimal | None = None
    custom_fields: dict[str, Any] | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceRecordRead(BaseModel):
    id: int
    batch_id: int
    company_name: str
    invoice_number: str
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    direction: str = "unclassified"
    source_worksheet: str
    source_row_number: int | None = None
    custom_fields: dict[str, Any] | None = None
    created_at: datetime
    line_items: list[InvoiceLineItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class InvoiceRecordUpdate(BaseModel):
    company_name: str | None = Field(None, min_length=1, max_length=255)
    invoice_number: str | None = Field(None, min_length=1, max_length=100)
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = Field(None, max_length=10)
    direction: str | None = Field(None, max_length=20)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def require_identifiers_when_provided(self):
        for field in ("company_name", "invoice_number"):
            if field in self.model_fields_set and (getattr(self, field) is None or not getattr(self, field).strip()):
                raise ValueError(f"{field} cannot be blank")
        if self.direction is not None:
            norm = self.direction.strip().lower()
            if norm not in {"sales", "purchase", "unclassified"}:
                raise ValueError("direction must be 'sales', 'purchase', or 'unclassified'")
            self.direction = norm
        return self


class ReceiptLineItemRead(BaseModel):
    id: int
    receipt_id: int
    source_row_number: int
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    amount: Decimal | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReceiptRecordRead(BaseModel):
    id: int
    batch_id: int
    merchant_name: str
    receipt_number: str | None = None
    transaction_date: date | None = None
    transaction_time: str | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    direction: str = "unclassified"
    payment_method: str | None = None
    store_address: str | None = None
    cashier: str | None = None
    branch: str | None = None
    cash_paid: Decimal | None = None
    change_amount: Decimal | None = None
    created_at: datetime
    line_items: list[ReceiptLineItemRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ReceiptRecordUpdate(BaseModel):
    """Update the financial direction on a receipt record.

    Only the direction field is exposed; monetary amounts and extraction
    results are intentionally excluded from this endpoint.
    """

    direction: str = Field(..., description="Receipt direction: 'expense', 'income', or 'unclassified'")

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_direction(self):
        norm = self.direction.strip().lower()
        if norm not in {"expense", "income", "unclassified"}:
            raise ValueError("direction must be 'expense', 'income', or 'unclassified'")
        self.direction = norm
        return self


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
    receipt_records: list[ReceiptRecordRead] = Field(default_factory=list)
    validation_issues: list[ValidationErrorRecordRead] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)
