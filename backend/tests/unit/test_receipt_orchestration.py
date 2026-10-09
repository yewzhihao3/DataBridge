"""
tests/unit/test_receipt_orchestration.py — Unit and pipeline tests for receipt extraction orchestration and fallback.
"""
import base64
import json
from decimal import Decimal
from pathlib import Path
import httpx
import pytest

from app.config import settings
from app.services.document_processing import process_document_pipeline, map_ai_extraction_to_review_state
from app.services.vision_provider import (
    DeepSeekVisionProvider,
    MissingApiKeyError,
    VisionExtractionResult,
    VisionTimeoutError,
    VisionRateLimitError,
    VisionMalformedResponseError,
)
from app.schemas.ai_receipt import AIReceiptExtraction


# Sample test images
SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + b"\x00" * 50

MOCK_RECEIPT_JSON = {
    "header": {
        "merchant_name": "PETRONAS DAGANGAN BERHAD",
        "merchant_address": "Kuala Lumpur, Malaysia",
        "merchant_tax_id": "W10-1808-32000123",
        "merchant_phone": "+603-2051-5000",
        "receipt_number": "TXN-998822",
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
    "notes": ["Sample fuel receipt note"],
}


def _make_mock_provider(handler):
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return DeepSeekVisionProvider(
        api_key="test-key-12345",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        http_client=client,
    )


@pytest.fixture
def temp_receipt_image(tmp_path):
    img_path = tmp_path / "test_receipt.jpg"
    img_path.write_bytes(SAMPLE_JPEG)
    return img_path


def test_scenario_1_local_ocr_never_invokes_vision_provider(temp_receipt_image):
    called = False

    def handler(request):
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="local_ocr", provider=mock_prov)

    assert not called
    assert res["processing_method"] in {"image_ocr", "ocr_required"}
    assert res["status"] == "needs_review"


def test_scenario_2_auto_mode_success(temp_receipt_image):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps(MOCK_RECEIPT_JSON)}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 500},
            },
        )

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="auto", provider=mock_prov)

    assert res["status"] == "needs_review"
    assert res["document_type"] == "receipt"
    assert res["provider"] == "deepseek_vision:deepseek-flash"
    assert res["processing_method"] == "vision_llm"
    assert res["fields"]["merchant_name"]["value"] == "PETRONAS DAGANGAN BERHAD"
    assert res["fields"]["total_amount"]["value"] == "50.00"
    assert len(res["line_items"]) == 1
    assert res["line_items"][0]["description"] == "PRIMAX 95"
    assert "AI Note: Sample fuel receipt note" in res["warnings"]


def test_scenario_3_auto_mode_without_credentials_uses_local_ocr(temp_receipt_image, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="auto")
    # Must fallback cleanly to local OCR
    assert "fell back to local OCR engine" in res["warnings"][0]
    assert res["status"] == "needs_review"


def test_scenario_4_auto_mode_falls_back_after_timeout(temp_receipt_image):
    def handler(request):
        raise httpx.ReadTimeout("Socket timed out")

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="auto", provider=mock_prov)

    assert any("fell back to local OCR engine" in w for w in res["warnings"])
    assert res["status"] == "needs_review"


def test_scenario_5_auto_mode_falls_back_after_rate_limit(temp_receipt_image):
    def handler(request):
        return httpx.Response(429, json={"error": "Rate limit exceeded"})

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="auto", provider=mock_prov)

    assert any("fell back to local OCR engine" in w for w in res["warnings"])
    assert res["status"] == "needs_review"


def test_scenario_6_auto_mode_handles_invalid_json(temp_receipt_image):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "INVALID JSON {{{"}}]})

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="auto", provider=mock_prov)

    assert any("fell back to local OCR engine" in w for w in res["warnings"])
    assert res["status"] == "needs_review"


def test_scenario_7_vision_only_rejects_missing_credentials(temp_receipt_image, monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="vision_only")

    assert res["status"] == "failed"
    assert "vision_only mode" in res["error_message"]
    assert res["ocr_status"] == "failed"


def test_scenario_8_vision_only_never_falls_back(temp_receipt_image):
    def handler(request):
        return httpx.Response(500, json={"error": "Server error"})

    mock_prov = _make_mock_provider(handler)
    res = process_document_pipeline(temp_receipt_image, "image/jpeg", mode="vision_only", provider=mock_prov)

    assert res["status"] == "failed"
    assert res["error_message"] is not None
    assert "fell back" not in str(res["warnings"])


def test_scenario_19_20_data_mapping_and_decimal_exactness():
    ext = AIReceiptExtraction.model_validate(MOCK_RECEIPT_JSON)
    result = VisionExtractionResult(
        extraction=ext,
        reconciliation_warnings=["Warning A"],
        provider="deepseek_vision",
        model="deepseek-flash",
        processing_duration_seconds=1.23,
        token_usage={"total_tokens": 100},
        finish_reason="stop",
        raw_response_text=json.dumps(MOCK_RECEIPT_JSON),
    )
    fields, lines, warnings = map_ai_extraction_to_review_state(result)

    assert fields["merchant_name"]["value"] == "PETRONAS DAGANGAN BERHAD"
    assert fields["total_amount"]["value"] == "50.00"
    assert fields["subtotal"]["value"] == "50.00"
    assert fields["store_address"]["value"] == "Kuala Lumpur, Malaysia"
    assert lines[0]["amount"] == "50.00"
    assert lines[0]["quantity"] == "24.39"
    assert "Warning A" in warnings
    assert "AI Note: Sample fuel receipt note" in warnings
