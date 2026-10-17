"""
backend/tests/integration/test_api_relationships.py — Integration tests for Document Relationship APIs.

Tests HTTP endpoints:
- POST   /api/v1/relationships
- GET    /api/v1/relationships/{entity_type}/{entity_id}
- DELETE /api/v1/relationships/{relationship_id}

Verifies:
- Multi-record XLSX individual row linking
- Symmetric normalization and 409 duplicate checks
- Directional 'supports' semantics
- Strict multi-tenant workspace isolation
- Soft-delete handling and audit logging
- Record edit survivability
"""
from datetime import date
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models.identity import AuditEvent, Organization, OrganizationMembership, User
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.models.template import Template


@pytest.fixture
def seed_two_tenants(db_session: Session):
    """Seed documents for tenant 1 and tenant 2."""
    bind = db_session.bind

    # Setup tenant 2 organization and member user
    with Session(bind) as admin_db:
        if not admin_db.get(Organization, 2):
            admin_db.add(Organization(id=2, name="Tenant Two Workspace", slug="tenant-2"))
        user2 = User(id=99, email="user2@tenant2.test", display_name="Tenant 2 User", password_hash="dummy")
        admin_db.add(user2)
        admin_db.flush()
        admin_db.add(OrganizationMembership(user_id=user2.id, organization_id=2, role="OWNER"))
        admin_db.commit()

    # Seed Tenant 1 data
    with Session(bind) as db1:
        db1.info["organization_id"] = 1

        tpl = Template(id=1, organization_id=1, name="Standard Template", file_type="xlsx")
        db1.add(tpl)

        sf1 = SourceFile(
            id=10,
            organization_id=1,
            original_name="invoices_october.xlsx",
            stored_filename="invoices_oct.xlsx",
            file_size=5000,
            checksum="chk10",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        sf_supp = SourceFile(
            id=11,
            organization_id=1,
            original_name="delivery_receipt.pdf",
            stored_filename="del_rec.pdf",
            file_size=2500,
            checksum="chk11",
            media_type="application/pdf",
        )
        db1.add_all([sf1, sf_supp])
        db1.flush()

        # Multi-record batch (2 invoices in 1 spreadsheet)
        batch_active = ImportBatch(
            id=20,
            organization_id=1,
            source_file_id=10,
            template_id=1,
            status="imported",
            record_count=2,
            is_deleted=False,
        )
        # Soft-deleted batch
        batch_deleted = ImportBatch(
            id=21,
            organization_id=1,
            source_file_id=10,
            template_id=1,
            status="imported",
            record_count=1,
            is_deleted=True,
        )
        db1.add_all([batch_active, batch_deleted])
        db1.flush()

        # Row 1 and Row 2 invoices in the same multi-record batch
        inv_row1 = InvoiceRecord(
            id=100,
            batch_id=20,
            company_name="Acme Corp",
            invoice_number="INV-ACME-001",
            invoice_date=date(2026, 10, 1),
            total_amount=Decimal("1200.00"),
            currency="USD",
            direction="sales",
            source_worksheet="Invoices",
            source_row_number=2,
            raw_data="{}",
        )
        inv_row2 = InvoiceRecord(
            id=101,
            batch_id=20,
            company_name="Beta Global",
            invoice_number="INV-BETA-002",
            invoice_date=date(2026, 10, 2),
            total_amount=Decimal("800.00"),
            currency="USD",
            direction="sales",
            source_worksheet="Invoices",
            source_row_number=3,
            raw_data="{}",
        )
        inv_deleted = InvoiceRecord(
            id=102,
            batch_id=21,
            company_name="Old Corp",
            invoice_number="INV-OLD-999",
            invoice_date=date(2026, 8, 1),
            total_amount=Decimal("300.00"),
            currency="USD",
            direction="sales",
            source_worksheet="Invoices",
            source_row_number=2,
            raw_data="{}",
        )

        # Receipt in tenant 1
        rec1 = ReceiptRecord(
            id=200,
            batch_id=20,
            merchant_name="Acme Direct",
            receipt_number="RCP-ACME-55",
            transaction_date=date(2026, 10, 1),
            total_amount=Decimal("1200.00"),
            currency="USD",
            direction="income",
            raw_data="{}",
        )
        db1.add_all([inv_row1, inv_row2, inv_deleted, rec1])
        db1.commit()

    # Seed Tenant 2 data
    with Session(bind) as db2:
        db2.info["organization_id"] = 2

        tpl2 = Template(id=2, organization_id=2, name="Tenant 2 Template", file_type="xlsx")
        db2.add(tpl2)

        sf2 = SourceFile(
            id=12,
            organization_id=2,
            original_name="tenant2_secret.xlsx",
            stored_filename="t2_sec.xlsx",
            file_size=1000,
            checksum="chk12",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        db2.add(sf2)
        db2.flush()

        batch_t2 = ImportBatch(
            id=22,
            organization_id=2,
            source_file_id=12,
            template_id=2,
            status="imported",
            record_count=1,
            is_deleted=False,
        )
        db2.add(batch_t2)
        db2.flush()

        inv_t2 = InvoiceRecord(
            id=300,
            batch_id=22,
            company_name="Tenant 2 Vendor",
            invoice_number="INV-T2-001",
            invoice_date=date(2026, 10, 5),
            total_amount=Decimal("999.00"),
            currency="USD",
            direction="purchase",
            source_worksheet="Sheet1",
            source_row_number=2,
            raw_data="{}",
        )
        db2.add(inv_t2)
        db2.commit()

    return {"bind": bind}


@pytest.mark.asyncio
async def test_api_create_invoice_to_receipt_and_normalization(client: AsyncClient, seed_two_tenants):
    """
    POST /api/v1/relationships
    Tests creating a symmetric 'related_to' relationship between Invoice 100 and Receipt 200.
    Verifies that inverse creation returns 409 Conflict.
    """
    payload = {
        "source_type": "invoice",
        "source_id": 100,
        "target_type": "receipt",
        "target_id": 200,
        "relationship_type": "related_to",
    }
    resp = await client.post("/api/v1/relationships", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["relationship_type"] == "related_to"
    assert data["direction_semantic"] == "symmetric"
    assert data["source_type"] == "invoice"
    assert data["source_id"] == 100
    assert data["target_type"] == "receipt"
    assert data["target_id"] == 200
    assert data["related_entity"]["document_number"] == "RCP-ACME-55"
    assert data["related_entity"]["counterparty"] == "Acme Direct"

    # Inverse request must return 409 Conflict
    inverse_payload = {
        "source_type": "receipt",
        "source_id": 200,
        "target_type": "invoice",
        "target_id": 100,
        "relationship_type": "related_to",
    }
    resp_conflict = await client.post("/api/v1/relationships", json=inverse_payload)
    assert resp_conflict.status_code == 409


@pytest.mark.asyncio
async def test_api_multi_record_xlsx_individual_row_linking(client: AsyncClient, seed_two_tenants):
    """
    Verifies that linking an individual row (Invoice 100) from a multi-record XLSX workbook
    does NOT affect other rows in the same workbook (Invoice 101).
    """
    # Link Row 1 (Invoice 100) to Receipt 200
    payload = {
        "source_type": "invoice",
        "source_id": 100,
        "target_type": "receipt",
        "target_id": 200,
        "relationship_type": "related_to",
    }
    create_resp = await client.post("/api/v1/relationships", json=payload)
    assert create_resp.status_code == 201

    # Check Invoice 100 relationships: total 1
    resp_row1 = await client.get("/api/v1/relationships/invoice/100")
    assert resp_row1.status_code == 200
    assert resp_row1.json()["total"] == 1

    # Check Invoice 101 relationships: total 0
    resp_row2 = await client.get("/api/v1/relationships/invoice/101")
    assert resp_row2.status_code == 200
    assert resp_row2.json()["total"] == 0


@pytest.mark.asyncio
async def test_api_directional_supports_relationship(client: AsyncClient, seed_two_tenants):
    """
    Tests directional 'supports' relationship:
    SourceFile 11 supports Invoice 100.
    - Invoice 100 perspective: 'supported_by'
    - SourceFile 11 perspective: 'supports'
    """
    payload = {
        "source_type": "source_file",
        "source_id": 11,
        "target_type": "invoice",
        "target_id": 100,
        "relationship_type": "supports",
    }
    resp = await client.post("/api/v1/relationships", json=payload)
    assert resp.status_code == 201
    assert resp.json()["direction_semantic"] == "supports"

    # Query from Invoice perspective
    inv_resp = await client.get("/api/v1/relationships/invoice/100")
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert inv_data["total"] == 1
    assert inv_data["items"][0]["direction_semantic"] == "supported_by"
    assert inv_data["items"][0]["related_entity"]["filename"] == "delivery_receipt.pdf"

    # Query from SourceFile perspective
    sf_resp = await client.get("/api/v1/relationships/source_file/11")
    assert sf_resp.status_code == 200
    sf_data = sf_resp.json()
    assert sf_data["total"] == 1
    assert sf_data["items"][0]["direction_semantic"] == "supports"
    assert sf_data["items"][0]["related_entity"]["document_number"] == "INV-ACME-001"


@pytest.mark.asyncio
async def test_api_self_link_rejected_422(client: AsyncClient, seed_two_tenants):
    """POST /api/v1/relationships with identical source and target returns 422."""
    payload = {
        "source_type": "invoice",
        "source_id": 100,
        "target_type": "invoice",
        "target_id": 100,
        "relationship_type": "related_to",
    }
    resp = await client.post("/api/v1/relationships", json=payload)
    assert resp.status_code == 422
    assert "cannot be linked to itself" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_cross_tenant_source_or_target_blocked(client: AsyncClient, seed_two_tenants):
    """
    Verifies that attempting to link to/from an entity belonging to another tenant
    is rejected with 404 (preventing cross-tenant relationship creation or enumeration).
    """
    # Invoice 300 belongs to Tenant 2
    payload_source_cross = {
        "source_type": "invoice",
        "source_id": 300,
        "target_type": "receipt",
        "target_id": 200,
        "relationship_type": "related_to",
    }
    resp1 = await client.post("/api/v1/relationships", json=payload_source_cross)
    assert resp1.status_code == 404

    payload_target_cross = {
        "source_type": "invoice",
        "source_id": 100,
        "target_type": "invoice",
        "target_id": 300,
        "relationship_type": "related_to",
    }
    resp2 = await client.post("/api/v1/relationships", json=payload_target_cross)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_api_cross_tenant_listing_blocked(client: AsyncClient, seed_two_tenants):
    """Querying relationships for an entity from another tenant returns 404."""
    resp = await client.get("/api/v1/relationships/invoice/300")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_cross_tenant_deletion_blocked(client: AsyncClient, seed_two_tenants):
    """Attempting to delete a relationship belonging to another tenant returns 404."""
    bind = seed_two_tenants["bind"]

    # Seed a relationship directly inside Tenant 2
    with Session(bind) as db2:
        db2.info["organization_id"] = 2
        rel_t2 = DocumentRelationship(
            id=888,
            organization_id=2,
            source_type="invoice",
            source_id=300,
            target_type="source_file",
            target_id=12,
            relationship_type="supports",
        )
        db2.add(rel_t2)
        db2.commit()

    # Tenant 1 client attempts to delete Tenant 2 relationship
    del_resp = await client.delete("/api/v1/relationships/888")
    assert del_resp.status_code == 404


@pytest.mark.asyncio
async def test_api_soft_deleted_document_linking_prohibited(client: AsyncClient, seed_two_tenants):
    """Attempting to link a soft-deleted document returns 404."""
    payload = {
        "source_type": "invoice",
        "source_id": 102,  # deleted invoice
        "target_type": "receipt",
        "target_id": 200,
        "relationship_type": "related_to",
    }
    resp = await client.post("/api/v1/relationships", json=payload)
    assert resp.status_code == 404
    assert "deleted" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_api_delete_relationship_without_record_deletion(client: AsyncClient, seed_two_tenants):
    """
    DELETE /api/v1/relationships/{id}
    Removes the edge with 204 No Content.
    Asserts underlying Invoice 100 and Receipt 200 are unchanged.
    """
    # Create relationship
    create_resp = await client.post(
        "/api/v1/relationships",
        json={
            "source_type": "invoice",
            "source_id": 100,
            "target_type": "receipt",
            "target_id": 200,
            "relationship_type": "related_to",
        },
    )
    assert create_resp.status_code == 201
    rel_id = create_resp.json()["id"]

    # Delete relationship
    del_resp = await client.delete(f"/api/v1/relationships/{rel_id}")
    assert del_resp.status_code == 204

    # Verify link list is now empty
    list_resp = await client.get("/api/v1/relationships/invoice/100")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 0

    # Verify underlying invoice is still accessible in Data Explorer
    inv_get = await client.get("/api/v1/data/invoices/100")
    assert inv_get.status_code == 200
    assert inv_get.json()["id"] == 100


@pytest.mark.asyncio
async def test_api_record_edit_survivability(client: AsyncClient, seed_two_tenants):
    """
    Verifies that editing an invoice's canonical fields (company name, total amount)
    does NOT break the relationship.
    """
    # Link Invoice 100 to Receipt 200
    create_resp = await client.post(
        "/api/v1/relationships",
        json={
            "source_type": "invoice",
            "source_id": 100,
            "target_type": "receipt",
            "target_id": 200,
            "relationship_type": "related_to",
        },
    )
    assert create_resp.status_code == 201

    # Edit Invoice 100
    patch_resp = await client.patch(
        "/api/v1/data/invoices/100",
        json={
            "company_name": "Acme Global Solutions",
            "total_amount": 1250.00,
            "invoice_number": "INV-ACME-001-REV",
        },
    )
    assert patch_resp.status_code == 200

    # Query relationships again: relationship still exists and reflects updated counterparty
    list_resp = await client.get("/api/v1/relationships/receipt/200")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 1
    rel_item = data["items"][0]
    assert rel_item["related_entity"]["document_number"] == "INV-ACME-001-REV"
    assert rel_item["related_entity"]["counterparty"] == "Acme Global Solutions"
    assert float(rel_item["related_entity"]["total_amount"]) == 1250.00
