"""
backend/tests/integration/test_api_duplicate_and_suggestions.py

Integration tests for M16.5C:
- Receipt duplicate prevention with merchant+amount+date triple matching [1, 2]
- Different transaction dates permit re-import without 409 (no false-positive) [3]
- Exact file checksum duplicate raises 409 unless acknowledged [4, 5]
- acknowledge_duplicate=True allows confirmed import of known duplicates [6]
- acknowledge_warnings (backwards-compat alias) permits import [7]
- GET /api/v1/relationships/suggestions/invoice/{id} returns structured suggestions [8]
- GET /api/v1/relationships/suggestions/receipt/{id} returns structured suggestions [9]
- exact_file_duplicate candidates appear correctly [10]
- Matching identifier between invoice and receipt creates possible_related [11]
- Already-linked entities are excluded from suggestions [12]
- Cross-tenant isolation: foreign documents are never suggested [13]
- Suggestions bounded to limit parameter [14]
- Suggestions sorted by match_category priority then heuristic_score descending [15]
"""
from __future__ import annotations

import io
import json
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.orm import Session

from app.models.identity import Organization, OrganizationMembership, User
from app.models.invoice import ImportBatch, InvoiceRecord, ReceiptRecord
from app.models.relationship import DocumentRelationship
from app.models.source_file import SourceFile
from app.models.template import Template
from app.services.vision_provider import DeepSeekVisionProvider, VisionExtractionResult
from app.schemas.ai_receipt import AIReceiptExtraction
from app.config import settings


# ===========================================================================
# Shared helpers
# ===========================================================================

def _build_image_bytes(color: str = "white") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _mock_receipt_extraction(
    merchant: str,
    receipt_number: str | None,
    total: str,
    currency: str = "MYR",
    tx_date: str = "2026-10-10",
):
    raw = {
        "header": {
            "merchant_name": merchant,
            "merchant_address": None,
            "merchant_tax_id": None,
            "merchant_phone": None,
            "receipt_number": receipt_number,
            "transaction_date": tx_date,
            "transaction_time": None,
            "currency": currency,
            "subtotal": total,
            "tax_amount": "0.00",
            "service_charge": None,
            "discount_amount": None,
            "rounding_adjustment": "0.00",
            "total_amount": total,
            "payment_method": "Cash",
            "cash_paid": None,
            "change_amount": None,
        },
        "line_items": [],
        "confidence_ratings": {"merchant_name": "high", "total_amount": "high"},
        "field_evidence": {},
        "unreadable_elements": [],
        "notes": [],
    }
    return raw


async def _upload_mock_receipt(
    client: AsyncClient,
    monkeypatch,
    merchant: str,
    receipt_number: str | None,
    total: str,
    currency: str = "MYR",
    tx_date: str = "2026-10-10",
    image_color: str = "white",
) -> tuple[int, dict]:
    """Upload an image, mock DeepSeek extraction, return (document_id, review_fields)."""
    monkeypatch.setattr(settings, "ai_receipt_mode", "auto")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key-mock")

    raw = _mock_receipt_extraction(merchant, receipt_number, total, currency, tx_date)
    ext = AIReceiptExtraction.model_validate(raw)
    mock_result = VisionExtractionResult(
        extraction=ext, reconciliation_warnings=[], provider="deepseek_vision",
        model="deepseek-flash", processing_duration_seconds=0.5,
        token_usage={"total_tokens": 100}, finish_reason="stop",
        raw_response_text=json.dumps(raw),
    )
    monkeypatch.setattr(DeepSeekVisionProvider, "extract_receipt", lambda self, *a, **kw: mock_result)

    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt.jpg", _build_image_bytes(color=image_color), "image/jpeg")},
    )
    assert upload_res.status_code == 201, upload_res.text
    doc_id = upload_res.json()["document_id"]

    get_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200, get_res.text
    fields = get_res.json()["fields"]
    return doc_id, fields


async def _confirm_receipt(
    client: AsyncClient,
    doc_id: int,
    merchant: str,
    receipt_number: str | None,
    total: str,
    currency: str = "MYR",
    tx_date: str = "2026-10-10",
    acknowledge: bool = False,
    use_alias: bool = False,
) -> "httpx.Response":
    """POST confirm for a receipt document."""
    payload: dict = {
        "document_type": "receipt",
        "merchant_name": merchant,
        "total_amount": total,
        "currency": currency,
        "transaction_date": tx_date,
        "line_items": [],
    }
    if receipt_number is not None:
        payload["receipt_number"] = receipt_number
    if acknowledge:
        if use_alias:
            payload["acknowledge_warnings"] = True  # backwards-compat alias
        else:
            payload["acknowledge_duplicate"] = True
    return await client.post(f"/api/v1/documents/{doc_id}/confirm", json=payload)


# ===========================================================================
# Duplicate Detection Tests [1-7]
# ===========================================================================

@pytest.mark.asyncio
async def test_receipt_with_printed_number_duplicate_raises_409(client: AsyncClient, monkeypatch):
    """Same merchant + receipt_number in same tenant raises HTTP 409 [1, 2]."""
    # First import
    doc1, _ = await _upload_mock_receipt(
        client, monkeypatch, "Petronas Station A1", "TXN-101", "50.00", tx_date="2026-10-10"
    )
    res1 = await _confirm_receipt(client, doc1, "Petronas Station A1", "TXN-101", "50.00", tx_date="2026-10-10")
    assert res1.status_code == 200, f"First import failed: {res1.text}"

    # Second import — same merchant + receipt_number
    doc2, _ = await _upload_mock_receipt(
        client, monkeypatch, "Petronas Station A1", "TXN-101", "60.00", tx_date="2026-10-15"
    )
    res2 = await _confirm_receipt(client, doc2, "Petronas Station A1", "TXN-101", "60.00", tx_date="2026-10-15")
    assert res2.status_code == 409
    assert "duplicate" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receipt_without_number_same_date_raises_409(client: AsyncClient, monkeypatch):
    """Same merchant + amount + same date without receipt_number raises 409 [2]."""
    doc1, _ = await _upload_mock_receipt(
        client, monkeypatch, "Coffee Express", None, "12.00", tx_date="2026-10-10"
    )
    res1 = await _confirm_receipt(client, doc1, "Coffee Express", None, "12.00", tx_date="2026-10-10")
    assert res1.status_code == 200, f"First import failed: {res1.text}"

    doc2, _ = await _upload_mock_receipt(
        client, monkeypatch, "Coffee Express", None, "12.00", tx_date="2026-10-10"
    )
    res2 = await _confirm_receipt(client, doc2, "Coffee Express", None, "12.00", tx_date="2026-10-10")
    assert res2.status_code == 409
    assert "duplicate" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receipt_without_number_different_date_is_allowed(client: AsyncClient, monkeypatch):
    """Same merchant + amount but DIFFERENT date must NOT raise 409 (repeat purchase) [3]."""
    doc1, _ = await _upload_mock_receipt(
        client, monkeypatch, "Coffee Express", None, "12.00", tx_date="2026-10-10"
    )
    res1 = await _confirm_receipt(client, doc1, "Coffee Express", None, "12.00", tx_date="2026-10-10")
    assert res1.status_code == 200, f"First import failed: {res1.text}"

    # Different date — legitimate repeat purchase (coffee every day)
    doc2, _ = await _upload_mock_receipt(
        client, monkeypatch, "Coffee Express", None, "12.00", tx_date="2026-10-17", image_color="blue"
    )
    res2 = await _confirm_receipt(client, doc2, "Coffee Express", None, "12.00", tx_date="2026-10-17")
    assert res2.status_code == 200, f"Different-date receipt incorrectly blocked: {res2.text}"
    assert res2.json()["status"] == "imported"


@pytest.mark.asyncio
async def test_acknowledge_duplicate_true_allows_import(client: AsyncClient, monkeypatch):
    """acknowledge_duplicate=True permits confirming a known duplicate [6]."""
    doc1, _ = await _upload_mock_receipt(
        client, monkeypatch, "Grab Food", "GF-8877", "35.00", tx_date="2026-10-12"
    )
    res1 = await _confirm_receipt(client, doc1, "Grab Food", "GF-8877", "35.00", tx_date="2026-10-12")
    assert res1.status_code == 200

    doc2, _ = await _upload_mock_receipt(
        client, monkeypatch, "Grab Food", "GF-8877", "35.00", tx_date="2026-10-12"
    )
    # Without acknowledgement: 409
    res2 = await _confirm_receipt(client, doc2, "Grab Food", "GF-8877", "35.00", tx_date="2026-10-12")
    assert res2.status_code == 409

    # With acknowledgement: 200
    res3 = await _confirm_receipt(
        client, doc2, "Grab Food", "GF-8877", "35.00",
        tx_date="2026-10-12", acknowledge=True
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "imported"


@pytest.mark.asyncio
async def test_acknowledge_warnings_alias_allows_import(client: AsyncClient, monkeypatch):
    """acknowledge_warnings (backwards-compat alias) permits confirming a known duplicate [7]."""
    doc1, _ = await _upload_mock_receipt(
        client, monkeypatch, "KFC Jalan Ampang", "KFC-7799", "22.00", tx_date="2026-10-05"
    )
    res1 = await _confirm_receipt(client, doc1, "KFC Jalan Ampang", "KFC-7799", "22.00", tx_date="2026-10-05")
    assert res1.status_code == 200

    doc2, _ = await _upload_mock_receipt(
        client, monkeypatch, "KFC Jalan Ampang", "KFC-7799", "22.00", tx_date="2026-10-05"
    )
    res2 = await _confirm_receipt(
        client, doc2, "KFC Jalan Ampang", "KFC-7799", "22.00",
        tx_date="2026-10-05", acknowledge=True, use_alias=True
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "imported"


# ===========================================================================
# Fixture: Seeded Suggestions Data
# ===========================================================================

@pytest.fixture
def seed_suggestions_data(db_session: Session):
    """Seed documents for suggestions API integration tests."""
    bind = db_session.bind

    with Session(bind) as db:
        db.info["organization_id"] = 1

        tpl = Template(id=10, organization_id=1, name="Standard Invoice", file_type="xlsx")
        db.add(tpl)

        sf_xlsx = SourceFile(
            id=101, organization_id=1, original_name="q4_invoices.xlsx",
            stored_filename="q4_inv.xlsx", file_size=2048,
            checksum="sha256_q4_xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        sf_rec_orig = SourceFile(
            id=102, organization_id=1, original_name="parking_oct1.jpg",
            stored_filename="rec_102.jpg", file_size=512,
            checksum="sha256_parking_a",
            media_type="image/jpeg",
        )
        sf_rec_dup = SourceFile(
            id=103, organization_id=1, original_name="parking_oct1_copy.jpg",
            stored_filename="rec_103.jpg", file_size=512,
            checksum="sha256_parking_a",  # Same checksum!
            media_type="image/jpeg",
        )
        db.add_all([sf_xlsx, sf_rec_orig, sf_rec_dup])
        db.flush()

        b_xlsx = ImportBatch(id=201, organization_id=1, source_file_id=101, template_id=10, status="imported", is_deleted=False)
        b_rec_orig = ImportBatch(id=202, organization_id=1, source_file_id=102, template_id=10, status="imported", is_deleted=False)
        b_rec_dup = ImportBatch(id=203, organization_id=1, source_file_id=103, template_id=10, status="imported", is_deleted=False)
        db.add_all([b_xlsx, b_rec_orig, b_rec_dup])
        db.flush()

        # Invoice — referencing Dell
        inv_dell = InvoiceRecord(
            id=301, batch_id=201, company_name="Dell Malaysia Sdn Bhd",
            invoice_number="DELL-Q4-001", invoice_date=date(2026, 10, 1),
            total_amount=Decimal("9800.00"), currency="MYR",
            direction="purchase", source_worksheet="Sheet1", raw_data="{}",
        )
        db.add(inv_dell)

        # Receipt — matching Dell invoice number
        rec_dell_pay = ReceiptRecord(
            id=401, batch_id=202, merchant_name="Dell Malaysia",
            receipt_number="DELL-Q4-001",  # Same as invoice!
            transaction_date=date(2026, 10, 3),
            total_amount=Decimal("9800.00"), currency="MYR",
            direction="expense", raw_data="{}",
        )
        # Receipt — exact file duplicate of the above
        rec_dup_file = ReceiptRecord(
            id=402, batch_id=203, merchant_name="Ampang Park Parking Sdn Bhd",
            receipt_number="PARK-2301",
            transaction_date=date(2026, 10, 1),
            total_amount=Decimal("6.00"), currency="MYR",
            direction="expense", raw_data="{}",
        )
        # Original parking receipt
        rec_park_orig = ReceiptRecord(
            id=403, batch_id=202, merchant_name="Ampang Park Parking Sdn Bhd",
            receipt_number="PARK-2301",
            transaction_date=date(2026, 10, 1),
            total_amount=Decimal("6.00"), currency="MYR",
            direction="expense", raw_data="{}",
        )
        db.add_all([rec_dell_pay, rec_dup_file, rec_park_orig])
        db.commit()

    # Org 2 cross-tenant isolation data
    with Session(bind) as db2:
        db2.info["organization_id"] = 2

        if not db2.get(Organization, 2):
            db2.add(Organization(id=2, name="Tenant Two", slug="tenant-2"))
        db2.flush()

        tpl2 = Template(id=20, organization_id=2, name="Org2 Template", file_type="xlsx")
        db2.add(tpl2)

        sf_org2 = SourceFile(
            id=501, organization_id=2, original_name="org2_doc.jpg",
            stored_filename="rec_501.jpg", file_size=512,
            checksum="sha256_q4_xlsx",  # Same checksum as Org 1's invoice batch
            media_type="image/jpeg",
        )
        db2.add(sf_org2)
        db2.flush()

        b_org2 = ImportBatch(id=601, organization_id=2, source_file_id=501, template_id=20, status="imported", is_deleted=False)
        db2.add(b_org2)
        db2.flush()

        rec_org2 = ReceiptRecord(
            id=701, batch_id=601, merchant_name="Dell Malaysia Sdn Bhd",
            receipt_number="DELL-Q4-001",  # Same number as Org 1!
            transaction_date=date(2026, 10, 1),
            total_amount=Decimal("9800.00"), currency="MYR",
            direction="expense", raw_data="{}",
        )
        db2.add(rec_org2)
        db2.commit()


# ===========================================================================
# Suggestions Endpoint Tests [8-15]
# ===========================================================================

@pytest.mark.asyncio
async def test_invoice_suggestions_returns_200_with_evidence(
    client: AsyncClient, seed_suggestions_data
):
    """GET suggestions for an invoice returns valid categories and evidence [8]."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["target_type"] == "invoice"
    assert data["target_id"] == 301
    assert isinstance(data["suggestions"], list)
    assert isinstance(data["total"], int)

    # Each suggestion must have required fields
    for sug in data["suggestions"]:
        assert "match_category" in sug
        assert sug["match_category"] in ["exact_file_duplicate", "possible_duplicate", "possible_related"]
        assert "heuristic_score" in sug
        assert 0.0 <= sug["heuristic_score"] <= 1.0
        assert "evidence" in sug
        assert isinstance(sug["evidence"], list)
        assert len(sug["evidence"]) > 0
        assert "candidate_summary" in sug


@pytest.mark.asyncio
async def test_receipt_suggestions_returns_200_with_evidence(
    client: AsyncClient, seed_suggestions_data
):
    """GET suggestions for a receipt returns valid categories and evidence [9]."""
    res = await client.get("/api/v1/relationships/suggestions/receipt/401")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["target_type"] == "receipt"
    assert data["target_id"] == 401
    assert isinstance(data["suggestions"], list)


@pytest.mark.asyncio
async def test_suggestions_exact_file_duplicate_detected(
    client: AsyncClient, seed_suggestions_data
):
    """Receipt 402 and 403 share source file checksum -> exact_file_duplicate [10]."""
    res = await client.get("/api/v1/relationships/suggestions/receipt/402")
    assert res.status_code == 200
    data = res.json()
    dup_sug = next(
        (s for s in data["suggestions"]
         if s["candidate_id"] == 403 and s["candidate_type"] == "receipt"),
        None
    )
    assert dup_sug is not None, "Receipt 403 (same checksum) must appear in suggestions for 402"
    assert dup_sug["match_category"] == "exact_file_duplicate"


@pytest.mark.asyncio
async def test_suggestions_cross_document_reference_creates_possible_related(
    client: AsyncClient, seed_suggestions_data
):
    """Invoice DELL-Q4-001 and receipt referencing same number are possible_related [11]."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301")
    assert res.status_code == 200
    data = res.json()
    related_sug = next(
        (s for s in data["suggestions"]
         if s["candidate_id"] == 401 and s["candidate_type"] == "receipt"),
        None
    )
    assert related_sug is not None, "Receipt 401 (referencing DELL-Q4-001) should be suggested for invoice 301"
    assert related_sug["match_category"] == "possible_related"


@pytest.mark.asyncio
async def test_suggestions_exclude_already_linked_entity(
    client: AsyncClient, db_session: Session, seed_suggestions_data
):
    """Entities that already have a confirmed relationship are excluded from suggestions [12]."""
    # Create a relationship between invoice 301 and receipt 401
    create_res = await client.post(
        "/api/v1/relationships",
        json={
            "source_type": "invoice", "source_id": 301,
            "target_type": "receipt", "target_id": 401,
            "relationship_type": "related_to",
        }
    )
    assert create_res.status_code == 201, create_res.text

    # Now suggestions for invoice 301 must NOT include receipt 401
    res = await client.get("/api/v1/relationships/suggestions/invoice/301")
    assert res.status_code == 200
    data = res.json()
    linked_ids = [(s["candidate_type"], s["candidate_id"]) for s in data["suggestions"]]
    assert ("receipt", 401) not in linked_ids, "Already-linked receipt must be excluded from suggestions"


@pytest.mark.asyncio
async def test_suggestions_cross_tenant_isolation(
    client: AsyncClient, seed_suggestions_data
):
    """Foreign tenant documents must never appear in suggestions [13]."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301")
    assert res.status_code == 200
    data = res.json()
    org2_ids = [(s["candidate_type"], s["candidate_id"]) for s in data["suggestions"]]
    assert ("receipt", 701) not in org2_ids, "Org 2 receipt must not appear in Org 1 suggestions"


@pytest.mark.asyncio
async def test_suggestions_limit_parameter(client: AsyncClient, seed_suggestions_data):
    """limit=1 returns at most 1 suggestion [14]."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301?limit=1")
    assert res.status_code == 200
    data = res.json()
    assert len(data["suggestions"]) <= 1


@pytest.mark.asyncio
async def test_suggestions_sorted_by_category_then_score(
    client: AsyncClient, seed_suggestions_data
):
    """Suggestions must be sorted: category priority first, score descending [15]."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301")
    assert res.status_code == 200
    data = res.json()
    cat_order = {"exact_file_duplicate": 0, "possible_duplicate": 1, "possible_related": 2}
    suggestions = data["suggestions"]
    for i in range(len(suggestions) - 1):
        a = suggestions[i]
        b = suggestions[i + 1]
        a_key = (cat_order.get(a["match_category"], 3), -a["heuristic_score"])
        b_key = (cat_order.get(b["match_category"], 3), -b["heuristic_score"])
        assert a_key <= b_key, f"Suggestions not stably sorted: {a} then {b}"


@pytest.mark.asyncio
async def test_suggestions_404_for_unknown_entity(client: AsyncClient, seed_suggestions_data):
    """GET suggestions for non-existent entity returns 404."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/99999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_suggestions_422_for_invalid_entity_type(client: AsyncClient, seed_suggestions_data):
    """GET suggestions with invalid entity type returns error."""
    res = await client.get("/api/v1/relationships/suggestions/payment/301")
    # Service should raise 404 or 422 for unsupported entity type
    assert res.status_code in [404, 422]


@pytest.mark.asyncio
async def test_suggestions_limit_max_50(client: AsyncClient, seed_suggestions_data):
    """limit parameter must reject values > 50."""
    res = await client.get("/api/v1/relationships/suggestions/invoice/301?limit=999")
    assert res.status_code == 422  # FastAPI Query validation
