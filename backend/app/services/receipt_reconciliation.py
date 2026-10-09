"""
app/services/receipt_reconciliation.py — Deterministic verification and arithmetic reconciliation for receipt extractions.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Sequence
from app.schemas.ai_receipt import AIReceiptExtraction, AIReceiptLineItem


ZERO_DECIMAL_CURRENCIES = {"JPY", "KRW", "VND", "CLP", "BIF", "GNF", "RWF", "PYG", "UGX"}
THREE_DECIMAL_CURRENCIES = {"BHD", "KWD", "OMR", "JOD"}


def get_currency_tolerance(currency: str | None) -> Decimal:
    """Returns currency-appropriate arithmetic comparison tolerance."""
    if not currency:
        return Decimal("0.02")
    curr_upper = currency.strip().upper()
    if curr_upper in ZERO_DECIMAL_CURRENCIES:
        return Decimal("1.00")
    if curr_upper in THREE_DECIMAL_CURRENCIES:
        return Decimal("0.005")
    return Decimal("0.02")


def reconcile_receipt_arithmetic(
    extraction: AIReceiptExtraction,
    custom_tolerance: Decimal | None = None,
    reference_date: date | None = None,
) -> list[str]:
    """
    Performs multi-point accounting reconciliation on an extracted receipt.
    
    Checks:
    - Date rationality (future dates, historical stale dates)
    - Non-negative quantities and amounts
    - Line item quantity × unit price arithmetic
    - Line item totals sum vs. subtotal
    - Tax-inclusive and tax-exclusive grand total consistency
    - Service charges, discounts, and cash rounding adjustments
    - Cash paid and change returned consistency
    
    Returns a list of structured warning messages. Does NOT mutate extracted data.
    """
    warnings: list[str] = []
    header = extraction.header
    tolerance = custom_tolerance or get_currency_tolerance(header.currency)
    cash_rounding_tolerance = max(tolerance, Decimal("0.05"))
    today = reference_date or date.today()

    # 1. Date consistency
    if header.transaction_date:
        try:
            tx_date = datetime.strptime(header.transaction_date, "%Y-%m-%d").date()
            if tx_date > today + timedelta(days=2):
                warnings.append(f"Transaction date ({header.transaction_date}) is in the future.")
            elif tx_date < today - timedelta(days=365 * 5):
                warnings.append(f"Transaction date ({header.transaction_date}) is more than 5 years old.")
        except ValueError:
            warnings.append(f"Invalid transaction date '{header.transaction_date}'.")

    # 2. Line item consistency and quantity × unit price check
    has_line_amounts = False
    line_item_sum = Decimal("0.00")

    for idx, item in enumerate(extraction.line_items, 1):
        desc = item.description or f"Item {idx}"

        if item.quantity is not None and item.quantity < Decimal("0.00"):
            warnings.append(f"Line {idx} ({desc}): quantity cannot be negative ({item.quantity}).")

        if item.amount is not None:
            has_line_amounts = True
            line_item_sum += item.amount

            if item.amount < Decimal("0.00") and (item.discount is None or item.discount == Decimal("0.00")):
                warnings.append(f"Line {idx} ({desc}): amount is negative ({item.amount}).")

        if item.quantity is not None and item.unit_price is not None and item.amount is not None:
            expected_line = item.quantity * item.unit_price
            if item.discount is not None:
                expected_line -= item.discount
            if abs(expected_line - item.amount) > tolerance:
                warnings.append(
                    f"Line {idx} ({desc}): Qty ({item.quantity}) × Unit Price ({item.unit_price}) does not match line amount ({item.amount})."
                )

    # 3. Line items sum vs Subtotal
    if has_line_amounts and header.subtotal is not None:
        if abs(line_item_sum - header.subtotal) > tolerance:
            warnings.append(
                f"Sum of line items ({line_item_sum}) does not reconcile with stated subtotal ({header.subtotal})."
            )

    # 4. Grand Total Reconciliation (Tax-exclusive & Tax-inclusive models)
    if header.total_amount is not None:
        if header.total_amount < Decimal("0.00"):
            warnings.append(f"Grand total cannot be negative ({header.total_amount}).")

        base_subtotal = header.subtotal if header.subtotal is not None else (line_item_sum if has_line_amounts else None)

        if base_subtotal is not None:
            tax = header.tax_amount or Decimal("0.00")
            service = header.service_charge or Decimal("0.00")
            discount = header.discount_amount or Decimal("0.00")
            rounding = header.rounding_adjustment or Decimal("0.00")

            # Model A: Tax-exclusive (Subtotal + Tax + Service - Discount + Rounding)
            expected_tax_exclusive = base_subtotal + tax + service - discount + rounding
            # Model B: Tax-inclusive (Subtotal + Service - Discount + Rounding, tax is part of subtotal)
            expected_tax_inclusive = base_subtotal + service - discount + rounding

            diff_exclusive = abs(expected_tax_exclusive - header.total_amount)
            diff_inclusive = abs(expected_tax_inclusive - header.total_amount)

            # Check if either accounting model reconciles within tolerance or standard cash rounding
            if min(diff_exclusive, diff_inclusive) > cash_rounding_tolerance:
                warnings.append(
                    f"Stated total ({header.total_amount}) does not reconcile with subtotal ({base_subtotal}), "
                    f"tax ({tax}), service charge ({service}), discount ({discount}), and rounding ({rounding})."
                )

    # 5. Cash paid and change consistency
    if header.cash_paid is not None and header.change_amount is not None and header.total_amount is not None:
        if header.cash_paid < header.total_amount:
            warnings.append(
                f"Cash paid ({header.cash_paid}) is less than the total amount ({header.total_amount})."
            )
        else:
            expected_change = header.cash_paid - header.total_amount
            if abs(expected_change - header.change_amount) > cash_rounding_tolerance:
                warnings.append(
                    f"Cash paid ({header.cash_paid}) minus total ({header.total_amount}) does not match change returned ({header.change_amount})."
                )

    return warnings
