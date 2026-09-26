"""
app/schemas/data_explorer.py — Schemas for Data Explorer endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.import_batch import InvoiceLineItemRead


class InvoiceListItem(BaseModel):
    id: int
    batch_id: int
    company_name: str
    invoice_number: str
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    source_worksheet: str
    source_row_number: int | None = None
    line_item_count: int = 0
    created_at: datetime
    source_filename: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailBatchInfo(BaseModel):
    id: int
    source_file_id: int
    source_filename: str
    template_id: int
    template_name: str
    status: str
    imported_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailResponse(BaseModel):
    id: int
    batch_id: int
    company_name: str
    invoice_number: str
    invoice_date: date | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    source_worksheet: str
    source_row_number: int | None = None
    custom_fields: dict[str, Any] | None = None
    created_at: datetime
    batch: InvoiceDetailBatchInfo | None = None
    line_items: list[InvoiceLineItemRead] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class LineItemListItem(BaseModel):
    id: int
    invoice_id: int
    invoice_number: str
    company_name: str
    invoice_date: date | None = None
    currency: str | None = None
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


class PaginatedInvoicesResponse(BaseModel):
    items: list[InvoiceListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedLineItemsResponse(BaseModel):
    items: list[LineItemListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class DataExplorerFilterOptions(BaseModel):
    companies: list[str]
    currencies: list[str]
