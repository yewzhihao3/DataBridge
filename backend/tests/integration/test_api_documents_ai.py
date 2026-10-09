"""
tests/integration/test_api_documents_ai.py — Integration tests for AI-powered document extraction and confirmation.
"""
import io
import json
from decimal import Decimal
from PIL import Image
import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import DocumentExtraction, ReceiptRecord, ReceiptLineItem, SourceFile
from app.services.vision_provider import DeepSeekVisionProvider, VisionExtractionResult
from app.schemas.ai_receipt import AIReceiptExtraction


MOCK_AI_RECEIPT = {
    "header": {
        "merchant_name": "PETRONAS DAGANGAN BERHAD",
        "merchant_address": "Kuala Lumpur, Malaysia",
        "merchant_tax_id": "W10-1808-32000123",
        "merchant_phone": "+603-2051-5000",
        "receipt_number": "TXN-998833",
        "transaction_date": "2025-06-15",
        "transaction_time": "14:35",
        "currency": "MYR",
        "subtotal": "50.00",
        "tax_amount": "2.83",
        "service_charge": None,
        "discount_amount": None,
        "rounding_adjustment": "0.00",
        "total_amount": "50.00",
        "payment_method": "Credit Card",
        "cash_paid": None,
        "change_amount": None,
    },
    "line_items": [
        {
            "description": "PRIMAX 95",
            "quantity": "24.39",
            "unit": "L",
            "unit_price": "2.05",
            "discount": None,
            "tax_rate": "6.00",
            "tax_amount": "2.83",
            "amount": "50.00",
        }
    ],
    "confidence_ratings": {
        "merchant_name": "high",
        "total_amount": "high",
    },
    "field_evidence": {
        "merchant_name": "PETRONAS DAGANGAN BERHAD",
    },
    "unreadable_elements": [],
    "notes": [],
}


def _create_test_image_bytes():
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="white")
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_and_ai_extraction_review_and_confirm(
    client: AsyncClient, db_session: Session, monkeypatch
):
    monkeypatch.setattr(settings, "ai_receipt_mode", "auto")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key-mock")

    # Mock DeepSeek Vision extract_receipt method
    ext = AIReceiptExtraction.model_validate(MOCK_AI_RECEIPT)
    mock_result = VisionExtractionResult(
        extraction=ext,
        reconciliation_warnings=[],
        provider="deepseek_vision",
        model="deepseek-flash",
        processing_duration_seconds=1.2,
        token_usage={"total_tokens": 450},
        finish_reason="stop",
        raw_response_text=json.dumps(MOCK_AI_RECEIPT),
    )
    monkeypatch.setattr(DeepSeekVisionProvider, "extract_receipt", lambda self, *args, **kwargs: mock_result)

    image_bytes = _create_test_image_bytes()

    # 1. Upload document
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]

    # 2. Get document review state
    get_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["document_type"] == "receipt"
    assert detail["provider"] == "deepseek_vision:deepseek-flash"
    assert detail["processing_method"] == "vision_llm"
    assert detail["fields"]["merchant_name"]["value"] == "PETRONAS DAGANGAN BERHAD"
    assert detail["fields"]["total_amount"]["value"] == "50.00"
    assert len(detail["line_items"]) == 1
    assert detail["line_items"][0]["description"] == "PRIMAX 95"

    # 3. Confirm import
    confirm_payload = {
        "document_type": "receipt",
        "merchant_name": detail["fields"]["merchant_name"]["value"],
        "receipt_number": detail["fields"]["receipt_number"]["value"],
        "transaction_date": detail["fields"]["transaction_date"]["value"],
        "transaction_time": detail["fields"]["transaction_time"]["value"],
        "currency": detail["fields"]["currency"]["value"],
        "subtotal": detail["fields"]["subtotal"]["value"],
        "tax_amount": detail["fields"]["tax_amount"]["value"],
        "total_amount": detail["fields"]["total_amount"]["value"],
        "line_items": detail["line_items"],
    }
    confirm_res = await client.post(f"/api/v1/documents/{doc_id}/confirm", json=confirm_payload)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "imported"

    # 4. Verify DB persistence
    db_receipt = db_session.query(ReceiptRecord).filter_by(receipt_number="TXN-998833").first()
    assert db_receipt is not None
    assert db_receipt.merchant_name == "PETRONAS DAGANGAN BERHAD"
    assert db_receipt.total_amount == Decimal("50.00")
    assert len(db_receipt.line_items) == 1
    assert db_receipt.line_items[0].description == "PRIMAX 95"

    # 5. Verify already imported document cannot be reprocessed
    reprocess_res = await client.post(f"/api/v1/documents/{doc_id}/process")
    assert reprocess_res.status_code == 400
    assert "already imported" in reprocess_res.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_receipt_detection_on_confirmation(
    client: AsyncClient, db_session: Session, monkeypatch
):
    monkeypatch.setattr(settings, "ai_receipt_mode", "local_ocr")
    image_bytes = _create_test_image_bytes()

    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
    )
    doc_id = upload_res.json()["document_id"]

    # Confirm once
    payload = {
        "document_type": "receipt",
        "merchant_name": "Duplicate Merchant",
        "receipt_number": "DUP-100",
        "total_amount": "25.00",
        "currency": "USD",
        "line_items": [],
    }
    res1 = await client.post(f"/api/v1/documents/{doc_id}/confirm", json=payload)
    assert res1.status_code == 200

    # Upload second document
    upload_res2 = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt2.jpg", image_bytes, "image/jpeg")},
    )
    doc_id2 = upload_res2.json()["document_id"]

    # Attempt to confirm duplicate
    res2 = await client.post(f"/api/v1/documents/{doc_id2}/confirm", json=payload)
    assert res2.status_code == 409
    assert "duplicate" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_scanned_pdf_upload_auto_mode_and_confirm(
    client: AsyncClient, db_session: Session, monkeypatch
):
    monkeypatch.setattr(settings, "ai_receipt_mode", "auto")
    monkeypatch.setattr(settings, "deepseek_api_key", "test-key-mock")

    ext = AIReceiptExtraction.model_validate(MOCK_AI_RECEIPT)
    mock_result = VisionExtractionResult(
        extraction=ext,
        reconciliation_warnings=[],
        provider="deepseek_vision",
        model="deepseek-flash",
        processing_duration_seconds=0.8,
        token_usage={"total_tokens": 300},
        finish_reason="stop",
        raw_response_text=json.dumps(MOCK_AI_RECEIPT),
    )
    monkeypatch.setattr(DeepSeekVisionProvider, "extract_receipt", lambda self, *args, **kwargs: mock_result)

    # Create a 1-page scanned PDF
    buf = io.BytesIO()
    img = Image.new("RGB", (250, 350), color="white")
    img.save(buf, format="PDF")
    pdf_bytes = buf.getvalue()

    # 1. Upload scanned PDF
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("scanned_receipt.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_res.status_code == 201
    doc_id = upload_res.json()["document_id"]
    assert upload_res.json()["media_type"] == "application/pdf"
    assert upload_res.json()["page_count"] == 1

    # 2. Review state
    get_res = await client.get(f"/api/v1/documents/{doc_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["document_type"] == "receipt"
    assert "deepseek_vision" in detail["provider"]
    assert detail["processing_method"] == "scanned_pdf_vision"
    assert detail["fields"]["merchant_name"]["value"] == "PETRONAS DAGANGAN BERHAD"
    assert detail["fields"]["total_amount"]["value"] == "50.00"

    # 3. Confirm import
    confirm_payload = {
        "document_type": "receipt",
        "merchant_name": "PETRONAS DAGANGAN BERHAD",
        "receipt_number": "TXN-998833-PDF",
        "total_amount": "50.00",
        "currency": "MYR",
        "line_items": detail["line_items"],
    }
    confirm_res = await client.post(f"/api/v1/documents/{doc_id}/confirm", json=confirm_payload)
    assert confirm_res.status_code == 200
    assert confirm_res.json()["status"] == "imported"

    # 4. Persistence check
    db_receipt = db_session.query(ReceiptRecord).filter_by(receipt_number="TXN-998833-PDF").first()
    assert db_receipt is not None
    assert db_receipt.merchant_name == "PETRONAS DAGANGAN BERHAD"
    assert db_receipt.total_amount == Decimal("50.00")


@pytest.mark.asyncio
async def test_reprocess_with_explicit_mode_selector(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(settings, "ai_receipt_mode", "auto")
    image_bytes = _create_test_image_bytes()

    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("receipt.jpg", image_bytes, "image/jpeg")},
    )
    doc_id = upload_res.json()["document_id"]

    # 1. Reprocess with local_ocr
    reprocess_res = await client.post(f"/api/v1/documents/{doc_id}/process?mode=local_ocr")
    assert reprocess_res.status_code == 200
    assert reprocess_res.json()["provider"] == "tesseract"

    # 2. Invalid mode returns 422
    bad_res = await client.post(f"/api/v1/documents/{doc_id}/process?mode=invalid_engine")
    assert bad_res.status_code == 422


@pytest.mark.asyncio
async def test_extended_receipt_fields_persistence(
    client: AsyncClient, db_session: Session
):
    image_bytes = _create_test_image_bytes()
    upload_res = await client.post(
        "/api/v1/documents",
        files={"file": ("extended_receipt.jpg", image_bytes, "image/jpeg")},
    )
    doc_id = upload_res.json()["document_id"]

    confirm_payload = {
        "document_type": "receipt",
        "merchant_name": "KLCC Gourmet Cafe",
        "receipt_number": "KLCC-88221",
        "transaction_date": "2026-04-10",
        "transaction_time": "12:45",
        "currency": "MYR",
        "subtotal": "80.00",
        "tax_amount": "4.80",
        "total_amount": "84.80",
        "store_address": "Suria KLCC, Level 2, Kuala Lumpur",
        "payment_method": "Touch 'n Go eWallet",
        "cash_paid": "100.00",
        "change_amount": "15.20",
        "service_charge": "0.00",
        "discount_amount": "0.00",
        "rounding_adjustment": "0.00",
        "line_items": [
          {"description": "Latte", "quantity": "2", "unit_price": "15.00", "amount": "30.00"},
          {"description": "Club Sandwich", "quantity": "2", "unit_price": "25.00", "amount": "50.00"},
        ],
    }
    confirm_res = await client.post(f"/api/v1/documents/{doc_id}/confirm", json=confirm_payload)
    assert confirm_res.status_code == 200

    db_receipt = db_session.query(ReceiptRecord).filter_by(receipt_number="KLCC-88221").first()
    assert db_receipt is not None
    assert db_receipt.merchant_name == "KLCC Gourmet Cafe"
    assert db_receipt.store_address == "Suria KLCC, Level 2, Kuala Lumpur"
    assert db_receipt.payment_method == "Touch 'n Go eWallet"
    assert db_receipt.cash_paid == Decimal("100.00")
    assert db_receipt.change_amount == Decimal("15.20")
    assert len(db_receipt.line_items) == 2
