"""Integration tests for Milestone 16.2: Financial Direction and Receipt History Visibility."""
import io
from pathlib import Path
from PIL import Image
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.orm import Session

from app.main import app
from app.models.identity import Organization, OrganizationMembership, User
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.security import password_hasher
from tests.conftest import TestingSessionLocal


def _create_test_image_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="white")
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_invoice_confirmation_with_sales_and_purchase_direction(client: AsyncClient, db_session: Session):
    image_bytes = _create_test_image_bytes()

    # 1. Upload for Sales Invoice
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("invoice_sales.jpg", image_bytes, "image/jpeg")},
    )
    assert upload_res.status_code == 201
    doc_id_sales = upload_res.json()["document_id"]

    # Confirm with direction="sales"
    confirm_sales = await client.post(
        f"/api/v1/documents/{doc_id_sales}/confirm",
        json={
            "document_type": "invoice",
            "company_name": "Customer Corp",
            "invoice_number": "INV-SALES-001",
            "direction": "sales",
            "total_amount": "1500.00",
            "currency": "USD",
            "line_items": [
                {"description": "Consulting Services", "amount": "1500.00", "quantity": "1"}
            ],
        },
    )
    assert confirm_sales.status_code == 200
    batch_sales_id = confirm_sales.json()["batch_id"]

    # Verify persisted record
    inv_sales = db_session.query(InvoiceRecord).filter_by(invoice_number="INV-SALES-001").first()
    assert inv_sales is not None
    assert inv_sales.direction == "sales"

    # 2. Upload for Purchase Invoice
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("invoice_purch.jpg", image_bytes, "image/jpeg")},
    )
    assert upload_res.status_code == 201
    doc_id_purch = upload_res.json()["document_id"]

    # Confirm with direction="purchase"
    confirm_purch = await client.post(
        f"/api/v1/documents/{doc_id_purch}/confirm",
        json={
            "document_type": "invoice",
            "company_name": "Supplier Inc",
            "invoice_number": "INV-PURCH-001",
            "direction": "purchase",
            "total_amount": "800.00",
            "currency": "USD",
        },
    )
    assert confirm_purch.status_code == 200
    batch_purch_id = confirm_purch.json()["batch_id"]

    inv_purch = db_session.query(InvoiceRecord).filter_by(invoice_number="INV-PURCH-001").first()
    assert inv_purch is not None
    assert inv_purch.direction == "purchase"

    # Verify History detail response for invoices
    detail_res = await client.get(f"/api/v1/imports/{batch_sales_id}")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert len(detail_data["invoice_records"]) == 1
    assert detail_data["invoice_records"][0]["direction"] == "sales"
    assert len(detail_data["receipt_records"]) == 0


@pytest.mark.asyncio
async def test_receipt_confirmation_with_expense_and_income_direction(client: AsyncClient, db_session: Session):
    image_bytes = _create_test_image_bytes()

    # 1. Receipt with Expense direction
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt_exp.jpg", image_bytes, "image/jpeg")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]

    confirm_res = await client.post(
        f"/api/v1/documents/{doc_id}/confirm",
        json={
            "document_type": "receipt",
            "merchant_name": "Office Depot",
            "receipt_number": "REC-EXP-101",
            "direction": "expense",
            "total_amount": "45.50",
            "currency": "USD",
            "payment_method": "Credit Card",
            "line_items": [
                {"description": "Paper & Pens", "quantity": "2", "amount": "45.50"}
            ],
        },
    )
    assert confirm_res.status_code == 200
    batch_id = confirm_res.json()["batch_id"]

    rec = db_session.query(ReceiptRecord).filter_by(receipt_number="REC-EXP-101").first()
    assert rec is not None
    assert rec.direction == "expense"
    assert rec.merchant_name == "Office Depot"

    # 2. Verify Receipt Batch in History Details
    detail_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    assert len(detail["receipt_records"]) == 1
    receipt_data = detail["receipt_records"][0]
    assert receipt_data["merchant_name"] == "Office Depot"
    assert receipt_data["receipt_number"] == "REC-EXP-101"
    assert receipt_data["direction"] == "expense"
    assert receipt_data["currency"] == "USD"
    assert str(receipt_data["total_amount"]) == "45.50"
    assert receipt_data["payment_method"] == "Credit Card"
    assert len(receipt_data["line_items"]) == 1
    assert receipt_data["line_items"][0]["description"] == "Paper & Pens"
    assert len(detail["invoice_records"]) == 0

    # 3. Receipt with Income direction
    upload_res2 = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt_inc.jpg", image_bytes, "image/jpeg")},
    )
    doc_id2 = upload_res2.json()["document_id"]

    confirm_res2 = await client.post(
        f"/api/v1/documents/{doc_id2}/confirm",
        json={
            "document_type": "receipt",
            "merchant_name": "Client Cash Deposit",
            "receipt_number": "REC-INC-202",
            "direction": "income",
            "total_amount": "200.00",
            "currency": "USD",
        },
    )
    assert confirm_res2.status_code == 200
    batch_id2 = confirm_res2.json()["batch_id"]

    rec2 = db_session.query(ReceiptRecord).filter_by(receipt_number="REC-INC-202").first()
    assert rec2 is not None
    assert rec2.direction == "income"


@pytest.mark.asyncio
async def test_receipt_confirmation_without_direction_and_no_printed_number(client: AsyncClient, db_session: Session):
    image_bytes = _create_test_image_bytes()

    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt_simple.jpg", image_bytes, "image/jpeg")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]

    # Confirm without direction and without receipt_number
    confirm_res = await client.post(
        f"/api/v1/documents/{doc_id}/confirm",
        json={
            "document_type": "receipt",
            "merchant_name": "Corner Bakery",
            "receipt_number": None,
            "total_amount": "12.75",
            "currency": "MYR",
        },
    )
    assert confirm_res.status_code == 200
    batch_id = confirm_res.json()["batch_id"]

    # Verify defaults
    detail_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()

    assert len(detail["receipt_records"]) == 1
    receipt_data = detail["receipt_records"][0]
    assert receipt_data["merchant_name"] == "Corner Bakery"
    assert receipt_data["direction"] == "unclassified"
    # Receipt number is empty string or None, not an error or fabricated number
    assert receipt_data["receipt_number"] in ("", None)


@pytest.mark.asyncio
async def test_receipt_cross_tenant_isolation(client: AsyncClient, db_session: Session):
    # 1. Create a receipt under Organization 1 (client is logged in as Org 1)
    image_bytes = _create_test_image_bytes()
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("org1_receipt.jpg", image_bytes, "image/jpeg")},
    )
    doc_id = upload_res.json()["document_id"]
    confirm_res = await client.post(
        f"/api/v1/documents/{doc_id}/confirm",
        json={
            "document_type": "receipt",
            "merchant_name": "Org1 Secret Merchant",
            "receipt_number": "ORG1-REC-001",
            "direction": "expense",
            "total_amount": "99.00",
        },
    )
    batch_id = confirm_res.json()["batch_id"]

    # 2. Create Organization 2 and User 2
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

    # 3. Create Client 2 and attempt to fetch Org 1's batch
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client2:
        login_res = await client2.post(
            "/api/v1/auth/login",
            json={"email": "tenant2@example.test", "password": "tenant2-password"},
        )
        assert login_res.status_code == 200
        client2.headers["x-csrf-token"] = login_res.json()["csrf_token"]

        # Fetching Org 1's batch must return 404
        get_res = await client2.get(f"/api/v1/imports/{batch_id}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_receipt_soft_delete_behavior(client: AsyncClient, db_session: Session):
    image_bytes = _create_test_image_bytes()
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("to_delete.jpg", image_bytes, "image/jpeg")},
    )
    doc_id = upload_res.json()["document_id"]
    confirm_res = await client.post(
        f"/api/v1/documents/{doc_id}/confirm",
        json={
            "document_type": "receipt",
            "merchant_name": "Coffee Shop",
            "receipt_number": "COFFEE-999",
            "total_amount": "5.50",
        },
    )
    batch_id = confirm_res.json()["batch_id"]

    # Soft-delete the batch
    del_res = await client.delete(f"/api/v1/imports/{batch_id}")
    assert del_res.status_code == 204

    # Subsequent GET returns 404
    get_res = await client.get(f"/api/v1/imports/{batch_id}")
    assert get_res.status_code == 404

    # The batch is marked is_deleted=True in database
    batch = db_session.query(ImportBatch).filter_by(id=batch_id).first()
    assert batch.is_deleted is True


@pytest.mark.asyncio
async def test_dashboard_analytics_regression(client: AsyncClient):
    # Verify analytics dashboard continues to function properly
    dash_res = await client.get("/api/v1/analytics/dashboard")
    assert dash_res.status_code == 200
    data = dash_res.json()
    assert "summary" in data
    assert "invoice_value_over_time" in data
