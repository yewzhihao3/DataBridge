"""
tests/unit/test_ai_receipt_schemas.py — Unit tests for AI receipt Pydantic schemas.
"""
from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas.ai_receipt import (
    AIReceiptExtraction,
    AIReceiptHeader,
    AIReceiptLineItem,
)
from app.config import Settings


def test_scenario_1_valid_malaysian_receipt():
    data = {
        "header": {
            "merchant_name": "PETRONAS DAGANGAN BERHAD",
            "merchant_address": "Lot 1234, Jalan Ampang, 50450 Kuala Lumpur",
            "merchant_tax_id": "W10-1808-32000123",
            "merchant_phone": "+603-2051-5000",
            "receipt_number": "TXN-889921",
            "transaction_date": "2025-06-15",
            "transaction_time": "14:35",
            "currency": "MYR",
            "subtotal": "47.17",
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
                "description": "PRIMAX 95 WITH PRO-DRIVE",
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
        "notes": ["Standard fuel tax invoice"],
    }
    extraction = AIReceiptExtraction.model_validate(data)
    assert extraction.header.merchant_name == "PETRONAS DAGANGAN BERHAD"
    assert extraction.header.currency == "MYR"
    assert extraction.header.total_amount == Decimal("50.00")
    assert len(extraction.line_items) == 1
    assert extraction.line_items[0].quantity == Decimal("24.39")


def test_scenario_2_valid_international_receipt():
    data = {
        "header": {
            "merchant_name": "Whole Foods Market",
            "merchant_address": "525 N Lamar Blvd, Austin, TX 78703",
            "receipt_number": "WF-2024-99812",
            "transaction_date": "2024-11-20",
            "transaction_time": "18:45:10",
            "currency": "USD",
            "subtotal": "32.50",
            "tax_amount": "2.68",
            "total_amount": "35.18",
            "payment_method": "Apple Pay",
        },
        "line_items": [
            {
                "description": "Organic Avocados 4pk",
                "quantity": "1",
                "unit_price": "5.99",
                "amount": "5.99",
            },
            {
                "description": "Almond Milk 64oz",
                "quantity": "2",
                "unit_price": "3.49",
                "amount": "6.98",
            },
            {
                "description": "Wild Sockeye Salmon Fillet",
                "quantity": "1.25",
                "unit": "lbs",
                "unit_price": "15.62",
                "amount": "19.53",
            },
        ],
    }
    extraction = AIReceiptExtraction.model_validate(data)
    assert extraction.header.currency == "USD"
    assert extraction.header.total_amount == Decimal("35.18")
    assert len(extraction.line_items) == 3


def test_scenario_3_missing_optional_fields():
    # Only description is strictly required on line items, all header fields optional
    data = {
        "header": {},
        "line_items": [{"description": "Generic Item"}],
    }
    extraction = AIReceiptExtraction.model_validate(data)
    assert extraction.header.merchant_name is None
    assert extraction.header.total_amount is None
    assert extraction.line_items[0].description == "Generic Item"
    assert extraction.line_items[0].amount is None


def test_scenario_4_null_monetary_values():
    header = AIReceiptHeader(
        merchant_name="Cafe Null",
        subtotal=None,
        tax_amount=None,
        total_amount=None,
    )
    assert header.subtotal is None
    assert header.tax_amount is None
    assert header.total_amount is None


def test_scenario_5_malformed_decimal_strings():
    with pytest.raises(ValidationError):
        AIReceiptHeader(total_amount="abc")

    with pytest.raises(ValidationError):
        AIReceiptHeader(total_amount="$19.99")  # Raw dollar symbol disallowed in strict JSON schema

    with pytest.raises(ValidationError):
        AIReceiptLineItem(description="Item", amount="two dollars")


def test_scenario_6_invalid_transaction_dates():
    with pytest.raises(ValidationError):
        AIReceiptHeader(transaction_date="2025/06/15")  # Must be YYYY-MM-DD

    with pytest.raises(ValidationError):
        AIReceiptHeader(transaction_date="2025-02-30")  # Invalid calendar day

    with pytest.raises(ValidationError):
        AIReceiptHeader(transaction_date="not-a-date")


def test_scenario_7_incorrect_currency_identifiers():
    with pytest.raises(ValidationError):
        AIReceiptHeader(currency="DOLLARS")  # Must be 3 chars

    with pytest.raises(ValidationError):
        AIReceiptHeader(currency="123")  # Must be alphabetic

    # Valid 3-letter codes accepted and capitalized
    h = AIReceiptHeader(currency="sgd")
    assert h.currency == "SGD"


def test_scenario_18_unexpected_model_fields():
    with pytest.raises(ValidationError):
        AIReceiptHeader.model_validate({"merchant_name": "Test", "unexpected_payload_key": 123})

    with pytest.raises(ValidationError):
        AIReceiptLineItem.model_validate({"description": "Test", "arbitrary_field": "bad"})

    with pytest.raises(ValidationError):
        AIReceiptExtraction.model_validate({"header": {}, "unsupported_root_key": True})


def test_scenario_19_excessively_large_numbers():
    with pytest.raises(ValidationError):
        AIReceiptHeader(total_amount="99999999999999999999999.00")

    with pytest.raises(ValidationError):
        AIReceiptHeader(total_amount=float("nan"))

    with pytest.raises(ValidationError):
        AIReceiptHeader(total_amount=float("inf"))


def test_scenario_20_no_api_key_configured():
    settings = Settings(deepseek_api_key=None, ai_receipt_mode="local_ocr")
    assert settings.deepseek_api_key is None
    assert settings.ai_receipt_mode == "local_ocr"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-flash"
