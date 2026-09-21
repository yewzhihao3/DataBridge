"""
tests/unit/test_normalizer.py — Unit tests for app.services.normalizer.
"""

from datetime import date, datetime
from decimal import Decimal
import pytest

from app.services.normalizer import (
    NormalizationError,
    normalize_date,
    normalize_decimal,
    normalize_integer,
    normalize_text,
)


# ── Decimal Normalization Tests ───────────────────────────────────────────────


class TestDecimalNormalization:
    """Verify numeric and financial currency cleaning and conversion."""

    def test_plain_numbers(self) -> None:
        assert normalize_decimal(100) == Decimal("100")
        assert normalize_decimal(1250.50) == Decimal("1250.5")
        assert normalize_decimal(Decimal("45.99")) == Decimal("45.99")
        assert normalize_decimal(None) is None
        assert normalize_decimal("   ") is None

    def test_currency_symbols_and_thousands_commas(self) -> None:
        assert normalize_decimal(" RM 1,250.50 ") == Decimal("1250.50")
        assert normalize_decimal("$1,250.50") == Decimal("1250.50")
        assert normalize_decimal("€ 50,000.00") == Decimal("50000.00")
        assert normalize_decimal("100,000 USD") == Decimal("100000")
        assert normalize_decimal("£ 9.99") == Decimal("9.99")

    def test_accounting_parentheses_negatives(self) -> None:
        assert normalize_decimal("(1,250.50)") == Decimal("-1250.50")
        assert normalize_decimal(" ( 500.00 ) ") == Decimal("-500.00")
        assert normalize_decimal("($1,250.50)") == Decimal("-1250.50")

    def test_trailing_and_leading_minus(self) -> None:
        assert normalize_decimal("1250.50-") == Decimal("-1250.50")
        assert normalize_decimal("-1250.50") == Decimal("-1250.50")
        assert normalize_decimal("-RM 1,250.50") == Decimal("-1250.50")

    def test_malformed_comma_placement_raises_error(self) -> None:
        """Invalid groupings like 12,34.56 must be rejected."""
        with pytest.raises(NormalizationError, match="malformed thousands comma"):
            normalize_decimal("12,34.56")

        with pytest.raises(NormalizationError, match="malformed thousands comma"):
            normalize_decimal("1,2.3")

    def test_nan_and_infinity_rejected(self) -> None:
        with pytest.raises(NormalizationError, match="NaN/Inf"):
            normalize_decimal(float("nan"))

        with pytest.raises(NormalizationError, match="NaN/Inf"):
            normalize_decimal(float("inf"))

        with pytest.raises(NormalizationError, match="NaN/Inf"):
            normalize_decimal("NaN")

        with pytest.raises(NormalizationError, match="NaN/Inf"):
            normalize_decimal("Infinity")

    def test_boolean_input_rejected(self) -> None:
        with pytest.raises(NormalizationError, match="boolean"):
            normalize_decimal(True)

    def test_unparseable_strings_raise_error(self) -> None:
        with pytest.raises(NormalizationError, match="invalid numeric syntax"):
            normalize_decimal("not available")

        with pytest.raises(NormalizationError, match="invalid numeric syntax"):
            normalize_decimal("N/A")


# ── Date Normalization Tests ──────────────────────────────────────────────────


class TestDateNormalization:
    """Verify date parsing across datetime objects, serials, and strings."""

    def test_datetime_and_date_inputs(self) -> None:
        dt = datetime(2026, 9, 22, 14, 30, 0)
        d = date(2026, 9, 22)
        assert normalize_date(dt) == date(2026, 9, 22)
        assert normalize_date(d) == date(2026, 9, 22)
        assert normalize_date(None) is None
        assert normalize_date("   ") is None

    def test_excel_serial_number(self) -> None:
        # Serial 45557 corresponds to 2024-09-22
        res = normalize_date(45557)
        assert isinstance(res, date)
        assert res.year == 2024
        assert res.month == 9
        assert res.day == 22

    def test_custom_template_date_format(self) -> None:
        assert normalize_date("22/09/2026", date_format="%d/%m/%Y") == date(2026, 9, 22)
        assert normalize_date("09-22-2026", date_format="%m-%d-%Y") == date(2026, 9, 22)

    def test_mismatched_custom_date_format_raises_error(self) -> None:
        with pytest.raises(NormalizationError, match="does not match required template format"):
            normalize_date("2026-09-22", date_format="%d/%m/%Y")

    def test_deterministic_fallback_formats(self) -> None:
        assert normalize_date("2026-09-22") == date(2026, 9, 22)
        assert normalize_date("2026/09/22") == date(2026, 9, 22)
        assert normalize_date("22-Sep-2026") == date(2026, 9, 22)
        assert normalize_date("September 22, 2026") == date(2026, 9, 22)
        assert normalize_date("22 September 2026") == date(2026, 9, 22)

    def test_invalid_date_strings_raise_error(self) -> None:
        with pytest.raises(NormalizationError, match="Cannot parse 'TBD' as a valid date"):
            normalize_date("TBD")

        with pytest.raises(NormalizationError):
            normalize_date("2026-02-31")  # Invalid day for February


# ── Integer Normalization Tests ───────────────────────────────────────────────


class TestIntegerNormalization:
    """Verify integer conversions and fractional float rejections."""

    def test_valid_integers(self) -> None:
        assert normalize_integer(42) == 42
        assert normalize_integer(100.0) == 100
        assert normalize_integer(" 500 ") == 500
        assert normalize_integer("1,000") == 1000
        assert normalize_integer(None) is None
        assert normalize_integer("") is None

    def test_fractional_floats_and_strings_rejected(self) -> None:
        with pytest.raises(NormalizationError, match="fractional component"):
            normalize_integer(100.5)

        with pytest.raises(NormalizationError, match="invalid integer format"):
            normalize_integer("100.5")

        with pytest.raises(NormalizationError, match="boolean"):
            normalize_integer(False)

        with pytest.raises(NormalizationError, match="invalid integer format"):
            normalize_integer("abc")


# ── Text Normalization Tests ──────────────────────────────────────────────────


class TestTextNormalization:
    """Verify string trimming and None handling."""

    def test_text_trimming(self) -> None:
        assert normalize_text("  Acme Corp  ") == "Acme Corp"
        assert normalize_text("") is None
        assert normalize_text("   ") is None
        assert normalize_text(None) is None
        assert normalize_text(12345) == "12345"
