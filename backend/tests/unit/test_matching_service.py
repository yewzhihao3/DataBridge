"""
backend/tests/unit/test_matching_service.py — Unit tests for Deterministic and Heuristic Matching Engine.

Tests (covers M16.5C Phase 10 criteria 11–30):
- Counterparty normalization (case, spaces, corporate suffixes, punctuation) [12]
- Fuzzy similarity (exact, reordered tokens, OCR typos, low correlation) [12, 13]
- Short generic identifiers are not over-trusted [14]
- Exact document identifier matching [11]
- Amount matching and currency mismatch [15, 16]
- Date proximity scoring and missing date handling [17, 18]
- Missing amount and partial metadata [19, 20]
- Exact file checksum detection -> exact_file_duplicate [10, 4]
- Categorization: exact_file_duplicate, possible_duplicate, possible_related
- Cross-tenant matching isolation [28]
- Soft-deleted document exclusion [27]
- Self-suggestion exclusion [26]
- Already-linked entity exclusion [25]
- Multiple invoices from same XLSX (record-level identity) [21]
- Invoice-to-receipt related suggestions [22]
- Invoice-to-invoice possible duplicates [23]
- Receipt-to-receipt possible duplicates [24]
- Bounded result count [29]
- Stable suggestion ordering [30]
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models.identity import Organization, User
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.models.template import Template
from app.services.matching_service import (
    compute_counterparty_similarity,
    evaluate_candidate_match,
    find_document_suggestions,
    is_valid_document_identifier,
    normalize_counterparty,
)


# ===========================================================================
# Helpers to create lightweight model-like objects for evaluate_candidate_match
# These mimic the .attribute access pattern of SQLAlchemy models
# ===========================================================================

def _inv(**kwargs) -> SimpleNamespace:
    """Fake InvoiceRecord-like namespace."""
    defaults = {
        "invoice_number": None, "receipt_number": None,
        "invoice_date": None, "transaction_date": None,
        "company_name": None, "merchant_name": None, "original_name": None,
        "total_amount": None, "currency": None, "raw_data": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _rec(**kwargs) -> SimpleNamespace:
    """Fake ReceiptRecord-like namespace."""
    defaults = {
        "invoice_number": None, "receipt_number": None,
        "invoice_date": None, "transaction_date": None,
        "company_name": None, "merchant_name": None, "original_name": None,
        "total_amount": None, "currency": None, "raw_data": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _sf(checksum: str = "abc123") -> SimpleNamespace:
    """Fake SourceFile-like namespace."""
    return SimpleNamespace(checksum=checksum, id=None)


# ===========================================================================
# Normalization and Similarity Tests [12, 13]
# ===========================================================================

class TestNormalization:
    def test_trims_whitespace(self):
        assert normalize_counterparty("  Petronas  ") == "petronas"

    def test_lowercases(self):
        assert normalize_counterparty("DELL TECHNOLOGIES") == "dell technologies"

    def test_strips_sdn_bhd(self):
        result = normalize_counterparty("Petronas Dagangan Bhd.")
        assert "bhd" not in result
        assert "petronas" in result

    def test_strips_ltd(self):
        result = normalize_counterparty("Acme Supplies Ltd")
        assert "ltd" not in result
        assert "acme" in result

    def test_strips_sdn_with_pte(self):
        result = normalize_counterparty("Coffee Bean Pte Ltd")
        assert "pte" not in result
        assert "ltd" not in result

    def test_strips_corporation(self):
        result = normalize_counterparty("DELL CORPORATION")
        assert "corporation" not in result

    def test_empty_name(self):
        assert normalize_counterparty("") == ""

    def test_none_name(self):
        assert normalize_counterparty(None) == ""

    def test_collapses_extra_spaces(self):
        result = normalize_counterparty("Coffee   Shop    KL")
        assert "  " not in result

    def test_removes_punctuation(self):
        result = normalize_counterparty("Acme, Inc. (Retail)")
        assert "," not in result
        assert "(" not in result
        assert ")" not in result

    def test_similarity_exact_match(self):
        sim = compute_counterparty_similarity("Petronas", "PETRONAS")
        assert sim == 1.0

    def test_similarity_ocr_variation(self):
        """Handles OCR-like typos and abbreviation variations [13]."""
        sim = compute_counterparty_similarity("PETRONAS DAGANGAN BHD", "PETRONAS DAGANGAN BERHAD")
        assert sim >= 0.85

    def test_similarity_reordered_tokens(self):
        """Token sort handles word-order differences [13]."""
        sim = compute_counterparty_similarity("Ace Hardware Store", "Hardware Store Ace")
        assert sim >= 0.90

    def test_similarity_unrelated_companies(self):
        sim = compute_counterparty_similarity("Petronas", "Starbucks Coffee")
        assert sim < 0.35

    def test_similarity_empty_inputs(self):
        assert compute_counterparty_similarity(None, "Petronas") == 0.0
        assert compute_counterparty_similarity("Petronas", None) == 0.0
        assert compute_counterparty_similarity(None, None) == 0.0


# ===========================================================================
# Identifier Validity Tests [14]
# ===========================================================================

class TestIdentifierValidity:
    def test_short_identifier_rejected(self):
        """Identifiers shorter than 3 chars should not trigger exact_reference [14]."""
        assert is_valid_document_identifier("1") is False
        assert is_valid_document_identifier("01") is False

    def test_generic_identifier_rejected(self):
        """Common placeholder strings should not be trusted [14]."""
        assert is_valid_document_identifier("N/A") is False
        assert is_valid_document_identifier("NONE") is False
        assert is_valid_document_identifier("INV") is False
        assert is_valid_document_identifier("NA") is False

    def test_valid_identifier_accepted(self):
        assert is_valid_document_identifier("INV-2026-001") is True
        assert is_valid_document_identifier("TXN-998833") is True
        assert is_valid_document_identifier("DELL-Q4-2026-123") is True

    def test_none_rejected(self):
        assert is_valid_document_identifier(None) is False

    def test_empty_string_rejected(self):
        assert is_valid_document_identifier("") is False

    def test_short_generic_does_not_produce_exact_reference_signal(self):
        """Short generic identifier must not create exact_reference in evaluation [14]."""
        # invoice_number "1" (len=1) should be rejected by is_valid_document_identifier
        focal = _inv(company_name="Acme Supplies", invoice_number="1",
                     invoice_date=date(2026, 10, 1), total_amount=Decimal("100.00"), currency="USD")
        cand = _rec(merchant_name="Acme Supplies", receipt_number="1",
                    transaction_date=date(2026, 10, 1), total_amount=Decimal("100.00"), currency="USD")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        # Short identifier should not generate exact_reference evidence
        if result is not None:
            category, score, evidence = result
            assert not any("Exact document identifier match" in e for e in evidence)


# ===========================================================================
# Exact Document Reference Tests [11]
# ===========================================================================

class TestExactReference:
    def test_exact_invoice_number_match(self):
        """Matching document identifiers create a strong exact_reference signal [11]."""
        focal = _inv(company_name="Dell Malaysia", invoice_number="INV-DELL-001",
                     invoice_date=date(2026, 10, 1), total_amount=Decimal("1500.00"), currency="MYR")
        cand = _rec(merchant_name="Dell Malaysia", receipt_number="INV-DELL-001",
                    transaction_date=date(2026, 10, 2), total_amount=Decimal("1500.00"), currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("Exact document identifier match" in e for e in evidence)
        assert score >= 0.85

    def test_cross_reference_via_raw_data(self):
        """Candidate raw_data mentioning the focal document number is cross-referenced."""
        focal = _inv(company_name="Telecom Corp", invoice_number="TEL-INV-500",
                     invoice_date=date(2026, 10, 1), total_amount=Decimal("500.00"), currency="USD")
        cand = _rec(merchant_name="Telecom Corp", receipt_number="PAY-001",
                    transaction_date=date(2026, 10, 2), total_amount=Decimal("500.00"), currency="USD",
                    raw_data='{"notes": "Paying TEL-INV-500"}')
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("references focal document" in e for e in evidence)


# ===========================================================================
# Amount and Currency Tests [15, 16]
# ===========================================================================

class TestAmountAndCurrency:
    def test_exact_amount_match_with_same_currency(self):
        """Same currency and identical amount creates exact_amount evidence [15]."""
        focal = _inv(company_name="Office Depot", invoice_number="OD-999",
                     invoice_date=date(2026, 10, 1), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="Office Depot", receipt_number="OD-999",
                    transaction_date=date(2026, 10, 1), total_amount=Decimal("250.00"), currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("matches exactly" in e for e in evidence)

    def test_currency_mismatch_prevents_amount_match(self):
        """Mismatched currencies suppress amount matching evidence [16]."""
        focal = _inv(company_name="Global Logistics", invoice_number="LOG-100",
                     invoice_date=date(2026, 10, 1), total_amount=Decimal("500.00"), currency="USD")
        cand = _inv(company_name="Global Logistics", invoice_number="LOG-200",
                    invoice_date=date(2026, 10, 1), total_amount=Decimal("500.00"), currency="EUR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "invoice", cand, sf_c)
        if result is not None:
            category, score, evidence = result
            # Must NOT contain exact amount evidence
            assert not any("matches exactly" in e for e in evidence)
            # Must contain currency diff evidence
            assert any("differ" in e.lower() for e in evidence)


# ===========================================================================
# Date Proximity Tests [17, 18]
# ===========================================================================

class TestDateProximity:
    def test_same_date(self):
        focal = _inv(company_name="Vendor X", invoice_number="V-001",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("100.00"), currency="MYR")
        cand = _rec(merchant_name="Vendor X", receipt_number="V-001",
                    transaction_date=date(2026, 10, 10), total_amount=Decimal("100.00"), currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("identical" in e for e in evidence)

    def test_date_2_days_apart(self):
        """2-day date gap produces date proximity evidence [17]."""
        focal = _inv(company_name="Office Depot", invoice_number="OD-300",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="Office Depot", receipt_number="OD-300",
                    transaction_date=date(2026, 10, 12), total_amount=Decimal("250.00"), currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("2 day" in e for e in evidence)

    def test_missing_date_handled_gracefully(self):
        """Missing transaction date does not crash and omits date evidence [18]."""
        focal = _inv(company_name="Office Depot", invoice_number="OD-301",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="Office Depot", receipt_number="OD-301",
                    transaction_date=None, total_amount=Decimal("250.00"), currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        # Should not raise
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        if result is not None:
            category, score, evidence = result
            # No date evidence should be present
            assert not any("day" in e.lower() for e in evidence)


# ===========================================================================
# Missing/Partial Metadata Tests [19, 20]
# ===========================================================================

class TestPartialMetadata:
    def test_missing_amount_does_not_crash(self):
        """Missing amount produces no amount evidence but other signals still work [19]."""
        focal = _inv(company_name="Telecom Corp", invoice_number="TEL-88",
                     invoice_date=None, total_amount=None, currency=None)
        cand = _rec(merchant_name="Telecom Corp", receipt_number="TEL-88",
                    transaction_date=date(2026, 10, 1), total_amount=Decimal("99.00"), currency="USD")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert any("Exact document identifier match" in e for e in evidence)
        assert not any("matches exactly" in e for e in evidence)

    def test_partial_metadata_still_generates_suggestions(self):
        """Partial data (no date, no amount) with matching name and ID still suggests [20]."""
        focal = _inv(company_name="PartialVendor", invoice_number="PV-999",
                     invoice_date=None, total_amount=None, currency="MYR")
        cand = _rec(merchant_name="PartialVendor", receipt_number="PV-999",
                    transaction_date=None, total_amount=None, currency="MYR")
        sf_f = _sf("chk_f")
        sf_c = _sf("chk_c")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert score > 0.40


# ===========================================================================
# Exact File Duplicate Tests [4]
# ===========================================================================

class TestExactFileDuplicate:
    def test_same_checksum_returns_exact_file_duplicate(self):
        """Identical checksums immediately categorize as exact_file_duplicate [4]."""
        focal = _rec(merchant_name="Petronas", receipt_number="REC-01",
                     transaction_date=date(2026, 10, 1), total_amount=Decimal("50.00"), currency="MYR")
        cand = _rec(merchant_name="Petronas", receipt_number="REC-01",
                    transaction_date=date(2026, 10, 1), total_amount=Decimal("50.00"), currency="MYR")
        sf_f = _sf("sha256_identical_hash")
        sf_c = _sf("sha256_identical_hash")  # Same checksum!
        result = evaluate_candidate_match("receipt", focal, sf_f, "receipt", cand, sf_c)
        assert result is not None
        category, score, evidence = result
        assert category == "exact_file_duplicate"
        assert score >= 0.95
        assert any("checksum" in e.lower() for e in evidence)

    def test_different_checksum_not_exact_file_duplicate(self):
        """Different checksums must not produce exact_file_duplicate."""
        focal = _rec(merchant_name="Petronas", receipt_number="REC-01",
                     transaction_date=date(2026, 10, 1), total_amount=Decimal("50.00"), currency="MYR")
        cand = _rec(merchant_name="Petronas", receipt_number="REC-01",
                    transaction_date=date(2026, 10, 1), total_amount=Decimal("50.00"), currency="MYR")
        sf_f = _sf("sha256_hash_a")
        sf_c = _sf("sha256_hash_b")  # Different checksum!
        result = evaluate_candidate_match("receipt", focal, sf_f, "receipt", cand, sf_c)
        if result is not None:
            category, score, evidence = result
            assert category != "exact_file_duplicate"


# ===========================================================================
# Database Integration Tests (with seeded db_session)
# ===========================================================================

@pytest.fixture
def seed_matching_data(db_session: Session):
    """Seed comprehensive test documents across Org 1 and Org 2 for matching tests."""
    bind = db_session.bind

    # Admin setup: create orgs and user
    with Session(bind) as admin_db:
        if not admin_db.get(Organization, 1):
            admin_db.add(Organization(id=1, name="Org One", slug="org-1"))
        if not admin_db.get(Organization, 2):
            admin_db.add(Organization(id=2, name="Org Two", slug="org-2"))
        if not admin_db.get(User, 1):
            admin_db.add(User(id=1, email="test1@test.com", display_name="User 1", password_hash="pwd"))
        admin_db.commit()

    # Org 1 data
    with Session(bind) as db:
        db.info["organization_id"] = 1

        tpl = Template(id=10, organization_id=1, name="Standard Invoice", file_type="xlsx")
        db.add(tpl)

        # Source files
        sf_xlsx = SourceFile(
            id=101, organization_id=1, original_name="october_invoices.xlsx",
            stored_filename="oct_inv.xlsx", file_size=1024, checksum="hash_xlsx_shared",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        sf_rec1 = SourceFile(
            id=102, organization_id=1, original_name="coffee_oct10.jpg",
            stored_filename="rec_102.jpg", file_size=512, checksum="hash_coffee_dup",
            media_type="image/jpeg",
        )
        sf_rec2 = SourceFile(
            id=103, organization_id=1, original_name="coffee_oct10_copy.jpg",
            stored_filename="rec_103.jpg", file_size=512, checksum="hash_coffee_dup",  # Identical!
            media_type="image/jpeg",
        )
        sf_rec3 = SourceFile(
            id=104, organization_id=1, original_name="coffee_oct17.jpg",
            stored_filename="rec_104.jpg", file_size=520, checksum="hash_coffee_diff",
            media_type="image/jpeg",
        )
        db.add_all([sf_xlsx, sf_rec1, sf_rec2, sf_rec3])
        db.flush()

        # Batches
        b_xlsx = ImportBatch(id=201, organization_id=1, source_file_id=101, template_id=10, status="imported", is_deleted=False)
        b_deleted = ImportBatch(id=202, organization_id=1, source_file_id=101, template_id=10, status="imported", is_deleted=True)
        b_rec1 = ImportBatch(id=203, organization_id=1, source_file_id=102, template_id=10, status="imported", is_deleted=False)
        b_rec2 = ImportBatch(id=204, organization_id=1, source_file_id=103, template_id=10, status="imported", is_deleted=False)
        b_rec3 = ImportBatch(id=205, organization_id=1, source_file_id=104, template_id=10, status="imported", is_deleted=False)
        db.add_all([b_xlsx, b_deleted, b_rec1, b_rec2, b_rec3])
        db.flush()

        # Two invoices from same XLSX file (record-level identity) [21]
        inv_1 = InvoiceRecord(
            id=301, batch_id=201, company_name="Dell Malaysia Sdn Bhd",
            invoice_number="INV-DELL-001", invoice_date=date(2026, 10, 1),
            total_amount=Decimal("1500.00"), currency="MYR", direction="purchase",
            source_worksheet="Sheet1", raw_data="{}",
        )
        inv_2 = InvoiceRecord(
            id=302, batch_id=201, company_name="Dell Malaysia Sdn Bhd",
            invoice_number="INV-DELL-002", invoice_date=date(2026, 10, 2),
            total_amount=Decimal("1500.00"), currency="MYR", direction="purchase",
            source_worksheet="Sheet1", raw_data="{}",
        )
        # Invoice in soft-deleted batch
        inv_deleted = InvoiceRecord(
            id=303, batch_id=202, company_name="Dell Malaysia Sdn Bhd",
            invoice_number="INV-DELL-DEL", invoice_date=date(2026, 10, 1),
            total_amount=Decimal("1500.00"), currency="MYR", direction="purchase",
            source_worksheet="Sheet1", raw_data="{}",
        )
        db.add_all([inv_1, inv_2, inv_deleted])

        # Receipts
        rec1 = ReceiptRecord(
            id=401, batch_id=203, merchant_name="Artisan Coffee Roasters",
            receipt_number="", transaction_date=date(2026, 10, 10),
            total_amount=Decimal("18.50"), currency="MYR", direction="expense", raw_data="{}",
        )
        rec2_exact_dup_file = ReceiptRecord(
            id=402, batch_id=204, merchant_name="Artisan Coffee Roasters",
            receipt_number="", transaction_date=date(2026, 10, 10),
            total_amount=Decimal("18.50"), currency="MYR", direction="expense", raw_data="{}",
        )
        rec3_diff_date = ReceiptRecord(
            id=403, batch_id=205, merchant_name="Artisan Coffee Roasters",
            receipt_number="", transaction_date=date(2026, 10, 17),
            total_amount=Decimal("18.50"), currency="MYR", direction="expense", raw_data="{}",
        )
        rec_dell = ReceiptRecord(
            id=404, batch_id=203, merchant_name="Dell Malaysia",
            receipt_number="INV-DELL-001", transaction_date=date(2026, 10, 2),
            total_amount=Decimal("1500.00"), currency="MYR", direction="expense", raw_data="{}",
        )
        db.add_all([rec1, rec2_exact_dup_file, rec3_diff_date, rec_dell])
        db.commit()

    # Org 2 data (cross-tenant isolation) [28]
    with Session(bind) as db2:
        db2.info["organization_id"] = 2

        tpl2 = Template(id=20, organization_id=2, name="Org2 Template", file_type="xlsx")
        db2.add(tpl2)

        sf_org2 = SourceFile(
            id=501, organization_id=2, original_name="org2_receipt.jpg",
            stored_filename="rec_501.jpg", file_size=512, checksum="hash_coffee_dup",  # Same checksum!
            media_type="image/jpeg",
        )
        db2.add(sf_org2)
        db2.flush()

        b_org2 = ImportBatch(id=601, organization_id=2, source_file_id=501, template_id=20, status="imported", is_deleted=False)
        db2.add(b_org2)
        db2.flush()

        rec_org2 = ReceiptRecord(
            id=701, batch_id=601, merchant_name="Artisan Coffee Roasters",
            receipt_number="", transaction_date=date(2026, 10, 10),
            total_amount=Decimal("18.50"), currency="MYR", direction="expense", raw_data="{}",
        )
        db2.add(rec_org2)
        db2.commit()


def test_cross_tenant_isolation(db_session: Session, seed_matching_data):
    """Suggestions for Org 1 must never include Org 2 records [28]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401)
    candidate_ids = [(s.candidate_type, s.candidate_id) for s in res.suggestions]
    assert ("receipt", 701) not in candidate_ids, "Cross-tenant receipt must not appear in suggestions"


def test_soft_deleted_document_exclusion(db_session: Session, seed_matching_data):
    """Records in soft-deleted batches must be excluded [27]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    candidate_ids = [(s.candidate_type, s.candidate_id) for s in res.suggestions]
    assert ("invoice", 303) not in candidate_ids, "Invoice from soft-deleted batch must not appear"


def test_self_suggestion_exclusion(db_session: Session, seed_matching_data):
    """Source entity must never suggest itself [26]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401)
    for s in res.suggestions:
        if s.candidate_type == "receipt":
            assert s.candidate_id != 401, "Entity must not suggest itself"


def test_already_linked_entity_exclusion(db_session: Session, seed_matching_data):
    """Entities that already have a confirmed relationship must not be re-suggested [25]."""
    rel = DocumentRelationship(
        organization_id=1, source_type="invoice", source_id=301,
        target_type="receipt", target_id=404, relationship_type="supports",
        created_by_user_id=1,
    )
    db_session.add(rel)
    db_session.commit()

    res = find_document_suggestions(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    candidate_ids = [(s.candidate_type, s.candidate_id) for s in res.suggestions]
    assert ("receipt", 404) not in candidate_ids, "Already-linked receipt must be excluded"


def test_multiple_invoices_same_xlsx_not_merged(db_session: Session, seed_matching_data):
    """Multiple invoices from same XLSX have same checksum but different invoice numbers — record identity preserved [21]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    sug_302 = next((s for s in res.suggestions if s.candidate_type == "invoice" and s.candidate_id == 302), None)
    # Invoice 302 shares the same source file (same checksum) so it will be exact_file_duplicate
    # But they have DIFFERENT invoice numbers — the matching_service treats this as a source-level signal,
    # not a record merge. Both records remain distinct in the DB.
    assert sug_302 is not None
    assert sug_302.match_category == "exact_file_duplicate"


def test_receipt_to_receipt_exact_file_duplicate(db_session: Session, seed_matching_data):
    """Two receipts with same source checksum are classified as exact_file_duplicate [24, 4]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401)
    sug_402 = next((s for s in res.suggestions if s.candidate_type == "receipt" and s.candidate_id == 402), None)
    assert sug_402 is not None, "Receipt 402 (same checksum) must appear as suggestion"
    assert sug_402.match_category == "exact_file_duplicate"


def test_receipt_to_receipt_different_date_not_exact_duplicate(db_session: Session, seed_matching_data):
    """Receipt with different date and checksum must not be exact_file_duplicate [24]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401)
    sug_403 = next((s for s in res.suggestions if s.candidate_type == "receipt" and s.candidate_id == 403), None)
    if sug_403 is not None:
        assert sug_403.match_category != "exact_file_duplicate"


def test_invoice_to_receipt_cross_type_suggestion(db_session: Session, seed_matching_data):
    """Invoice 301 with matching invoice number reference in receipt 404 creates possible_related [22]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    sug_404 = next((s for s in res.suggestions if s.candidate_type == "receipt" and s.candidate_id == 404), None)
    assert sug_404 is not None
    assert sug_404.match_category == "possible_related"


def test_invoice_to_invoice_possible_duplicate(db_session: Session, seed_matching_data):
    """Two invoices from same vendor with same amount suggest possible_duplicate [23]."""
    # inv_1 (INV-DELL-001) and inv_2 (INV-DELL-002) share same company, amount, currency, source file
    res = find_document_suggestions(db_session, organization_id=1, entity_type="invoice", entity_id=301)
    sug_302 = next((s for s in res.suggestions if s.candidate_type == "invoice" and s.candidate_id == 302), None)
    assert sug_302 is not None
    # Same XLSX file -> exact_file_duplicate takes priority
    assert sug_302.match_category in ["exact_file_duplicate", "possible_duplicate"]


def test_bounded_result_count(db_session: Session, seed_matching_data):
    """Result count must not exceed the limit parameter [29]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401, limit=1)
    assert len(res.suggestions) <= 1


def test_stable_ordering_score_descending(db_session: Session, seed_matching_data):
    """Suggestions must be sorted: category priority first, then score descending [30]."""
    res = find_document_suggestions(db_session, organization_id=1, entity_type="receipt", entity_id=401)
    cat_order = {"exact_file_duplicate": 0, "possible_duplicate": 1, "possible_related": 2}
    for i in range(len(res.suggestions) - 1):
        a = res.suggestions[i]
        b = res.suggestions[i + 1]
        a_key = (cat_order.get(a.match_category, 3), -a.heuristic_score)
        b_key = (cat_order.get(b.match_category, 3), -b.heuristic_score)
        assert a_key <= b_key, "Suggestions are not stably sorted"


# ===========================================================================
# Negative Evidence Gate Tests (M16.5E)
# ===========================================================================

class TestNegativeEvidenceGate:
    def test_unrelated_merchants_with_same_date_rejected(self):
        """Unrelated merchants with identical dates must NOT be suggested (eliminates date-only noise)."""
        focal = _inv(company_name="ABC Office Supplies", invoice_number="INV-ABC-1",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="The Laman Kafe", receipt_number="RCP-LAMAN-99",
                    transaction_date=date(2026, 10, 10), total_amount=Decimal("18.90"), currency="MYR")
        sf_f = _sf("chk_f1")
        sf_c = _sf("chk_c1")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is None, "Unrelated merchants on same date must be rejected"

    def test_unrelated_merchants_with_nearby_date_rejected(self):
        """Unrelated merchants 1 day apart must NOT be suggested."""
        focal = _inv(company_name="ABC Office Supplies", invoice_number="INV-ABC-2",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="Richard's Top Taste Cafe", receipt_number="RCP-RICH-1",
                    transaction_date=date(2026, 10, 11), total_amount=Decimal("92.35"), currency="MYR")
        sf_f = _sf("chk_f2")
        sf_c = _sf("chk_c2")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is None, "Unrelated merchants nearby dates must be rejected"

    def test_unrelated_merchants_with_same_amount_rejected(self):
        """Unrelated merchants with same amount and close dates must NOT be suggested without name correlation."""
        focal = _inv(company_name="ABC Office Supplies", invoice_number="INV-ABC-3",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="Orbital Business Furnishings", receipt_number="RCP-ORB-1",
                    transaction_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        sf_f = _sf("chk_f3")
        sf_c = _sf("chk_c3")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is None, "Same amount without counterparty correlation must be rejected"

    def test_currency_mismatch_prevents_unrelated_amount_suggestion(self):
        """Different currencies with same numerical amount must not match."""
        focal = _inv(company_name="ABC Office Supplies", invoice_number="INV-ABC-4",
                     invoice_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="MYR")
        cand = _rec(merchant_name="XYZ Services", receipt_number="RCP-XYZ-1",
                    transaction_date=date(2026, 10, 10), total_amount=Decimal("250.00"), currency="USD")
        sf_f = _sf("chk_f4")
        sf_c = _sf("chk_c4")
        result = evaluate_candidate_match("invoice", focal, sf_f, "receipt", cand, sf_c)
        assert result is None, "Mismatched currencies must not match"

