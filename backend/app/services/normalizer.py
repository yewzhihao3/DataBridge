"""
app/services/normalizer.py — Deterministic data type normalization.

──────────────────────────────────────────────────────────────────────────────
Responsibilities:
1. Normalize raw values from Excel into typed Python objects (Decimal, date, int, str).
2. Clean financial strings (currency symbols, thousands separators, accounting negatives).
3. Handle Excel serial dates with workbook epoch awareness.
4. Fail explicitly with NormalizationError on invalid data—NEVER silently default
   to 0 or None for unparseable input.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl.utils.datetime import WINDOWS_EPOCH, from_excel


class NormalizationError(ValueError):
    """Raised when raw cell data cannot be converted into the requested data type."""


# ── Regular Expressions for Currency & Numeric Cleaning ──────────────────────

# Matches common currency symbols & 3-letter currency codes
_CURRENCY_PREFIX_REGEX = re.compile(
    r"^\s*(?:RM|USD|EUR|GBP|MYR|SGD|AUD|CAD|JPY|CNY|CHF|HKD|NZD|[$€£¥₹₩])\s*",
    re.IGNORECASE,
)
_CURRENCY_SUFFIX_REGEX = re.compile(
    r"\s*(?:RM|USD|EUR|GBP|MYR|SGD|AUD|CAD|JPY|CNY|CHF|HKD|NZD|[$€£¥₹₩])\s*$",
    re.IGNORECASE,
)

# Thousands comma separator format check:
# Valid: "1,250.50", "1,000,000", "500", "0.50"
# Invalid: "12,34.56", "1,2.3", ",123", "123,"
_VALID_COMMA_NUMBER_REGEX = re.compile(
    r"^[+-]?(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?$"
)


# ── Normalization Functions ───────────────────────────────────────────────────


def normalize_text(val: Any) -> str | None:
    """
    Normalizes a value to a stripped string, or None if empty.
    """
    if val is None:
        return None

    s = str(val).strip()
    return s if s else None


def normalize_integer(val: Any) -> int | None:
    """
    Normalizes an integer value.

    Accepts int, whole-number float (e.g. 100.0), or integer string ("100").
    Rejects fractional floats, strings with decimals, or non-numeric text.
    """
    if val is None:
        return None

    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None
        # Remove commas if present in integer string e.g. "1,000"
        if _VALID_COMMA_NUMBER_REGEX.match(cleaned):
            cleaned = cleaned.replace(",", "")
        try:
            # Check if string parses directly as int
            return int(cleaned)
        except ValueError:
            # Check if it was float string with .0
            try:
                flt = float(cleaned)
                if flt.is_integer():
                    return int(flt)
            except ValueError:
                pass
        raise NormalizationError(
            f"Cannot convert '{val}' to integer: invalid integer format."
        )

    if isinstance(val, bool):
        # In Python bool is a subclass of int, so reject True/False
        raise NormalizationError(f"Cannot convert boolean '{val}' to integer.")

    if isinstance(val, int):
        return val

    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise NormalizationError(f"Cannot convert '{val}' (NaN/Inf) to integer.")
        if val.is_integer():
            return int(val)
        raise NormalizationError(
            f"Cannot convert float '{val}' with fractional component to integer."
        )

    raise NormalizationError(
        f"Unsupported type {type(val).__name__} for integer normalization: {val!r}"
    )


def normalize_decimal(val: Any) -> Decimal | None:
    """
    Normalizes a numeric/financial value to a Python Decimal.

    Safeguards:
    - Rejects NaN, +Infinity, -Infinity.
    - Cleans currency symbols (e.g. 'RM 1,250.50', '$1,250.50').
    - Handles accounting parentheses negatives: '(1,250.50)' -> -1250.50.
    - Handles trailing minus: '1250.50-' -> -1250.50.
    - Validates thousands separator format (rejects malformed commas like '12,34.56').
    - Converts floats via str(val) without silent truncation.
    """
    if val is None:
        return None

    if isinstance(val, bool):
        raise NormalizationError(f"Cannot convert boolean '{val}' to decimal.")

    if isinstance(val, Decimal):
        if val.is_nan() or val.is_infinite():
            raise NormalizationError(f"Cannot convert '{val}' (NaN/Inf) to decimal.")
        return val

    if isinstance(val, int):
        return Decimal(val)

    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            raise NormalizationError(f"Cannot convert '{val}' (NaN/Inf) to decimal.")
        # Converting float to str preserves exact representation formatted by Python
        return Decimal(str(val))

    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None

        # Check for NaN / Infinity strings
        upper = cleaned.upper()
        if upper in {"NAN", "INF", "+INF", "-INF", "INFINITY", "+INFINITY", "-INFINITY"}:
            raise NormalizationError(f"Cannot convert '{val}' (NaN/Inf) to decimal.")

        # Detect accounting parentheses: "(1,250.50)" or "($1,250.50)"
        is_negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1].strip()

        # Detect leading/trailing signs
        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:].strip()
        elif cleaned.endswith("-"):
            is_negative = True
            cleaned = cleaned[:-1].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        # Strip currency prefixes and suffixes
        cleaned = _CURRENCY_PREFIX_REGEX.sub("", cleaned).strip()
        cleaned = _CURRENCY_SUFFIX_REGEX.sub("", cleaned).strip()

        # Check again in case minus/parens were after currency symbol (e.g. "-RM 1,250.50" or "RM -1,250.50")
        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:].strip()
        elif cleaned.endswith("-"):
            is_negative = True
            cleaned = cleaned[:-1].strip()
        elif cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1].strip()

        if not cleaned:
            raise NormalizationError(f"Cannot convert '{val}' to decimal: empty amount.")

        # Validate thousands grouping if commas exist
        if "," in cleaned:
            if not _VALID_COMMA_NUMBER_REGEX.match(cleaned):
                raise NormalizationError(
                    f"Cannot convert '{val}' to decimal: malformed thousands comma placement."
                )
            cleaned = cleaned.replace(",", "")

        try:
            result = Decimal(cleaned)
            if result.is_nan() or result.is_infinite():
                raise NormalizationError(f"Cannot convert '{val}' (NaN/Inf) to decimal.")
            return -result if is_negative else result
        except InvalidOperation as exc:
            raise NormalizationError(
                f"Cannot convert '{val}' to decimal: invalid numeric syntax."
            ) from exc

    raise NormalizationError(
        f"Unsupported type {type(val).__name__} for decimal normalization: {val!r}"
    )


def normalize_date(
    val: Any,
    date_format: str | None = None,
    workbook_epoch: datetime | None = None,
) -> date | None:
    """
    Normalizes a date value to a datetime.date object.

    Handles:
    1. datetime.datetime & datetime.date objects.
    2. Excel serial numbers (int / float) using workbook_epoch (defaults to WINDOWS_EPOCH 1899-12-30).
    3. Template-specific date_format if provided.
    4. Standard ISO dates ('YYYY-MM-DD', 'YYYY/MM/DD').
    5. Common unambiguous date formats ('DD-Mon-YYYY', 'Month DD, YYYY', 'DD/MM/YYYY').
    """
    if val is None:
        return None

    if isinstance(val, datetime):
        return val.date()

    if isinstance(val, date):
        return val

    # Excel numeric serial date (e.g. 45557 for 2024-09-22)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if math.isnan(val) or math.isinf(val):
            raise NormalizationError(f"Cannot parse date from '{val}' (NaN/Inf).")
        try:
            epoch = workbook_epoch or WINDOWS_EPOCH
            dt = from_excel(val, epoch=epoch)
            if isinstance(dt, datetime):
                return dt.date()
            if isinstance(dt, date):
                return dt
        except Exception as exc:
            raise NormalizationError(
                f"Failed to convert Excel serial number '{val}' to date: {exc}"
            ) from exc

    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return None

        # 1. Custom template-specific format
        if date_format:
            try:
                return datetime.strptime(cleaned, date_format).date()
            except ValueError as exc:
                raise NormalizationError(
                    f"Date string '{val}' does not match required template format '{date_format}'."
                ) from exc

        # 2. Deterministic fallback formats
        candidate_formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%m/%d/%Y",
            "%m-%d-%Y",
        ]

        for fmt in candidate_formats:
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue

        raise NormalizationError(
            f"Cannot parse '{val}' as a valid date. "
            "Specify a 'date_format' on the template if using a custom format."
        )

    raise NormalizationError(
        f"Unsupported type {type(val).__name__} for date normalization: {val!r}"
    )
