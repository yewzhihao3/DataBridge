"""
tests/unit/test_multi_row_validator.py — Unit tests for multi-row validation and duplicate detection.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from app.services.extractor import ExtractedField, ExtractionResult, RowExtractionResult
from app.services.validator import (
    RULE_DUPLICATE_INVOICE,
    RULE_REQ_FIELD_MISSING,
    ValidationConfig,
    validate_extraction,
)


def test_multi_row_validation_success() -> None:
    row1 = RowExtractionResult(
        row_number=2,
        fields=[
            ExtractedField("company_name", "column", "Sheet1", "A2", "ABC", "text", True, False, False, None, "ABC", "success"),
            ExtractedField("invoice_number", "column", "Sheet1", "B2", "INV-001", "text", True, False, False, None, "INV-001", "success"),
        ],
    )
    row2 = RowExtractionResult(
        row_number=3,
        fields=[
            ExtractedField("company_name", "column", "Sheet1", "A3", "XYZ", "text", True, False, False, None, "XYZ", "success"),
            ExtractedField("invoice_number", "column", "Sheet1", "B3", "INV-002", "text", True, False, False, None, "INV-002", "success"),
        ],
    )
    result = ExtractionResult(target_worksheet="Sheet1", is_multi_record=True, rows=[row1, row2])

    report = validate_extraction(result, ValidationConfig())

    assert report.is_multi_record is True
    assert report.is_valid_for_import is True
    assert report.error_count == 0
    assert len(report.row_reports) == 2
    assert report.row_reports[0].normalized_data["company_name"] == "ABC"
    assert report.row_reports[1].normalized_data["company_name"] == "XYZ"


def test_intra_batch_duplicate_detection() -> None:
    # Row 2 and Row 4 have identical company_name & invoice_number
    row1 = RowExtractionResult(
        row_number=2,
        fields=[
            ExtractedField("company_name", "column", "Sheet1", "A2", "ABC", "text", True, False, False, None, "ABC", "success"),
            ExtractedField("invoice_number", "column", "Sheet1", "B2", "INV-001", "text", True, False, False, None, "INV-001", "success"),
        ],
    )
    row2 = RowExtractionResult(
        row_number=4,
        fields=[
            ExtractedField("company_name", "column", "Sheet1", "A4", "ABC", "text", True, False, False, None, "ABC", "success"),
            ExtractedField("invoice_number", "column", "Sheet1", "B4", "INV-001", "text", True, False, False, None, "INV-001", "success"),
        ],
    )
    result = ExtractionResult(target_worksheet="Sheet1", is_multi_record=True, rows=[row1, row2])

    cfg = ValidationConfig(duplicate_severity="warning")
    report = validate_extraction(result, cfg)

    assert report.warning_count >= 1
    dup_issues = [i for i in report.issues if i.rule_id == RULE_DUPLICATE_INVOICE]
    assert len(dup_issues) == 1
    assert "duplicate of Row 2" in dup_issues[0].message


def test_database_duplicate_detection() -> None:
    row1 = RowExtractionResult(
        row_number=2,
        fields=[
            ExtractedField("company_name", "column", "Sheet1", "A2", "ABC", "text", True, False, False, None, "ABC", "success"),
            ExtractedField("invoice_number", "column", "Sheet1", "B2", "INV-999", "text", True, False, False, None, "INV-999", "success"),
        ],
    )
    result = ExtractionResult(target_worksheet="Sheet1", is_multi_record=True, rows=[row1])

    def mock_db_checker(company: str, inv: str) -> bool:
        return company == "ABC" and inv == "INV-999"

    cfg = ValidationConfig(duplicate_severity="warning")
    report = validate_extraction(result, cfg, duplicate_checker=mock_db_checker)

    assert report.warning_count >= 1
    dup_issues = [i for i in report.issues if i.rule_id == RULE_DUPLICATE_INVOICE]
    assert len(dup_issues) == 1
    assert "already been imported previously" in dup_issues[0].message
