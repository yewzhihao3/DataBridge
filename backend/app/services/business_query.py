"""Shared visibility boundary for standardized business data.

Queries must join ImportBatch before applying active_record_scope(). Future
workspace scoping belongs here. This module never changes persisted values.
"""
from datetime import date
from decimal import Decimal

from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord


def active_record_scope():
    return ImportBatch.is_deleted.is_(False)


def invoice_filter_conditions(
    company: str | None = None,
    currency: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    direction: str | None = None,
) -> list:
    conditions = []
    if company and company.strip():
        conditions.append(InvoiceRecord.company_name.ilike(f"%{company.strip()}%"))
    if currency and currency.strip():
        conditions.append(InvoiceRecord.currency == currency.strip().upper())
    if date_from:
        conditions.append(InvoiceRecord.invoice_date >= date_from)
    if date_to:
        conditions.append(InvoiceRecord.invoice_date <= date_to)
    if direction and direction.strip() and direction.strip().lower() != "all":
        conditions.append(InvoiceRecord.direction == direction.strip().lower())
    return conditions


def receipt_filter_conditions(
    merchant: str | None = None,
    currency: str | None = None,
    direction: str | None = None,
    payment_method: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
) -> list:
    conditions = []
    if merchant and merchant.strip():
        conditions.append(ReceiptRecord.merchant_name.ilike(f"%{merchant.strip()}%"))
    if currency and currency.strip():
        conditions.append(ReceiptRecord.currency == currency.strip().upper())
    if direction and direction.strip() and direction.strip().lower() != "all":
        conditions.append(ReceiptRecord.direction == direction.strip().lower())
    if payment_method and payment_method.strip():
        conditions.append(ReceiptRecord.payment_method.ilike(f"%{payment_method.strip()}%"))
    if date_from:
        conditions.append(ReceiptRecord.transaction_date >= date_from)
    if date_to:
        conditions.append(ReceiptRecord.transaction_date <= date_to)
    if amount_min is not None:
        conditions.append(ReceiptRecord.total_amount >= amount_min)
    if amount_max is not None:
        conditions.append(ReceiptRecord.total_amount <= amount_max)
    return conditions
