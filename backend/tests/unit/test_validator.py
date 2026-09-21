"""
tests/unit/test_validator.py — Unit tests for app.services.validator.
"""

from datetime import date
from decimal import Decimal
import pytest

from app.services.extractor import ExtractedField, ExtractionError, ExtractionResult
from app.services.validator import (
    RULE_DUPLICATE_INVOICE,
    RULE_EMPTY_IDENTIFIER,
    RULE_EXTRACTION_FAILURE,
    RULE_INVALID_DATA_TYPE,
    RULE_NEGATIVE_AMOUNT,
    RULE_REQ_FIELD_MISSING,
    RULE_STALE_INVOICE_DATE,
    RULE_UNBOUNDED_FUTURE_DATE,
    RULE_ZERO_AMOUNT,
    ValidationConfig,
    validate_extraction,
)


# ── Configuration Tests ───────────────────────────────────────────────────────


class TestValidationConfig:
    """Verify ValidationConfig parameter validation."""

    def test_valid_config_instantiation(self) -> None:
        cfg = ValidationConfig(
            allow_negative_amounts=False,
            max_future_days=15,
            reference_date=date(2026, 9, 22),
        )
        assert cfg.max_future_days == 15
        assert cfg.allow_negative_amounts is False

    def test_negative_future_days_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="max_future_days must be >= 0"):
            ValidationConfig(max_future_days=-5)

    def test_negative_past_days_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="max_past_days must be >= 0"):
            ValidationConfig(max_past_days=-10)

    def test_invalid_duplicate_severity_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="duplicate_severity must be one of"):
            ValidationConfig(duplicate_severity="fatal")  # type: ignore[arg-type]


# ── Clean Validation Tests ───────────────────────────────────────────────────


class TestCleanValidation:
    """Verify that clean extracted records pass validation with zero errors."""

    def test_clean_invoice_passes_validation(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="Acme Corp",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="Acme Corp",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value="INV-1001",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="INV-1001",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_date",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="F3",
                    raw_value="2026-09-22",
                    data_type="date",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=date(2026, 9, 22),
                    status="success",
                ),
                ExtractedField(
                    field_name="total_amount",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="D6",
                    raw_value="1,450.50",
                    data_type="decimal",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=Decimal("1450.50"),
                    status="success",
                ),
            ],
        )

        cfg = ValidationConfig(reference_date=date(2026, 9, 22))
        report = validate_extraction(extraction, config=cfg)

        assert report.is_valid_for_import is True
        assert report.error_count == 0
        assert report.warning_count == 0
        assert len(report.issues) == 0
        assert report.normalized_data["company_name"] == "Acme Corp"
        # Verify Decimal precision is preserved exactly
        assert report.normalized_data["total_amount"] == Decimal("1450.50")


# ── Missing & Empty Identifier Tests ──────────────────────────────────────────


class TestMissingAndEmptyIdentifiers:
    """Verify required field missing and empty whitespace identifiers."""

    def test_missing_required_field_blocks_import(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value=None,
                    data_type="text",
                    is_required=True,
                    is_empty_cell=True,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=None,
                    status="error",
                    error_message="Required field 'invoice_number' is empty.",
                ),
            ],
        )
        report = validate_extraction(extraction)
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert report.issues[0].rule_id == RULE_REQ_FIELD_MISSING
        assert report.issues[0].severity == "error"

    def test_empty_whitespace_identifier_blocks_import(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="   ",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="   ",
                    status="success",
                ),
            ],
        )
        report = validate_extraction(extraction)
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert report.issues[0].rule_id == RULE_EMPTY_IDENTIFIER


# ── Date Rule Tests ───────────────────────────────────────────────────────────


class TestDateRules:
    """Verify future and stale date warnings with deterministic reference dates."""

    def test_future_date_within_limit_has_no_warning(self) -> None:
        cfg = ValidationConfig(reference_date=date(2026, 9, 22), max_future_days=30)
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="invoice_date",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="F3",
                    raw_value="2026-10-10",
                    data_type="date",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=date(2026, 10, 10),
                    status="success",
                )
            ],
        )
        report = validate_extraction(extraction, config=cfg)
        assert report.warning_count == 0
        assert report.is_valid_for_import is True

    def test_future_date_exceeding_limit_produces_warning(self) -> None:
        cfg = ValidationConfig(reference_date=date(2026, 9, 22), max_future_days=30)
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="invoice_date",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="F3",
                    raw_value="2026-11-15",
                    data_type="date",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=date(2026, 11, 15),  # 54 days in future
                    status="success",
                )
            ],
        )
        report = validate_extraction(extraction, config=cfg)
        assert report.warning_count == 1
        assert report.issues[0].rule_id == RULE_UNBOUNDED_FUTURE_DATE
        assert report.issues[0].severity == "warning"
        assert report.is_valid_for_import is True  # Warning does not block import

    def test_stale_invoice_date_produces_warning(self) -> None:
        cfg = ValidationConfig(reference_date=date(2026, 9, 22), max_past_days=1825)
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="invoice_date",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="F3",
                    raw_value="2018-01-01",
                    data_type="date",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=date(2018, 1, 1),
                    status="success",
                )
            ],
        )
        report = validate_extraction(extraction, config=cfg)
        assert report.warning_count == 1
        assert report.issues[0].rule_id == RULE_STALE_INVOICE_DATE
        assert report.issues[0].severity == "warning"
        assert report.is_valid_for_import is True


# ── Amount Rule Tests ─────────────────────────────────────────────────────────


class TestAmountRules:
    """Verify negative and zero amount handling across configurations."""

    def test_negative_amount_warning_when_allowed(self) -> None:
        cfg = ValidationConfig(allow_negative_amounts=True)
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="total_amount",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="D6",
                    raw_value="-500.00",
                    data_type="decimal",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=Decimal("-500.00"),
                    status="success",
                )
            ],
        )
        report = validate_extraction(extraction, config=cfg)
        assert report.is_valid_for_import is True
        assert report.warning_count == 1
        assert report.issues[0].rule_id == RULE_NEGATIVE_AMOUNT
        assert report.issues[0].severity == "warning"
        assert "credit note" in report.issues[0].message

    def test_negative_amount_error_when_disallowed(self) -> None:
        cfg = ValidationConfig(allow_negative_amounts=False)
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="total_amount",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="D6",
                    raw_value="-500.00",
                    data_type="decimal",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=Decimal("-500.00"),
                    status="success",
                )
            ],
        )
        report = validate_extraction(extraction, config=cfg)
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert report.issues[0].rule_id == RULE_NEGATIVE_AMOUNT
        assert report.issues[0].severity == "error"

    def test_zero_amount_warning_vs_error(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="total_amount",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="D6",
                    raw_value="0.00",
                    data_type="decimal",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=Decimal("0.00"),
                    status="success",
                )
            ],
        )
        # 1. Zero allowed -> Warning
        rep_warn = validate_extraction(extraction, config=ValidationConfig(allow_zero_amounts=True))
        assert rep_warn.is_valid_for_import is True
        assert rep_warn.warning_count == 1
        assert rep_warn.issues[0].rule_id == RULE_ZERO_AMOUNT

        # 2. Zero disallowed -> Error
        rep_err = validate_extraction(extraction, config=ValidationConfig(allow_zero_amounts=False))
        assert rep_err.is_valid_for_import is False
        assert rep_err.error_count == 1
        assert rep_err.issues[0].severity == "error"


# ── Duplicate Checking Tests ──────────────────────────────────────────────────


class TestDuplicateChecking:
    """Verify duplicate invoice detection, severity configuration, and error isolation."""

    def test_duplicate_detected_with_warning_severity(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="Acme Corp",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="Acme Corp",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value="INV-1001",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="INV-1001",
                    status="success",
                ),
            ],
        )

        def mock_checker(company: str, inv: str) -> bool:
            return company == "Acme Corp" and inv == "INV-1001"

        cfg = ValidationConfig(check_duplicates=True, duplicate_severity="warning")
        report = validate_extraction(extraction, config=cfg, duplicate_checker=mock_checker)

        assert report.is_valid_for_import is True
        assert report.warning_count == 1
        assert report.issues[0].rule_id == RULE_DUPLICATE_INVOICE
        assert report.issues[0].severity == "warning"

    def test_duplicate_detected_with_error_severity(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="Acme Corp",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="Acme Corp",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value="INV-1001",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="INV-1001",
                    status="success",
                ),
            ],
        )

        cfg = ValidationConfig(check_duplicates=True, duplicate_severity="error")
        report = validate_extraction(
            extraction, config=cfg, duplicate_checker=lambda c, i: True
        )
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert report.issues[0].severity == "error"

    def test_duplicate_check_disabled(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="Acme Corp",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="Acme Corp",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value="INV-1001",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="INV-1001",
                    status="success",
                ),
            ],
        )
        cfg = ValidationConfig(check_duplicates=False)
        report = validate_extraction(
            extraction, config=cfg, duplicate_checker=lambda c, i: True
        )
        assert report.warning_count == 0
        assert report.error_count == 0

    def test_duplicate_checker_exception_handled_gracefully(self) -> None:
        def broken_checker(c: str, i: str) -> bool:
            raise ConnectionError("Database connection lost")

        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value="Acme Corp",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="Acme Corp",
                    status="success",
                ),
                ExtractedField(
                    field_name="invoice_number",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B3",
                    raw_value="INV-1001",
                    data_type="text",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value="INV-1001",
                    status="success",
                ),
            ],
        )
        report = validate_extraction(
            extraction, config=ValidationConfig(), duplicate_checker=broken_checker
        )
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert "Database connection lost" in report.issues[0].message


# ── Multiple Issues and Extraction Failure Tests ──────────────────────────────


class TestMultipleIssuesAndExtractionFailures:
    """Verify multiple issue aggregation and extraction failure handling."""

    def test_multiple_issues_on_single_invoice(self) -> None:
        cfg = ValidationConfig(
            reference_date=date(2026, 9, 22),
            allow_negative_amounts=False,  # Error
            max_future_days=10,            # Warning
        )
        extraction = ExtractionResult(
            target_worksheet="Invoice",
            fields=[
                # Error 1: Missing required field
                ExtractedField(
                    field_name="company_name",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="B2",
                    raw_value=None,
                    data_type="text",
                    is_required=True,
                    is_empty_cell=True,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=None,
                    status="error",
                    error_message="Required field is empty.",
                ),
                # Error 2: Negative amount with policy False
                ExtractedField(
                    field_name="total_amount",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="D6",
                    raw_value="-100",
                    data_type="decimal",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=Decimal("-100"),
                    status="success",
                ),
                # Warning 1: Future date
                ExtractedField(
                    field_name="invoice_date",
                    mapping_type="cell",
                    source_worksheet="Invoice",
                    source_cell_ref="F3",
                    raw_value="2026-10-20",
                    data_type="date",
                    is_required=True,
                    is_empty_cell=False,
                    is_formula=False,
                    formula_expression=None,
                    normalized_value=date(2026, 10, 20),
                    status="success",
                ),
            ],
        )

        report = validate_extraction(extraction, config=cfg)
        assert report.is_valid_for_import is False
        assert report.error_count == 2
        assert report.warning_count == 1
        assert len(report.issues) == 3

    def test_missing_worksheet_extraction_failure_translated(self) -> None:
        extraction = ExtractionResult(
            target_worksheet="MissingSheet",
            errors=[
                ExtractionError(
                    field_name=None,
                    message="Worksheet 'MissingSheet' not found in workbook.",
                    worksheet="MissingSheet",
                    cell_ref=None,
                    error_type="missing_worksheet",
                )
            ],
        )
        report = validate_extraction(extraction)
        assert report.is_valid_for_import is False
        assert report.error_count == 1
        assert report.issues[0].rule_id == RULE_EXTRACTION_FAILURE
