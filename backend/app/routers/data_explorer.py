"""
app/routers/data_explorer.py — Endpoints for Data Explorer (browse, search, filter, inspect business records).
"""

from __future__ import annotations

import json
import math
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.invoice import ImportBatch, InvoiceLineItem, InvoiceRecord
from app.models.source_file import SourceFile
from app.schemas.data_explorer import (
    DataExplorerFilterOptions,
    InvoiceDetailBatchInfo,
    InvoiceDetailResponse,
    InvoiceListItem,
    LineItemListItem,
    PaginatedInvoicesResponse,
    PaginatedLineItemsResponse,
)
from app.schemas.import_batch import InvoiceLineItemRead, InvoiceRecordUpdate

router = APIRouter(prefix="/api/v1/data", tags=["Data Explorer"])


# ── Allowed Sort Fields Allowlist ──────────────────────────────────────────────

INVOICE_SORT_FIELDS = {
    "company_name": InvoiceRecord.company_name,
    "invoice_number": InvoiceRecord.invoice_number,
    "invoice_date": InvoiceRecord.invoice_date,
    "total_amount": InvoiceRecord.total_amount,
    "created_at": InvoiceRecord.created_at,
}

LINE_ITEM_SORT_FIELDS = {
    "id": InvoiceLineItem.id,
    "description": InvoiceLineItem.description,
    "quantity": InvoiceLineItem.quantity,
    "unit_price": InvoiceLineItem.unit_price,
    "tax_rate": InvoiceLineItem.tax_rate,
    "tax_amount": InvoiceLineItem.tax_amount,
    "amount": InvoiceLineItem.amount,
    "source_row_number": InvoiceLineItem.source_row_number,
    "company_name": InvoiceRecord.company_name,
    "invoice_number": InvoiceRecord.invoice_number,
    "invoice_date": InvoiceRecord.invoice_date,
    "created_at": InvoiceLineItem.created_at,
}


# ── Invoices Listing Endpoint ──────────────────────────────────────────────────


@router.get(
    "/invoices",
    response_model=PaginatedInvoicesResponse,
    summary="Browse and filter normalized invoice records",
)
def list_invoices(
    search: str | None = Query(None, description="Search across company name and invoice number"),
    company: str | None = Query(None, description="Filter by company name"),
    currency: str | None = Query(None, description="Filter by currency code (e.g., MYR, USD)"),
    date_from: date | None = Query(None, description="Filter invoices on or after this date"),
    date_to: date | None = Query(None, description="Filter invoices on or before this date"),
    has_line_items: bool | None = Query(None, description="Filter invoices with or without line items"),
    sort_by: str = Query("invoice_date", description="Column to sort by"),
    sort_order: str = Query("desc", description="Sort direction ('asc' or 'desc')"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
) -> PaginatedInvoicesResponse:
    """
    Returns a paginated list of invoice records stored in DataBridge.
    Soft-deleted import batches are strictly excluded.
    """
    # Validate sort parameters
    if sort_by not in INVOICE_SORT_FIELDS and sort_by != "line_item_count":
        sort_by = "invoice_date"
    if sort_order.lower() not in {"asc", "desc"}:
        sort_order = "desc"

    # Line item subquery for line_item_count
    li_count_subq = (
        db.query(
            InvoiceLineItem.invoice_id,
            func.count(InvoiceLineItem.id).label("li_count"),
        )
        .group_by(InvoiceLineItem.invoice_id)
        .subquery()
    )

    # Base query for filtering
    base_query = (
        db.query(InvoiceRecord)
        .join(InvoiceRecord.batch)
        .filter(ImportBatch.is_deleted == False)  # noqa: E712
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        base_query = base_query.filter(
            or_(
                InvoiceRecord.company_name.ilike(search_term),
                InvoiceRecord.invoice_number.ilike(search_term),
            )
        )

    if company and company.strip():
        base_query = base_query.filter(
            InvoiceRecord.company_name.ilike(f"%{company.strip()}%")
        )

    if currency and currency.strip():
        base_query = base_query.filter(
            InvoiceRecord.currency == currency.strip().upper()
        )

    if date_from:
        base_query = base_query.filter(InvoiceRecord.invoice_date >= date_from)

    if date_to:
        base_query = base_query.filter(InvoiceRecord.invoice_date <= date_to)

    if has_line_items is not None:
        if has_line_items:
            base_query = base_query.filter(InvoiceRecord.line_items.any())
        else:
            base_query = base_query.filter(~InvoiceRecord.line_items.any())

    total = base_query.count()

    # Build data query with line item count and source file name
    data_query = (
        db.query(
            InvoiceRecord,
            func.coalesce(li_count_subq.c.li_count, 0).label("line_item_count"),
            SourceFile.original_name.label("source_filename"),
        )
        .join(InvoiceRecord.batch)
        .outerjoin(ImportBatch.source_file)
        .outerjoin(li_count_subq, InvoiceRecord.id == li_count_subq.c.invoice_id)
        .filter(ImportBatch.is_deleted == False)  # noqa: E712
    )

    # Re-apply same filters
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        data_query = data_query.filter(
            or_(
                InvoiceRecord.company_name.ilike(search_term),
                InvoiceRecord.invoice_number.ilike(search_term),
            )
        )
    if company and company.strip():
        data_query = data_query.filter(
            InvoiceRecord.company_name.ilike(f"%{company.strip()}%")
        )
    if currency and currency.strip():
        data_query = data_query.filter(
            InvoiceRecord.currency == currency.strip().upper()
        )
    if date_from:
        data_query = data_query.filter(InvoiceRecord.invoice_date >= date_from)
    if date_to:
        data_query = data_query.filter(InvoiceRecord.invoice_date <= date_to)
    if has_line_items is not None:
        if has_line_items:
            data_query = data_query.filter(InvoiceRecord.line_items.any())
        else:
            data_query = data_query.filter(~InvoiceRecord.line_items.any())

    # Apply sorting
    if sort_by == "line_item_count":
        sort_col = func.coalesce(li_count_subq.c.li_count, 0)
    else:
        sort_col = INVOICE_SORT_FIELDS[sort_by]

    if sort_order.lower() == "asc":
        data_query = data_query.order_by(sort_col.asc().nulls_last(), InvoiceRecord.id.asc())
    else:
        data_query = data_query.order_by(sort_col.desc().nulls_last(), InvoiceRecord.id.desc())

    # Pagination
    offset = (page - 1) * page_size
    rows = data_query.offset(offset).limit(page_size).all()

    items: list[InvoiceListItem] = []
    for rec, li_count, src_name in rows:
        items.append(
            InvoiceListItem(
                id=rec.id,
                batch_id=rec.batch_id,
                company_name=rec.company_name,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                total_amount=rec.total_amount,
                currency=rec.currency,
                source_worksheet=rec.source_worksheet,
                source_row_number=rec.source_row_number,
                line_item_count=li_count,
                created_at=rec.created_at,
                source_filename=src_name,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedInvoicesResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── Invoice Detail Endpoint ────────────────────────────────────────────────────


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailResponse,
    summary="Get complete detail of an invoice record",
)
def get_invoice_detail(
    invoice_id: int,
    db: Session = Depends(get_db),
) -> InvoiceDetailResponse:
    """
    Retrieves full details for a single invoice record, including custom fields,
    child line items, and batch provenance.
    """
    record = (
        db.query(InvoiceRecord)
        .options(
            joinedload(InvoiceRecord.batch).joinedload(ImportBatch.source_file),
            joinedload(InvoiceRecord.batch).joinedload(ImportBatch.template),
            joinedload(InvoiceRecord.line_items),
        )
        .join(InvoiceRecord.batch)
        .filter(InvoiceRecord.id == invoice_id, ImportBatch.is_deleted == False)  # noqa: E712
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice record with ID {invoice_id} was not found.",
        )

    # Parse raw_data JSON safely if present
    raw_dict: dict[str, Any] | None = None
    if record.raw_data:
        try:
            raw_dict = json.loads(record.raw_data)
        except Exception:
            raw_dict = None

    batch_info: InvoiceDetailBatchInfo | None = None
    if record.batch:
        batch_info = InvoiceDetailBatchInfo(
            id=record.batch.id,
            source_file_id=record.batch.source_file_id,
            source_filename=record.batch.source_file.original_name if record.batch.source_file else "Unknown",
            template_id=record.batch.template_id,
            template_name=record.batch.template.name if record.batch.template else "Unknown",
            status=record.batch.status,
            imported_at=record.batch.imported_at,
        )

    return InvoiceDetailResponse(
        id=record.id,
        batch_id=record.batch_id,
        company_name=record.company_name,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        total_amount=record.total_amount,
        currency=record.currency,
        source_worksheet=record.source_worksheet,
        source_row_number=record.source_row_number,
        custom_fields=record.custom_fields,
        created_at=record.created_at,
        batch=batch_info,
        line_items=[InvoiceLineItemRead.model_validate(li) for li in record.line_items],
        raw_data=raw_dict,
    )


# ── Invoice Record Update Endpoint ────────────────────────────────────────────


@router.patch(
    "/invoices/{invoice_id}",
    response_model=InvoiceDetailResponse,
    summary="Update canonical fields on an invoice record",
)
def update_invoice(
    invoice_id: int,
    payload: InvoiceRecordUpdate,
    db: Session = Depends(get_db),
) -> InvoiceDetailResponse:
    """
    Updates canonical header fields (company_name, invoice_number, invoice_date,
    total_amount, currency) on an existing invoice record.
    Preserves custom_fields, raw_data, and child line items.
    """
    record = (
        db.query(InvoiceRecord)
        .options(
            joinedload(InvoiceRecord.batch).joinedload(ImportBatch.source_file),
            joinedload(InvoiceRecord.batch).joinedload(ImportBatch.template),
            joinedload(InvoiceRecord.line_items),
        )
        .join(InvoiceRecord.batch)
        .filter(InvoiceRecord.id == invoice_id, ImportBatch.is_deleted == False)  # noqa: E712
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Invoice record with ID {invoice_id} was not found.",
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(record, field_name, value)

    try:
        db.commit()
        db.refresh(record)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update invoice record: {exc}",
        ) from exc

    raw_dict: dict[str, Any] | None = None
    if record.raw_data:
        try:
            raw_dict = json.loads(record.raw_data)
        except Exception:
            raw_dict = None

    batch_info: InvoiceDetailBatchInfo | None = None
    if record.batch:
        batch_info = InvoiceDetailBatchInfo(
            id=record.batch.id,
            source_file_id=record.batch.source_file_id,
            source_filename=record.batch.source_file.original_name if record.batch.source_file else "Unknown",
            template_id=record.batch.template_id,
            template_name=record.batch.template.name if record.batch.template else "Unknown",
            status=record.batch.status,
            imported_at=record.batch.imported_at,
        )

    return InvoiceDetailResponse(
        id=record.id,
        batch_id=record.batch_id,
        company_name=record.company_name,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        total_amount=record.total_amount,
        currency=record.currency,
        source_worksheet=record.source_worksheet,
        source_row_number=record.source_row_number,
        custom_fields=record.custom_fields,
        created_at=record.created_at,
        batch=batch_info,
        line_items=[InvoiceLineItemRead.model_validate(li) for li in record.line_items],
        raw_data=raw_dict,
    )


# ── Line Items Listing Endpoint ────────────────────────────────────────────────


@router.get(
    "/line-items",
    response_model=PaginatedLineItemsResponse,
    summary="Browse and filter flattened line items across all invoices",
)
def list_line_items(
    search: str | None = Query(None, description="Search across description, company name, and invoice number"),
    company: str | None = Query(None, description="Filter by parent invoice company name"),
    currency: str | None = Query(None, description="Filter by parent invoice currency"),
    date_from: date | None = Query(None, description="Filter parent invoices on or after this date"),
    date_to: date | None = Query(None, description="Filter parent invoices on or before this date"),
    sort_by: str = Query("id", description="Column to sort by"),
    sort_order: str = Query("asc", description="Sort direction ('asc' or 'desc')"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=100, description="Number of items per page"),
    db: Session = Depends(get_db),
) -> PaginatedLineItemsResponse:
    """
    Returns a paginated, flattened list of line items with their parent invoice details.
    Soft-deleted batches are strictly excluded.
    """
    if sort_by not in LINE_ITEM_SORT_FIELDS:
        sort_by = "id"
    if sort_order.lower() not in {"asc", "desc"}:
        sort_order = "asc"

    base_query = (
        db.query(InvoiceLineItem)
        .join(InvoiceLineItem.invoice_record)
        .join(InvoiceRecord.batch)
        .filter(ImportBatch.is_deleted == False)  # noqa: E712
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        base_query = base_query.filter(
            or_(
                InvoiceLineItem.description.ilike(search_term),
                InvoiceRecord.company_name.ilike(search_term),
                InvoiceRecord.invoice_number.ilike(search_term),
            )
        )

    if company and company.strip():
        base_query = base_query.filter(
            InvoiceRecord.company_name.ilike(f"%{company.strip()}%")
        )

    if currency and currency.strip():
        base_query = base_query.filter(
            InvoiceRecord.currency == currency.strip().upper()
        )

    if date_from:
        base_query = base_query.filter(InvoiceRecord.invoice_date >= date_from)

    if date_to:
        base_query = base_query.filter(InvoiceRecord.invoice_date <= date_to)

    total = base_query.count()

    # Eager load parent invoice for performance
    data_query = (
        db.query(InvoiceLineItem)
        .options(joinedload(InvoiceLineItem.invoice_record))
        .join(InvoiceLineItem.invoice_record)
        .join(InvoiceRecord.batch)
        .filter(ImportBatch.is_deleted == False)  # noqa: E712
    )

    # Re-apply same filters
    if search and search.strip():
        search_term = f"%{search.strip()}%"
        data_query = data_query.filter(
            or_(
                InvoiceLineItem.description.ilike(search_term),
                InvoiceRecord.company_name.ilike(search_term),
                InvoiceRecord.invoice_number.ilike(search_term),
            )
        )
    if company and company.strip():
        data_query = data_query.filter(
            InvoiceRecord.company_name.ilike(f"%{company.strip()}%")
        )
    if currency and currency.strip():
        data_query = data_query.filter(
            InvoiceRecord.currency == currency.strip().upper()
        )
    if date_from:
        data_query = data_query.filter(InvoiceRecord.invoice_date >= date_from)
    if date_to:
        data_query = data_query.filter(InvoiceRecord.invoice_date <= date_to)

    # Sorting
    sort_col = LINE_ITEM_SORT_FIELDS[sort_by]
    if sort_order.lower() == "asc":
        data_query = data_query.order_by(sort_col.asc().nulls_last(), InvoiceLineItem.id.asc())
    else:
        data_query = data_query.order_by(sort_col.desc().nulls_last(), InvoiceLineItem.id.desc())

    # Pagination
    offset = (page - 1) * page_size
    rows = data_query.offset(offset).limit(page_size).all()

    items: list[LineItemListItem] = []
    for li in rows:
        parent = li.invoice_record
        items.append(
            LineItemListItem(
                id=li.id,
                invoice_id=li.invoice_id,
                invoice_number=parent.invoice_number if parent else "Unknown",
                company_name=parent.company_name if parent else "Unknown",
                invoice_date=parent.invoice_date if parent else None,
                currency=parent.currency if parent else None,
                source_row_number=li.source_row_number,
                description=li.description,
                quantity=li.quantity,
                unit_price=li.unit_price,
                tax_rate=li.tax_rate,
                tax_amount=li.tax_amount,
                amount=li.amount,
                custom_fields=li.custom_fields,
                created_at=li.created_at,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedLineItemsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── Filter Options Endpoint ───────────────────────────────────────────────────


@router.get(
    "/filter-options",
    response_model=DataExplorerFilterOptions,
    summary="Get dynamic filter dropdown options (companies, currencies)",
)
def get_filter_options(
    db: Session = Depends(get_db),
) -> DataExplorerFilterOptions:
    """
    Returns unique lists of companies and currencies present in active (non-deleted) batches.
    """
    companies_query = (
        db.query(InvoiceRecord.company_name)
        .join(InvoiceRecord.batch)
        .filter(
            ImportBatch.is_deleted == False,  # noqa: E712
            InvoiceRecord.company_name.isnot(None),
            InvoiceRecord.company_name != "",
        )
        .distinct()
        .order_by(InvoiceRecord.company_name.asc())
        .all()
    )

    currencies_query = (
        db.query(InvoiceRecord.currency)
        .join(InvoiceRecord.batch)
        .filter(
            ImportBatch.is_deleted == False,  # noqa: E712
            InvoiceRecord.currency.isnot(None),
            InvoiceRecord.currency != "",
        )
        .distinct()
        .order_by(InvoiceRecord.currency.asc())
        .all()
    )

    companies = [c[0] for c in companies_query if c[0]]
    currencies = [c[0] for c in currencies_query if c[0]]

    return DataExplorerFilterOptions(
        companies=companies,
        currencies=currencies,
    )
