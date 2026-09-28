"""SQL aggregates over active persisted records, without invoice/child fan-out.

Canonical money has scale 2. Aggregate integer minor units in SQL so SQLite's
floating SUM/AVG cannot leak artifacts. Round each stored value to its model's
scale before summing (SQLite does not enforce NUMERIC scale). PostgreSQL also
supports these expressions. Divide and round averages with Decimal afterwards.
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import BigInteger, cast, extract, func
from sqlalchemy.orm import Session

from app.models.invoice import InvoiceLineItem, InvoiceRecord
from app.schemas.analytics import (
    AnalyticsFilterOptions, AnalyticsFilters, AnalyticsSummary, CompanyValue,
    DashboardResponse, InvoicePeriod, LineItemValue,
)
from app.services.business_query import active_record_scope, invoice_filter_conditions


def currency_key():
    return func.nullif(func.upper(func.trim(InvoiceRecord.currency)), "")


def money_sum(column):
    return func.sum(cast(func.round(column * 100, 0), BigInteger))


def money(cents) -> Decimal | None:
    if cents is None:
        return None
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def filter_options(db: Session) -> AnalyticsFilterOptions:
    base = db.query(InvoiceRecord).join(InvoiceRecord.batch).filter(active_record_scope())
    currencies = [row[0] for row in base.with_entities(currency_key()).distinct().all()]
    companies = base.with_entities(InvoiceRecord.company_name).filter(
        InvoiceRecord.company_name.isnot(None), InvoiceRecord.company_name != "",
    ).distinct().order_by(InvoiceRecord.company_name).all()
    bounds = base.with_entities(func.min(InvoiceRecord.invoice_date), func.max(InvoiceRecord.invoice_date)).one()
    return AnalyticsFilterOptions(
        currencies=sorted(c for c in currencies if c is not None),
        has_unspecified_currency=None in currencies,
        companies=[row[0] for row in companies], date_from=bounds[0], date_to=bounds[1],
    )


def dashboard(db: Session, filters: AnalyticsFilters) -> DashboardResponse:
    conditions = [active_record_scope(), *invoice_filter_conditions(
        company=filters.company, date_from=filters.date_from, date_to=filters.date_to,
    )]
    # No currency means ONLY unspecified records, never all currencies.
    conditions.append(currency_key() == filters.currency if filters.currency else currency_key().is_(None))
    invoices = db.query(InvoiceRecord).join(InvoiceRecord.batch).filter(*conditions)
    items = db.query(InvoiceLineItem).join(InvoiceLineItem.invoice_record).join(
        InvoiceRecord.batch,
    ).filter(*conditions)
    monetary = filters.currency is not None
    counts = invoices.with_entities(
        func.count(InvoiceRecord.id), func.count(InvoiceRecord.total_amount),
        func.count(InvoiceRecord.invoice_date), money_sum(InvoiceRecord.total_amount),
    ).one()
    item_counts = items.with_entities(func.count(InvoiceLineItem.id), func.count(InvoiceLineItem.amount)).one()
    total = money(counts[3]) if monetary else None
    average = (total / counts[1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total is not None and counts[1] else None

    year, month = extract("year", InvoiceRecord.invoice_date), extract("month", InvoiceRecord.invoice_date)
    periods = invoices.filter(InvoiceRecord.invoice_date.isnot(None)).with_entities(
        year, month, func.count(InvoiceRecord.id), func.count(InvoiceRecord.total_amount),
        money_sum(InvoiceRecord.total_amount),
    ).group_by(year, month).order_by(year, month).all()

    company_values = []
    line_item_values = []
    if monetary:
        company_sum = money_sum(InvoiceRecord.total_amount)
        company_rows = invoices.with_entities(
            InvoiceRecord.company_name, func.count(InvoiceRecord.id),
            func.count(InvoiceRecord.total_amount), company_sum,
        ).group_by(InvoiceRecord.company_name).having(func.count(InvoiceRecord.total_amount) > 0).order_by(
            company_sum.desc(), InvoiceRecord.company_name.asc().nulls_last(),
        ).limit(10).all()
        company_values = [CompanyValue(company_name=r[0], invoice_count=r[1], invoices_with_total=r[2], invoice_value=money(r[3])) for r in company_rows]

        # Conservative normalization: trim outer whitespace only. No fuzzy product
        # identity or unit-of-measure assumptions; case and internal text stay intact.
        description = func.nullif(func.trim(InvoiceLineItem.description), "")
        item_sum = money_sum(InvoiceLineItem.amount)
        item_rows = items.with_entities(
            description, func.count(InvoiceLineItem.id), func.count(InvoiceLineItem.amount), item_sum,
        ).group_by(description).having(func.count(InvoiceLineItem.amount) > 0).order_by(
            item_sum.desc(), description.asc().nulls_last(),
        ).limit(10).all()
        line_item_values = [LineItemValue(description=r[0], line_item_count=r[1], line_items_with_amount=r[2], amount=money(r[3])) for r in item_rows]

    return DashboardResponse(
        filters=filters, monetary_values_available=monetary,
        summary=AnalyticsSummary(
            invoice_count=counts[0], invoices_with_total=counts[1],
            invoices_without_total=counts[0] - counts[1], invoices_without_date=counts[0] - counts[2],
            total_invoice_value=total, average_invoice_value=average,
            line_item_count=item_counts[0], line_items_with_amount=item_counts[1],
        ),
        invoice_value_over_time=[InvoicePeriod(
            period=f"{int(r[0]):04d}-{int(r[1]):02d}", invoice_count=r[2],
            invoices_with_total=r[3], invoice_value=money(r[4]) if monetary else None,
        ) for r in periods],
        company_values=company_values, line_item_values=line_item_values,
    )
