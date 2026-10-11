"""Integration tests for Milestone 16.4.2:
- Queue Lifecycle Semantics & Batch Review
- Receipt Financial Direction Editing (PATCH /api/v1/data/receipts/{id})
- Audit logging & Cross-tenant security
- Dashboard Empty-State Clarity & Currency Filters
"""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.identity import AuditEvent
from app.models.invoice import (
    ImportBatch, InvoiceLineItem, InvoiceRecord, ReceiptLineItem, ReceiptRecord,
)
from app.models.source_file import SourceFile
from app.models.template import Template
from tests.integration.test_saas import register


@pytest.fixture
def test_setup(db_session: Session):
    source = SourceFile(
        organization_id=1,
        original_name="m16_4_2_test.xlsx",
        stored_filename="m16_4_2_test.xlsx",
        file_size=1024,
        checksum="a" * 64,
    )
    template = Template(organization_id=1, name="M16.4.2 Template", template_type="dataset")
    db_session.add_all([source, template])
    db_session.flush()

    def make_receipt(
        merchant="Test Merchant",
        direction="unclassified",
        currency="MYR",
        total="45.50",
        day="2026-10-01",
        deleted=False,
    ):
        batch = ImportBatch(
            organization_id=1,
            source_file_id=source.id,
            template_id=template.id,
            status="imported",
            is_deleted=deleted,
        )
        receipt = ReceiptRecord(
            merchant_name=merchant,
            receipt_number="RCPT-001",
            transaction_date=date.fromisoformat(day) if day else None,
            total_amount=Decimal(total) if total is not None else None,
            subtotal=Decimal(total) if total is not None else None,
            tax_amount=Decimal("0.00"),
            currency=currency,
            direction=direction,
            payment_method="Cash",
            raw_data='{"test": true}',
        )
        batch.receipt_records.append(receipt)
        receipt.line_items.append(ReceiptLineItem(
            source_row_number=1,
            description="Item 1",
            amount=Decimal(total) if total is not None else None,
        ))
        db_session.add(batch)
        db_session.commit()
        return receipt

    def make_invoice(
        company="Test Supplier",
        direction="purchase",
        currency="MYR",
        total="150.00",
        day="2026-10-02",
        deleted=False,
    ):
        batch = ImportBatch(
            organization_id=1,
            source_file_id=source.id,
            template_id=template.id,
            status="imported",
            is_deleted=deleted,
        )
        invoice = InvoiceRecord(
            company_name=company,
            invoice_number="INV-001",
            invoice_date=date.fromisoformat(day) if day else None,
            total_amount=Decimal(total) if total is not None else None,
            currency=currency,
            direction=direction,
            source_worksheet="Sheet1",
            raw_data='{}',
        )
        batch.invoice_records.append(invoice)
        db_session.add(batch)
        db_session.commit()
        return invoice

    return {
        "source": source,
        "template": template,
        "make_receipt": make_receipt,
        "make_invoice": make_invoice,
    }


# ── 1. Receipt Direction PATCH Endpoint Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_patch_receipt_direction_to_expense(client: AsyncClient, db_session: Session, test_setup):
    rcpt = test_setup["make_receipt"](direction="unclassified")

    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == rcpt.id
    assert data["direction"] == "expense"
    assert data["merchant_name"] == "Test Merchant"
    assert len(data["line_items"]) == 1

    # Verify DB persistence
    db_session.expire_all()
    reloaded = db_session.get(ReceiptRecord, rcpt.id)
    assert reloaded.direction == "expense"


@pytest.mark.asyncio
async def test_patch_receipt_direction_to_income(client: AsyncClient, db_session: Session, test_setup):
    rcpt = test_setup["make_receipt"](direction="expense")

    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "income"},
    )
    assert resp.status_code == 200
    assert resp.json()["direction"] == "income"

    db_session.expire_all()
    reloaded = db_session.get(ReceiptRecord, rcpt.id)
    assert reloaded.direction == "income"


@pytest.mark.asyncio
async def test_patch_receipt_direction_to_unclassified(client: AsyncClient, db_session: Session, test_setup):
    rcpt = test_setup["make_receipt"](direction="income")

    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "unclassified"},
    )
    assert resp.status_code == 200
    assert resp.json()["direction"] == "unclassified"


@pytest.mark.asyncio
async def test_patch_receipt_direction_validation_rejections(client: AsyncClient, test_setup):
    rcpt = test_setup["make_receipt"](direction="unclassified")

    # Invalid direction (e.g. 'sales' is for invoices, not receipts)
    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "sales"},
    )
    assert resp.status_code == 422

    # Arbitrary random string
    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "unknown_value"},
    )
    assert resp.status_code == 422

    # Mass assignment rejection (extra='forbid')
    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense", "unsupported_field": "9999.00"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_receipt_direction_audit_log(client: AsyncClient, db_session: Session, test_setup):
    rcpt = test_setup["make_receipt"](direction="unclassified")

    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense"},
    )
    assert resp.status_code == 200

    # Verify audit entry was written
    logs = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "RECEIPT_DIRECTION_UPDATED", AuditEvent.entity_id == rcpt.id)
        .all()
    )
    assert len(logs) >= 1
    assert logs[0].entity_type == "receipt_records"


@pytest.mark.asyncio
async def test_patch_receipt_soft_deleted_blocked(client: AsyncClient, test_setup):
    rcpt = test_setup["make_receipt"](deleted=True)

    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_receipt_cross_tenant_blocked(client: AsyncClient, test_setup):
    # Org A (org 1) has receipt
    rcpt = test_setup["make_receipt"](direction="unclassified")

    # Org B attempts to patch Org A's receipt
    await register(client, email="org_b_user@example.com", workspace="Org B")
    resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense"},
    )
    assert resp.status_code == 404


# ── 2. Dashboard Analytics & Empty-State Clarity Tests ─────────────────────────


@pytest.mark.asyncio
async def test_dashboard_empty_workspace_counts(client: AsyncClient):
    # Fresh empty workspace
    await register(client, email="empty_ws@example.com", workspace="Empty Workspace")
    resp = await client.get("/api/v1/analytics/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    # Empty workspace has zero total invoices and receipts
    assert data["financial_summary"]["total_workspace_invoices"] == 0
    assert data["financial_summary"]["total_workspace_receipts"] == 0
    assert data["financial_summary"]["receipt_count"] == 0
    assert data["summary"]["invoice_count"] == 0


@pytest.mark.asyncio
async def test_dashboard_currency_filter_with_different_currency_receipts(client: AsyncClient, test_setup):
    """When receipts exist only in USD/SGD, querying with currency=MYR returns counts=0, but total_workspace_receipts > 0."""
    test_setup["make_receipt"](currency="USD", direction="expense", total="50.00")
    test_setup["make_receipt"](currency="SGD", direction="income", total="80.00")
    test_setup["make_invoice"](currency="MYR", direction="sales", total="200.00")

    # Filter with MYR
    resp = await client.get("/api/v1/analytics/dashboard?currency=MYR")
    assert resp.status_code == 200
    data = resp.json()

    summary = data["financial_summary"]
    # Total workspace receipts exist!
    assert summary["total_workspace_receipts"] == 2
    # But matching receipts in MYR is 0!
    assert summary["receipt_count"] == 0
    assert summary["income_receipt_count"] == 0
    assert summary["expense_receipt_count"] == 0
    assert summary["income_receipts_value"] is None
    assert summary["expense_receipts_value"] is None

    # Invoices match MYR
    assert summary["sales_invoice_count"] == 1
    assert summary["sales_invoiced_value"] == "200.00"


@pytest.mark.asyncio
async def test_dashboard_missing_amount_vs_zero_count(client: AsyncClient, test_setup):
    """Distinguishes between count=0 (no matching records) and count>0 with amount=None (amount unavailable)."""
    test_setup["make_receipt"](currency="MYR", direction="expense", total=None)

    resp = await client.get("/api/v1/analytics/dashboard?currency=MYR")
    assert resp.status_code == 200
    data = resp.json()

    summary = data["financial_summary"]
    assert summary["expense_receipt_count"] == 1
    assert summary["expense_receipts_with_total"] == 0
    assert summary["expense_receipts_value"] is None


@pytest.mark.asyncio
async def test_dashboard_unspecified_currency(client: AsyncClient, test_setup):
    """When no currency is selected, monetary values are withheld."""
    test_setup["make_receipt"](currency="MYR", direction="expense", total="100.00")

    resp = await client.get("/api/v1/analytics/dashboard")
    assert resp.status_code == 200
    data = resp.json()

    assert data["monetary_values_available"] is False
    assert data["financial_summary"]["sales_invoiced_value"] is None
    assert data["financial_summary"]["expense_receipts_value"] is None


@pytest.mark.asyncio
async def test_dashboard_reflects_receipt_direction_patch(client: AsyncClient, test_setup):
    """Updating a receipt's direction via PATCH immediately updates dashboard aggregates."""
    rcpt = test_setup["make_receipt"](currency="MYR", direction="unclassified", total="120.00")

    # Initial dashboard: 1 unclassified receipt, 0 expense receipts
    resp1 = await client.get("/api/v1/analytics/dashboard?currency=MYR")
    assert resp1.status_code == 200
    assert resp1.json()["financial_summary"]["unclassified_receipt_count"] == 1
    assert resp1.json()["financial_summary"]["expense_receipt_count"] == 0

    # Patch receipt to expense
    patch_resp = await client.patch(
        f"/api/v1/data/receipts/{rcpt.id}",
        json={"direction": "expense"},
    )
    assert patch_resp.status_code == 200

    # Subsequent dashboard: 0 unclassified receipts, 1 expense receipt with 120.00
    resp2 = await client.get("/api/v1/analytics/dashboard?currency=MYR")
    assert resp2.status_code == 200
    summary = resp2.json()["financial_summary"]
    assert summary["unclassified_receipt_count"] == 0
    assert summary["expense_receipt_count"] == 1
    assert summary["expense_receipts_value"] == "120.00"
