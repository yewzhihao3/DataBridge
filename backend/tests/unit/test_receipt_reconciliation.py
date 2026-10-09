"""
tests/unit/test_receipt_reconciliation.py — Unit tests for deterministic receipt arithmetic reconciliation.
"""
from datetime import date
from decimal import Decimal
import pytest
from app.schemas.ai_receipt import (
    AIReceiptExtraction,
    AIReceiptHeader,
    AIReceiptLineItem,
)
from app.services.receipt_reconciliation import (
    reconcile_receipt_arithmetic,
    get_currency_tolerance,
)


def _make_extraction(header_kwargs, items_kwargs=None):
    items = [AIReceiptLineItem(**k) for k in (items_kwargs or [])]
    header = AIReceiptHeader(**header_kwargs)
    return AIReceiptExtraction(header=header, line_items=items)


def test_scenario_8_valid_tax_inclusive_receipt():
    # Subtotal $100.00 (tax $10.00 already included in items/subtotal), Total = $100.00
    ext = _make_extraction(
        header_kwargs={
            "merchant_name": "Singapore Retailer",
            "currency": "SGD",
            "subtotal": "100.00",
            "tax_amount": "9.00",  # 9% GST included
            "total_amount": "100.00",
        },
        items_kwargs=[
            {"description": "Item A", "quantity": "2", "unit_price": "50.00", "amount": "100.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_9_valid_tax_exclusive_receipt():
    # Subtotal $100.00, Tax $8.25 added on top, Total = $108.25
    ext = _make_extraction(
        header_kwargs={
            "merchant_name": "US Store",
            "currency": "USD",
            "subtotal": "100.00",
            "tax_amount": "8.25",
            "total_amount": "108.25",
        },
        items_kwargs=[
            {"description": "Hardware Widget", "quantity": "4", "unit_price": "25.00", "amount": "100.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_10_service_charges():
    # Subtotal 200.00 + 10% Service (20.00) + 6% SST (12.00) = 232.00
    ext = _make_extraction(
        header_kwargs={
            "merchant_name": "Fine Dining KL",
            "currency": "MYR",
            "subtotal": "200.00",
            "service_charge": "20.00",
            "tax_amount": "12.00",
            "total_amount": "232.00",
        },
        items_kwargs=[
            {"description": "Steak", "quantity": "2", "unit_price": "100.00", "amount": "200.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_11_discounts():
    # Subtotal 150.00, Discount 20.00, Tax 6.50 (on 130), Total = 136.50
    ext = _make_extraction(
        header_kwargs={
            "merchant_name": "Fashion Boutique",
            "currency": "MYR",
            "subtotal": "150.00",
            "discount_amount": "20.00",
            "tax_amount": "6.50",
            "total_amount": "136.50",
        },
        items_kwargs=[
            {"description": "Dress", "quantity": "1", "unit_price": "150.00", "amount": "150.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_12_cash_rounding():
    # Total before rounding = 19.98, Rounding = +0.02, Grand Total = 20.00
    # Cash paid = 50.00, Change = 30.00
    ext = _make_extraction(
        header_kwargs={
            "merchant_name": "Grocery Express",
            "currency": "MYR",
            "subtotal": "19.98",
            "rounding_adjustment": "0.02",
            "total_amount": "20.00",
            "cash_paid": "50.00",
            "change_amount": "30.00",
        },
        items_kwargs=[
            {"description": "Item 1", "amount": "19.98"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_13_product_quantity_and_price_mismatches():
    # Qty 3 x 10.00 should be 30.00, but stated amount is 45.00
    ext = _make_extraction(
        header_kwargs={"total_amount": "45.00"},
        items_kwargs=[
            {"description": "Widget", "quantity": "3", "unit_price": "10.00", "amount": "45.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert any("does not match line amount" in w for w in warnings)


def test_scenario_14_missing_subtotal_inferred_from_items():
    # Subtotal is None, but line items sum to 60.00 + tax 6.00 = total 66.00
    ext = _make_extraction(
        header_kwargs={
            "subtotal": None,
            "tax_amount": "6.00",
            "total_amount": "66.00",
        },
        items_kwargs=[
            {"description": "Item A", "amount": "30.00"},
            {"description": "Item B", "amount": "30.00"},
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_15_missing_total():
    # When total is None, we don't produce false grand total mismatch errors
    ext = _make_extraction(
        header_kwargs={
            "subtotal": "50.00",
            "total_amount": None,
        },
        items_kwargs=[
            {"description": "Item A", "amount": "50.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_16_empty_line_items():
    # No line items, but header subtotal 50.00 + tax 5.00 = 55.00
    ext = _make_extraction(
        header_kwargs={
            "subtotal": "50.00",
            "tax_amount": "5.00",
            "total_amount": "55.00",
        },
        items_kwargs=[],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert warnings == []


def test_scenario_17_conflicting_extracted_amounts():
    # Subtotal 100.00, Tax 10.00, Stated Total 999.00 -> Big conflict
    ext = _make_extraction(
        header_kwargs={
            "subtotal": "100.00",
            "tax_amount": "10.00",
            "total_amount": "999.00",
        },
        items_kwargs=[
            {"description": "Item A", "amount": "100.00"}
        ],
    )
    warnings = reconcile_receipt_arithmetic(ext)
    assert any("does not reconcile with subtotal" in w for w in warnings)


def test_future_and_stale_dates():
    ref_date = date(2025, 6, 1)
    future_ext = _make_extraction({"transaction_date": "2025-06-10"})
    assert any("in the future" in w for w in reconcile_receipt_arithmetic(future_ext, reference_date=ref_date))

    stale_ext = _make_extraction({"transaction_date": "2018-01-01"})
    assert any("more than 5 years old" in w for w in reconcile_receipt_arithmetic(stale_ext, reference_date=ref_date))


def test_negative_quantity_and_cash_mismatch():
    neg_qty_ext = _make_extraction(
        {"total_amount": "10.00"},
        [{"description": "Bad Qty", "quantity": "-2", "unit_price": "5.00", "amount": "10.00"}],
    )
    assert any("quantity cannot be negative" in w for w in reconcile_receipt_arithmetic(neg_qty_ext))

    cash_mismatch_ext = _make_extraction({
        "total_amount": "50.00",
        "cash_paid": "40.00",  # paid less than total
        "change_amount": "0.00",
    })
    assert any("less than the total" in w for w in reconcile_receipt_arithmetic(cash_mismatch_ext))


def test_currency_tolerances():
    assert get_currency_tolerance("JPY") == Decimal("1.00")
    assert get_currency_tolerance("KWD") == Decimal("0.005")
    assert get_currency_tolerance("MYR") == Decimal("0.02")
    assert get_currency_tolerance(None) == Decimal("0.02")
