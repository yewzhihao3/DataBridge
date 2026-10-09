"""
tests/unit/test_vision_provider.py — Mocked unit tests for DeepSeekVisionProvider.
"""
import base64
import json
from decimal import Decimal
import httpx
import pytest

from app.services.vision_provider import (
    DeepSeekVisionProvider,
    MissingApiKeyError,
    PayloadTooLargeError,
    UnsupportedMediaError,
    VisionAuthenticationError,
    VisionMalformedResponseError,
    VisionProviderError,
    VisionRateLimitError,
    VisionServerError,
    VisionTimeoutError,
)


# Minimal valid image payloads
SAMPLE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xdb\x00C\x00" + b"\x00" * 50
SAMPLE_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
SAMPLE_WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 \x0e\x00\x00\x00\x30\x01\x00\x9d\x01\x2a\x01\x00\x01\x00\x02\x00\x34\x25"

MOCK_SUCCESS_RECEIPT_JSON = {
    "header": {
        "merchant_name": "PETRONAS DAGANGAN BERHAD",
        "merchant_address": "Kuala Lumpur, Malaysia",
        "merchant_tax_id": "W10-1808-32000123",
        "merchant_phone": "+603-2051-5000",
        "receipt_number": "TXN-100234",
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


def _make_mock_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport)


def test_successful_receipt_extraction_and_request_serialization():
    captured_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        body = json.loads(request.content.decode("utf-8"))
        assert body["model"] == "deepseek-flash"
        assert body["response_format"] == {"type": "json_object"}
        assert request.headers["Authorization"] == "Bearer mock-secret-key"

        # Check base64 image URL structure
        user_content = body["messages"][1]["content"]
        image_part = next(p for p in user_content if p["type"] == "image_url")
        expected_b64 = base64.b64encode(SAMPLE_JPEG).decode("ascii")
        assert image_part["image_url"]["url"] == f"data:image/jpeg;base64,{expected_b64}"
        assert image_part["image_url"]["detail"] == "high"

        response_payload = {
            "id": "chatcmpl-mock-123",
            "object": "chat.completion",
            "created": 1728000000,
            "model": "deepseek-flash",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(MOCK_SUCCESS_RECEIPT_JSON),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 1250,
                "completion_tokens": 340,
                "total_tokens": 1590,
            },
        }
        return httpx.Response(200, json=response_payload)

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(
        api_key="mock-secret-key",
        base_url="https://api.deepseek.com",
        model="deepseek-flash",
        http_client=client,
    )

    result = provider.extract_receipt(SAMPLE_JPEG)

    assert len(captured_requests) == 1
    assert result.provider == "deepseek_vision"
    assert result.model == "deepseek-flash"
    assert result.finish_reason == "stop"
    assert result.token_usage == {"prompt_tokens": 1250, "completion_tokens": 340, "total_tokens": 1590}
    assert result.extraction.header.merchant_name == "PETRONAS DAGANGAN BERHAD"
    assert result.extraction.header.total_amount == Decimal("50.00")
    assert result.extraction.header.currency == "MYR"
    assert len(result.extraction.line_items) == 1
    assert result.extraction.line_items[0].quantity == Decimal("24.39")
    assert result.reconciliation_warnings == []


def test_markdown_wrapped_json_handling():
    def handler(request: httpx.Request) -> httpx.Response:
        wrapped_json = f"```json\n{json.dumps(MOCK_SUCCESS_RECEIPT_JSON)}\n```"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": wrapped_json}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 100},
            },
        )

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    result = provider.extract_receipt(SAMPLE_PNG)
    assert result.extraction.header.merchant_name == "PETRONAS DAGANGAN BERHAD"


def test_missing_api_key_raises_exception(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    provider_from_settings = DeepSeekVisionProvider()
    with pytest.raises(MissingApiKeyError, match="not configured"):
        provider_from_settings.extract_receipt(SAMPLE_JPEG)

    provider_explicit_empty = DeepSeekVisionProvider(api_key="")
    with pytest.raises(MissingApiKeyError, match="not configured"):
        provider_explicit_empty.extract_receipt(SAMPLE_JPEG)


def test_unsupported_media_and_empty_payload():
    provider = DeepSeekVisionProvider(api_key="mock-key")
    with pytest.raises(UnsupportedMediaError, match="empty"):
        provider.extract_receipt(b"")

    with pytest.raises(UnsupportedMediaError, match="Unsupported document image"):
        provider.extract_receipt(b"NOT_AN_IMAGE_FILE_DATA_12345")


def test_oversized_image_rejection(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "max_document_image_size_mb", 1)  # 1 MB limit
    provider = DeepSeekVisionProvider(api_key="mock-key")
    huge_data = SAMPLE_JPEG + (b"0" * (2 * 1024 * 1024))
    with pytest.raises(PayloadTooLargeError, match="exceeds allowable limit"):
        provider.extract_receipt(huge_data)


def test_authentication_error_401():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="bad-key", http_client=client)
    with pytest.raises(VisionAuthenticationError, match="HTTP 401"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_rate_limit_429_with_retry():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "Rate limited"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(MOCK_SUCCESS_RECEIPT_JSON)}}]},
        )

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", max_retries=1, http_client=client)
    result = provider.extract_receipt(SAMPLE_JPEG)
    assert call_count == 2
    assert result.extraction.header.merchant_name == "PETRONAS DAGANGAN BERHAD"


def test_server_error_500_exceeding_retries():
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "Internal server error"})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", max_retries=1, http_client=client)
    with pytest.raises(VisionServerError, match="HTTP 500"):
        provider.extract_receipt(SAMPLE_JPEG)
    assert call_count == 2  # 1 initial + 1 retry


def test_timeout_handling():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Socket read timed out")

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", max_retries=0, timeout_seconds=5, http_client=client)
    with pytest.raises(VisionTimeoutError, match="timed out"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_malformed_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "Not a valid json {{"}}]})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    with pytest.raises(VisionMalformedResponseError, match="not valid JSON"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_schema_validation_failure_on_invalid_types():
    def handler(request: httpx.Request) -> httpx.Response:
        bad_schema = {"header": {"transaction_date": "invalid-date-format"}}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(bad_schema)}}]})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    with pytest.raises(VisionMalformedResponseError, match="validation failed"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_empty_completion_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    with pytest.raises(VisionMalformedResponseError, match="empty completion"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_missing_choices_in_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    with pytest.raises(VisionMalformedResponseError, match="contains no choices"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_webp_image_handling():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        user_content = body["messages"][1]["content"]
        image_part = next(p for p in user_content if p["type"] == "image_url")
        assert image_part["image_url"]["url"].startswith("data:image/webp;base64,")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(MOCK_SUCCESS_RECEIPT_JSON)}}]},
        )

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    result = provider.extract_receipt(SAMPLE_WEBP)
    assert result.extraction.header.merchant_name == "PETRONAS DAGANGAN BERHAD"


def test_network_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by host")

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", max_retries=0, http_client=client)
    with pytest.raises(VisionServerError, match="Failed to establish network connection"):
        provider.extract_receipt(SAMPLE_JPEG)


def test_credentials_not_leaked_in_exceptions():
    secret_key = "super-secret-key-12345"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "Something went wrong internally"})

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key=secret_key, max_retries=0, http_client=client)

    with pytest.raises(VisionServerError) as exc_info:
        provider.extract_receipt(SAMPLE_JPEG)

    # Ensure secret API key is NEVER leaked in the exception message
    assert secret_key not in str(exc_info.value)


def test_decimal_exact_preservation():
    custom_json = dict(MOCK_SUCCESS_RECEIPT_JSON)
    custom_json["header"] = dict(MOCK_SUCCESS_RECEIPT_JSON["header"])
    custom_json["header"]["subtotal"] = "123.456"
    custom_json["header"]["total_amount"] = "123.456"
    custom_json["line_items"] = [
        {"description": "Special Item", "quantity": "3.1415", "unit_price": "39.298", "amount": "123.456"}
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(custom_json)}}]},
        )

    client = _make_mock_client(handler)
    provider = DeepSeekVisionProvider(api_key="mock-key", http_client=client)
    result = provider.extract_receipt(SAMPLE_JPEG)

    # Decimal exact values must be preserved
    assert result.extraction.header.total_amount == Decimal("123.456")
    assert result.extraction.line_items[0].quantity == Decimal("3.1415")
    assert result.extraction.line_items[0].unit_price == Decimal("39.298")


def test_invalid_base_url():
    with pytest.raises(ValueError, match="Invalid DEEPSEEK_BASE_URL"):
        DeepSeekVisionProvider(api_key="mock-key", base_url="not-a-url")
