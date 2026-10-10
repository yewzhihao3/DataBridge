"""
app/schemas/data_explorer.py — Schemas for Data Explorer endpoints.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.import_batch import InvoiceLineItemRead, ReceiptLineItemRead


class InvoiceListItem(BaseModel):
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
    line_item_count: int = 0
    created_at: datetime
    source_file_id: int | None = None
    source_filename: str | None = None
    source_media_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailBatchInfo(BaseModel):
    id: int
    source_file_id: int
    source_filename: str
    source_media_type: str | None = None
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
    direction: str = "unclassified"
    source_worksheet: str
    source_row_number: int | None = None
    custom_fields: dict[str, Any] | None = None
    created_at: datetime
    batch: InvoiceDetailBatchInfo | None = None
    line_items: list[InvoiceLineItemRead] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class ReceiptListItem(BaseModel):
    id: int
    batch_id: int
    merchant_name: str
    receipt_number: str | None = None
    transaction_date: date | None = None
    transaction_time: str | None = None
    currency: str | None = None
    direction: str = "unclassified"
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = None
    line_item_count: int = 0
    created_at: datetime
    source_file_id: int | None = None
    source_filename: str | None = None
    source_media_type: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ReceiptDetailResponse(BaseModel):
    id: int
    batch_id: int
    merchant_name: str
    receipt_number: str | None = None
    transaction_date: date | None = None
    transaction_time: str | None = None
    currency: str | None = None
    direction: str = "unclassified"
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = None
    store_address: str | None = None
    cashier: str | None = None
    branch: str | None = None
    cash_paid: Decimal | None = None
    change_amount: Decimal | None = None
    created_at: datetime
    batch: InvoiceDetailBatchInfo | None = None
    line_items: list[ReceiptLineItemRead] = Field(default_factory=list)
    raw_data: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class UnifiedDocumentListItem(BaseModel):
    id: str
    record_id: int
    document_type: str  # "invoice" | "receipt"
    document_number: str | None = None
    counterparty: str
    document_date: date | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    direction: str = "unclassified"
    batch_id: int
    source_file_id: int | None = None
    source_filename: str | None = None
    source_worksheet: str | None = None
    source_media_type: str | None = None
    line_item_count: int = 0
    status: str = "imported"
    created_at: datetime

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


class PaginatedReceiptsResponse(BaseModel):
    items: list[ReceiptListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedDocumentsResponse(BaseModel):
    items: list[UnifiedDocumentListItem]
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
    merchants: list[str] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    directions: list[str] = Field(default_factory=list)
