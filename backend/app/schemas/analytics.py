"""Monetary values serialize as Decimal strings, never JSON floats."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


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


class FinancialSummary(BaseModel):
    # Invoices by direction
    sales_invoiced_value: Decimal | None = None
    sales_invoice_count: int = 0
    sales_invoices_with_total: int = 0

    purchases_invoiced_value: Decimal | None = None
    purchase_invoice_count: int = 0
    purchase_invoices_with_total: int = 0

    unclassified_invoice_value: Decimal | None = None
    unclassified_invoice_count: int = 0
    unclassified_invoices_with_total: int = 0

    # Receipts by direction
    income_receipts_value: Decimal | None = None
    income_receipt_count: int = 0
    income_receipts_with_total: int = 0

    expense_receipts_value: Decimal | None = None
    expense_receipt_count: int = 0
    expense_receipts_with_total: int = 0

    unclassified_receipts_value: Decimal | None = None
    unclassified_receipt_count: int = 0
    unclassified_receipts_with_total: int = 0

    # Overall receipts
    receipt_count: int = 0
    receipts_with_total: int = 0
    receipts_without_total: int = 0
    receipts_without_date: int = 0


class InvoicePeriod(BaseModel):
    period: str
    invoice_count: int
    invoices_with_total: int
    invoice_value: Decimal | None


class FinancialInvoiceTrend(BaseModel):
    period: str
    sales_count: int = 0
    sales_value: Decimal | None = None
    purchase_count: int = 0
    purchase_value: Decimal | None = None
    unclassified_count: int = 0
    unclassified_value: Decimal | None = None
    total_count: int = 0
    total_value: Decimal | None = None


class FinancialReceiptTrend(BaseModel):
    period: str
    income_count: int = 0
    income_value: Decimal | None = None
    expense_count: int = 0
    expense_value: Decimal | None = None
    unclassified_count: int = 0
    unclassified_value: Decimal | None = None
    total_count: int = 0
    total_value: Decimal | None = None


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

    # M16.4 Direction-Aware Analytics
    financial_summary: FinancialSummary = Field(default_factory=FinancialSummary)
    financial_invoice_trends: list[FinancialInvoiceTrend] = Field(default_factory=list)
    financial_receipt_trends: list[FinancialReceiptTrend] = Field(default_factory=list)


class AnalyticsFilterOptions(BaseModel):
    currencies: list[str]
    has_unspecified_currency: bool
    companies: list[str]
    date_from: date | None
    date_to: date | None
