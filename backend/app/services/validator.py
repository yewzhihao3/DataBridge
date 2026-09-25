"""
app/services/validator.py — Business validation layer for extracted invoice data.

──────────────────────────────────────────────────────────────────────────────
Responsibilities:
1. Assess extracted & normalized fields against configurable business rules.
2. Differentiate between Errors (blocking import) and Warnings (informational).
3. Provide deterministic date checks via injected reference_date.
4. Abstract duplicate invoice checking safely without tight coupling to ORMs.
5. Operate strictly in-memory without database mutations.
6. Support explicit target_field mapping: when a field_to_target dict is provided,
   normalized_data keys are set to the target field name so that the importer can
   route values directly to the correct InvoiceRecord column or custom_fields JSON.
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
RULE_LINE_ITEM_ERROR = "LINE_ITEM_ERROR"
RULE_LINE_ITEM_MATH_MISMATCH = "LINE_ITEM_MATH_MISMATCH"


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
class RowValidationReport:
    """
    Validation outcome for a single row in a multi-record extraction.
    """

    source_row_number: int
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class LineItemValidationReport:
    """
    Validation outcome for a single line item in a composite invoice extraction.
    """

    source_row_number: int
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized_data: dict[str, Any] = field(default_factory=dict)


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
    is_multi_record: bool = False
    row_reports: list[RowValidationReport] = field(default_factory=list)
    has_line_items: bool = False
    line_item_reports: list[LineItemValidationReport] = field(default_factory=list)



# ── Validation Engine ─────────────────────────────────────────────────────────


def validate_extraction(
    extraction_result: ExtractionResult,
    config: ValidationConfig | None = None,
    duplicate_checker: Callable[[str, str], bool] | None = None,
    field_to_target: dict[str, str] | None = None,
) -> ValidationReport:
    """
    Evaluates business rules against an ExtractionResult in-memory.

    Args:
        extraction_result: The raw output from extractor.py.
        config: Optional ValidationConfig. Defaults to standard parameters.
        duplicate_checker: Optional read-only callable taking (company_name, invoice_number)
                           and returning True if a duplicate exists.
        field_to_target: Optional dict mapping field_name -> target_field. When provided,
                         normalized_data keys use target_field instead of field_name,
                         allowing the importer to route values to the correct columns.
                         Explicit target_field mappings take priority over alias-based
                         fallbacks in the persistence layer.

    Returns:
        ValidationReport containing is_valid_for_import, issue list, counts, and normalized data.
    """
    cfg = config or ValidationConfig()
    today = cfg.reference_date or date.today()
    _field_to_target: dict[str, str] = field_to_target or {}

    if extraction_result.is_multi_record:
        return _validate_multi_record_extraction(
            extraction_result=extraction_result,
            cfg=cfg,
            today=today,
            _field_to_target=_field_to_target,
            duplicate_checker=duplicate_checker,
        )

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
            # Use target_field as the key if explicitly configured
            norm_key = _field_to_target.get(f.field_name, f.field_name)
            normalized_data[norm_key] = None
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
        # Use target_field as the key if explicitly configured
        norm_key = _field_to_target.get(f.field_name, f.field_name)
        normalized_data[norm_key] = val

        # Rule: Empty identifier check (company_name, invoice_number)
        # Check using the canonical target key OR original field_name
        if norm_key in {"company_name", "invoice_number"}:
            if isinstance(val, str) and not val.strip():
                issues.append(
                    ValidationIssue(
                        rule_id=RULE_EMPTY_IDENTIFIER,
                        field_name=f.field_name,
                        severity="error",
                        message=f"Identifier field '{norm_key}' cannot be empty or whitespace.",
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

    # 4. Validate Line Items if present
    line_item_reports: list[LineItemValidationReport] = []
    if extraction_result.has_line_items:
        line_item_reports, li_issues = _validate_line_items(
            line_items=extraction_result.line_items,
            _field_to_target=_field_to_target,
        )
        issues.extend(li_issues)

    # 5. Calculate summary counts
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
        has_line_items=extraction_result.has_line_items,
        line_item_reports=line_item_reports,
    )


def _validate_line_items(
    line_items: list[Any],
    _field_to_target: dict[str, str],
) -> tuple[list[LineItemValidationReport], list[ValidationIssue]]:
    line_item_reports: list[LineItemValidationReport] = []
    all_li_issues: list[ValidationIssue] = []

    for item in line_items:
        row_issues: list[ValidationIssue] = []
        row_norm_data: dict[str, Any] = {}

        for f in item.fields:
            target_key = _field_to_target.get(f.field_name, f.field_name)
            if f.status == "error":
                if f.is_empty_cell and f.is_required:
                    iss = ValidationIssue(
                        rule_id=RULE_REQ_FIELD_MISSING,
                        field_name=f.field_name,
                        severity="error",
                        message=f.error_message or f"Required line-item field '{f.field_name}' in row {item.row_number} is empty.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                else:
                    iss = ValidationIssue(
                        rule_id=RULE_INVALID_DATA_TYPE,
                        field_name=f.field_name,
                        severity="error",
                        message=f.error_message or f"Line-item field '{f.field_name}' in row {item.row_number} has invalid format.",
                        cell_ref=f.source_cell_ref,
                        worksheet=f.source_worksheet,
                        actual_value=f.raw_value,
                    )
                row_issues.append(iss)
                all_li_issues.append(iss)
            elif f.status in ("success", "empty_optional"):
                if f.normalized_value is not None:
                    row_norm_data[target_key] = f.normalized_value

        # Check line item math consistency (Quantity * Unit Price ~ Amount) if present
        qty = row_norm_data.get("quantity") or row_norm_data.get("qty")
        unit_p = row_norm_data.get("unit_price") or row_norm_data.get("price")
        amt = row_norm_data.get("amount") or row_norm_data.get("line_total")
        if (
            isinstance(qty, (int, float, Decimal))
            and isinstance(unit_p, (int, float, Decimal))
            and isinstance(amt, (int, float, Decimal))
        ):
            calc_amt = Decimal(str(qty)) * Decimal(str(unit_p))
            actual_amt = Decimal(str(amt))
            # If difference > 0.05 (allowing minor rounding differences)
            if abs(calc_amt - actual_amt) > Decimal("0.05"):
                tax_amt = row_norm_data.get("tax_amount") or row_norm_data.get("tax")
                tax_d = Decimal(str(tax_amt)) if isinstance(tax_amt, (int, float, Decimal)) else Decimal("0")
                if abs((calc_amt + tax_d) - actual_amt) > Decimal("0.05"):
                    iss = ValidationIssue(
                        rule_id=RULE_LINE_ITEM_MATH_MISMATCH,
                        field_name="amount",
                        severity="warning",
                        message=(
                            f"Line item row {item.row_number}: Quantity ({qty}) * Unit Price ({unit_p}) = {calc_amt:.2f}, "
                            f"which differs from stated Amount ({actual_amt:.2f})."
                        ),
                        cell_ref=next((f.source_cell_ref for f in item.fields if f.field_name == "amount" or _field_to_target.get(f.field_name) == "amount"), None),
                        worksheet=item.fields[0].source_worksheet if item.fields else None,
                        actual_value=actual_amt,
                    )
                    row_issues.append(iss)
                    all_li_issues.append(iss)

        has_row_errors = any(i.severity == "error" for i in row_issues)
        line_item_reports.append(
            LineItemValidationReport(
                source_row_number=item.row_number,
                is_valid=(not has_row_errors),
                issues=row_issues,
                normalized_data=row_norm_data,
            )
        )

    return line_item_reports, all_li_issues



def _validate_multi_record_extraction(
    extraction_result: ExtractionResult,
    cfg: ValidationConfig,
    today: date,
    _field_to_target: dict[str, str],
    duplicate_checker: Callable[[str, str], bool] | None,
) -> ValidationReport:
    all_issues: list[ValidationIssue] = []
    row_reports: list[RowValidationReport] = []

    # 1. Capture batch-level extraction errors
    for err in extraction_result.errors:
        if err.field_name is None:
            all_issues.append(
                ValidationIssue(
                    rule_id=RULE_EXTRACTION_FAILURE,
                    field_name=None,
                    severity="error",
                    message=err.message,
                    worksheet=err.worksheet,
                    cell_ref=err.cell_ref,
                )
            )

    seen_in_batch: dict[tuple[str, str], int] = {}

    for row_res in extraction_result.rows:
        row_issues: list[ValidationIssue] = []
        row_norm_data: dict[str, Any] = {}

        # Capture row extraction errors
        for err in row_res.errors:
            row_issues.append(
                ValidationIssue(
                    rule_id=RULE_EXTRACTION_FAILURE,
                    field_name=err.field_name,
                    severity="error",
                    message=err.message,
                    worksheet=err.worksheet,
                    cell_ref=err.cell_ref,
                )
            )

        for f in row_res.fields:
            if f.status == "error":
                if f.is_empty_cell and f.is_required:
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_REQ_FIELD_MISSING,
                            field_name=f.field_name,
                            severity="error",
                            message=f.error_message or f"Required field '{f.field_name}' in Row {row_res.row_number} is empty.",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=f.raw_value,
                        )
                    )
                elif f.is_formula and f.normalized_value is None and f.is_required:
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_EXTRACTION_FAILURE,
                            field_name=f.field_name,
                            severity="error",
                            message=f.error_message or f"Required formula in field '{f.field_name}' at Row {row_res.row_number} has no cached value.",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=f.raw_value,
                        )
                    )
                else:
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_INVALID_DATA_TYPE,
                            field_name=f.field_name,
                            severity="error",
                            message=f.error_message or f"Failed to normalize field '{f.field_name}' at Row {row_res.row_number} as {f.data_type}.",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=f.raw_value,
                        )
                    )
                continue

            if f.status == "empty_optional":
                norm_key = _field_to_target.get(f.field_name, f.field_name)
                row_norm_data[norm_key] = None
                if f.warning_message:
                    row_issues.append(
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

            val = f.normalized_value
            norm_key = _field_to_target.get(f.field_name, f.field_name)
            row_norm_data[norm_key] = val

            # Rule: Empty identifier check (company_name, invoice_number)
            if norm_key in {"company_name", "invoice_number"}:
                if isinstance(val, str) and not val.strip():
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_EMPTY_IDENTIFIER,
                            field_name=f.field_name,
                            severity="error",
                            message=f"Identifier field '{norm_key}' at Row {row_res.row_number} cannot be empty or whitespace.",
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
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_UNBOUNDED_FUTURE_DATE,
                            field_name=f.field_name,
                            severity="warning",
                            message=f"Invoice date {val.isoformat()} at Row {row_res.row_number} is more than {cfg.max_future_days} days in the future.",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=val.isoformat(),
                        )
                    )
                elif val < past_limit:
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_STALE_INVOICE_DATE,
                            field_name=f.field_name,
                            severity="warning",
                            message=f"Invoice date {val.isoformat()} at Row {row_res.row_number} is more than {cfg.max_past_days} days old.",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=val.isoformat(),
                        )
                    )

            # Rule: Amount rules
            if f.data_type == "decimal" and isinstance(val, Decimal):
                if val < Decimal("0"):
                    severity: Severity = "warning" if cfg.allow_negative_amounts else "error"
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_NEGATIVE_AMOUNT,
                            field_name=f.field_name,
                            severity=severity,
                            message=f"Total amount at Row {row_res.row_number} is negative ({val}).",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=float(val),
                        )
                    )
                elif val == Decimal("0"):
                    severity = "warning" if cfg.allow_zero_amounts else "error"
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_ZERO_AMOUNT,
                            field_name=f.field_name,
                            severity=severity,
                            message=f"Total amount at Row {row_res.row_number} is zero (0.00).",
                            cell_ref=f.source_cell_ref,
                            worksheet=f.source_worksheet,
                            actual_value=0.0,
                        )
                    )

        # Duplicate detection for this row
        comp_name = row_norm_data.get("company_name")
        inv_num = row_norm_data.get("invoice_number")
        if comp_name and inv_num and isinstance(comp_name, str) and isinstance(inv_num, str):
            comp_clean = comp_name.strip()
            inv_clean = inv_num.strip()
            dedup_key = (comp_clean.lower(), inv_clean.lower())

            # 1. Intra-batch duplicate check
            if dedup_key in seen_in_batch:
                first_row = seen_in_batch[dedup_key]
                row_issues.append(
                    ValidationIssue(
                        rule_id=RULE_DUPLICATE_INVOICE,
                        field_name="invoice_number",
                        severity=cfg.duplicate_severity,
                        message=f"Invoice number '{inv_clean}' for company '{comp_clean}' at Row {row_res.row_number} is a duplicate of Row {first_row} in this import batch.",
                        worksheet=extraction_result.target_worksheet,
                        actual_value=inv_clean,
                    )
                )
            else:
                seen_in_batch[dedup_key] = row_res.row_number

            # 2. Database duplicate check
            if cfg.check_duplicates and duplicate_checker is not None:
                try:
                    if duplicate_checker(comp_clean, inv_clean):
                        row_issues.append(
                            ValidationIssue(
                                rule_id=RULE_DUPLICATE_INVOICE,
                                field_name="invoice_number",
                                severity=cfg.duplicate_severity,
                                message=f"Invoice number '{inv_clean}' for company '{comp_clean}' at Row {row_res.row_number} has already been imported previously.",
                                worksheet=extraction_result.target_worksheet,
                                actual_value=inv_clean,
                            )
                        )
                except Exception as exc:
                    row_issues.append(
                        ValidationIssue(
                            rule_id=RULE_DUPLICATE_INVOICE,
                            field_name="invoice_number",
                            severity="error",
                            message=f"Failed to verify invoice uniqueness at Row {row_res.row_number}: {exc}",
                        )
                    )

        row_error_cnt = sum(1 for i in row_issues if i.severity == "error")
        row_reports.append(
            RowValidationReport(
                source_row_number=row_res.row_number,
                is_valid=(row_error_cnt == 0),
                issues=row_issues,
                normalized_data=row_norm_data,
            )
        )
        all_issues.extend(row_issues)

    error_cnt = sum(1 for i in all_issues if i.severity == "error")
    warning_cnt = sum(1 for i in all_issues if i.severity == "warning")
    info_cnt = sum(1 for i in all_issues if i.severity == "info")

    return ValidationReport(
        is_valid_for_import=(error_cnt == 0),
        issues=all_issues,
        error_count=error_cnt,
        warning_count=warning_cnt,
        info_count=info_cnt,
        normalized_data={},
        is_multi_record=True,
        row_reports=row_reports,
    )

