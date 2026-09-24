"""
tests/unit/test_extractor.py — Unit tests for app.services.extractor.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

from app.services.extractor import extract_from_file


@dataclass
class DummyMapping:
    field_name: str
    mapping_type: str = "cell"
    cell_ref: str | None = None
    column_ref: str | None = None
    is_required: bool = False
    data_type: str = "text"


@dataclass
class DummyTemplate:
    name: str = "Test Template"
    worksheet: str | None = None
    header_row: int | None = 1
    data_start_row: int | None = 2
    date_format: str | None = None
    field_mappings: list[DummyMapping] | None = None


class TestExtractorEngine:
    """Verify extraction accuracy, provenance tracking, and error handling."""

    def test_extract_clean_invoice_with_provenance(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        template = DummyTemplate(
            name="Acme Invoice Template",
            worksheet="Invoice",
            field_mappings=[
                DummyMapping("company_name", "cell", "B2", is_required=True, data_type="text"),
                DummyMapping("invoice_number", "cell", "B3", is_required=True, data_type="text"),
                DummyMapping("invoice_date", "cell", "F3", is_required=True, data_type="date"),
                DummyMapping("total_amount", "cell", "D6", is_required=False, data_type="decimal"),
            ],
        )

        result = extract_from_file(clean_single_sheet_xlsx, template)

        assert result.has_errors is False
        assert result.target_worksheet == "Invoice"
        assert len(result.fields) == 4

        fields_by_name = {f.field_name: f for f in result.fields}

        # 1. Company Name
        comp = fields_by_name["company_name"]
        assert comp.source_cell_ref == "B2"
        assert comp.raw_value == "Acme Supplies Ltd"
        assert comp.normalized_value == "Acme Supplies Ltd"
        assert comp.status == "success"
        assert comp.is_empty_cell is False
        assert comp.is_formula is False

        # 2. Invoice Date
        inv_date = fields_by_name["invoice_date"]
        assert inv_date.source_cell_ref == "F3"
        assert inv_date.normalized_value == date(2026, 9, 22)
        assert inv_date.status == "success"

        # 3. Total Amount
        total = fields_by_name["total_amount"]
        assert total.source_cell_ref == "D6"
        assert total.normalized_value == Decimal("1450.5")
        assert total.status == "success"

    def test_empty_required_field_flags_error(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        template = DummyTemplate(
            worksheet="Invoice",
            field_mappings=[
                DummyMapping("po_number", "cell", "Z1", is_required=True, data_type="text"),
            ],
        )
        result = extract_from_file(clean_single_sheet_xlsx, template)
        assert result.has_errors is True
        assert len(result.errors) == 1
        assert result.errors[0].error_type == "required_empty"
        assert result.fields[0].status == "error"
        assert result.fields[0].is_empty_cell is True

    def test_empty_optional_field_flags_empty_optional(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        template = DummyTemplate(
            worksheet="Invoice",
            field_mappings=[
                DummyMapping("optional_notes", "cell", "Z1", is_required=False, data_type="text"),
            ],
        )
        result = extract_from_file(clean_single_sheet_xlsx, template)
        assert result.has_errors is False
        assert result.fields[0].status == "empty_optional"
        assert result.fields[0].normalized_value is None

    def test_uncalculated_formula_handling(
        self, workbook_with_formulas_xlsx: Path
    ) -> None:
        # Cell A3 has formula =SUM(A1:A2) with NO cached calculated value
        template_required = DummyTemplate(
            worksheet="Calculations",
            field_mappings=[
                DummyMapping("sum_total", "cell", "A3", is_required=True, data_type="decimal"),
            ],
        )
        result_req = extract_from_file(workbook_with_formulas_xlsx, template_required)
        assert result_req.has_errors is True
        assert result_req.errors[0].error_type == "uncalculated_formula"
        assert result_req.fields[0].status == "error"
        assert result_req.fields[0].is_formula is True
        assert "=SUM(A1:A2)" in str(result_req.fields[0].formula_expression)

        # When optional: status is empty_optional with a warning
        template_optional = DummyTemplate(
            worksheet="Calculations",
            field_mappings=[
                DummyMapping("sum_total", "cell", "A3", is_required=False, data_type="decimal"),
            ],
        )
        result_opt = extract_from_file(workbook_with_formulas_xlsx, template_optional)
        assert result_opt.has_errors is False
        assert result_opt.fields[0].status == "empty_optional"
        assert result_opt.warning_count > 0

    def test_missing_worksheet_returns_structured_error(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        template = DummyTemplate(
            worksheet="NonExistentSheet",
            field_mappings=[
                DummyMapping("company_name", "cell", "B2", is_required=True, data_type="text"),
            ],
        )
        result = extract_from_file(clean_single_sheet_xlsx, template)
        assert result.has_errors is True
        assert result.errors[0].error_type == "missing_worksheet"

    def test_unsupported_mapping_type_and_missing_ref_captured(
        self, clean_single_sheet_xlsx: Path
    ) -> None:
        template = DummyTemplate(
            worksheet="Invoice",
            field_mappings=[
                DummyMapping("unknown_field", "unsupported", "B2", is_required=False),
                DummyMapping("missing_ref_field", "cell", "", is_required=False),
            ],
        )
        result = extract_from_file(clean_single_sheet_xlsx, template)
        assert result.has_errors is True
        error_types = {e.error_type for e in result.errors}
        assert "unsupported_mapping_type" in error_types
        assert "missing_cell_ref" in error_types
