"""
backend/tests/unit/test_relationship_service.py — Unit tests for RelationshipService.

Tests service-level validation, canonical normalization, symmetric/directional semantics,
cross-tenant protections, soft-deletion boundaries, and audit logging.
"""
from datetime import date
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.identity import AuditEvent, Organization, User
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.models.template import Template
from app.schemas.relationship import RelationshipCreateRequest
from app.services.relationship_service import (
    create_relationship,
    delete_relationship,
    list_relationships,
    validate_and_resolve_entity,
)


@pytest.fixture
def org_and_docs(db_session: Session):
    """Seed sample data for Organization 1 and Organization 2."""
    bind = db_session.bind

    # Ensure Organizations and Users exist
    with Session(bind) as admin_db:
        if not admin_db.get(Organization, 1):
            admin_db.add(Organization(id=1, name="Workspace One", slug="ws-1"))
        if not admin_db.get(Organization, 2):
            admin_db.add(Organization(id=2, name="Workspace Two", slug="ws-2"))
        if not admin_db.get(User, 1):
            admin_db.add(User(id=1, email="user1@example.test", display_name="User 1", password_hash="hash"))
        admin_db.commit()

    # Seed Org 1 data
    with Session(bind) as db1:
        db1.info["organization_id"] = 1

        tpl = Template(id=10, organization_id=1, name="Standard Invoice", file_type="xlsx")
        db1.add(tpl)

        sf1 = SourceFile(
            id=101,
            organization_id=1,
            original_name="contract_dell.pdf",
            stored_filename="sf-101.pdf",
            file_size=2048,
            checksum="hash101",
            media_type="application/pdf",
        )
        db1.add(sf1)
        db1.flush()

        batch_active = ImportBatch(
            id=201,
            organization_id=1,
            source_file_id=101,
            template_id=10,
            status="imported",
            is_deleted=False,
        )
        batch_deleted = ImportBatch(
            id=202,
            organization_id=1,
            source_file_id=101,
            template_id=10,
            status="imported",
            is_deleted=True,
        )
        db1.add_all([batch_active, batch_deleted])
        db1.flush()

        inv1 = InvoiceRecord(
            id=301,
            batch_id=201,
            company_name="Dell Technologies",
            invoice_number="INV-DELL-01",
            invoice_date=date(2026, 10, 1),
            total_amount=Decimal("1500.00"),
            currency="USD",
            direction="purchase",
            source_worksheet="Sheet1",
            raw_data="{}",
        )
        inv2 = InvoiceRecord(
            id=302,
            batch_id=201,
            company_name="Dell Technologies",
            invoice_number="INV-DELL-02",
            invoice_date=date(2026, 10, 5),
            total_amount=Decimal("750.00"),
            currency="USD",
            direction="purchase",
            source_worksheet="Sheet1",
            raw_data="{}",
        )
        inv_deleted = InvoiceRecord(
            id=303,
            batch_id=202,
            company_name="Voided Supplier",
            invoice_number="INV-VOID-99",
            invoice_date=date(2026, 9, 1),
            total_amount=Decimal("100.00"),
            currency="USD",
            direction="purchase",
            source_worksheet="Sheet1",
            raw_data="{}",
        )
        rec1 = ReceiptRecord(
            id=401,
            batch_id=201,
            merchant_name="Dell Online Store",
            receipt_number="RCP-DELL-88",
            transaction_date=date(2026, 10, 2),
            total_amount=Decimal("1500.00"),
            currency="USD",
            direction="expense",
            raw_data="{}",
        )
        rec_deleted = ReceiptRecord(
            id=402,
            batch_id=202,
            merchant_name="Deleted Store",
            receipt_number="RCP-DEL-00",
            transaction_date=date(2026, 9, 2),
            total_amount=Decimal("50.00"),
            currency="USD",
            direction="expense",
            raw_data="{}",
        )
        db1.add_all([inv1, inv2, inv_deleted, rec1, rec_deleted])
        db1.commit()

    # Seed Org 2 data in an Org 2 session
    with Session(bind) as db2:
        db2.info["organization_id"] = 2

        tpl2 = Template(id=11, organization_id=2, name="Org 2 Invoice", file_type="xlsx")
        db2.add(tpl2)

        sf_other_org = SourceFile(
            id=102,
            organization_id=2,
            original_name="other_org_doc.pdf",
            stored_filename="sf-102.pdf",
            file_size=1024,
            checksum="hash102",
            media_type="application/pdf",
        )
        db2.add(sf_other_org)
        db2.flush()

        batch_org2 = ImportBatch(
            id=203,
            organization_id=2,
            source_file_id=102,
            template_id=11,
            status="imported",
            is_deleted=False,
        )
        db2.add(batch_org2)
        db2.flush()

        inv_org2 = InvoiceRecord(
            id=304,
            batch_id=203,
            company_name="Foreign Org Supplier",
            invoice_number="INV-ORG2-01",
            invoice_date=date(2026, 10, 2),
            total_amount=Decimal("500.00"),
            currency="USD",
            direction="purchase",
            source_worksheet="Sheet1",
            raw_data="{}",
        )
        rec_org2 = ReceiptRecord(
            id=403,
            batch_id=203,
            merchant_name="Org 2 Merchant",
            receipt_number="RCP-ORG2-99",
            transaction_date=date(2026, 10, 3),
            total_amount=Decimal("200.00"),
            currency="USD",
            direction="expense",
            raw_data="{}",
        )
        db2.add_all([inv_org2, rec_org2])
        db2.commit()

    return {"bind": bind}


def test_entity_resolution_active_invoice(db_session: Session, org_and_docs):
    """Verifies active invoice resolves with correct summary."""
    obj, summary = validate_and_resolve_entity(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    assert obj.id == 301
    assert summary.entity_type == "invoice"
    assert summary.document_number == "INV-DELL-01"
    assert summary.counterparty == "Dell Technologies"
    assert summary.total_amount == Decimal("1500.00")
    assert summary.source_file_id == 101


def test_entity_resolution_soft_deleted_invoice_rejected(db_session: Session, org_and_docs):
    """Verifies that an invoice under a soft-deleted ImportBatch raises 404."""
    with pytest.raises(HTTPException) as exc:
        validate_and_resolve_entity(db_session, organization_id=1, entity_type="invoice", entity_id=303)
    assert exc.value.status_code == 404
    assert "deleted" in exc.value.detail.lower()


def test_entity_resolution_cross_tenant_rejected(db_session: Session, org_and_docs):
    """Verifies that attempting to resolve an entity from another org raises 404."""
    with pytest.raises(HTTPException) as exc:
        validate_and_resolve_entity(db_session, organization_id=1, entity_type="invoice", entity_id=304)
    assert exc.value.status_code == 404


def test_entity_resolution_invalid_type(db_session: Session, org_and_docs):
    """Verifies that an invalid entity type raises 422."""
    with pytest.raises(HTTPException) as exc:
        validate_and_resolve_entity(db_session, organization_id=1, entity_type="purchase_order", entity_id=1)
    assert exc.value.status_code == 422


def test_create_symmetric_relationship_and_normalization(db_session: Session, org_and_docs):
    """
    Verifies that creating a symmetric 'related_to' relationship:
    1. Normalizes the tuple ordering so (receipt, 401) <-> (invoice, 301) is stored canonically.
    2. An inverse request is detected as a duplicate.
    """
    req = RelationshipCreateRequest(
        source_type="receipt",
        source_id=401,
        target_type="invoice",
        target_id=301,
        relationship_type="related_to",
    )
    result = create_relationship(db_session, organization_id=1, user_id=1, payload=req)
    assert result.relationship_type == "related_to"
    assert result.direction_semantic == "symmetric"

    # In canonical alphabetical/id sorting: ("invoice", 301) < ("receipt", 401)
    rel_in_db = db_session.get(DocumentRelationship, result.id)
    assert rel_in_db.source_type == "invoice"
    assert rel_in_db.source_id == 301
    assert rel_in_db.target_type == "receipt"
    assert rel_in_db.target_id == 401

    # Attempting to create the inverse link must raise 409 Conflict
    req_inverse = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="receipt",
        target_id=401,
        relationship_type="related_to",
    )
    with pytest.raises(HTTPException) as exc:
        create_relationship(db_session, organization_id=1, user_id=1, payload=req_inverse)
    assert exc.value.status_code == 409


def test_create_directional_relationship_supports(db_session: Session, org_and_docs):
    """
    Verifies that 'supports' relationships maintain directional semantics
    (source supports target).
    """
    req = RelationshipCreateRequest(
        source_type="source_file",
        source_id=101,
        target_type="invoice",
        target_id=301,
        relationship_type="supports",
    )
    result = create_relationship(db_session, organization_id=1, user_id=1, payload=req)
    assert result.relationship_type == "supports"
    assert result.direction_semantic == "supports"
    assert result.source_type == "source_file"
    assert result.source_id == 101
    assert result.target_type == "invoice"
    assert result.target_id == 301

    # From target perspective (Invoice 301), the relationship is 'supported_by'
    listing = list_relationships(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    assert listing.total == 1
    item = listing.items[0]
    assert item.direction_semantic == "supported_by"
    assert item.related_entity.entity_type == "source_file"
    assert item.related_entity.entity_id == 101
    assert item.related_entity.filename == "contract_dell.pdf"


def test_self_link_rejection(db_session: Session, org_and_docs):
    """Verifies that linking an entity to itself raises 422."""
    req = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="invoice",
        target_id=301,
        relationship_type="related_to",
    )
    with pytest.raises(HTTPException) as exc:
        create_relationship(db_session, organization_id=1, user_id=1, payload=req)
    assert exc.value.status_code == 422
    assert "cannot be linked to itself" in exc.value.detail.lower()


def test_cross_tenant_source_or_target_blocked(db_session: Session, org_and_docs):
    """Verifies that cross-tenant linking is strictly blocked with 404."""
    # Source belongs to org 2
    req1 = RelationshipCreateRequest(
        source_type="invoice",
        source_id=304,
        target_type="receipt",
        target_id=401,
        relationship_type="related_to",
    )
    with pytest.raises(HTTPException) as exc1:
        create_relationship(db_session, organization_id=1, user_id=1, payload=req1)
    assert exc1.value.status_code == 404

    # Target belongs to org 2
    req2 = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="receipt",
        target_id=403,
        relationship_type="related_to",
    )
    with pytest.raises(HTTPException) as exc2:
        create_relationship(db_session, organization_id=1, user_id=1, payload=req2)
    assert exc2.value.status_code == 404


def test_soft_deleted_entity_linking_blocked(db_session: Session, org_and_docs):
    """Verifies that linking to a soft-deleted document raises 404."""
    req = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="receipt",
        target_id=402,  # deleted
        relationship_type="related_to",
    )
    with pytest.raises(HTTPException) as exc:
        create_relationship(db_session, organization_id=1, user_id=1, payload=req)
    assert exc.value.status_code == 404
    assert "deleted" in exc.value.detail.lower()


def test_soft_deleted_partner_hidden_from_active_list(db_session: Session, org_and_docs):
    """
    If a relationship was created, and subsequently the target batch is soft-deleted,
    listing relationships for the source must exclude the soft-deleted partner.
    """
    bind = org_and_docs["bind"]

    # In org 1 session, link inv1 (301) to inv2 (302)
    req = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="invoice",
        target_id=302,
        relationship_type="related_to",
    )
    rel = create_relationship(db_session, organization_id=1, user_id=1, payload=req)
    assert rel.id is not None

    # Before soft-delete: listed
    listing_before = list_relationships(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    assert listing_before.total == 1

    # Soft-delete the batch of inv2
    with Session(bind) as db:
        db.info["organization_id"] = 1
        b_temp = ImportBatch(id=299, organization_id=1, source_file_id=101, template_id=10, is_deleted=False)
        db.add(b_temp)
        db.flush()
        inv2 = db.get(InvoiceRecord, 302)
        inv2.batch_id = 299
        db.commit()

        # Now soft-delete batch 299
        b_temp.is_deleted = True
        db.commit()

    # After soft-delete: listed should omit the partner
    listing_after = list_relationships(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    assert listing_after.total == 0


def test_delete_relationship_only_removes_edge(db_session: Session, org_and_docs):
    """
    Verifies that deleting a relationship removes ONLY the link and
    never deletes the underlying invoice, receipt, or source file.
    """
    req = RelationshipCreateRequest(
        source_type="invoice",
        source_id=301,
        target_type="receipt",
        target_id=401,
        relationship_type="related_to",
    )
    rel = create_relationship(db_session, organization_id=1, user_id=1, payload=req)

    # Delete relationship
    delete_relationship(db_session, organization_id=1, user_id=1, relationship_id=rel.id)

    # Edge must be gone
    assert db_session.get(DocumentRelationship, rel.id) is None

    # Documents must still exist
    assert db_session.get(InvoiceRecord, 301) is not None
    assert db_session.get(ReceiptRecord, 401) is not None

    # Audit event must be logged
    audit_ev = (
        db_session.query(AuditEvent)
        .filter(
            AuditEvent.action == "DELETE_RELATIONSHIP",
            AuditEvent.entity_type == "document_relationships",
            AuditEvent.entity_id == rel.id,
        )
        .first()
    )
    assert audit_ev is not None
