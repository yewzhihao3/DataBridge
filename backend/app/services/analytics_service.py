"""SQL aggregates over active persisted records, without invoice/child fan-out.

Canonical money has scale 2. Aggregate integer minor units in SQL so SQLite's
floating SUM/AVG cannot leak artifacts. Round each stored value to its model's
scale before summing (SQLite does not enforce NUMERIC scale). PostgreSQL also
supports these expressions. Divide and round averages with Decimal afterwards.
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import BigInteger, and_, case, cast, extract, func
from sqlalchemy.orm import Session

from app.models.invoice import InvoiceLineItem, InvoiceRecord, ReceiptRecord
from app.schemas.analytics import (
    AnalyticsFilterOptions, AnalyticsFilters, AnalyticsSummary, CompanyValue,
    DashboardResponse, FinancialInvoiceTrend, FinancialReceiptTrend, FinancialSummary,
    InvoicePeriod, LineItemValue,
)
from app.services.business_query import (
    active_record_scope, invoice_filter_conditions, receipt_filter_conditions,
)


def currency_key():
    return func.nullif(func.upper(func.trim(InvoiceRecord.currency)), "")


def receipt_currency_key():
    return func.nullif(func.upper(func.trim(ReceiptRecord.currency)), "")


def money_sum(column):
    return func.sum(cast(func.round(column * 100, 0), BigInteger))


def money(cents) -> Decimal | None:
    if cents is None:
        return None
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


def filter_options(db: Session) -> AnalyticsFilterOptions:
    inv_base = db.query(InvoiceRecord).join(InvoiceRecord.batch).filter(active_record_scope())
    rcpt_base = db.query(ReceiptRecord).join(ReceiptRecord.batch).filter(active_record_scope())

    inv_currencies = [row[0] for row in inv_base.with_entities(currency_key()).distinct().all()]
    rcpt_currencies = [row[0] for row in rcpt_base.with_entities(receipt_currency_key()).distinct().all()]
    all_currencies = inv_currencies + rcpt_currencies
    currencies = sorted(set(c for c in all_currencies if c is not None))
    has_unspecified = None in all_currencies

    companies = inv_base.with_entities(InvoiceRecord.company_name).filter(
        InvoiceRecord.company_name.isnot(None), InvoiceRecord.company_name != "",
    ).distinct().all()
    merchants = rcpt_base.with_entities(ReceiptRecord.merchant_name).filter(
        ReceiptRecord.merchant_name.isnot(None), ReceiptRecord.merchant_name != "",
    ).distinct().all()
    all_companies = sorted(set(r[0] for r in companies + merchants if r[0]))

    inv_bounds = inv_base.with_entities(func.min(InvoiceRecord.invoice_date), func.max(InvoiceRecord.invoice_date)).one()
    rcpt_bounds = rcpt_base.with_entities(func.min(ReceiptRecord.transaction_date), func.max(ReceiptRecord.transaction_date)).one()
    dates = [d for d in [inv_bounds[0], inv_bounds[1], rcpt_bounds[0], rcpt_bounds[1]] if d is not None]
    min_date = min(dates) if dates else None
    max_date = max(dates) if dates else None

    return AnalyticsFilterOptions(
        currencies=currencies,
        has_unspecified_currency=has_unspecified,
        companies=all_companies,
        date_from=min_date,
        date_to=max_date,
    )


def dashboard(db: Session, filters: AnalyticsFilters) -> DashboardResponse:
    # ── 1. Invoices Base ──
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

    cents_col = cast(func.round(InvoiceRecord.total_amount * 100, 0), BigInteger)
    counts = invoices.with_entities(
        func.count(InvoiceRecord.id),
        func.count(InvoiceRecord.total_amount),
        func.count(InvoiceRecord.invoice_date),
        money_sum(InvoiceRecord.total_amount),
        # Sales
        func.sum(case((InvoiceRecord.direction == "sales", 1), else_=0)),
        func.sum(case((and_(InvoiceRecord.direction == "sales", InvoiceRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "sales", cents_col), else_=None)),
        # Purchase
        func.sum(case((InvoiceRecord.direction == "purchase", 1), else_=0)),
        func.sum(case((and_(InvoiceRecord.direction == "purchase", InvoiceRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "purchase", cents_col), else_=None)),
        # Unclassified
        func.sum(case((InvoiceRecord.direction == "unclassified", 1), else_=0)),
        func.sum(case((and_(InvoiceRecord.direction == "unclassified", InvoiceRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "unclassified", cents_col), else_=None)),
    ).one()

    item_counts = items.with_entities(func.count(InvoiceLineItem.id), func.count(InvoiceLineItem.amount)).one()
    total = money(counts[3]) if monetary else None
    average = (total / counts[1]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total is not None and counts[1] else None

    # ── 2. Receipts Base ──
    rcpt_conditions = [
        active_record_scope(),
        *receipt_filter_conditions(
            merchant=filters.company,
            date_from=filters.date_from,
            date_to=filters.date_to,
        ),
    ]
    rcpt_conditions.append(receipt_currency_key() == filters.currency if filters.currency else receipt_currency_key().is_(None))
    receipts = db.query(ReceiptRecord).join(ReceiptRecord.batch).filter(*rcpt_conditions)

    rcpt_cents_col = cast(func.round(ReceiptRecord.total_amount * 100, 0), BigInteger)
    rcpt_counts = receipts.with_entities(
        func.count(ReceiptRecord.id),
        func.count(ReceiptRecord.total_amount),
        func.count(ReceiptRecord.transaction_date),
        money_sum(ReceiptRecord.total_amount),
        # Income
        func.sum(case((ReceiptRecord.direction == "income", 1), else_=0)),
        func.sum(case((and_(ReceiptRecord.direction == "income", ReceiptRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "income", rcpt_cents_col), else_=None)),
        # Expense
        func.sum(case((ReceiptRecord.direction == "expense", 1), else_=0)),
        func.sum(case((and_(ReceiptRecord.direction == "expense", ReceiptRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "expense", rcpt_cents_col), else_=None)),
        # Unclassified
        func.sum(case((ReceiptRecord.direction == "unclassified", 1), else_=0)),
        func.sum(case((and_(ReceiptRecord.direction == "unclassified", ReceiptRecord.total_amount.isnot(None)), 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "unclassified", rcpt_cents_col), else_=None)),
    ).one()

    # ── 3. Time Series Trends ──
    year, month = extract("year", InvoiceRecord.invoice_date), extract("month", InvoiceRecord.invoice_date)
    periods = invoices.filter(InvoiceRecord.invoice_date.isnot(None)).with_entities(
        year, month, func.count(InvoiceRecord.id), func.count(InvoiceRecord.total_amount),
        money_sum(InvoiceRecord.total_amount),
        # Sales
        func.sum(case((InvoiceRecord.direction == "sales", 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "sales", cents_col), else_=None)),
        # Purchase
        func.sum(case((InvoiceRecord.direction == "purchase", 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "purchase", cents_col), else_=None)),
        # Unclassified
        func.sum(case((InvoiceRecord.direction == "unclassified", 1), else_=0)),
        func.sum(case((InvoiceRecord.direction == "unclassified", cents_col), else_=None)),
    ).group_by(year, month).order_by(year, month).all()

    rcpt_year, rcpt_month = extract("year", ReceiptRecord.transaction_date), extract("month", ReceiptRecord.transaction_date)
    rcpt_periods = receipts.filter(ReceiptRecord.transaction_date.isnot(None)).with_entities(
        rcpt_year, rcpt_month, func.count(ReceiptRecord.id), func.count(ReceiptRecord.total_amount),
        money_sum(ReceiptRecord.total_amount),
        # Income
        func.sum(case((ReceiptRecord.direction == "income", 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "income", rcpt_cents_col), else_=None)),
        # Expense
        func.sum(case((ReceiptRecord.direction == "expense", 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "expense", rcpt_cents_col), else_=None)),
        # Unclassified
        func.sum(case((ReceiptRecord.direction == "unclassified", 1), else_=0)),
        func.sum(case((ReceiptRecord.direction == "unclassified", rcpt_cents_col), else_=None)),
    ).group_by(rcpt_year, rcpt_month).order_by(rcpt_year, rcpt_month).all()

    # ── 4. Rankings ──
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
        filters=filters,
        monetary_values_available=monetary,
        summary=AnalyticsSummary(
            invoice_count=counts[0],
            invoices_with_total=counts[1],
            invoices_without_total=counts[0] - counts[1],
            invoices_without_date=counts[0] - counts[2],
            total_invoice_value=total,
            average_invoice_value=average,
            line_item_count=item_counts[0],
            line_items_with_amount=item_counts[1],
        ),
        invoice_value_over_time=[InvoicePeriod(
            period=f"{int(r[0]):04d}-{int(r[1]):02d}",
            invoice_count=r[2],
            invoices_with_total=r[3],
            invoice_value=money(r[4]) if monetary else None,
        ) for r in periods],
        financial_summary=FinancialSummary(
            sales_invoiced_value=money(counts[6]) if monetary else None,
            sales_invoice_count=int(counts[4] or 0),
            sales_invoices_with_total=int(counts[5] or 0),
            purchases_invoiced_value=money(counts[9]) if monetary else None,
            purchase_invoice_count=int(counts[7] or 0),
            purchase_invoices_with_total=int(counts[8] or 0),
            unclassified_invoice_value=money(counts[12]) if monetary else None,
            unclassified_invoice_count=int(counts[10] or 0),
            unclassified_invoices_with_total=int(counts[11] or 0),
            income_receipts_value=money(rcpt_counts[6]) if monetary else None,
            income_receipt_count=int(rcpt_counts[4] or 0),
            income_receipts_with_total=int(rcpt_counts[5] or 0),
            expense_receipts_value=money(rcpt_counts[9]) if monetary else None,
            expense_receipt_count=int(rcpt_counts[7] or 0),
            expense_receipts_with_total=int(rcpt_counts[8] or 0),
            unclassified_receipts_value=money(rcpt_counts[12]) if monetary else None,
            unclassified_receipt_count=int(rcpt_counts[10] or 0),
            unclassified_receipts_with_total=int(rcpt_counts[11] or 0),
            receipt_count=rcpt_counts[0],
            receipts_with_total=rcpt_counts[1],
            receipts_without_total=rcpt_counts[0] - rcpt_counts[1],
            receipts_without_date=rcpt_counts[0] - rcpt_counts[2],
        ),
        financial_invoice_trends=[FinancialInvoiceTrend(
            period=f"{int(r[0]):04d}-{int(r[1]):02d}",
            sales_count=int(r[5] or 0),
            sales_value=money(r[6]) if monetary else None,
            purchase_count=int(r[7] or 0),
            purchase_value=money(r[8]) if monetary else None,
            unclassified_count=int(r[9] or 0),
            unclassified_value=money(r[10]) if monetary else None,
            total_count=r[2],
            total_value=money(r[4]) if monetary else None,
        ) for r in periods],
        financial_receipt_trends=[FinancialReceiptTrend(
            period=f"{int(r[0]):04d}-{int(r[1]):02d}",
            income_count=int(r[5] or 0),
            income_value=money(r[6]) if monetary else None,
            expense_count=int(r[7] or 0),
            expense_value=money(r[8]) if monetary else None,
            unclassified_count=int(r[9] or 0),
            unclassified_value=money(r[10]) if monetary else None,
            total_count=r[2],
            total_value=money(r[4]) if monetary else None,
        ) for r in rcpt_periods],
        company_values=company_values,
        line_item_values=line_item_values,
    )
