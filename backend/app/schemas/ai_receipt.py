"""
app/schemas/ai_receipt.py — Strict Pydantic models for AI vision receipt extraction.
"""
from __future__ import annotations
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_REASONABLE_DECIMAL = Decimal("1000000000000.00")  # 1 trillion cap


def _clean_decimal(value: Any) -> Decimal | None:
    """Safely coerces and validates Decimal values, rejecting NaN, Inf, and malformed strings."""
    if value is None:
        return None
    if isinstance(value, str):
        val_str = value.strip()
        if not val_str or val_str.lower() in {"null", "none", "n/a", "-"}:
            return None
        # Disallow raw currency symbols in structured JSON — AI is expected to output clean numeric strings
        if any(c in val_str for c in "$€£¥₹"):
            raise ValueError(f"Monetary value '{val_str}' must be numeric without currency symbols")
        # Disallow malformed comma placements (only standard comma-separated thousand separators or plain numbers)
        if "," in val_str:
            if re.search(r",\d{3}(?:,\d{3})*(?:\.\d+)?$", val_str):
                val_str = val_str.replace(",", "")
            elif re.search(r",\d{2}$", val_str) and "." not in val_str:
                # European comma decimal (e.g. 19,90)
                val_str = val_str.replace(",", ".")
            else:
                val_str = val_str.replace(",", "")
        try:
            parsed = Decimal(val_str)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid decimal string: '{value}'") from exc
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise ValueError(f"Invalid float value: {value}")
        parsed = Decimal(str(value))
    elif isinstance(value, Decimal):
        parsed = value
    else:
        raise ValueError(f"Cannot convert type '{type(value).__name__}' to Decimal")

    if parsed.is_nan() or parsed.is_infinite():
        raise ValueError(f"Value '{value}' is NaN or infinite")
    if abs(parsed) > MAX_REASONABLE_DECIMAL:
        raise ValueError(f"Value '{value}' exceeds maximum allowable limit")
    return parsed


class AIReceiptHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_name: str | None = Field(default=None, max_length=255)
    merchant_address: str | None = Field(default=None, max_length=500)
    merchant_tax_id: str | None = Field(default=None, max_length=50)
    merchant_phone: str | None = Field(default=None, max_length=50)
    receipt_number: str | None = Field(default=None, max_length=100)
    transaction_date: str | None = None
    transaction_time: str | None = None
    currency: str | None = Field(default=None, max_length=10)

    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    service_charge: Decimal | None = None
    discount_amount: Decimal | None = None
    rounding_adjustment: Decimal | None = None
    total_amount: Decimal | None = None
    payment_method: str | None = Field(default=None, max_length=50)
    cash_paid: Decimal | None = None
    change_amount: Decimal | None = None

    @field_validator("receipt_number", mode="before")
    @classmethod
    def validate_receipt_number(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            if not val or val.lower() in {"null", "none", "n/a", "-", "nil"}:
                return None
            if re.search(r"[*xX]{3,}|\b\d{4}[-* ]?[*xX]{4,}|\b\d{12,19}\b", val):
                return None
            if re.search(r"^(?:table|tab|tbl|seat)\s*#?\s*\d+$", val, re.I):
                return None
            return val
        return None

    @field_validator("transaction_date", mode="before")
    @classmethod
    def validate_date(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            if not val or val.lower() in {"null", "none", "n/a"}:
                return None
            # Validate ISO 8601 YYYY-MM-DD
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", val):
                raise ValueError(f"Date '{val}' must be in YYYY-MM-DD format")
            try:
                datetime.strptime(val, "%Y-%m-%d")
            except ValueError as exc:
                raise ValueError(f"Invalid calendar date '{val}'") from exc
            return val
        raise ValueError("transaction_date must be a string or null")

    @field_validator("transaction_time", mode="before")
    @classmethod
    def validate_time(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip()
            if not val or val.lower() in {"null", "none", "n/a"}:
                return None
            # Accept HH:MM or HH:MM:SS or 12h format HH:MM (am/pm)
            if not re.match(r"^(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?(?:\s*(?:am|pm|AM|PM))?$", val):
                raise ValueError(f"Time '{val}' must be in standard time format (e.g. 14:30 or 02:30 PM)")
            return val
        raise ValueError("transaction_time must be a string or null")

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            val = v.strip().upper()
            if not val or val.lower() in {"null", "none", "n/a"}:
                return None
            if not re.match(r"^[A-Z]{3}$", val):
                raise ValueError(f"Currency code '{val}' must be a 3-letter ISO code (e.g. MYR, SGD, USD, EUR)")
            return val
        raise ValueError("currency must be a string or null")

    @field_validator(
        "subtotal",
        "tax_amount",
        "service_charge",
        "discount_amount",
        "rounding_adjustment",
        "total_amount",
        "cash_paid",
        "change_amount",
        mode="before",
    )
    @classmethod
    def validate_monetary(cls, v: Any) -> Decimal | None:
        return _clean_decimal(v)


class AIReceiptLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(..., max_length=500)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=20)
    unit_price: Decimal | None = None
    discount: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    amount: Decimal | None = None

    @field_validator("description", mode="before")
    @classmethod
    def validate_description(cls, v: Any) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Line item description must be a non-empty string")
        return v.strip()

    @field_validator(
        "quantity",
        "unit_price",
        "discount",
        "tax_rate",
        "tax_amount",
        "amount",
        mode="before",
    )
    @classmethod
    def validate_numeric(cls, v: Any) -> Decimal | None:
        return _clean_decimal(v)


class AIReceiptExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: AIReceiptHeader
    line_items: list[AIReceiptLineItem] = Field(default_factory=list)
    confidence_ratings: dict[str, Literal["high", "medium", "low"]] = Field(default_factory=dict)
    field_evidence: dict[str, str] = Field(default_factory=dict)
    unreadable_elements: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
