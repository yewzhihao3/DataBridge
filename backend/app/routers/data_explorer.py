"""
app/routers/data_explorer.py — Endpoints for Data Explorer (browse, search, filter, inspect business records).
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, literal, or_
from sqlalchemy.orm import Session, joinedload

from app.security import audit
from app.tenancy import get_tenant_db as get_db
from app.models.invoice import ImportBatch, InvoiceLineItem, InvoiceRecord, ReceiptLineItem, ReceiptRecord
from app.services.business_query import active_record_scope, invoice_filter_conditions, receipt_filter_conditions
from app.services.relationship_service import get_connected_counts_batch
from app.models.source_file import SourceFile
from app.schemas.data_explorer import (
    DataExplorerFilterOptions,
    InvoiceDetailBatchInfo,
    InvoiceDetailResponse,
    InvoiceListItem,
    LineItemListItem,
    PaginatedDocumentsResponse,
    PaginatedInvoicesResponse,
    PaginatedLineItemsResponse,
    PaginatedReceiptsResponse,
    ReceiptDetailResponse,
    ReceiptListItem,
    UnifiedDocumentListItem,
)
from app.schemas.import_batch import InvoiceLineItemRead, InvoiceRecordUpdate, ReceiptLineItemRead, ReceiptRecordUpdate

router = APIRouter(prefix="/api/v1/data", tags=["Data Explorer"])


# ── Allowed Sort Fields Allowlist ──────────────────────────────────────────────

INVOICE_SORT_FIELDS = {
    "company_name": InvoiceRecord.company_name,
    "invoice_number": InvoiceRecord.invoice_number,
    "invoice_date": InvoiceRecord.invoice_date,
    "total_amount": InvoiceRecord.total_amount,
    "created_at": InvoiceRecord.created_at,
    "direction": InvoiceRecord.direction,
}

RECEIPT_SORT_FIELDS = {
    "transaction_date": ReceiptRecord.transaction_date,
    "merchant_name": ReceiptRecord.merchant_name,
    "total_amount": ReceiptRecord.total_amount,
    "id": ReceiptRecord.id,
    "created_at": ReceiptRecord.created_at,
    "direction": ReceiptRecord.direction,
    "receipt_number": ReceiptRecord.receipt_number,
}

DOCUMENT_SORT_FIELDS = {
    "document_date",
    "counterparty",
    "total_amount",
    "created_at",
    "document_number",
    "line_item_count",
    "direction",
    "record_id",
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
    direction: str | None = Query(None, description="Filter by financial direction (sales, purchase, unclassified)"),
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
        .filter(active_record_scope())
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        base_query = base_query.filter(
            or_(
                InvoiceRecord.company_name.ilike(search_term),
                InvoiceRecord.invoice_number.ilike(search_term),
            )
        )

    base_query = base_query.filter(*invoice_filter_conditions(company, currency, date_from, date_to, direction))

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
            SourceFile.id.label("source_file_id"),
            SourceFile.media_type.label("source_media_type"),
        )
        .join(InvoiceRecord.batch)
        .outerjoin(ImportBatch.source_file)
        .outerjoin(li_count_subq, InvoiceRecord.id == li_count_subq.c.invoice_id)
        .filter(active_record_scope())
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
    data_query = data_query.filter(*invoice_filter_conditions(company, currency, date_from, date_to, direction))

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

    org_id = db.info.get("organization_id", 0)
    inv_ids = [rec.id for rec, *_ in rows]
    connected_counts = get_connected_counts_batch(db, org_id, "invoice", inv_ids)

    items: list[InvoiceListItem] = []
    for rec, li_count, src_name, src_id, src_media in rows:
        items.append(
            InvoiceListItem(
                id=rec.id,
                batch_id=rec.batch_id,
                company_name=rec.company_name,
                invoice_number=rec.invoice_number,
                invoice_date=rec.invoice_date,
                total_amount=rec.total_amount,
                currency=rec.currency,
                direction=rec.direction,
                source_worksheet=rec.source_worksheet,
                source_row_number=rec.source_row_number,
                line_item_count=li_count,
                created_at=rec.created_at,
                source_file_id=src_id,
                source_filename=src_name,
                source_media_type=src_media,
                connected_count=connected_counts.get(rec.id, 0),
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
        .filter(InvoiceRecord.id == invoice_id, active_record_scope())
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
            source_media_type=record.batch.source_file.media_type if record.batch.source_file else None,
            template_id=record.batch.template_id,
            template_name=record.batch.template.name if record.batch.template else "Unknown",
            status=record.batch.status,
            imported_at=record.batch.imported_at,
        )

    org_id = db.info.get("organization_id", 0)
    connected_count = get_connected_counts_batch(db, org_id, "invoice", [record.id]).get(record.id, 0)

    return InvoiceDetailResponse(
        id=record.id,
        batch_id=record.batch_id,
        company_name=record.company_name,
        invoice_number=record.invoice_number,
        invoice_date=record.invoice_date,
        total_amount=record.total_amount,
        currency=record.currency,
        direction=record.direction,
        source_worksheet=record.source_worksheet,
        source_row_number=record.source_row_number,
        custom_fields=record.custom_fields,
        created_at=record.created_at,
        batch=batch_info,
        line_items=[InvoiceLineItemRead.model_validate(li) for li in record.line_items],
        raw_data=raw_dict,
        connected_count=connected_count,
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
    total_amount, currency, direction) on an existing invoice record.
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
        .filter(InvoiceRecord.id == invoice_id, active_record_scope())
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
            detail="Failed to update invoice record",
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
        direction=record.direction,
        source_worksheet=record.source_worksheet,
        source_row_number=record.source_row_number,
        custom_fields=record.custom_fields,
        created_at=record.created_at,
        batch=batch_info,
        line_items=[InvoiceLineItemRead.model_validate(li) for li in record.line_items],
        raw_data=raw_dict,
        connected_count=get_connected_counts_batch(db, db.info.get("organization_id", 0), "invoice", [record.id]).get(record.id, 0),
    )


# ── Receipts Listing Endpoint ──────────────────────────────────────────────────


@router.get(
    "/receipts",
    response_model=PaginatedReceiptsResponse,
    summary="Browse and filter normalized receipt records",
)
def list_receipts(
    search: str | None = Query(None, description="Search across merchant name and receipt number"),
    merchant: str | None = Query(None, description="Filter by merchant name"),
    receipt_number: str | None = Query(None, description="Filter by receipt number"),
    currency: str | None = Query(None, description="Filter by currency code"),
    direction: str | None = Query(None, description="Filter by financial direction (expense, income, unclassified)"),
    payment_method: str | None = Query(None, description="Filter by payment method"),
    date_from: date | None = Query(None, description="Filter receipts on or after this transaction date"),
    date_to: date | None = Query(None, description="Filter receipts on or before this transaction date"),
    amount_min: Decimal | None = Query(None, description="Minimum total amount"),
    amount_max: Decimal | None = Query(None, description="Maximum total amount"),
    sort_by: str = Query("transaction_date", description="Column to sort by"),
    sort_order: str = Query("desc", description="Sort direction ('asc' or 'desc')"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
) -> PaginatedReceiptsResponse:
    """
    Returns a paginated list of receipt records stored in DataBridge.
    Soft-deleted import batches are strictly excluded.
    """
    if sort_by not in RECEIPT_SORT_FIELDS and sort_by != "line_item_count":
        sort_by = "transaction_date"
    if sort_order.lower() not in {"asc", "desc"}:
        sort_order = "desc"

    # Line item subquery for line_item_count
    rec_li_count = (
        db.query(
            ReceiptLineItem.receipt_id,
            func.count(ReceiptLineItem.id).label("li_count"),
        )
        .group_by(ReceiptLineItem.receipt_id)
        .subquery()
    )

    base_query = (
        db.query(ReceiptRecord)
        .join(ReceiptRecord.batch)
        .filter(active_record_scope())
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        base_query = base_query.filter(
            or_(
                ReceiptRecord.merchant_name.ilike(search_term),
                ReceiptRecord.receipt_number.ilike(search_term),
            )
        )

    if receipt_number and receipt_number.strip():
        base_query = base_query.filter(ReceiptRecord.receipt_number.ilike(f"%{receipt_number.strip()}%"))

    base_query = base_query.filter(
        *receipt_filter_conditions(
            merchant=merchant,
            currency=currency,
            direction=direction,
            payment_method=payment_method,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
        )
    )

    total = base_query.count()

    data_query = (
        db.query(
            ReceiptRecord,
            func.coalesce(rec_li_count.c.li_count, 0).label("line_item_count"),
            SourceFile.original_name.label("source_filename"),
            SourceFile.id.label("source_file_id"),
            SourceFile.media_type.label("source_media_type"),
        )
        .join(ReceiptRecord.batch)
        .outerjoin(ImportBatch.source_file)
        .outerjoin(rec_li_count, ReceiptRecord.id == rec_li_count.c.receipt_id)
        .filter(active_record_scope())
    )

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        data_query = data_query.filter(
            or_(
                ReceiptRecord.merchant_name.ilike(search_term),
                ReceiptRecord.receipt_number.ilike(search_term),
            )
        )

    if receipt_number and receipt_number.strip():
        data_query = data_query.filter(ReceiptRecord.receipt_number.ilike(f"%{receipt_number.strip()}%"))

    data_query = data_query.filter(
        *receipt_filter_conditions(
            merchant=merchant,
            currency=currency,
            direction=direction,
            payment_method=payment_method,
            date_from=date_from,
            date_to=date_to,
            amount_min=amount_min,
            amount_max=amount_max,
        )
    )

    if sort_by == "line_item_count":
        sort_col = func.coalesce(rec_li_count.c.li_count, 0)
    else:
        sort_col = RECEIPT_SORT_FIELDS[sort_by]

    if sort_order.lower() == "asc":
        data_query = data_query.order_by(sort_col.asc().nulls_last(), ReceiptRecord.id.asc())
    else:
        data_query = data_query.order_by(sort_col.desc().nulls_last(), ReceiptRecord.id.desc())

    offset = (page - 1) * page_size
    rows = data_query.offset(offset).limit(page_size).all()

    org_id = db.info.get("organization_id", 0)
    rec_ids = [rec.id for rec, *_ in rows]
    connected_counts = get_connected_counts_batch(db, org_id, "receipt", rec_ids)

    items: list[ReceiptListItem] = []
    for rec, li_count, src_name, src_id, src_media in rows:
        items.append(
            ReceiptListItem(
                id=rec.id,
                batch_id=rec.batch_id,
                merchant_name=rec.merchant_name,
                receipt_number=rec.receipt_number,
                transaction_date=rec.transaction_date,
                transaction_time=rec.transaction_time,
                currency=rec.currency,
                direction=rec.direction,
                subtotal=rec.subtotal,
                tax_amount=rec.tax_amount,
                total_amount=rec.total_amount,
                payment_method=rec.payment_method,
                line_item_count=li_count,
                created_at=rec.created_at,
                source_file_id=src_id,
                source_filename=src_name,
                source_media_type=src_media,
                connected_count=connected_counts.get(rec.id, 0),
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedReceiptsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ── Receipt Detail Endpoint ────────────────────────────────────────────────────


@router.get(
    "/receipts/{receipt_id}",
    response_model=ReceiptDetailResponse,
    summary="Get complete detail of a receipt record",
)
def get_receipt_detail(
    receipt_id: int,
    db: Session = Depends(get_db),
) -> ReceiptDetailResponse:
    """
    Retrieves full details for a single receipt record, including line items,
    source file reference, and batch provenance.
    """
    record = (
        db.query(ReceiptRecord)
        .options(
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.source_file),
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.template),
            joinedload(ReceiptRecord.line_items),
        )
        .join(ReceiptRecord.batch)
        .filter(ReceiptRecord.id == receipt_id, active_record_scope())
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt record with ID {receipt_id} was not found.",
        )

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
            source_media_type=record.batch.source_file.media_type if record.batch.source_file else None,
            template_id=record.batch.template_id,
            template_name=record.batch.template.name if record.batch.template else "Unknown",
            status=record.batch.status,
            imported_at=record.batch.imported_at,
        )

    return ReceiptDetailResponse(
        id=record.id,
        batch_id=record.batch_id,
        merchant_name=record.merchant_name,
        receipt_number=record.receipt_number,
        transaction_date=record.transaction_date,
        transaction_time=record.transaction_time,
        currency=record.currency,
        direction=record.direction,
        subtotal=record.subtotal,
        tax_amount=record.tax_amount,
        total_amount=record.total_amount,
        payment_method=record.payment_method,
        store_address=record.store_address,
        cashier=record.cashier,
        branch=record.branch,
        cash_paid=record.cash_paid,
        change_amount=record.change_amount,
        created_at=record.created_at,
        batch=batch_info,
        line_items=[ReceiptLineItemRead.model_validate(li) for li in record.line_items],
        raw_data=raw_dict,
        connected_count=get_connected_counts_batch(db, db.info.get("organization_id", 0), "receipt", [record.id]).get(record.id, 0),
    )


# ── Receipt Direction Update Endpoint ────────────────────────────────────────


@router.patch(
    "/receipts/{receipt_id}",
    response_model=ReceiptDetailResponse,
    summary="Update a receipt record and its line items",
)
def update_receipt(
    receipt_id: int,
    payload: ReceiptRecordUpdate,
    db: Session = Depends(get_db),
) -> ReceiptDetailResponse:
    """
    Updates editable fields and line items on a confirmed receipt record.
    Supports partial updates while preserving extraction provenance and audit trails.

    Rejects: cross-tenant records, soft-deleted batches, invalid direction values,
    unauthorized line item IDs, and unallowed fields.
    """
    record = (
        db.query(ReceiptRecord)
        .options(
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.source_file),
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.template),
            joinedload(ReceiptRecord.line_items),
        )
        .join(ReceiptRecord.batch)
        .filter(ReceiptRecord.id == receipt_id, active_record_scope())
        .first()
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Receipt record with ID {receipt_id} was not found.",
        )

    fields_set = payload.model_fields_set

    # 1. Update allowlisted header fields if explicitly present in payload
    if "merchant_name" in fields_set:
        if not payload.merchant_name or not payload.merchant_name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Merchant name cannot be empty.",
            )
        record.merchant_name = payload.merchant_name.strip()

    if "receipt_number" in fields_set:
        record.receipt_number = payload.receipt_number.strip() if payload.receipt_number else ""

    if "transaction_date" in fields_set:
        record.transaction_date = payload.transaction_date

    if "transaction_time" in fields_set:
        record.transaction_time = payload.transaction_time

    if "currency" in fields_set:
        record.currency = payload.currency

    if "direction" in fields_set:
        if payload.direction is not None:
            record.direction = payload.direction

    if "subtotal" in fields_set:
        record.subtotal = payload.subtotal

    if "tax_amount" in fields_set:
        record.tax_amount = payload.tax_amount

    if "total_amount" in fields_set:
        record.total_amount = payload.total_amount

    if "payment_method" in fields_set:
        record.payment_method = payload.payment_method

    if "store_address" in fields_set:
        record.store_address = payload.store_address

    if "cashier" in fields_set:
        record.cashier = payload.cashier

    if "branch" in fields_set:
        record.branch = payload.branch

    if "cash_paid" in fields_set:
        record.cash_paid = payload.cash_paid

    if "change_amount" in fields_set:
        record.change_amount = payload.change_amount

    # 2. Line Items Update
    if "line_items" in fields_set and payload.line_items is not None:
        existing_items = {li.id: li for li in record.line_items}

        # Check for duplicate IDs in payload
        payload_item_ids = [li.id for li in payload.line_items if li.id is not None]
        if len(payload_item_ids) != len(set(payload_item_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Duplicate line item IDs in update payload.",
            )

        # Validate line-item ownership against this receipt
        for li in payload.line_items:
            if li.id is not None and li.id not in existing_items:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Line item with ID {li.id} does not belong to receipt {receipt_id}.",
                )

        # Remove omitted line items
        payload_id_set = set(payload_item_ids)
        for ex_id, ex_item in list(existing_items.items()):
            if ex_id not in payload_id_set:
                db.delete(ex_item)

        # Update existing and add new line items
        for index, item_data in enumerate(payload.line_items, start=1):
            if item_data.id is not None:
                item = existing_items[item_data.id]
                item.source_row_number = index
                item.description = item_data.description
                item.quantity = item_data.quantity
                item.unit_price = item_data.unit_price
                item.tax_rate = item_data.tax_rate
                item.tax_amount = item_data.tax_amount
                item.amount = item_data.amount
            else:
                new_item = ReceiptLineItem(
                    receipt_id=record.id,
                    source_row_number=index,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit_price=item_data.unit_price,
                    tax_rate=item_data.tax_rate,
                    tax_amount=item_data.tax_amount,
                    amount=item_data.amount,
                    raw_data=json.dumps(item_data.model_dump(mode="json"), default=str),
                )
                db.add(new_item)

    # 3. Preserve Extraction Evidence & Record Edit Audit in raw_data
    org_id = db.info.get("organization_id")
    user_id = db.info.get("user_id")

    raw_dict: dict[str, Any] = {}
    if record.raw_data:
        try:
            raw_dict = json.loads(record.raw_data)
        except Exception:
            raw_dict = {"original_raw": record.raw_data}

    edit_history = raw_dict.setdefault("edit_history", [])
    edit_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "fields_changed": sorted(list(fields_set)),
    })
    record.raw_data = json.dumps(raw_dict, default=str)

    # 4. Atomic Commit & Audit Logging
    try:
        if org_id and user_id:
            audit_action = "RECEIPT_DIRECTION_UPDATED" if fields_set == {"direction"} else "RECEIPT_UPDATED"
            audit(
                db,
                org_id,
                user_id,
                audit_action,
                "receipt_records",
                record.id,
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update receipt record",
        ) from exc

    # Refresh record with all relationships
    db.expire(record)
    refreshed_record = (
        db.query(ReceiptRecord)
        .options(
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.source_file),
            joinedload(ReceiptRecord.batch).joinedload(ImportBatch.template),
            joinedload(ReceiptRecord.line_items),
        )
        .filter(ReceiptRecord.id == receipt_id)
        .first()
    ) or record

    batch_info: InvoiceDetailBatchInfo | None = None
    if refreshed_record.batch:
        batch_info = InvoiceDetailBatchInfo(
            id=refreshed_record.batch.id,
            source_file_id=refreshed_record.batch.source_file_id,
            source_filename=refreshed_record.batch.source_file.original_name if refreshed_record.batch.source_file else "Unknown",
            source_media_type=refreshed_record.batch.source_file.media_type if refreshed_record.batch.source_file else None,
            template_id=refreshed_record.batch.template_id,
            template_name=refreshed_record.batch.template.name if refreshed_record.batch.template else "Unknown",
            status=refreshed_record.batch.status,
            imported_at=refreshed_record.batch.imported_at,
        )

    return ReceiptDetailResponse(
        id=refreshed_record.id,
        batch_id=refreshed_record.batch_id,
        merchant_name=refreshed_record.merchant_name,
        receipt_number=refreshed_record.receipt_number,
        transaction_date=refreshed_record.transaction_date,
        transaction_time=refreshed_record.transaction_time,
        currency=refreshed_record.currency,
        direction=refreshed_record.direction,
        subtotal=refreshed_record.subtotal,
        tax_amount=refreshed_record.tax_amount,
        total_amount=refreshed_record.total_amount,
        payment_method=refreshed_record.payment_method,
        store_address=refreshed_record.store_address,
        cashier=refreshed_record.cashier,
        branch=refreshed_record.branch,
        cash_paid=refreshed_record.cash_paid,
        change_amount=refreshed_record.change_amount,
        created_at=refreshed_record.created_at,
        batch=batch_info,
        line_items=[ReceiptLineItemRead.model_validate(li) for li in refreshed_record.line_items],
        raw_data=raw_dict,
        connected_count=get_connected_counts_batch(db, db.info.get("organization_id", 0), "receipt", [refreshed_record.id]).get(refreshed_record.id, 0),
    )


# ── Unified Financial Documents Endpoint ───────────────────────────────────────


@router.get(
    "/documents",
    response_model=PaginatedDocumentsResponse,
    summary="Browse and filter normalized financial documents (invoices and receipts)",
)
def list_documents(
    search: str | None = Query(None, description="Search across counterparty name and document number"),
    document_type: str | None = Query(None, description="Filter by document type ('invoice', 'receipt', or 'all')"),
    direction: str | None = Query(None, description="Filter by financial direction"),
    currency: str | None = Query(None, description="Filter by currency code"),
    date_from: date | None = Query(None, description="Filter documents on or after date"),
    date_to: date | None = Query(None, description="Filter documents on or before date"),
    sort_by: str = Query("document_date", description="Column to sort by"),
    sort_order: str = Query("desc", description="Sort direction ('asc' or 'desc')"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(25, ge=1, le=100, description="Number of records per page"),
    db: Session = Depends(get_db),
) -> PaginatedDocumentsResponse:
    """
    Returns a unified paginated document register combining invoices and receipts
    without double-counting or altering underlying tables.
    """
    if sort_by not in DOCUMENT_SORT_FIELDS:
        sort_by = "document_date"
    if sort_order.lower() not in {"asc", "desc"}:
        sort_order = "desc"

    # Line item count subqueries
    inv_li_count = (
        db.query(InvoiceLineItem.invoice_id, func.count(InvoiceLineItem.id).label("cnt"))
        .group_by(InvoiceLineItem.invoice_id)
        .subquery()
    )
    rec_li_count = (
        db.query(ReceiptLineItem.receipt_id, func.count(ReceiptLineItem.id).label("cnt"))
        .group_by(ReceiptLineItem.receipt_id)
        .subquery()
    )

    queries = []
    include_invoices = document_type in {None, "", "all", "invoice"}
    include_receipts = document_type in {None, "", "all", "receipt"}

    if include_invoices:
        q_inv = (
            db.query(
                literal("invoice").label("doc_type"),
                InvoiceRecord.id.label("record_id"),
                InvoiceRecord.invoice_number.label("document_number"),
                InvoiceRecord.company_name.label("counterparty"),
                InvoiceRecord.invoice_date.label("document_date"),
                InvoiceRecord.currency.label("currency"),
                InvoiceRecord.total_amount.label("total_amount"),
                InvoiceRecord.direction.label("direction"),
                InvoiceRecord.batch_id.label("batch_id"),
                SourceFile.id.label("source_file_id"),
                SourceFile.original_name.label("source_filename"),
                SourceFile.media_type.label("source_media_type"),
                InvoiceRecord.source_worksheet.label("source_worksheet"),
                func.coalesce(inv_li_count.c.cnt, 0).label("line_item_count"),
                ImportBatch.status.label("status"),
                InvoiceRecord.created_at.label("created_at"),
            )
            .join(InvoiceRecord.batch)
            .outerjoin(ImportBatch.source_file)
            .outerjoin(inv_li_count, InvoiceRecord.id == inv_li_count.c.invoice_id)
            .filter(active_record_scope())
        )
        queries.append(q_inv)

    if include_receipts:
        q_rec = (
            db.query(
                literal("receipt").label("doc_type"),
                ReceiptRecord.id.label("record_id"),
                ReceiptRecord.receipt_number.label("document_number"),
                ReceiptRecord.merchant_name.label("counterparty"),
                ReceiptRecord.transaction_date.label("document_date"),
                ReceiptRecord.currency.label("currency"),
                ReceiptRecord.total_amount.label("total_amount"),
                ReceiptRecord.direction.label("direction"),
                ReceiptRecord.batch_id.label("batch_id"),
                SourceFile.id.label("source_file_id"),
                SourceFile.original_name.label("source_filename"),
                SourceFile.media_type.label("source_media_type"),
                literal(None).label("source_worksheet"),
                func.coalesce(rec_li_count.c.cnt, 0).label("line_item_count"),
                ImportBatch.status.label("status"),
                ReceiptRecord.created_at.label("created_at"),
            )
            .join(ReceiptRecord.batch)
            .outerjoin(ImportBatch.source_file)
            .outerjoin(rec_li_count, ReceiptRecord.id == rec_li_count.c.receipt_id)
            .filter(active_record_scope())
        )
        queries.append(q_rec)

    if not queries:
        return PaginatedDocumentsResponse(items=[], total=0, page=page, page_size=page_size, total_pages=0)

    if len(queries) == 1:
        union_subq = queries[0].subquery()
    else:
        union_subq = queries[0].union_all(queries[1]).subquery()

    doc_query = db.query(union_subq)

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        doc_query = doc_query.filter(
            or_(
                union_subq.c.counterparty.ilike(search_term),
                union_subq.c.document_number.ilike(search_term),
            )
        )

    if direction and direction.strip() and direction.strip().lower() != "all":
        doc_query = doc_query.filter(union_subq.c.direction == direction.strip().lower())

    if currency and currency.strip():
        doc_query = doc_query.filter(union_subq.c.currency == currency.strip().upper())

    if date_from:
        doc_query = doc_query.filter(union_subq.c.document_date >= date_from)

    if date_to:
        doc_query = doc_query.filter(union_subq.c.document_date <= date_to)

    total = doc_query.count()

    sort_col = getattr(union_subq.c, sort_by)
    if sort_order.lower() == "asc":
        doc_query = doc_query.order_by(sort_col.asc().nulls_last(), union_subq.c.record_id.asc())
    else:
        doc_query = doc_query.order_by(sort_col.desc().nulls_last(), union_subq.c.record_id.desc())

    offset = (page - 1) * page_size
    rows = doc_query.offset(offset).limit(page_size).all()

    org_id = db.info.get("organization_id", 0)
    page_inv_ids = [r.record_id for r in rows if r.doc_type == "invoice"]
    page_rec_ids = [r.record_id for r in rows if r.doc_type == "receipt"]
    inv_counts = get_connected_counts_batch(db, org_id, "invoice", page_inv_ids)
    rec_counts = get_connected_counts_batch(db, org_id, "receipt", page_rec_ids)

    items: list[UnifiedDocumentListItem] = []
    for r in rows:
        cnt = inv_counts.get(r.record_id, 0) if r.doc_type == "invoice" else rec_counts.get(r.record_id, 0)
        items.append(
            UnifiedDocumentListItem(
                id=f"{r.doc_type}_{r.record_id}",
                record_id=r.record_id,
                document_type=r.doc_type,
                document_number=r.document_number,
                counterparty=r.counterparty,
                document_date=r.document_date,
                currency=r.currency,
                total_amount=r.total_amount,
                direction=r.direction,
                batch_id=r.batch_id,
                source_file_id=r.source_file_id,
                source_filename=r.source_filename,
                source_worksheet=r.source_worksheet,
                source_media_type=r.source_media_type,
                line_item_count=r.line_item_count,
                status=r.status,
                created_at=r.created_at,
                connected_count=cnt,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedDocumentsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
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
        .filter(active_record_scope())
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

    base_query = base_query.filter(*invoice_filter_conditions(company, currency, date_from, date_to))

    total = base_query.count()

    # Eager load parent invoice for performance
    data_query = (
        db.query(InvoiceLineItem)
        .options(joinedload(InvoiceLineItem.invoice_record))
        .join(InvoiceLineItem.invoice_record)
        .join(InvoiceRecord.batch)
        .filter(active_record_scope())
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
    data_query = data_query.filter(*invoice_filter_conditions(company, currency, date_from, date_to))

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
    summary="Get dynamic filter dropdown options (companies, currencies, merchants, etc.)",
)
def get_filter_options(
    db: Session = Depends(get_db),
) -> DataExplorerFilterOptions:
    """
    Returns unique lists of companies, merchants, currencies, payment methods, and directions
    present in active (non-deleted) batches.
    """
    companies_query = (
        db.query(InvoiceRecord.company_name)
        .join(InvoiceRecord.batch)
        .filter(
            active_record_scope(),
            InvoiceRecord.company_name.isnot(None),
            InvoiceRecord.company_name != "",
        )
        .distinct()
        .order_by(InvoiceRecord.company_name.asc())
        .all()
    )

    merchants_query = (
        db.query(ReceiptRecord.merchant_name)
        .join(ReceiptRecord.batch)
        .filter(
            active_record_scope(),
            ReceiptRecord.merchant_name.isnot(None),
            ReceiptRecord.merchant_name != "",
        )
        .distinct()
        .order_by(ReceiptRecord.merchant_name.asc())
        .all()
    )

    currencies_inv = (
        db.query(InvoiceRecord.currency)
        .join(InvoiceRecord.batch)
        .filter(
            active_record_scope(),
            InvoiceRecord.currency.isnot(None),
            InvoiceRecord.currency != "",
        )
        .distinct()
        .all()
    )

    currencies_rec = (
        db.query(ReceiptRecord.currency)
        .join(ReceiptRecord.batch)
        .filter(
            active_record_scope(),
            ReceiptRecord.currency.isnot(None),
            ReceiptRecord.currency != "",
        )
        .distinct()
        .all()
    )

    payment_methods_query = (
        db.query(ReceiptRecord.payment_method)
        .join(ReceiptRecord.batch)
        .filter(
            active_record_scope(),
            ReceiptRecord.payment_method.isnot(None),
            ReceiptRecord.payment_method != "",
        )
        .distinct()
        .order_by(ReceiptRecord.payment_method.asc())
        .all()
    )

    companies = [c[0] for c in companies_query if c[0]]
    merchants = [m[0] for m in merchants_query if m[0]]
    all_currencies = sorted(list(set(c[0] for c in (currencies_inv + currencies_rec) if c[0])))
    payment_methods = [p[0] for p in payment_methods_query if p[0]]
    directions = ["sales", "purchase", "expense", "income", "unclassified"]

    return DataExplorerFilterOptions(
        companies=companies,
        currencies=all_currencies,
        merchants=merchants,
        payment_methods=payment_methods,
        directions=directions,
    )
