"""Shared visibility boundary for standardized business data.

Queries must join ImportBatch before applying active_record_scope(). Future
workspace scoping belongs here. This module never changes persisted values.
"""
from datetime import date

from app.models.invoice import ImportBatch, InvoiceRecord


def active_record_scope():
    return ImportBatch.is_deleted.is_(False)


def invoice_filter_conditions(
    company: str | None = None,
    currency: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
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
    return conditions
