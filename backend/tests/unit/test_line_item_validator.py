"""
tests/unit/test_line_item_validator.py — Unit tests for composite invoice line item validation.
"""

from decimal import Decimal
from types import SimpleNamespace
import pytest

from app.services.extractor import (
    ExtractedField,
    ExtractionResult,
    RowExtractionResult,
)
from app.services.validator import (
    validate_extraction,
    RULE_REQ_FIELD_MISSING,
    RULE_INVALID_DATA_TYPE,
    RULE_LINE_ITEM_MATH_MISMATCH,
)


def test_validator_passes_valid_composite_invoice():
    header_fields = [
        ExtractedField(
            field_name="supplier",
            mapping_type="cell",
            source_worksheet="Invoice",
            source_cell_ref="A1",
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
            field_name="inv_no",
            mapping_type="cell",
            source_worksheet="Invoice",
            source_cell_ref="F5",
            raw_value="INV-100",
            data_type="text",
            is_required=True,
            is_empty_cell=False,
            is_formula=False,
            formula_expression=None,
            normalized_value="INV-100",
            status="success",
        ),
    ]

    line_items = [
        RowExtractionResult(
            row_number=11,
            fields=[
                ExtractedField(field_name="desc", mapping_type="column", source_worksheet="Invoice", source_cell_ref="A11", raw_value="Chair", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="Chair", status="success"),
                ExtractedField(field_name="qty", mapping_type="column", source_worksheet="Invoice", source_cell_ref="B11", raw_value=2, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("2"), status="success"),
                ExtractedField(field_name="price", mapping_type="column", source_worksheet="Invoice", source_cell_ref="C11", raw_value=100.0, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("100.00"), status="success"),
                ExtractedField(field_name="amount", mapping_type="column", source_worksheet="Invoice", source_cell_ref="D11", raw_value=200.0, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("200.00"), status="success"),
            ],
        )
    ]

    extraction_result = ExtractionResult(
        target_worksheet="Invoice",
        fields=header_fields,
        line_items=line_items,
        is_multi_record=False,
        has_line_items=True,
    )

    report = validate_extraction(
        extraction_result,
        field_to_target={"supplier": "company_name", "inv_no": "invoice_number", "desc": "description", "qty": "quantity", "price": "unit_price", "amount": "amount"},
    )

    assert report.is_valid_for_import is True
    assert report.error_count == 0
    assert report.has_line_items is True
    assert len(report.line_item_reports) == 1
    assert report.line_item_reports[0].is_valid is True
    assert report.line_item_reports[0].normalized_data["description"] == "Chair"
    assert report.line_item_reports[0].normalized_data["quantity"] == Decimal("2")


def test_validator_fails_on_missing_required_line_item_field():
    header_fields = [
        ExtractedField(field_name="supplier", mapping_type="cell", source_worksheet="Invoice", source_cell_ref="A1", raw_value="Acme Corp", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="Acme Corp", status="success"),
        ExtractedField(field_name="inv_no", mapping_type="cell", source_worksheet="Invoice", source_cell_ref="F5", raw_value="INV-100", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="INV-100", status="success"),
    ]

    line_items = [
        RowExtractionResult(
            row_number=11,
            fields=[
                ExtractedField(field_name="desc", mapping_type="column", source_worksheet="Invoice", source_cell_ref="A11", raw_value=None, data_type="text", is_required=True, is_empty_cell=True, is_formula=False, formula_expression=None, normalized_value=None, status="error", error_message="Required line-item field 'desc' is empty."),
            ],
        )
    ]

    extraction_result = ExtractionResult(
        target_worksheet="Invoice",
        fields=header_fields,
        line_items=line_items,
        is_multi_record=False,
        has_line_items=True,
    )

    report = validate_extraction(extraction_result)

    assert report.is_valid_for_import is False
    assert report.error_count >= 1
    assert any(iss.rule_id == RULE_REQ_FIELD_MISSING for iss in report.issues)


def test_validator_warns_on_line_item_math_mismatch():
    header_fields = [
        ExtractedField(field_name="supplier", mapping_type="cell", source_worksheet="Invoice", source_cell_ref="A1", raw_value="Acme Corp", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="Acme Corp", status="success"),
        ExtractedField(field_name="inv_no", mapping_type="cell", source_worksheet="Invoice", source_cell_ref="F5", raw_value="INV-100", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="INV-100", status="success"),
    ]

    # Qty 2 * Price 100 = 200, but stated amount is 500
    line_items = [
        RowExtractionResult(
            row_number=11,
            fields=[
                ExtractedField(field_name="desc", mapping_type="column", source_worksheet="Invoice", source_cell_ref="A11", raw_value="Chair", data_type="text", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value="Chair", status="success"),
                ExtractedField(field_name="quantity", mapping_type="column", source_worksheet="Invoice", source_cell_ref="B11", raw_value=2, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("2"), status="success"),
                ExtractedField(field_name="unit_price", mapping_type="column", source_worksheet="Invoice", source_cell_ref="C11", raw_value=100.0, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("100.00"), status="success"),
                ExtractedField(field_name="amount", mapping_type="column", source_worksheet="Invoice", source_cell_ref="D11", raw_value=500.0, data_type="decimal", is_required=True, is_empty_cell=False, is_formula=False, formula_expression=None, normalized_value=Decimal("500.00"), status="success"),
            ],
        )
    ]

    extraction_result = ExtractionResult(
        target_worksheet="Invoice",
        fields=header_fields,
        line_items=line_items,
        is_multi_record=False,
        has_line_items=True,
    )

    report = validate_extraction(extraction_result)

    assert report.is_valid_for_import is True  # Warning does not block import unless acknowledged
    assert report.warning_count >= 1
    assert any(iss.rule_id == RULE_LINE_ITEM_MATH_MISMATCH for iss in report.issues)
