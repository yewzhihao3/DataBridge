"""
app/services/validator.py — Business validation layer for extracted invoice data.

──────────────────────────────────────────────────────────────────────────────
Responsibilities:
1. Assess extracted & normalized fields against configurable business rules.
2. Differentiate between Errors (blocking import) and Warnings (informational).
3. Provide deterministic date checks via injected reference_date.
4. Abstract duplicate invoice checking safely without tight coupling to ORMs.
5. Operate strictly in-memory without database mutations.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Literal

from app.services.extractor import ExtractionResult

Severity = Literal["error", "warning", "info"]

# ── Standardized Rule IDs ─────────────────────────────────────────────────────
RULE_REQ_FIELD_MISSING = "REQ_FIELD_MISSING"
RULE_EMPTY_IDENTIFIER = "EMPTY_IDENTIFIER"
RULE_INVALID_DATA_TYPE = "INVALID_DATA_TYPE"
RULE_UNBOUNDED_FUTURE_DATE = "UNBOUNDED_FUTURE_DATE"
RULE_STALE_INVOICE_DATE = "STALE_INVOICE_DATE"
RULE_NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
RULE_ZERO_AMOUNT = "ZERO_AMOUNT"
RULE_DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
RULE_EXTRACTION_FAILURE = "EXTRACTION_FAILURE"


# ── Configuration Model ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationConfig:
    """
    Configurable parameters for business validation rules.
    """

    allow_negative_amounts: bool = True
    allow_zero_amounts: bool = True
    max_future_days: int = 30
    max_past_days: int = 1825  # ~5 years
    check_duplicates: bool = True
    duplicate_severity: Severity = "warning"
    reference_date: date | None = None

    def __post_init__(self) -> None:
        if self.max_future_days < 0:
            raise ValueError(
                f"max_future_days must be >= 0, got {self.max_future_days}"
            )
        if self.max_past_days < 0:
            raise ValueError(
                f"max_past_days must be >= 0, got {self.max_past_days}"
            )
        if self.duplicate_severity not in {"error", "warning", "info"}:
            raise ValueError(
                f"duplicate_severity must be one of 'error', 'warning', 'info', got '{self.duplicate_severity}'"
            )


# ── Validation Models ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationIssue:
    """
    A single diagnostic issue produced by the validation engine.
    """

    rule_id: str
    field_name: str | None
    severity: Severity
    message: str
    cell_ref: str | None = None
    worksheet: str | None = None
    actual_value: Any = None


@dataclass
class ValidationReport:
    """
    Aggregated outcome of validating an extraction result.
    """

    is_valid_for_import: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    normalized_data: dict[str, Any] = field(default_factory=dict)


# ── Validation Engine ─────────────────────────────────────────────────────────


def validate_extraction(
    extraction_result: ExtractionResult,
    config: ValidationConfig | None = None,
    duplicate_checker: Callable[[str, str], bool] | None = None,
) -> ValidationReport:
    """
    Evaluates business rules against an ExtractionResult in-memory.

    Args:
        extraction_result: The raw output from extractor.py.
        config: Optional ValidationConfig. Defaults to standard parameters.
        duplicate_checker: Optional read-only callable taking (company_name, invoice_number)
                           and returning True if a duplicate exists.

    Returns:
        ValidationReport containing is_valid_for_import, issue list, counts, and normalized data.
    """
    cfg = config or ValidationConfig()
    today = cfg.reference_date or date.today()

    issues: list[ValidationIssue] = []
    normalized_data: dict[str, Any] = {}

    # 1. Capture batch-level extraction errors (e.g. missing worksheet)
    for err in extraction_result.errors:
        if err.field_name is None:
            issues.append(
                ValidationIssue(
                    rule_id=RULE_EXTRACTION_FAILURE,
                    field_name=None,
                    severity="error",
                    message=err.message,
                    worksheet=err.worksheet,
                    cell_ref=err.cell_ref,
                )
            )

    # 2. Process each field from extraction
    for f in extraction_result.fields:
        # A. If field failed during extraction/normalization, translate cleanly
        if f.status == "error":
            if f.is_empty_cell and f.is_required:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_REQ_FIELD_MISSING,
                        field_name=f.field_name,
                        severity="error",
                        message=f.error_message or f"Required field '{f.field_name}' is empty.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                )
            elif f.is_formula and f.normalized_value is None and f.is_required:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_EXTRACTION_FAILURE,
                        field_name=f.field_name,
                        severity="error",
                        message=f.error_message or f"Required formula in field '{f.field_name}' has no cached value.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_INVALID_DATA_TYPE,
                        field_name=f.field_name,
                        severity="error",
                        message=f.error_message or f"Failed to normalize field '{f.field_name}' as {f.data_type}.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                )
            continue

        # B. If field is empty optional, record None and proceed
        if f.status == "empty_optional":
            normalized_data[f.field_name] = None
            if f.warning_message:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_EXTRACTION_FAILURE,
                        field_name=f.field_name,
                        severity="warning",
                        message=f.warning_message,
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                )
            continue

        # C. Field status == "success": record normalized value and apply business rules
        val = f.normalized_value
        normalized_data[f.field_name] = val

        # Rule: Empty identifier check (company_name, invoice_number)
        if f.field_name in {"company_name", "invoice_number"}:
            if isinstance(val, str) and not val.strip():
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_EMPTY_IDENTIFIER,
                        field_name=f.field_name,
                        severity="error",
                        message=f"Identifier field '{f.field_name}' cannot be empty or whitespace.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=val,
                    )
                )

        # Rule: Invoice Date rules
        if f.data_type == "date" and isinstance(val, date):
            future_limit = today + timedelta(days=cfg.max_future_days)
            past_limit = today - timedelta(days=cfg.max_past_days)

            if val > future_limit:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_UNBOUNDED_FUTURE_DATE,
                        field_name=f.field_name,
                        severity="warning",
                        message=(
                            f"Invoice date {val.isoformat()} is more than {cfg.max_future_days} days "
                            f"in the future (relative to reference date {today.isoformat()})."
                        ),
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=val.isoformat(),
                    )
                )
            elif val < past_limit:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_STALE_INVOICE_DATE,
                        field_name=f.field_name,
                        severity="warning",
                        message=(
                            f"Invoice date {val.isoformat()} is more than {cfg.max_past_days} days "
                            f"old (relative to reference date {today.isoformat()})."
                        ),
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=val.isoformat(),
                    )
                )

        # Rule: Amount rules
        if f.data_type == "decimal" and isinstance(val, Decimal):
            if val < Decimal("0"):
                severity: Severity = "warning" if cfg.allow_negative_amounts else "error"
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_NEGATIVE_AMOUNT,
                        field_name=f.field_name,
                        severity=severity,
                        message=(
                            f"Total amount is negative ({val}). "
                            + ("This record may represent a credit note, refund, or adjustment."
                               if cfg.allow_negative_amounts else "Negative amounts are disallowed by policy.")
                        ),
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=float(val),
                    )
                )
            elif val == Decimal("0"):
                severity = "warning" if cfg.allow_zero_amounts else "error"
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_ZERO_AMOUNT,
                        field_name=f.field_name,
                        severity=severity,
                        message="Total amount is zero (0.00).",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=0.0,
                    )
                )

    # 3. Duplicate invoice check
    if cfg.check_duplicates and duplicate_checker is not None:
        comp_name = normalized_data.get("company_name")
        inv_num = normalized_data.get("invoice_number")

        if comp_name and inv_num and isinstance(comp_name, str) and isinstance(inv_num, str):
            try:
                is_duplicate = duplicate_checker(comp_name.strip(), inv_num.strip())
                if is_duplicate:
                    issues.append(
                        ValidationIssue(
                            rule_id=RULE_DUPLICATE_INVOICE,
                            field_name="invoice_number",
                            severity=cfg.duplicate_severity,
                            message=(
                                f"Invoice number '{inv_num}' for company '{comp_name}' "
                                "has already been imported previously."
                            ),
                            actual_value=inv_num,
                        )
                    )
            except Exception as exc:
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_DUPLICATE_INVOICE,
                        field_name="invoice_number",
                        severity="error",
                        message=f"Failed to verify invoice uniqueness due to a database/checker error: {exc}",
                    )
                )

    # 4. Calculate summary counts
    error_cnt = sum(1 for i in issues if i.severity == "error")
    warning_cnt = sum(1 for i in issues if i.severity == "warning")
    info_cnt = sum(1 for i in issues if i.severity == "info")

    return ValidationReport(
        is_valid_for_import=(error_cnt == 0),
        issues=issues,
        error_count=error_cnt,
        warning_count=warning_cnt,
        info_count=info_cnt,
        normalized_data=normalized_data,
    )
