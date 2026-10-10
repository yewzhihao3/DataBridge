"""
tests/integration/test_m16_3_data_explorer.py — Integration tests for Milestone 16.3 Unified Financial Data Explorer.
"""

from datetime import date, datetime
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session

from app.main import app
from app.models.identity import Organization, OrganizationMembership, User
from app.models.invoice import ImportBatch, InvoiceLineItem, InvoiceRecord, ReceiptLineItem, ReceiptRecord
from app.models.source_file import SourceFile
from app.models.template import Template
from app.security import password_hasher
from tests.conftest import TestingSessionLocal


@pytest.fixture
def seed_m16_3_data(db_session: Session) -> dict:
    """
    Seeds test data for M16.3:
    - 2 Invoices (one sales, one purchase)
    - 2 Receipts (one expense, one income, one with missing receipt_number)
    - 1 Soft-deleted Batch (invoice and receipt)
    """
    # Source Files
    sf1 = SourceFile(
        organization_id=1,
        stored_filename="inv1.xlsx",
        original_name="Invoice_Alpha.xlsx",
        file_size=5000,
        checksum="c1",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    sf2 = SourceFile(
        organization_id=1,
        stored_filename="rec1.jpg",
        original_name="Receipt_Beta.jpg",
        file_size=3000,
        checksum="c2",
        media_type="image/jpeg",
    )
    sf_del = SourceFile(
        organization_id=1,
        stored_filename="del.xlsx",
        original_name="Deleted.xlsx",
        file_size=2000,
        checksum="c3",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    db_session.add_all([sf1, sf2, sf_del])
    db_session.flush()

    # Templates
    tmpl = Template(
        organization_id=1,
        name="Standard Invoice",
        template_type="invoice",
        file_type="xlsx",
        worksheet="Sheet1",
    )
    db_session.add(tmpl)
    db_session.flush()

    # Active Batch 1 (Invoices)
    batch1 = ImportBatch(
        organization_id=1,
        source_file_id=sf1.id,
        template_id=tmpl.id,
        status="imported",
        record_count=2,
        is_deleted=False,
        imported_at=datetime(2026, 9, 15, 10, 0, 0),
    )
    # Active Batch 2 (Receipts)
    batch2 = ImportBatch(
        organization_id=1,
        source_file_id=sf2.id,
        template_id=tmpl.id,
        status="imported",
        record_count=2,
        is_deleted=False,
        imported_at=datetime(2026, 9, 16, 12, 0, 0),
    )
    # Deleted Batch 3
    batch3 = ImportBatch(
        organization_id=1,
        source_file_id=sf_del.id,
        template_id=tmpl.id,
        status="imported",
        record_count=1,
        is_deleted=True,
        imported_at=datetime(2026, 9, 10, 9, 0, 0),
    )
    db_session.add_all([batch1, batch2, batch3])
    db_session.flush()

    # Invoices
    inv_sales = InvoiceRecord(
        batch_id=batch1.id,
        company_name="Acme Corp",
        invoice_number="INV-2026-001",
        invoice_date=date(2026, 9, 15),
        total_amount=Decimal("1250.00"),
        currency="USD",
        direction="sales",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    inv_purchase = InvoiceRecord(
        batch_id=batch1.id,
        company_name="Beta Logistics",
        invoice_number="INV-2026-002",
        invoice_date=date(2026, 9, 20),
        total_amount=Decimal("450.00"),
        currency="USD",
        direction="purchase",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    inv_deleted = InvoiceRecord(
        batch_id=batch3.id,
        company_name="Ghost Corp",
        invoice_number="INV-GHOST",
        invoice_date=date(2026, 9, 1),
        total_amount=Decimal("999.00"),
        currency="USD",
        direction="sales",
        source_worksheet="Sheet1",
        raw_data="{}",
    )
    db_session.add_all([inv_sales, inv_purchase, inv_deleted])
    db_session.flush()

    # Invoice line item
    inv_li = InvoiceLineItem(
        invoice_id=inv_sales.id,
        source_row_number=1,
        description="Widget Pro",
        quantity=Decimal("5"),
        unit_price=Decimal("250.00"),
        amount=Decimal("1250.00"),
    )
    db_session.add(inv_li)

    # Receipts
    rec_expense = ReceiptRecord(
        batch_id=batch2.id,
        merchant_name="Starbucks Coffee",
        receipt_number="REC-SB-101",
        transaction_date=date(2026, 9, 16),
        transaction_time="08:30:00",
        total_amount=Decimal("18.50"),
        currency="USD",
        direction="expense",
        payment_method="Credit Card",
        store_address="123 Main St",
        raw_data="{}",
    )
    rec_income = ReceiptRecord(
        batch_id=batch2.id,
        merchant_name="Register Inflow",
        receipt_number="",  # missing printed receipt number
        transaction_date=date(2026, 9, 18),
        transaction_time="17:00:00",
        total_amount=Decimal("320.00"),
        currency="USD",
        direction="income",
        payment_method="Cash",
        store_address="Branch North",
        raw_data="{}",
    )
    rec_deleted = ReceiptRecord(
        batch_id=batch3.id,
        merchant_name="Deleted Cafe",
        receipt_number="DEL-999",
        transaction_date=date(2026, 9, 2),
        total_amount=Decimal("50.00"),
        currency="USD",
        direction="expense",
        raw_data="{}",
    )
    db_session.add_all([rec_expense, rec_income, rec_deleted])
    db_session.flush()

    # Receipt line items
    rec_li1 = ReceiptLineItem(
        receipt_id=rec_expense.id,
        source_row_number=1,
        description="Caramel Macchiato",
        quantity=Decimal("2"),
        unit_price=Decimal("6.50"),
        amount=Decimal("13.00"),
    )
    rec_li2 = ReceiptLineItem(
        receipt_id=rec_expense.id,
        source_row_number=2,
        description="Blueberry Muffin",
        quantity=Decimal("1"),
        unit_price=Decimal("5.50"),
        amount=Decimal("5.50"),
    )
    db_session.add_all([rec_li1, rec_li2])
    db_session.commit()

    return {
        "inv_sales": inv_sales,
        "inv_purchase": inv_purchase,
        "rec_expense": rec_expense,
        "rec_income": rec_income,
        "batch1": batch1,
        "batch2": batch2,
        "batch3": batch3,
    }


# ── 1. Receipts Listing & Detail Tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_receipts_default_and_search(client: AsyncClient, seed_m16_3_data):
    res = await client.get("/api/v1/data/receipts")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    merchants = [r["merchant_name"] for r in data["items"]]
    assert "Starbucks Coffee" in merchants
    assert "Register Inflow" in merchants
    # Soft deleted must be excluded
    assert "Deleted Cafe" not in merchants

    # Search merchant
    search_res = await client.get("/api/v1/data/receipts?search=Starbucks")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["merchant_name"] == "Starbucks Coffee"
    assert search_data["items"][0]["line_item_count"] == 2
    assert search_data["items"][0]["direction"] == "expense"


@pytest.mark.asyncio
async def test_receipt_detail_with_line_items_and_missing_number(client: AsyncClient, seed_m16_3_data):
    rec_expense = seed_m16_3_data["rec_expense"]
    rec_income = seed_m16_3_data["rec_income"]

    # Detail for expense receipt
    res = await client.get(f"/api/v1/data/receipts/{rec_expense.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["merchant_name"] == "Starbucks Coffee"
    assert data["direction"] == "expense"
    assert len(data["line_items"]) == 2
    assert data["line_items"][0]["description"] == "Caramel Macchiato"
    assert data["batch"]["source_filename"] == "Receipt_Beta.jpg"

    # Detail for income receipt with empty receipt_number
    res_inc = await client.get(f"/api/v1/data/receipts/{rec_income.id}")
    assert res_inc.status_code == 200
    data_inc = res_inc.json()
    assert data_inc["merchant_name"] == "Register Inflow"
    assert data_inc["receipt_number"] == ""
    assert data_inc["direction"] == "income"


@pytest.mark.asyncio
async def test_receipts_filtering_and_sorting(client: AsyncClient, seed_m16_3_data):
    # Direction filter
    exp_res = await client.get("/api/v1/data/receipts?direction=expense")
    assert exp_res.status_code == 200
    assert exp_res.json()["total"] == 1
    assert exp_res.json()["items"][0]["merchant_name"] == "Starbucks Coffee"

    inc_res = await client.get("/api/v1/data/receipts?direction=income")
    assert inc_res.status_code == 200
    assert inc_res.json()["total"] == 1
    assert inc_res.json()["items"][0]["merchant_name"] == "Register Inflow"

    # Date filter
    date_res = await client.get("/api/v1/data/receipts?date_from=2026-09-17")
    assert date_res.status_code == 200
    assert date_res.json()["total"] == 1
    assert date_res.json()["items"][0]["merchant_name"] == "Register Inflow"

    # Amount range filter
    amt_res = await client.get("/api/v1/data/receipts?amount_min=50.00")
    assert amt_res.status_code == 200
    assert amt_res.json()["total"] == 1
    assert amt_res.json()["items"][0]["merchant_name"] == "Register Inflow"

    # Sorting by total_amount asc
    sort_res = await client.get("/api/v1/data/receipts?sort_by=total_amount&sort_order=asc")
    assert sort_res.status_code == 200
    items = sort_res.json()["items"]
    assert float(items[0]["total_amount"]) < float(items[1]["total_amount"])


# ── 2. Invoice Direction Filtering Tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_invoice_direction_filter(client: AsyncClient, seed_m16_3_data):
    # List invoices with direction filter
    sales_res = await client.get("/api/v1/data/invoices?direction=sales")
    assert sales_res.status_code == 200
    sales_items = sales_res.json()["items"]
    assert len(sales_items) == 1
    assert sales_items[0]["company_name"] == "Acme Corp"
    assert sales_items[0]["direction"] == "sales"
    assert sales_items[0]["source_file_id"] is not None

    purch_res = await client.get("/api/v1/data/invoices?direction=purchase")
    assert purch_res.status_code == 200
    purch_items = purch_res.json()["items"]
    assert len(purch_items) == 1
    assert purch_items[0]["company_name"] == "Beta Logistics"
    assert purch_items[0]["direction"] == "purchase"

    # Invoice detail includes direction
    inv_id = sales_items[0]["id"]
    detail_res = await client.get(f"/api/v1/data/invoices/{inv_id}")
    assert detail_res.status_code == 200
    assert detail_res.json()["direction"] == "sales"


# ── 3. Unified Financial Documents Register Tests ───────────────────────────────


@pytest.mark.asyncio
async def test_unified_documents_listing(client: AsyncClient, seed_m16_3_data):
    # Default list combines invoices and receipts
    res = await client.get("/api/v1/data/documents")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4  # 2 active invoices + 2 active receipts (deleted excluded)
    types = [doc["document_type"] for doc in data["items"]]
    assert "invoice" in types
    assert "receipt" in types

    # Filter document_type=invoice
    inv_res = await client.get("/api/v1/data/documents?document_type=invoice")
    assert inv_res.status_code == 200
    inv_data = inv_res.json()
    assert inv_data["total"] == 2
    assert all(d["document_type"] == "invoice" for d in inv_data["items"])

    # Filter document_type=receipt
    rec_res = await client.get("/api/v1/data/documents?document_type=receipt")
    assert rec_res.status_code == 200
    rec_data = rec_res.json()
    assert rec_data["total"] == 2
    assert all(d["document_type"] == "receipt" for d in rec_data["items"])

    # Filter direction=expense
    dir_res = await client.get("/api/v1/data/documents?direction=expense")
    assert dir_res.status_code == 200
    assert dir_res.json()["total"] == 1
    assert dir_res.json()["items"][0]["counterparty"] == "Starbucks Coffee"

    # Search across counterparty
    search_res = await client.get("/api/v1/data/documents?search=Beta")
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total"] == 1
    assert search_data["items"][0]["counterparty"] == "Beta Logistics"


# ── 4. Cross-Tenant Security Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client: AsyncClient, seed_m16_3_data):
    rec_expense = seed_m16_3_data["rec_expense"]

    # Create tenant 2 user
    with TestingSessionLocal() as seed:
        org2 = Organization(id=2, name="Tenant Two Workspace", slug="tenant-two")
        seed.add(org2)
        seed.flush()
        user2 = User(
            email="tenant2@example.test",
            display_name="Tenant 2 User",
            password_hash=password_hasher.hash("tenant2-password"),
        )
        seed.add(user2)
        seed.flush()
        seed.add(OrganizationMembership(user_id=user2.id, organization_id=2, role="OWNER"))
        seed.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        # Login as tenant 2
        login_res = await client2.post(
            "/api/v1/auth/login",
            json={"email": "tenant2@example.test", "password": "tenant2-password"},
        )
        assert login_res.status_code == 200
        client2.headers["x-csrf-token"] = login_res.json()["csrf_token"]

        # Attempt to access Tenant 1 receipt detail -> 404
        t2_rec = await client2.get(f"/api/v1/data/receipts/{rec_expense.id}")
        assert t2_rec.status_code == 404

        # Listing receipts as Tenant 2 -> empty
        t2_list = await client2.get("/api/v1/data/receipts")
        assert t2_list.status_code == 200
        assert t2_list.json()["total"] == 0

        # Listing unified documents as Tenant 2 -> empty
        t2_docs = await client2.get("/api/v1/data/documents")
        assert t2_docs.status_code == 200
        assert t2_docs.json()["total"] == 0


# ── 5. Export Tests with Formula Injection Protection ──────────────────────────


@pytest.mark.asyncio
async def test_export_summary_and_receipts_export(client: AsyncClient, seed_m16_3_data):
    # Summary for receipts
    summary_rec = await client.get("/api/v1/exports/summary?dataset=receipts")
    assert summary_rec.status_code == 200
    s_data = summary_rec.json()
    assert s_data["dataset"] == "receipts"
    assert s_data["total_records"] == 2
    assert "Merchant Name" in s_data["columns"]
    assert "Direction" in s_data["columns"]

    # Summary for unified documents
    summary_doc = await client.get("/api/v1/exports/summary?dataset=documents")
    assert summary_doc.status_code == 200
    d_data = summary_doc.json()
    assert d_data["dataset"] == "documents"
    assert d_data["total_records"] == 4
    assert "Document Type" in d_data["columns"]

    # Receipts CSV download
    csv_res = await client.get("/api/v1/exports/receipts.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    csv_content = csv_res.text
    assert "Starbucks Coffee" in csv_content
    assert "Register Inflow" in csv_content
    assert "REC-SB-101" in csv_content

    # Receipts XLSX download
    xlsx_res = await client.get("/api/v1/exports/receipts.xlsx")
    assert xlsx_res.status_code == 200
    assert len(xlsx_res.content) > 1000

    # Unified documents CSV download
    doc_csv_res = await client.get("/api/v1/exports/documents.csv")
    assert doc_csv_res.status_code == 200
    doc_content = doc_csv_res.text
    assert "Invoice" in doc_content
    assert "Receipt" in doc_content
    assert "Acme Corp" in doc_content
    assert "Starbucks Coffee" in doc_content

    # Invoices CSV includes Direction column
    inv_csv_res = await client.get("/api/v1/exports/invoices.csv")
    assert inv_csv_res.status_code == 200
    inv_content = inv_csv_res.text
    assert "Direction" in inv_content
    assert "sales" in inv_content
    assert "purchase" in inv_content
