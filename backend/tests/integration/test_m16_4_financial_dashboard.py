"""Integration tests for Milestone 16.4: Direction-Aware Financial Dashboard."""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.invoice import (
    ImportBatch, InvoiceLineItem, InvoiceRecord, ReceiptLineItem, ReceiptRecord,
)
from app.models.source_file import SourceFile
from app.models.template import Template
from tests.integration.test_saas import register


@pytest.fixture
def add_records(db_session: Session):
    source = SourceFile(original_name="financial_test.xlsx", stored_filename="financial_test.xlsx", file_size=1, checksum="f" * 64)
    template = Template(name="Financial Template", template_type="dataset")
    db_session.add_all([source, template])
    db_session.flush()
    inv_seq = 0
    rcpt_seq = 0

    def add_invoice(
        total="100.00",
        direction="sales",
        currency="MYR",
        day="2026-09-15",
        company="Customer Corp",
        amounts=(),
        deleted=False,
    ):
        nonlocal inv_seq
        inv_seq += 1
        batch = ImportBatch(source_file_id=source.id, template_id=template.id, is_deleted=deleted)
        record = InvoiceRecord(
            company_name=company,
            invoice_number=f"INV-{inv_seq}",
            invoice_date=date.fromisoformat(day) if day else None,
            total_amount=Decimal(total) if total is not None else None,
            currency=currency,
            direction=direction,
            source_worksheet="Sheet1",
            raw_data="{}",
        )
        batch.invoice_records.append(record)
        for i, amt in enumerate(amounts, 1):
            record.line_items.append(InvoiceLineItem(
                source_row_number=i,
                description=f"Item {i}",
                amount=Decimal(amt) if amt is not None else None,
            ))
        db_session.add(batch)
        db_session.commit()
        return record

    def add_receipt(
        total="50.00",
        direction="expense",
        currency="MYR",
        day="2026-09-15",
        merchant="Office Supply Co",
        amounts=(),
        deleted=False,
    ):
        nonlocal rcpt_seq
        rcpt_seq += 1
        batch = ImportBatch(source_file_id=source.id, template_id=template.id, is_deleted=deleted)
        record = ReceiptRecord(
            merchant_name=merchant,
            receipt_number=f"RCPT-{rcpt_seq}",
            transaction_date=date.fromisoformat(day) if day else None,
            total_amount=Decimal(total) if total is not None else None,
            currency=currency,
            direction=direction,
            raw_data="{}",
        )
        batch.receipt_records.append(record)
        for i, amt in enumerate(amounts, 1):
            record.line_items.append(ReceiptLineItem(
                source_row_number=i,
                description=f"Receipt Item {i}",
                amount=Decimal(amt) if amt is not None else None,
            ))
        db_session.add(batch)
        db_session.commit()
        return record

    return add_invoice, add_receipt


async def get_dashboard(client: AsyncClient, **params):
    response = await client.get("/api/v1/analytics/dashboard", params={"currency": "MYR", **params})
    assert response.status_code == 200, response.text
    return response.json()


# ── Scenario 1, 2, 3: Invoice Aggregations by Direction ───────────────────────
async def test_invoice_aggregations_by_direction(client: AsyncClient, add_records):
    add_inv, _ = add_records
    add_inv(total="1000.00", direction="sales")
    add_inv(total="500.00", direction="sales")
    add_inv(total="300.00", direction="purchase")
    add_inv(total="120.00", direction="unclassified")
    add_inv(total=None, direction="unclassified")

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    # Sales
    assert fin["sales_invoiced_value"] == "1500.00"
    assert fin["sales_invoice_count"] == 2
    assert fin["sales_invoices_with_total"] == 2

    # Purchases
    assert fin["purchases_invoiced_value"] == "300.00"
    assert fin["purchase_invoice_count"] == 1
    assert fin["purchase_invoices_with_total"] == 1

    # Unclassified
    assert fin["unclassified_invoice_value"] == "120.00"
    assert fin["unclassified_invoice_count"] == 2
    assert fin["unclassified_invoices_with_total"] == 1

    # Overall invoices preserved
    assert data["summary"]["invoice_count"] == 5
    assert data["summary"]["total_invoice_value"] == "1920.00"


# ── Scenario 4, 5, 6: Receipt Aggregations by Direction ───────────────────────
async def test_receipt_aggregations_by_direction(client: AsyncClient, add_records):
    _, add_rcpt = add_records
    add_rcpt(total="250.00", direction="income")
    add_rcpt(total="75.00", direction="expense")
    add_rcpt(total="25.00", direction="expense")
    add_rcpt(total="40.00", direction="unclassified")
    add_rcpt(total=None, direction="expense")

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    # Income
    assert fin["income_receipts_value"] == "250.00"
    assert fin["income_receipt_count"] == 1
    assert fin["income_receipts_with_total"] == 1

    # Expense
    assert fin["expense_receipts_value"] == "100.00"
    assert fin["expense_receipt_count"] == 3
    assert fin["expense_receipts_with_total"] == 2

    # Unclassified
    assert fin["unclassified_receipts_value"] == "40.00"
    assert fin["unclassified_receipt_count"] == 1
    assert fin["unclassified_receipts_with_total"] == 1

    # Overall receipts
    assert fin["receipt_count"] == 5
    assert fin["receipts_with_total"] == 4
    assert fin["receipts_without_total"] == 1


# ── Scenario 7 & 8: Mixed Directions Across Invoices and Receipts ─────────────
async def test_mixed_invoices_and_receipts_remain_strictly_separate(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    # 200 sales invoice, 50 expense receipt
    add_inv(total="200.00", direction="sales")
    add_rcpt(total="50.00", direction="expense")

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    assert fin["sales_invoiced_value"] == "200.00"
    assert fin["expense_receipts_value"] == "50.00"
    assert fin["purchases_invoiced_value"] is None
    assert fin["income_receipts_value"] is None
    # Verify no combining into a net figure
    assert "net_profit" not in fin
    assert "cash_flow" not in fin


# ── Scenario 9: Date Filtering (Inclusive & Undated) ──────────────────────────
async def test_date_filtering_on_invoices_and_receipts(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total="100.00", direction="sales", day="2026-08-15")
    add_inv(total="200.00", direction="sales", day="2026-09-01")
    add_inv(total="300.00", direction="purchase", day="2026-09-30")
    add_inv(total="400.00", direction="sales", day="2026-10-01")
    add_inv(total="500.00", direction="sales", day=None)

    add_rcpt(total="10.00", direction="income", day="2026-08-15")
    add_rcpt(total="20.00", direction="expense", day="2026-09-10")
    add_rcpt(total="30.00", direction="expense", day="2026-10-05")
    add_rcpt(total="40.00", direction="expense", day=None)

    # Filter for September 2026
    data = await get_dashboard(client, date_from="2026-09-01", date_to="2026-09-30")
    fin = data["financial_summary"]

    assert fin["sales_invoiced_value"] == "200.00"
    assert fin["purchases_invoiced_value"] == "300.00"
    assert fin["expense_receipts_value"] == "20.00"
    assert fin["income_receipts_value"] is None


# ── Scenario 10 & 11: Currency Filtering & Mixed-Currency Protection ──────────
async def test_currency_filtering_and_multi_currency_protection(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total="100.00", currency="MYR", direction="sales")
    add_inv(total="500.00", currency="USD", direction="sales")
    add_rcpt(total="20.00", currency="MYR", direction="expense")
    add_rcpt(total="80.00", currency="USD", direction="expense")

    myr = await get_dashboard(client, currency="MYR")
    assert myr["financial_summary"]["sales_invoiced_value"] == "100.00"
    assert myr["financial_summary"]["expense_receipts_value"] == "20.00"

    usd = await get_dashboard(client, currency="USD")
    assert usd["financial_summary"]["sales_invoiced_value"] == "500.00"
    assert usd["financial_summary"]["expense_receipts_value"] == "80.00"

    # Unspecified currency suppresses monetary values
    unspec = (await client.get("/api/v1/analytics/dashboard")).json()
    assert unspec["monetary_values_available"] is False
    assert unspec["financial_summary"]["sales_invoiced_value"] is None
    assert unspec["financial_summary"]["expense_receipts_value"] is None


# ── Scenario 12: Soft-Deleted Records Excluded Everywhere ─────────────────────
async def test_soft_deleted_batches_excluded(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total="100.00", direction="sales", deleted=False)
    add_inv(total="999.00", direction="sales", deleted=True)
    add_rcpt(total="50.00", direction="expense", deleted=False)
    add_rcpt(total="888.00", direction="expense", deleted=True)

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    assert fin["sales_invoiced_value"] == "100.00"
    assert fin["sales_invoice_count"] == 1
    assert fin["expense_receipts_value"] == "50.00"
    assert fin["expense_receipt_count"] == 1


# ── Scenario 13: Cross-Tenant Isolation ───────────────────────────────────────
async def test_cross_tenant_isolation_on_dashboard(client: AsyncClient, db_session: Session):
    # Register Org A
    reg_a = await register(client, email="user_a@test.com", workspace="Workspace A")
    org_a_id = reg_a["workspaces"][0]["id"]
    with Session(db_session.bind) as db:
        db.info["organization_id"] = org_a_id
        source_a = SourceFile(original_name="a.xlsx", stored_filename="a.xlsx", file_size=1, checksum="a"*64, organization_id=org_a_id)
        template_a = Template(name="Tmpl A", organization_id=org_a_id)
        db.add_all([source_a, template_a])
        db.flush()
        batch_a = ImportBatch(source_file_id=source_a.id, template_id=template_a.id, organization_id=org_a_id)
        batch_a.invoice_records.append(InvoiceRecord(
            company_name="Company A", invoice_number="INV-A", total_amount=Decimal("150.00"), currency="MYR", direction="sales",
            source_worksheet="S1", raw_data="{}",
        ))
        db.add(batch_a)
        db.commit()

    # Org A sees its 150.00 sales
    res_a = await client.get("/api/v1/analytics/dashboard", params={"currency": "MYR"})
    assert res_a.status_code == 200
    assert res_a.json()["financial_summary"]["sales_invoiced_value"] == "150.00"

    # Register Org B
    client.cookies.clear()
    reg_b = await register(client, email="user_b@test.com", workspace="Workspace B")
    # Org B sees zero records from Org A
    res_b = await client.get("/api/v1/analytics/dashboard", params={"currency": "MYR"})
    assert res_b.status_code == 200
    assert res_b.json()["financial_summary"]["sales_invoiced_value"] is None
    assert res_b.json()["financial_summary"]["sales_invoice_count"] == 0


# ── Scenario 14: Empty Dataset ────────────────────────────────────────────────
async def test_empty_financial_dataset(client: AsyncClient):
    data = await get_dashboard(client)
    fin = data["financial_summary"]
    assert fin["sales_invoiced_value"] is None
    assert fin["sales_invoice_count"] == 0
    assert fin["purchases_invoiced_value"] is None
    assert fin["purchase_invoice_count"] == 0
    assert fin["income_receipts_value"] is None
    assert fin["income_receipt_count"] == 0
    assert fin["expense_receipts_value"] is None
    assert fin["expense_receipt_count"] == 0
    assert fin["receipt_count"] == 0
    assert data["financial_invoice_trends"] == []
    assert data["financial_receipt_trends"] == []


# ── Scenario 15: Nullable Amount Handling ─────────────────────────────────────
async def test_nullable_amounts_in_counts_and_sums(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total=None, direction="sales")
    add_rcpt(total=None, direction="expense")

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    assert fin["sales_invoice_count"] == 1
    assert fin["sales_invoices_with_total"] == 0
    assert fin["sales_invoiced_value"] is None

    assert fin["expense_receipt_count"] == 1
    assert fin["expense_receipts_with_total"] == 0
    assert fin["expense_receipts_value"] is None


# ── Scenario 16: Monthly Trend Accuracy by Direction ──────────────────────────
async def test_monthly_financial_trends_accuracy(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    # Invoices
    add_inv(total="100.00", direction="sales", day="2026-08-10")
    add_inv(total="250.00", direction="sales", day="2026-08-25")
    add_inv(total="80.00", direction="purchase", day="2026-08-15")
    add_inv(total="300.00", direction="purchase", day="2026-09-05")

    # Receipts
    add_rcpt(total="40.00", direction="income", day="2026-08-20")
    add_rcpt(total="60.00", direction="expense", day="2026-08-22")
    add_rcpt(total="90.00", direction="expense", day="2026-09-10")

    data = await get_dashboard(client)
    inv_trends = data["financial_invoice_trends"]
    rcpt_trends = data["financial_receipt_trends"]

    assert len(inv_trends) == 2
    # 2026-08 invoices
    assert inv_trends[0]["period"] == "2026-08"
    assert inv_trends[0]["sales_count"] == 2
    assert inv_trends[0]["sales_value"] == "350.00"
    assert inv_trends[0]["purchase_count"] == 1
    assert inv_trends[0]["purchase_value"] == "80.00"

    # 2026-09 invoices
    assert inv_trends[1]["period"] == "2026-09"
    assert inv_trends[1]["sales_count"] == 0
    assert inv_trends[1]["sales_value"] is None
    assert inv_trends[1]["purchase_count"] == 1
    assert inv_trends[1]["purchase_value"] == "300.00"

    assert len(rcpt_trends) == 2
    # 2026-08 receipts
    assert rcpt_trends[0]["period"] == "2026-08"
    assert rcpt_trends[0]["income_count"] == 1
    assert rcpt_trends[0]["income_value"] == "40.00"
    assert rcpt_trends[0]["expense_count"] == 1
    assert rcpt_trends[0]["expense_value"] == "60.00"

    # 2026-09 receipts
    assert rcpt_trends[1]["period"] == "2026-09"
    assert rcpt_trends[1]["income_count"] == 0
    assert rcpt_trends[1]["income_value"] is None
    assert rcpt_trends[1]["expense_count"] == 1
    assert rcpt_trends[1]["expense_value"] == "90.00"


# ── Scenario 17: No Duplicate Totals From Joined Line Items ───────────────────
async def test_no_fan_out_with_line_items(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total="100.00", direction="sales", amounts=["10.00", "20.00", "70.00"])
    add_rcpt(total="50.00", direction="expense", amounts=["25.00", "25.00"])

    data = await get_dashboard(client)
    fin = data["financial_summary"]

    assert fin["sales_invoiced_value"] == "100.00"
    assert fin["expense_receipts_value"] == "50.00"


# ── Scenario 18: Filter Options Includes Invoices and Receipts ────────────────
async def test_filter_options_unifies_currencies_and_merchants(client: AsyncClient, add_records):
    add_inv, add_rcpt = add_records
    add_inv(total="100.00", currency="EUR", company="Acme Invoices", day="2026-07-01")
    add_rcpt(total="50.00", currency="SGD", merchant="Coffee Corner", day="2026-10-15")

    res = await client.get("/api/v1/analytics/filter-options")
    assert res.status_code == 200
    options = res.json()

    assert "EUR" in options["currencies"]
    assert "SGD" in options["currencies"]
    assert "Acme Invoices" in options["companies"]
    assert "Coffee Corner" in options["companies"]
    assert options["date_from"] == "2026-07-01"
    assert options["date_to"] == "2026-10-15"
