"""Monetary values serialize as Decimal strings, never JSON floats."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class AnalyticsFilters(BaseModel):
    currency: str | None
    date_from: date | None = None
    date_to: date | None = None
    company: str | None = None


class AnalyticsSummary(BaseModel):
    invoice_count: int
    invoices_with_total: int
    invoices_without_total: int
    invoices_without_date: int
    total_invoice_value: Decimal | None
    average_invoice_value: Decimal | None
    line_item_count: int
    line_items_with_amount: int


class InvoicePeriod(BaseModel):
    period: str
    invoice_count: int
    invoices_with_total: int
    invoice_value: Decimal | None


class CompanyValue(BaseModel):
    company_name: str | None
    invoice_count: int
    invoices_with_total: int
    invoice_value: Decimal


class LineItemValue(BaseModel):
    description: str | None
    line_item_count: int
    line_items_with_amount: int
    amount: Decimal


class DashboardResponse(BaseModel):
    filters: AnalyticsFilters
    monetary_values_available: bool
    grouping: str = "month"
    summary: AnalyticsSummary
    invoice_value_over_time: list[InvoicePeriod]
    company_values: list[CompanyValue]
    line_item_values: list[LineItemValue]


class AnalyticsFilterOptions(BaseModel):
    currencies: list[str]
    has_unspecified_currency: bool
    companies: list[str]
    date_from: date | None
    date_to: date | None
